"""The screening run: rules, questions, policy, verdict, and the screening log."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from llm_ingestion_screener.canonical import canonical_json
from llm_ingestion_screener.decision_model import DecisionInquiry
from llm_ingestion_screener.domain import (
    Material,
    PolicyEscalation,
    Provenance,
    QuarantinedPassage,
    RuleHit,
    Threshold,
    VerdictLevel,
)
from llm_ingestion_screener.errors import ScreeningError, ValidationError
from llm_ingestion_screener.policy import Policy
from llm_ingestion_screener.questions import (
    DEFAULT_QUESTIONS,
    Answer,
    Question,
    validate_questions,
)
from llm_ingestion_screener.rules import RuleEngine
from llm_ingestion_screener.verdict import Verdict


@dataclass(frozen=True)
class ScreeningLogEntry:
    """One append-only log row. It carries no raw material text."""

    run_id: str
    screened_at: datetime
    source: str
    content_sha256: str
    level: VerdictLevel
    rule_ids: tuple[str, ...]
    answer_ids: tuple[str, ...]
    thresholds: tuple[Threshold, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.run_id, str) or not self.run_id.strip():
            raise ValidationError("log entry requires a non-empty run id")
        if not isinstance(self.screened_at, datetime) or self.screened_at.tzinfo is None:
            raise ValidationError("log entry screened_at must be timezone-aware")
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValidationError("log entry requires a source")
        if not isinstance(self.content_sha256, str) or len(self.content_sha256) != 64:
            raise ValidationError("log entry requires a SHA-256 content digest")
        try:
            level = VerdictLevel(self.level)
        except ValueError as exc:
            raise ValidationError(f"unknown verdict level: {self.level!r}") from exc
        object.__setattr__(self, "level", level)
        object.__setattr__(self, "rule_ids", tuple(self.rule_ids))
        object.__setattr__(self, "answer_ids", tuple(self.answer_ids))
        object.__setattr__(self, "thresholds", tuple(self.thresholds))
        if not all(isinstance(rule_id, str) for rule_id in self.rule_ids):
            raise ValidationError("log entry rule ids must be strings")
        if not all(isinstance(answer_id, str) for answer_id in self.answer_ids):
            raise ValidationError("log entry answer ids must be strings")
        if not all(isinstance(threshold, Threshold) for threshold in self.thresholds):
            raise ValidationError("log entry thresholds must be Threshold values")
        if not self.thresholds:
            raise ValidationError("log entry must record the thresholds in force")

    def to_dict(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "screened_at": self.screened_at.isoformat(),
            "source": self.source,
            "content_sha256": self.content_sha256,
            "level": self.level.label,
            "rule_ids": list(self.rule_ids),
            "answer_ids": list(self.answer_ids),
            "thresholds": [threshold.to_dict() for threshold in self.thresholds],
        }

    def to_json_line(self) -> str:
        return canonical_json(self.to_dict())


@dataclass(frozen=True)
class ScreeningRun:
    """One immutable screening run with exactly one verdict and log entry."""

    run_id: str
    screened_at: datetime
    material: Material
    provenance: Provenance
    verdict: Verdict
    log_entry: ScreeningLogEntry

    def __post_init__(self) -> None:
        if not isinstance(self.run_id, str) or not self.run_id.strip():
            raise ValidationError("screening run requires a non-empty run id")
        if not isinstance(self.screened_at, datetime) or self.screened_at.tzinfo is None:
            raise ValidationError("screening run screened_at must be timezone-aware")
        if not isinstance(self.material, Material):
            raise ValidationError("screening run requires a Material")
        if not isinstance(self.provenance, Provenance):
            raise ValidationError("screening run requires a Provenance")
        if not isinstance(self.verdict, Verdict):
            raise ValidationError("screening run requires a Verdict")
        if not isinstance(self.log_entry, ScreeningLogEntry):
            raise ValidationError("screening run requires a screening-log entry")
        if self.log_entry.run_id != self.run_id:
            raise ValidationError("screening-log entry belongs to a different run")
        if self.log_entry.screened_at != self.screened_at:
            raise ValidationError("screening-log entry has a different screen time")
        if self.log_entry.level is not self.verdict.level:
            raise ValidationError("screening-log entry level differs from the verdict")
        if self.log_entry.content_sha256 != self.material.content_sha256:
            raise ValidationError("screening-log entry content digest differs")
        if self.log_entry.source != self.provenance.source:
            raise ValidationError("screening-log entry source differs from provenance")

    def to_dict(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "screened_at": self.screened_at.isoformat(),
            "material": {
                "media_type": self.material.media_type,
                "content_sha256": self.material.content_sha256,
                "content_length": len(self.material.content),
            },
            "provenance": {
                "source_url": self.provenance.source_url,
                "retriever": self.provenance.retriever,
                "retrieved_at": self.provenance.retrieved_at.isoformat(),
                "referrer": self.provenance.referrer,
            },
            "verdict": self.verdict.to_dict(),
            "log_entry": self.log_entry.to_dict(),
        }

    def to_json(self) -> str:
        return canonical_json(self.to_dict())


class ScreeningLog:
    """An append-only in-memory log, optionally mirrored to JSON lines."""

    def __init__(self, path: str | Path | None = None) -> None:
        self._path = None if path is None else Path(path)
        self._entries: list[ScreeningLogEntry] = []
        self._run_ids: set[str] = set()

    @property
    def entries(self) -> tuple[ScreeningLogEntry, ...]:
        return tuple(self._entries)

    def append(self, entry: ScreeningLogEntry) -> None:
        if not isinstance(entry, ScreeningLogEntry):
            raise ScreeningError("screening log only accepts ScreeningLogEntry values")
        if entry.run_id in self._run_ids:
            raise ScreeningError(f"run {entry.run_id!r} is already logged")
        if self._path is not None:
            try:
                with self._path.open("a", encoding="utf-8") as handle:
                    handle.write(entry.to_json_line())
                    handle.write("\n")
            except OSError as exc:
                raise ScreeningError(
                    f"could not append to screening log {self._path}: {exc}"
                ) from exc
        self._entries.append(entry)
        self._run_ids.add(entry.run_id)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def screen(
    material: Material,
    provenance: Provenance,
    *,
    inquiry: DecisionInquiry,
    questions: Sequence[Question] | None = None,
    rules: RuleEngine | None = None,
    policy: Policy | None = None,
    clock: Callable[[], datetime] = _utc_now,
    log: ScreeningLog | None = None,
) -> ScreeningRun:
    """Screen one piece of material, or raise.

    There is no clean-by-default path: any failure to run propagates as an
    error and no verdict is returned.
    """

    if not isinstance(material, Material):
        raise ScreeningError("screen requires a Material")
    if not isinstance(provenance, Provenance):
        raise ScreeningError("screen requires a Provenance")
    if not isinstance(inquiry, DecisionInquiry):
        raise ScreeningError("screen requires a DecisionInquiry")
    if not isinstance(clock, Callable):  # type: ignore[arg-type]
        raise ScreeningError("screen requires a callable clock")
    if log is not None and not isinstance(log, ScreeningLog):
        raise ScreeningError("screen log must be a ScreeningLog")

    question_set = validate_questions(
        DEFAULT_QUESTIONS if questions is None else questions
    )
    rule_engine = RuleEngine() if rules is None else rules
    if not isinstance(rule_engine, RuleEngine):
        raise ScreeningError("screen rules must be a RuleEngine")
    active_policy = Policy() if policy is None else policy
    if not isinstance(active_policy, Policy):
        raise ScreeningError("screen policy must be a Policy")

    rule_hits = rule_engine.scan(material.content)
    answers_by_id = inquiry.ask(material.content, question_set)
    answers = tuple(answers_by_id[question.id] for question in question_set)
    decision = active_policy.decide(rule_hits, answers)
    passages = _build_passages(
        material,
        provenance,
        rule_hits,
        decision.escalations,
    )

    screened_at = clock()
    if not isinstance(screened_at, datetime):
        raise ScreeningError("screen clock must return a datetime")
    if screened_at.tzinfo is None:
        raise ScreeningError("screen clock must return a timezone-aware datetime")

    verdict = Verdict(
        level=decision.level,
        rule_hits=rule_hits,
        answers=answers,
        quarantined_passages=passages,
        thresholds=active_policy.thresholds,
        escalations=decision.escalations,
    )
    run_id = _build_run_id(material, provenance, question_set, screened_at)
    log_entry = ScreeningLogEntry(
        run_id=run_id,
        screened_at=screened_at,
        source=provenance.source,
        content_sha256=material.content_sha256,
        level=verdict.level,
        rule_ids=tuple(hit.rule_id for hit in rule_hits),
        answer_ids=tuple(answer.question_id for answer in answers),
        thresholds=active_policy.thresholds,
    )
    run = ScreeningRun(
        run_id=run_id,
        screened_at=screened_at,
        material=material,
        provenance=provenance,
        verdict=verdict,
        log_entry=log_entry,
    )

    if log is not None:
        log.append(log_entry)
    return run


def _build_passages(
    material: Material,
    provenance: Provenance,
    rule_hits: tuple[RuleHit, ...],
    escalations: tuple[PolicyEscalation, ...],
) -> tuple[QuarantinedPassage, ...]:
    passages: list[QuarantinedPassage] = []
    for hit in rule_hits:
        if hit.level is VerdictLevel.QUARANTINE:
            passages.append(
                QuarantinedPassage(
                    text=hit.excerpt,
                    source=provenance.source,
                    flagged_by=hit.rule_id,
                    start=hit.start,
                    end=hit.end,
                )
            )

    for escalation in escalations:
        if escalation.level is not VerdictLevel.QUARANTINE:
            continue
        if escalation.source_kind != "answer":
            continue
        passages.append(
            QuarantinedPassage(
                text=material.content,
                source=provenance.source,
                flagged_by=f"answer:{escalation.source_id}",
                start=0,
                end=len(material.content),
            )
        )

    deduplicated: dict[tuple[str, str, str, int, int], QuarantinedPassage] = {}
    for passage in passages:
        key = (
            passage.text,
            passage.source,
            passage.flagged_by,
            passage.start,
            passage.end,
        )
        deduplicated[key] = passage
    return tuple(
        sorted(
            deduplicated.values(),
            key=lambda passage: (passage.start, passage.end, passage.flagged_by),
        )
    )


def _build_run_id(
    material: Material,
    provenance: Provenance,
    questions: tuple[Question, ...],
    screened_at: datetime,
) -> str:
    seed = {
        "content_sha256": material.content_sha256,
        "source": provenance.source,
        "question_ids": [question.id for question in questions],
        "screened_at": screened_at.isoformat(),
    }
    digest = hashlib.sha256(canonical_json(seed).encode("utf-8")).hexdigest()
    return f"run-{digest[:16]}"
