"""Metrics arithmetic, not-applicable reasons, and coverage floors."""

from __future__ import annotations

import pytest

from llm_ingestion_screener.domain import VerdictLevel
from llm_ingestion_screener.eval.metrics import METRIC_NAMES, compute_metrics
from llm_ingestion_screener.eval.runner import FixtureResult


def make_result(
    fixture_id: str,
    corpus: str,
    label: str,
    *,
    surface: str = "web-page",
    threat_class: str = "agent-directed-imperative",
    expect_min_verdict: str = "flagged",
    verdict: str = "clean",
    rule_ids: tuple[str, ...] = (),
    derived_from: str | None = None,
    evidence_ok: bool = True,
) -> FixtureResult:
    return FixtureResult(
        fixture_id=fixture_id,
        corpus=corpus,
        surface=surface,
        label=label,
        threat_class=threat_class,
        expect_min_verdict=expect_min_verdict,
        expect_any_rule=(),
        derived_from=derived_from,
        transform="split-string-literals" if derived_from else None,
        content_sha256="0" * 64,
        verdict=verdict,
        rule_ids=rule_ids,
        answer_ids=("q.agent-directed-instruction",),
        caught=(
            VerdictLevel[verdict.upper()]
            >= VerdictLevel[expect_min_verdict.upper()]
        ),
        expected_rule_met=True,
        evidence_ok=evidence_ok,
    )


def sample_results() -> tuple[FixtureResult, ...]:
    return (
        make_result(
            "g1",
            "golden",
            "malicious",
            verdict="quarantine",
            rule_ids=("rule.agent-directed-imperative",),
        ),
        make_result(
            "g2",
            "golden",
            "malicious",
            threat_class="instruction-override",
            verdict="flagged",
            rule_ids=("rule.instruction-override",),
        ),
        make_result(
            "e1",
            "eval",
            "malicious",
            threat_class="exfiltration-request",
            expect_min_verdict="quarantine",
            verdict="quarantine",
            rule_ids=("rule.exfiltration-request",),
        ),
        make_result(
            "e2",
            "eval",
            "malicious",
            threat_class="encoded-obfuscated",
            verdict="flagged",
            rule_ids=("rule.encoded-execution",),
        ),
        make_result(
            "e3",
            "eval",
            "malicious",
            threat_class="non-english",
            surface="document",
        ),
        make_result(
            "b1",
            "benign",
            "benign",
            threat_class="benign-imperative-vocabulary",
        ),
        make_result(
            "b2",
            "benign",
            "benign",
            surface="tool-output",
            threat_class="benign-legitimate-tool-output",
            expect_min_verdict="clean",
            verdict="flagged",
            rule_ids=("rule.tool-result-injection",),
        ),
        make_result(
            "f1",
            "frontier",
            "malicious",
            threat_class="task-irrelevant-injection",
        ),
        make_result(
            "t1",
            "transforms",
            "malicious",
            threat_class="exfiltration-request",
            expect_min_verdict="quarantine",
            derived_from="e1",
        ),
        make_result(
            "t2",
            "transforms",
            "malicious",
            threat_class="encoded-obfuscated",
            verdict="flagged",
            rule_ids=("rule.encoded-execution",),
            derived_from="e2",
        ),
    )


FLOORS = {
    "directories": {
        "golden": 2,
        "eval": 3,
        "frontier": 1,
        "benign": 2,
        "transforms": 2,
    },
    "surfaces": {"web-page": 1, "tool-output": 1},
    "threat_classes": {"non-english": 1},
}


def test_recall_false_positives_and_frontier_arithmetic() -> None:
    report = compute_metrics(
        sample_results(),
        deterministic=True,
        malformed_answer_fails_batch=True,
        coverage_floors=FLOORS,
    )
    metrics = report.by_name()
    assert metrics["malicious_recall"].value == pytest.approx(4 / 5)
    assert metrics["malicious_recall"].data["caught"] == 4
    assert metrics["benign_false_positive_rate"].value == pytest.approx(1 / 2)
    assert metrics["frontier_recall"].value == 0.0
    assert metrics["malicious_recall_by_threat_class"].data["classes"][
        "non-english"
    ]["value"] == 0.0
    assert metrics["recall_and_fpr_by_surface"].data["surfaces"]["web-page"][
        "benign_false_positive_rate"
    ] == 0.0
    assert metrics["evidence_record_well_formedness"].value == 1.0
    assert metrics["determinism"].value is True
    assert metrics["malformed_answer_batch_failure"].value is True


def test_transform_blocked_rate_and_rule_retention() -> None:
    report = compute_metrics(
        sample_results(),
        deterministic=True,
        malformed_answer_fails_batch=True,
        coverage_floors=FLOORS,
    )
    metrics = report.by_name()
    assert metrics["evasion_transform_blocked_rate"].value == pytest.approx(0.5)
    assert metrics["evasion_transform_rule_retention"].value == pytest.approx(0.5)


def test_every_plan_metric_is_present_and_na_rows_carry_a_reason() -> None:
    report = compute_metrics(
        sample_results(),
        deterministic=True,
        malformed_answer_fails_batch=True,
        coverage_floors=FLOORS,
    )
    assert tuple(metric.name for metric in report.metrics) == METRIC_NAMES
    for metric in report.metrics:
        if metric.status == "not-applicable":
            assert metric.reason, metric.name
            assert metric.value is None
        else:
            assert metric.status == "computed"


def test_coverage_floor_fails_when_a_directory_is_short() -> None:
    floors = {
        "directories": {"golden": 99},
        "surfaces": {},
        "threat_classes": {},
    }
    report = compute_metrics(
        sample_results(),
        deterministic=True,
        malformed_answer_fails_batch=True,
        coverage_floors=floors,
    )
    coverage = report.by_name()["corpus_coverage"]
    assert coverage.value is False
    assert coverage.data["directories"]["golden"]["met"] is False


def test_coverage_floor_requires_a_mapping_per_section() -> None:
    floors = {"directories": ["golden"]}
    with pytest.raises(Exception, match="coverage floors section"):
        compute_metrics(
            sample_results(),
            deterministic=True,
            malformed_answer_fails_batch=True,
            coverage_floors=floors,
        )


def test_a_malformed_answer_that_does_not_fail_is_reported_and_gated() -> None:
    report = compute_metrics(
        sample_results(),
        deterministic=True,
        malformed_answer_fails_batch=False,
        coverage_floors=FLOORS,
    )
    assert report.by_name()["malformed_answer_batch_failure"].value is False
