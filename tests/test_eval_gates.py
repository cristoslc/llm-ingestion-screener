"""Gate registry validation and gate application."""

from __future__ import annotations

from pathlib import Path

import pytest

from llm_ingestion_screener.decision_model import RecordedDecisionModel
from llm_ingestion_screener.errors import EvaluationError
from llm_ingestion_screener.eval.fixtures import load_corpus
from llm_ingestion_screener.eval.gates import METRIC_NAMES, evaluate_gates, load_gates
from llm_ingestion_screener.eval.metrics import compute_metrics
from llm_ingestion_screener.eval.runner import run_corpus
from eval_support import CASSETTE, CORPUS, GATES, gates_with

GATED = {
    "malicious_recall",
    "benign_false_positive_rate",
    "determinism",
    "evidence_record_well_formedness",
    "malformed_answer_batch_failure",
    "corpus_coverage",
}


def test_committed_gate_registry_tags_every_metric() -> None:
    registry = load_gates(GATES)
    assert tuple(registry.rules) == METRIC_NAMES
    assert {
        name for name, rule in registry.rules.items() if rule.status == "gated"
    } == GATED
    assert registry.malicious_recall_corpora == ("golden", "eval")
    assert registry.coverage_floors["directories"]["golden"] == 5


def test_rejects_an_unknown_metric(tmp_path: Path) -> None:
    path = gates_with(
        tmp_path,
        lambda payload: payload["metrics"].__setitem__(
            "invented_metric", {"status": "reported"}
        ),
    )
    with pytest.raises(EvaluationError, match="unknown metric"):
        load_gates(path)


def test_rejects_a_missing_metric(tmp_path: Path) -> None:
    path = gates_with(
        tmp_path,
        lambda payload: payload["metrics"].pop("frontier_recall"),
    )
    with pytest.raises(EvaluationError, match="missing metric"):
        load_gates(path)


def test_rejects_a_gated_metric_without_a_threshold(tmp_path: Path) -> None:
    def mutate(payload):
        payload["metrics"]["malicious_recall"].pop("threshold")

    path = gates_with(tmp_path, mutate)
    with pytest.raises(EvaluationError, match="requires a finite numeric threshold"):
        load_gates(path)


def test_rejects_a_reported_metric_with_a_threshold(tmp_path: Path) -> None:
    def mutate(payload):
        payload["metrics"]["frontier_recall"]["threshold"] = 0.5

    path = gates_with(tmp_path, mutate)
    with pytest.raises(EvaluationError, match="must not carry an operator"):
        load_gates(path)


def test_rejects_an_unknown_status(tmp_path: Path) -> None:
    def mutate(payload):
        payload["metrics"]["frontier_recall"]["status"] = "advisory"

    path = gates_with(tmp_path, mutate)
    with pytest.raises(EvaluationError, match="gated or reported"):
        load_gates(path)


def test_rejects_a_boolean_gate_with_a_threshold(tmp_path: Path) -> None:
    def mutate(payload):
        payload["metrics"]["determinism"]["threshold"] = 1.0

    path = gates_with(tmp_path, mutate)
    with pytest.raises(EvaluationError, match="boolean gate"):
        load_gates(path)


def test_rejects_an_unknown_coverage_key(tmp_path: Path) -> None:
    def mutate(payload):
        payload["coverage"]["directories"]["invented"] = 1

    path = gates_with(tmp_path, mutate)
    with pytest.raises(EvaluationError, match="unknown key"):
        load_gates(path)


def test_rejects_a_negative_coverage_floor(tmp_path: Path) -> None:
    def mutate(payload):
        payload["coverage"]["directories"]["golden"] = -1

    path = gates_with(tmp_path, mutate)
    with pytest.raises(EvaluationError, match="non-negative integer"):
        load_gates(path)


def _current_metrics(registry):
    corpus = load_corpus(CORPUS)
    results = run_corpus(corpus, RecordedDecisionModel.from_file(CASSETTE))
    return compute_metrics(
        results,
        gate_corpora=registry.malicious_recall_corpora,
        deterministic=True,
        malformed_answer_fails_batch=True,
        coverage_floors=registry.coverage_floors,
    )


def test_a_deliberately_broken_recall_gate_fails(tmp_path: Path) -> None:
    registry = load_gates(GATES)
    metrics = _current_metrics(registry)
    evaluation = evaluate_gates(registry, metrics)
    assert evaluation.failures == ()

    broken = gates_with(
        tmp_path,
        lambda payload: payload["metrics"]["malicious_recall"].__setitem__(
            "threshold", 0.99
        ),
    )
    broken_registry = load_gates(broken)
    broken_evaluation = evaluate_gates(broken_registry, metrics)
    assert "malicious_recall" in broken_evaluation.failures
