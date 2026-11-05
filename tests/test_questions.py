"""The typed-question schema and its wire representation."""

from __future__ import annotations

import pytest

from llm_ingestion_screener.domain import IngestionSurface
from llm_ingestion_screener.errors import ValidationError
from llm_ingestion_screener.questions import (
    DEFAULT_QUESTIONS,
    TOOL_OUTPUT_QUESTIONS,
    ChoiceCriterion,
    Question,
    QuestionKind,
    questions_for_surface,
    validate_questions,
)


def test_noul_question_serialises_to_the_systemone_wire_shape() -> None:
    question = Question.noul("q.injection", "Is there an injection?")

    assert question.kind is QuestionKind.NOUL
    assert question.to_wire() == {
        "type": "noul",
        "instructions": "Is there an injection?",
    }


def test_choice_question_serialises_criteria_as_a_mapping() -> None:
    question = Question.choice(
        "q.class",
        "Which class fits?",
        {"none": "No instruction.", "override": "Replaces instructions."},
    )

    assert question.to_wire() == {
        "type": "choice",
        "instructions": "Which class fits?",
        "criteria": {
            "none": "No instruction.",
            "override": "Replaces instructions.",
        },
    }


def test_score_question_serialises_criteria_as_an_ordered_list() -> None:
    question = Question.score(
        "q.severity",
        "How severe?",
        ["none", "low", "high"],
    )

    assert question.to_wire() == {
        "type": "score",
        "instructions": "How severe?",
        "criteria": ["none", "low", "high"],
    }


def test_noul_rejects_criteria() -> None:
    with pytest.raises(ValidationError, match="noul"):
        Question(
            id="q.bad",
            kind=QuestionKind.NOUL,
            instructions="Is it bad?",
            criteria=("yes", "no"),
        )


def test_choice_requires_at_least_two_options() -> None:
    with pytest.raises(ValidationError, match="at least two"):
        Question.choice("q.bad", "Pick one.", {"only": "The only option."})


def test_choice_rejects_duplicate_labels() -> None:
    with pytest.raises(ValidationError, match="duplicate"):
        Question(
            id="q.bad",
            kind=QuestionKind.CHOICE,
            instructions="Pick one.",
            criteria=(
                ChoiceCriterion("yes", "Yes."),
                ChoiceCriterion("yes", "Also yes."),
            ),
        )


def test_score_requires_between_two_and_ten_levels() -> None:
    with pytest.raises(ValidationError, match="at least two"):
        Question.score("q.bad", "How bad?", ["only"])

    with pytest.raises(ValidationError, match="at most ten"):
        Question.score(
            "q.bad",
            "How bad?",
            [f"level-{index}" for index in range(11)],
        )


def test_score_rejects_duplicate_levels() -> None:
    with pytest.raises(ValidationError, match="duplicate"):
        Question.score("q.bad", "How bad?", ["low", "low"])


@pytest.mark.parametrize(
    ("question_id", "instructions"),
    [("", "Is it bad?"), ("q.bad", "")],
)
def test_question_rejects_empty_id_or_instructions(
    question_id: str, instructions: str
) -> None:
    with pytest.raises(ValidationError):
        Question.noul(question_id, instructions)


def test_question_ids_are_unique_in_a_question_set() -> None:
    question = Question.noul("q.same", "Is it bad?")
    with pytest.raises(ValidationError, match="duplicate question id"):
        validate_questions([question, question])


def test_a_question_set_cannot_be_empty() -> None:
    with pytest.raises(ValidationError, match="at least one question"):
        validate_questions([])


def test_default_question_set_covers_all_three_kinds() -> None:
    assert {question.kind for question in DEFAULT_QUESTIONS} == {
        QuestionKind.NOUL,
        QuestionKind.CHOICE,
        QuestionKind.SCORE,
    }


def test_tool_output_uses_its_own_instruction_question() -> None:
    tool_ids = {question.id for question in TOOL_OUTPUT_QUESTIONS}
    default_ids = {question.id for question in DEFAULT_QUESTIONS}

    assert "q.tool-result-instruction" in tool_ids
    assert "q.tool-result-instruction" not in default_ids
    assert "q.agent-directed-instruction" in default_ids
    assert "q.agent-directed-instruction" not in tool_ids


@pytest.mark.parametrize(
    ("surface", "expected"),
    [
        (IngestionSurface.WEB_PAGE, DEFAULT_QUESTIONS),
        (IngestionSurface.SEARCH_RESULT, DEFAULT_QUESTIONS),
        (IngestionSurface.DOCUMENT, DEFAULT_QUESTIONS),
        (IngestionSurface.THIRD_PARTY_SKILL, DEFAULT_QUESTIONS),
        (IngestionSurface.TOOL_OUTPUT, TOOL_OUTPUT_QUESTIONS),
    ],
)
def test_questions_for_surface_selects_the_right_set(
    surface: IngestionSurface, expected: tuple[Question, ...]
) -> None:
    assert questions_for_surface(surface) == expected


def test_questions_for_surface_rejects_an_unknown_surface() -> None:
    with pytest.raises(ValidationError, match="unknown ingestion surface"):
        questions_for_surface("carrier-pigeon")
