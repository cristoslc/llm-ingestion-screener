"""Phase 3 corpus coverage targets and the gated coverage floors."""

from __future__ import annotations

from collections import Counter

from llm_ingestion_screener.decision_model import RecordedDecisionModel
from llm_ingestion_screener.eval.fixtures import (
    BENIGN_THREAT_CLASSES,
    MALICIOUS_THREAT_CLASSES,
    TRANSFORM_NAMES,
    load_corpus,
)
from llm_ingestion_screener.eval.gates import load_gates
from llm_ingestion_screener.eval.metrics import compute_metrics
from llm_ingestion_screener.eval.runner import run_corpus
from llm_ingestion_screener.rules import RuleEngine
from eval_support import CASSETTE, CORPUS, GATES


def test_the_committed_corpus_meets_the_phase_three_targets() -> None:
    corpus = load_corpus(CORPUS)
    assert len(corpus.fixtures) >= 100

    malicious_by_class = Counter(
        fixture.threat_class
        for fixture in corpus.fixtures
        if fixture.label == "malicious"
    )
    for class_name in MALICIOUS_THREAT_CLASSES:
        assert malicious_by_class[class_name] >= 8, class_name

    benign_by_class = Counter(
        fixture.threat_class
        for fixture in corpus.fixtures
        if fixture.label == "benign"
    )
    for class_name in BENIGN_THREAT_CLASSES:
        assert benign_by_class[class_name] >= 6, class_name

    surfaces = {fixture.surface.value for fixture in corpus.fixtures}
    for surface in surfaces:
        assert any(
            fixture.surface.value == surface and fixture.label == "malicious"
            for fixture in corpus.fixtures
        ), surface
        assert any(
            fixture.surface.value == surface and fixture.label == "benign"
            for fixture in corpus.fixtures
        ), surface


def test_every_named_transform_holds_at_least_eight_samples() -> None:
    corpus = load_corpus(CORPUS)
    counts = Counter(
        fixture.transform
        for fixture in corpus.fixtures
        if fixture.corpus == "transforms"
    )
    for name in TRANSFORM_NAMES:
        assert counts[name] >= 8, (name, counts[name])


def test_every_eval_and_golden_malicious_fixture_meets_its_expected_rule() -> None:
    corpus = load_corpus(CORPUS)
    engine = RuleEngine()
    for fixture in corpus.fixtures:
        if fixture.corpus not in {"golden", "eval"}:
            continue
        if fixture.label != "malicious":
            continue
        hits = {hit.rule_id for hit in engine.scan(fixture.content)}
        assert hits, fixture.id
        assert any(
            rule in hits for rule in fixture.expect_any_rule
        ), (fixture.id, sorted(hits))


def test_every_benign_fixture_is_clean_on_the_production_path() -> None:
    corpus = load_corpus(CORPUS)
    results = run_corpus(corpus, RecordedDecisionModel.from_file(CASSETTE))
    for result in results:
        if result.label == "benign":
            assert result.verdict == "clean", result.fixture_id


def test_every_eval_malicious_fixture_is_caught() -> None:
    corpus = load_corpus(CORPUS)
    results = run_corpus(corpus, RecordedDecisionModel.from_file(CASSETTE))
    for result in results:
        if result.corpus == "eval" and result.label == "malicious":
            assert result.caught, result.fixture_id


def test_frontier_holds_at_least_one_expected_miss() -> None:
    corpus = load_corpus(CORPUS)
    results = run_corpus(corpus, RecordedDecisionModel.from_file(CASSETTE))
    frontier = [
        result
        for result in results
        if result.corpus == "frontier" and result.label == "malicious"
    ]
    assert frontier
    assert any(not result.caught for result in frontier)


def test_the_committed_coverage_floors_hold() -> None:
    corpus = load_corpus(CORPUS)
    registry = load_gates(GATES)
    results = run_corpus(corpus, RecordedDecisionModel.from_file(CASSETTE))
    metrics = compute_metrics(
        results,
        gate_corpora=registry.malicious_recall_corpora,
        deterministic=True,
        malformed_answer_fails_batch=True,
        coverage_floors=registry.coverage_floors,
    )
    coverage = metrics.by_name()["corpus_coverage"]
    assert coverage.value is True
    for section in ("directories", "surfaces", "threat_classes"):
        for key, row in coverage.data[section].items():
            assert row["count"] >= row["floor"], (section, key, row)
