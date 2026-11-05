"""Runner behaviour: production path, truth isolation, determinism, fail-loud."""

from __future__ import annotations

from dataclasses import replace

from llm_ingestion_screener.decision_model import RecordedDecisionModel
from llm_ingestion_screener.domain import VerdictLevel
from llm_ingestion_screener.eval.fixtures import load_corpus
from llm_ingestion_screener.eval.runner import (
    check_malformed_answer_fails_batch,
    results_are_byte_identical,
    run_corpus,
    screen_fixture,
)
from eval_support import CASSETTE, CORPUS, NeutralModel


class RecordingModel:
    def __init__(self) -> None:
        self.states: list[str] = []
        self._inner = NeutralModel()

    def ask(self, state: str, questions):
        self.states.append(state)
        return self._inner.ask(state, questions)


def test_the_runner_records_verdicts_and_evidence() -> None:
    corpus = load_corpus(CORPUS)
    model = RecordedDecisionModel.from_file(CASSETTE)
    results = run_corpus(corpus, model)
    assert len(results) == len(corpus.fixtures)
    by_id = {result.fixture_id: result for result in results}
    assert by_id["web-page-agent-directed-imperative"].caught
    assert not by_id["web-page-non-english"].caught
    for result in results:
        if result.verdict != "clean":
            assert result.evidence_ok


def test_the_screen_never_sees_the_truth_label() -> None:
    corpus = load_corpus(CORPUS)
    fixture = corpus.by_id["web-page-non-english"]
    assert fixture.label == "malicious"
    benign_content = "An ordinary page about gardening and the weather.\n"
    disguised = replace(
        fixture,
        content=benign_content,
        expect_min_verdict=VerdictLevel.FLAGGED,
    )
    model = RecordingModel()
    run = screen_fixture(disguised, model)
    assert run.verdict.level is VerdictLevel.CLEAN
    assert model.states == [benign_content]


def test_two_recorded_batches_are_byte_identical() -> None:
    corpus = load_corpus(CORPUS)
    model = RecordedDecisionModel.from_file(CASSETTE)
    first = run_corpus(corpus, model)
    second = run_corpus(corpus, model)
    assert results_are_byte_identical(first, second)


def test_a_malformed_answer_fails_the_batch() -> None:
    corpus = load_corpus(CORPUS)
    assert check_malformed_answer_fails_batch(corpus.fixtures[0])
