"""Parsing and validating typed answers from untrusted model output."""

from __future__ import annotations

import math

import pytest

from llm_ingestion_screener.errors import MalformedAnswerError
from llm_ingestion_screener.questions import Question, parse_answers

NOUL = Question.noul("q.noul", "Is it bad?")
CHOICE = Question.choice(
    "q.choice",
    "Which class?",
    {"none": "Nothing.", "attack": "An attack."},
)
SCORE = Question.score(
    "q.score",
    "How severe?",
    ["none", "low", "high"],
)


def test_noul_derives_probabilities_and_confidence() -> None:
    answers = parse_answers(
        [NOUL],
        {"q.noul": {"type": "noul", "noul": 0.8}},
    )

    answer = answers["q.noul"]
    assert answer.kind.value == "noul"
    assert answer.value == pytest.approx(0.8)
    assert dict(answer.probabilities) == {
        "yes": pytest.approx(0.8),
        "no": pytest.approx(0.2),
    }
    assert answer.confidence == pytest.approx(0.8)


def test_choice_answer_keeps_label_probabilities_and_confidence() -> None:
    answers = parse_answers(
        [CHOICE],
        {
            "q.choice": {
                "type": "choice",
                "choice": "attack",
                "probabilities": {"none": 0.1, "attack": 0.9},
                "confidence": 0.8,
            }
        },
    )

    answer = answers["q.choice"]
    assert answer.value == "attack"
    assert dict(answer.probabilities) == {
        "none": pytest.approx(0.1),
        "attack": pytest.approx(0.9),
    }
    assert answer.confidence == pytest.approx(0.8)


def test_score_answer_maps_indices_to_labels() -> None:
    answers = parse_answers(
        [SCORE],
        {
            "q.score": {
                "type": "score",
                "score": 1.6,
                "legend": {"0": "none", "1": "low", "2": "high"},
                "probabilities": {"0": 0.1, "1": 0.7, "2": 0.2},
                "confidence": 0.6,
            }
        },
    )

    answer = answers["q.score"]
    assert answer.value == pytest.approx(1.6)
    assert dict(answer.probabilities) == {
        "none": pytest.approx(0.1),
        "low": pytest.approx(0.7),
        "high": pytest.approx(0.2),
    }
    assert answer.confidence == pytest.approx(0.6)


def test_missing_answer_fails_the_batch() -> None:
    with pytest.raises(MalformedAnswerError, match="missing answer"):
        parse_answers([NOUL], {})


def test_extra_answer_fails_the_batch() -> None:
    with pytest.raises(MalformedAnswerError, match="unknown question"):
        parse_answers(
            [NOUL],
            {
                "q.noul": {"type": "noul", "noul": 0.1},
                "q.extra": {"type": "noul", "noul": 0.1},
            },
        )


def test_truncated_answer_fails_the_batch() -> None:
    with pytest.raises(MalformedAnswerError, match="noul"):
        parse_answers([NOUL], {"q.noul": {"type": "noul"}})


def test_wrong_answer_kind_fails_the_batch() -> None:
    with pytest.raises(MalformedAnswerError, match="expected noul"):
        parse_answers(
            [NOUL],
            {"q.noul": {"type": "choice", "choice": "none"}},
        )


def test_probabilities_must_sum_to_one() -> None:
    with pytest.raises(MalformedAnswerError, match="sum to 1"):
        parse_answers(
            [CHOICE],
            {
                "q.choice": {
                    "type": "choice",
                    "choice": "attack",
                    "probabilities": {"none": 0.1, "attack": 0.2},
                    "confidence": 0.5,
                }
            },
        )


def test_probabilities_must_match_the_choice_labels() -> None:
    with pytest.raises(MalformedAnswerError, match="labels"):
        parse_answers(
            [CHOICE],
            {
                "q.choice": {
                    "type": "choice",
                    "choice": "attack",
                    "probabilities": {"none": 0.5, "other": 0.5},
                    "confidence": 0.5,
                }
            },
        )


def test_chosen_choice_must_be_a_known_label() -> None:
    with pytest.raises(MalformedAnswerError, match="chosen option"):
        parse_answers(
            [CHOICE],
            {
                "q.choice": {
                    "type": "choice",
                    "choice": "other",
                    "probabilities": {"none": 0.5, "attack": 0.5},
                    "confidence": 0.5,
                }
            },
        )


def test_confidence_must_be_a_probability() -> None:
    with pytest.raises(MalformedAnswerError, match="confidence"):
        parse_answers(
            [CHOICE],
            {
                "q.choice": {
                    "type": "choice",
                    "choice": "attack",
                    "probabilities": {"none": 0.5, "attack": 0.5},
                    "confidence": 1.2,
                }
            },
        )


def test_booleans_are_not_numbers() -> None:
    with pytest.raises(MalformedAnswerError, match="noul"):
        parse_answers([NOUL], {"q.noul": {"type": "noul", "noul": True}})


def test_non_finite_numbers_are_rejected() -> None:
    with pytest.raises(MalformedAnswerError, match="finite"):
        parse_answers([NOUL], {"q.noul": {"type": "noul", "noul": math.nan}})


def test_score_legend_must_match_the_question_criteria() -> None:
    with pytest.raises(MalformedAnswerError, match="legend"):
        parse_answers(
            [SCORE],
            {
                "q.score": {
                    "type": "score",
                    "score": 1.0,
                    "legend": {"0": "none", "1": "low", "2": "other"},
                    "probabilities": {"0": 0.1, "1": 0.7, "2": 0.2},
                    "confidence": 0.6,
                }
            },
        )


def test_answer_probabilities_are_read_only() -> None:
    answers = parse_answers(
        [NOUL],
        {"q.noul": {"type": "noul", "noul": 0.8}},
    )

    with pytest.raises(TypeError):
        answers["q.noul"].probabilities["yes"] = 0.0  # type: ignore[index]


def test_answers_are_returned_in_question_order() -> None:
    answers = parse_answers(
        [NOUL, CHOICE, SCORE],
        {
            "q.score": {
                "type": "score",
                "score": 0.1,
                "legend": {"0": "none", "1": "low", "2": "high"},
                "probabilities": {"0": 0.9, "1": 0.05, "2": 0.05},
                "confidence": 0.8,
            },
            "q.choice": {
                "type": "choice",
                "choice": "none",
                "probabilities": {"none": 0.9, "attack": 0.1},
                "confidence": 0.8,
            },
            "q.noul": {"type": "noul", "noul": 0.1},
        },
    )

    assert list(answers) == ["q.noul", "q.choice", "q.score"]
