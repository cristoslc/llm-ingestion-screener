"""Decision-model clients: recorded replay, live request shape, and faults."""

from __future__ import annotations

import pytest

from llm_ingestion_screener.decision_model import (
    CASSETTE_FORMAT,
    Cassette,
    DecisionInquiry,
    FaultInjectionDecisionModel,
    FaultMode,
    RecordedDecisionModel,
    build_systemone_request,
    cassette_key,
    parse_systemone_envelope,
    validate_live_config,
)
from llm_ingestion_screener.errors import (
    CassetteError,
    DecisionModelError,
    MalformedAnswerError,
    ValidationError,
)
from llm_ingestion_screener.questions import (
    DEFAULT_QUESTIONS,
    Question,
    parse_answers,
)

from cassette_fixtures import CASSETTE_ANSWERS, CASSETTE_MATERIAL, CASSETTE_PATH


class StubDecisionModel:
    def __init__(self, answers: object) -> None:
        self._answers = answers

    def ask(self, state: str, questions: tuple[Question, ...]) -> object:
        return self._answers


def test_build_systemone_request_uses_the_documented_wire_shape() -> None:
    request = build_systemone_request(
        "clef-flash",
        "The sky is blue.",
        [
            Question.noul("q.blue", "Is the sky blue?"),
            Question.choice(
                "q.colour",
                "What colour?",
                {"blue": "Blue.", "green": "Green."},
            ),
        ],
    )

    assert request == {
        "model": "clef-flash",
        "state": "The sky is blue.",
        "questions": {
            "q.blue": {
                "type": "noul",
                "instructions": "Is the sky blue?",
            },
            "q.colour": {
                "type": "choice",
                "instructions": "What colour?",
                "criteria": {"blue": "Blue.", "green": "Green."},
            },
        },
    }


def test_build_systemone_request_rejects_an_empty_question_set() -> None:
    with pytest.raises(ValidationError, match="at least one question"):
        build_systemone_request("clef-flash", "state", [])


def test_parse_systemone_envelope_returns_the_answers_mapping() -> None:
    payload = {
        "model": "clef",
        "answers": {"q.blue": {"type": "noul", "noul": 0.99}},
    }

    assert parse_systemone_envelope(payload) == payload["answers"]


def test_parse_systemone_envelope_raises_on_an_endpoint_error() -> None:
    with pytest.raises(DecisionModelError, match="error"):
        parse_systemone_envelope({"error": "model not found"})


def test_parse_systemone_envelope_raises_when_answers_are_missing() -> None:
    with pytest.raises(DecisionModelError, match="answers"):
        parse_systemone_envelope({"model": "clef"})


def test_parse_systemone_envelope_raises_on_a_non_mapping_answer() -> None:
    with pytest.raises(DecisionModelError, match="not a mapping"):
        parse_systemone_envelope({"answers": {"q.blue": "yes"}})


@pytest.mark.parametrize(
    ("model", "endpoint"),
    [
        ("", "http://127.0.0.1:11434/v1/systemone"),
        ("clef-flash", ""),
        ("clef-flash", "file:///tmp/model"),
        ("clef-flash", "not-a-url"),
    ],
)
def test_live_configuration_fails_loudly(model: str, endpoint: str) -> None:
    with pytest.raises(DecisionModelError):
        validate_live_config(model, endpoint)


def test_cassette_key_is_stable_and_sensitive_to_inputs() -> None:
    question = DEFAULT_QUESTIONS[0]

    assert cassette_key("state", question) == cassette_key("state", question)
    assert cassette_key("state", question) != cassette_key("other", question)
    assert cassette_key("state", question) != cassette_key(
        "state", Question.noul(question.id, "A different question?")
    )


def test_recorded_client_replays_the_committed_cassette() -> None:
    client = RecordedDecisionModel.from_file(CASSETTE_PATH)
    raw = client.ask(CASSETTE_MATERIAL, DEFAULT_QUESTIONS)

    assert raw == CASSETTE_ANSWERS
    answers = parse_answers(DEFAULT_QUESTIONS, raw)
    assert answers["q.agent-directed-instruction"].value == pytest.approx(0.93)
    assert answers["q.injection-class"].value == "agent-directed-imperative"


