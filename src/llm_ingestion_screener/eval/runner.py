"""Run the production screen over the eval corpus.

The runner builds the production input from fixture content and provenance and
calls :func:`llm_ingestion_screener.screen.screen`. It never reads the fixture
label: the label is attached to the result only after a verdict exists, for the
metrics engine.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone

from llm_ingestion_screener.canonical import canonical_json
from llm_ingestion_screener.decision_model import (
    DecisionInquiry,
    FaultInjectionDecisionModel,
)
from llm_ingestion_screener.domain import (
    Material,
    Provenance,
    VerdictLevel,
)
from llm_ingestion_screener.errors import MalformedAnswerError
from llm_ingestion_screener.eval.fixtures import Corpus, Fixture
from llm_ingestion_screener.questions import questions_for_surface
from llm_ingestion_screener.screen import ScreeningRun, screen

FIXED_SCREENED_AT = datetime(2026, 11, 4, 12, 0, tzinfo=timezone.utc)
FIXTURE_RETRIEVER = "screener-eval-corpus"


def provenance_for(fixture: Fixture) -> Provenance:
    """A deterministic provenance for one fixture. Never carries truth."""

    return Provenance(
        retriever=FIXTURE_RETRIEVER,
        retrieved_at=FIXED_SCREENED_AT,
        source_url=f"https://example.invalid/corpus/{fixture.id}",
    )


def screen_fixture(
    fixture: Fixture,
    model: object,
    *,
    clock: datetime = FIXED_SCREENED_AT,
) -> ScreeningRun:
    """Screen one fixture's content through the production code path.

    Only ``fixture.content`` and ``fixture.surface`` reach the screen. The
    truth label, expected verdict, and threat class stay in the harness.
    """

    material = Material(content=fixture.content)
    provenance = provenance_for(fixture)
    questions = questions_for_surface(fixture.surface)
    return screen(
        material,
        provenance,
        inquiry=DecisionInquiry(model=model),
        questions=questions,
        clock=lambda: clock,
    )


@dataclass(frozen=True)
class FixtureResult:
    """One fixture's verdict plus the truth metadata used for arithmetic."""

    fixture_id: str
    corpus: str
    surface: str
    label: str
    threat_class: str
    expect_min_verdict: str
    expect_any_rule: tuple[str, ...]
    derived_from: str | None
    transform: str | None
    content_sha256: str
    verdict: str
    rule_ids: tuple[str, ...]
    answer_ids: tuple[str, ...]
    caught: bool
    expected_rule_met: bool
    evidence_ok: bool
    verdict_evidence: Mapping[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "fixture_id": self.fixture_id,
            "corpus": self.corpus,
            "surface": self.surface,
            "label": self.label,
            "threat_class": self.threat_class,
            "expect_min_verdict": self.expect_min_verdict,
            "expect_any_rule": list(self.expect_any_rule),
            "derived_from": self.derived_from,
            "transform": self.transform,
            "content_sha256": self.content_sha256,
            "verdict": self.verdict,
            "rule_ids": list(self.rule_ids),
            "answer_ids": list(self.answer_ids),
            "caught": self.caught,
            "expected_rule_met": self.expected_rule_met,
            "evidence_ok": self.evidence_ok,
            "evidence": dict(self.verdict_evidence),
        }


def run_fixture(fixture: Fixture, model: object) -> FixtureResult:
    run = screen_fixture(fixture, model)
    verdict_level = run.verdict.level
    expected = fixture.expect_min_verdict
    caught = verdict_level >= expected
    rule_ids = run.verdict.rule_ids
    expected_rule_met = (
        True
        if not fixture.expect_any_rule
        else any(rule in rule_ids for rule in fixture.expect_any_rule)
    )
    return FixtureResult(
        fixture_id=fixture.id,
        corpus=fixture.corpus,
        surface=fixture.surface.value,
        label=fixture.label,
        threat_class=fixture.threat_class,
        expect_min_verdict=expected.label,
        expect_any_rule=fixture.expect_any_rule,
        derived_from=fixture.derived_from,
        transform=fixture.transform,
        content_sha256=fixture.content_sha256,
        verdict=verdict_level.label,
        rule_ids=rule_ids,
        answer_ids=tuple(answer.question_id for answer in run.verdict.answers),
        caught=caught,
        expected_rule_met=expected_rule_met,
        evidence_ok=evidence_is_well_formed(run),
        verdict_evidence=run.verdict.to_dict(),
    )


def run_corpus(corpus: Corpus, model: object) -> tuple[FixtureResult, ...]:
    """Run every fixture in stable corpus order."""

    return tuple(run_fixture(fixture, model) for fixture in corpus.fixtures)


def evidence_is_well_formed(run: ScreeningRun) -> bool:
    """Whether a flagged or quarantined verdict is citable downstream."""

    verdict = run.verdict
    if verdict.level is VerdictLevel.CLEAN:
        return True
    if not verdict.thresholds:
        return False
    if not run.log_entry.source.strip():
        return False
    if not verdict.rule_hits and not any(
        answer.probabilities for answer in verdict.answers
    ):
        return False
    for hit in verdict.rule_hits:
        if not hit.excerpt or hit.end <= hit.start:
            return False
    if verdict.level is VerdictLevel.QUARANTINE:
        if not verdict.quarantined_passages:
            return False
        for passage in verdict.quarantined_passages:
            if not passage.text or not passage.source:
                return False
    return True


def batch_signature(results: tuple[FixtureResult, ...]) -> bytes:
    """The byte-deterministic signature of one recorded batch."""

    return canonical_json([result.to_dict() for result in results]).encode("utf-8")


def results_are_byte_identical(
    first: tuple[FixtureResult, ...],
    second: tuple[FixtureResult, ...],
) -> bool:
    return batch_signature(first) == batch_signature(second)


def check_malformed_answer_fails_batch(fixture: Fixture) -> bool:
    """Prove a malformed model answer fails the batch instead of passing.

    A different exception propagates: only a typed malformed-answer failure is
    evidence that the fail-loud path held.
    """

    model = FaultInjectionDecisionModel("malformed")
    try:
        screen_fixture(fixture, model)
    except MalformedAnswerError:
        return True
    return False