def test_recorded_client_is_deterministic() -> None:
    client = RecordedDecisionModel.from_file(CASSETTE_PATH)

    first = client.ask(CASSETTE_MATERIAL, DEFAULT_QUESTIONS)
    second = client.ask(CASSETTE_MATERIAL, DEFAULT_QUESTIONS)

    assert first == second


def test_recorded_client_raises_when_a_key_is_missing() -> None:
    client = RecordedDecisionModel.from_file(CASSETTE_PATH)

    with pytest.raises(CassetteError, match="no cassette entry"):
        client.ask("a different state", DEFAULT_QUESTIONS)


def test_recorded_client_raises_when_the_stored_question_does_not_match() -> None:
    question = DEFAULT_QUESTIONS[0]
    key = cassette_key("state", question)
    wrong_question = Question.noul(question.id, "A different question?")
    cassette = Cassette.from_mapping(
        {
            "format": CASSETTE_FORMAT,
            "model": "synthetic",
            "synthetic": True,
            "comment": "synthetic",
            "entries": {
                key: {
                    "question_id": question.id,
                    "question": wrong_question.to_dict(),
                    "answer": {"type": "noul", "noul": 0.5},
                }
            },
        }
    )

    with pytest.raises(CassetteError, match="does not match"):
        RecordedDecisionModel(cassette).ask("state", [question])


def test_cassette_requires_the_synthetic_flag() -> None:
    with pytest.raises(CassetteError, match="synthetic"):
        Cassette.from_mapping(
            {
                "format": CASSETTE_FORMAT,
                "model": "synthetic",
                "comment": "synthetic",
                "entries": {},
            }
        )


def test_cassette_rejects_an_unknown_format() -> None:
    with pytest.raises(CassetteError, match="format"):
        Cassette.from_mapping(
            {
                "format": "something-else",
                "model": "synthetic",
                "synthetic": True,
                "entries": {},
            }
        )


def test_committed_cassette_is_explicitly_synthetic() -> None:
    cassette = Cassette.from_file(CASSETTE_PATH)

    assert cassette.synthetic is True
    assert "SYNTHETIC" in cassette.comment.upper()


@pytest.mark.parametrize(
    "mode",
    [
        FaultMode.MALFORMED,
        FaultMode.TRUNCATED,
        FaultMode.MISSING_ANSWER,
        FaultMode.WRONG_KIND,
        FaultMode.PROBABILITIES_DO_NOT_SUM,
        FaultMode.NON_NUMERIC,
    ],
)
def test_fault_injection_fails_the_typed_parse(mode: FaultMode) -> None:
    inquiry = DecisionInquiry(FaultInjectionDecisionModel(mode))

    with pytest.raises(MalformedAnswerError):
        inquiry.ask(CASSETTE_MATERIAL, DEFAULT_QUESTIONS)


def test_fault_injection_rejects_an_unknown_mode() -> None:
    with pytest.raises(ValidationError, match="fault mode"):
        FaultInjectionDecisionModel("bogus")  # type: ignore[arg-type]


def test_decision_inquiry_returns_typed_answers() -> None:
    inquiry = DecisionInquiry(StubDecisionModel(CASSETTE_ANSWERS))
    answers = inquiry.ask(CASSETTE_MATERIAL, DEFAULT_QUESTIONS)

    assert set(answers) == {question.id for question in DEFAULT_QUESTIONS}
    assert answers["q.exfiltration"].kind.value == "noul"


def test_decision_inquiry_rejects_a_non_mapping_response() -> None:
    inquiry = DecisionInquiry(StubDecisionModel("not a mapping"))

    with pytest.raises(MalformedAnswerError):
        inquiry.ask(CASSETTE_MATERIAL, DEFAULT_QUESTIONS)
