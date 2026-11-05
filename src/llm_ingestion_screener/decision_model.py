"""Decision Inquiry: the client protocol and its three implementations.

Clients return untrusted, JSON-shaped answer data. :class:`DecisionInquiry`
normalises that data into typed answers and fails loudly on anything malformed.
"""

from __future__ import annotations

import hashlib
import json
import math
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Protocol

from llm_ingestion_screener.canonical import canonical_json
from llm_ingestion_screener.errors import (
    CassetteError,
    DecisionModelError,
    FaultInjectionError,
    ValidationError,
)
from llm_ingestion_screener.questions import (
    Answer,
    Question,
    parse_answers,
    validate_questions,
)

CASSETTE_FORMAT = "llm-ingestion-screener/cassette/v1"
DEFAULT_LIVE_MODEL = "clef-flash"
DEFAULT_SYSTEMONE_ENDPOINT = "http://127.0.0.1:11434/v1/systemone"


class DecisionModel(Protocol):
    """A decision-model transport. It may return any untrusted JSON-shaped data."""

    def ask(self, state: str, questions: Sequence[Question]) -> object:
        """Return raw answers for every question, keyed by question id."""


@dataclass(frozen=True)
class DecisionInquiry:
    """The anticorruption layer between the screening core and a model client."""

    model: DecisionModel

    def ask(
        self,
        state: str,
        questions: Sequence[Question],
    ) -> dict[str, Answer]:
        question_set = validate_questions(questions)
        if not isinstance(state, str):
            raise ValidationError("decision-model state must be a string")
        raw = self.model.ask(state, question_set)
        return parse_answers(question_set, raw)


def cassette_key(state: str, question: Question) -> str:
    """Key a cassette entry by the material and the full question identity."""

    if not isinstance(state, str):
        raise ValidationError("cassette state must be a string")
    if not isinstance(question, Question):
        raise ValidationError("cassette key requires a Question")
    payload = {
        "version": 1,
        "state": state,
        "question": question.to_dict(),
    }
    digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
    return digest


@dataclass(frozen=True)
class CassetteEntry:
    """One recorded raw answer, tied to its question identity."""

    key: str
    question_id: str
    question: Mapping[str, object]
    answer: Mapping[str, object]


@dataclass(frozen=True)
class Cassette:
    """A committed set of recorded raw answers."""

    model: str
    synthetic: bool
    comment: str
    entries: Mapping[str, CassetteEntry]

    @classmethod
    def from_file(cls, path: str | Path) -> Cassette:
        cassette_path = Path(path)
        try:
            text = cassette_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise CassetteError(
                f"could not read cassette {cassette_path}: {exc}"
            ) from exc
        try:
            raw = json.loads(text)
        except json.JSONDecodeError as exc:
            raise CassetteError(
                f"cassette {cassette_path} is not valid JSON: {exc}"
            ) from exc
        return cls.from_mapping(raw)

    @classmethod
    def from_mapping(cls, raw: object) -> Cassette:
        if not isinstance(raw, Mapping):
            raise CassetteError("cassette must be a mapping")
        if raw.get("format") != CASSETTE_FORMAT:
            raise CassetteError(
                f"cassette format must be {CASSETTE_FORMAT!r}, "
                f"got {raw.get('format')!r}"
            )

        model = raw.get("model")
        if not isinstance(model, str) or not model.strip():
            raise CassetteError("cassette requires a non-empty model name")

        synthetic = raw.get("synthetic")
        if not isinstance(synthetic, bool):
            raise CassetteError(
                "cassette must declare whether it is synthetic with a boolean "
                "'synthetic' field"
            )

        comment = raw.get("comment", "")
        if not isinstance(comment, str):
            raise CassetteError("cassette comment must be a string")

        entries_raw = raw.get("entries")
        if not isinstance(entries_raw, Mapping):
            raise CassetteError("cassette entries must be a mapping")

        entries: dict[str, CassetteEntry] = {}
        for key, entry in entries_raw.items():
            if not isinstance(key, str) or not key:
                raise CassetteError("cassette entry keys must be non-empty strings")
            if not isinstance(entry, Mapping):
                raise CassetteError(f"cassette entry {key!r} must be a mapping")
            question_id = entry.get("question_id")
            if not isinstance(question_id, str) or not question_id.strip():
                raise CassetteError(
                    f"cassette entry {key!r} requires a non-empty question_id"
                )
            question = entry.get("question")
            if not isinstance(question, Mapping):
                raise CassetteError(
                    f"cassette entry {key!r} requires a question mapping"
                )
            answer = entry.get("answer")
            if not isinstance(answer, Mapping):
                raise CassetteError(
                    f"cassette entry {key!r} requires an answer mapping"
                )
            entries[key] = CassetteEntry(
                key=key,
                question_id=question_id,
                question=question,
                answer=answer,
            )

        return cls(
            model=model,
            synthetic=synthetic,
            comment=comment,
            entries=MappingProxyType(entries),
        )


class RecordedDecisionModel:
    """Replay committed cassettes, keyed by the question and the material."""

    def __init__(self, cassette: Cassette) -> None:
        if not isinstance(cassette, Cassette):
            raise ValidationError("recorded model requires a Cassette")
        self._cassette = cassette

    @classmethod
    def from_file(cls, path: str | Path) -> RecordedDecisionModel:
        return cls(Cassette.from_file(path))

    @property
    def cassette(self) -> Cassette:
        return self._cassette

    def ask(self, state: str, questions: Sequence[Question]) -> object:
        question_set = validate_questions(questions)
        answers: dict[str, Mapping[str, object]] = {}
        for question in question_set:
            key = cassette_key(state, question)
            entry = self._cassette.entries.get(key)
            if entry is None:
                raise CassetteError(
                    f"no cassette entry for question {question.id!r} "
                    f"(key {key})"
                )
            if entry.question_id != question.id:
                raise CassetteError(
                    f"cassette entry {key!r} stores question id "
                    f"{entry.question_id!r}, expected {question.id!r}"
                )
            if dict(entry.question) != question.to_dict():
                raise CassetteError(
                    f"cassette entry {key!r} question does not match the "
                    f"requested question {question.id!r}"
                )
            answers[question.id] = dict(entry.answer)
        return answers


def validate_live_config(model: str, endpoint: str) -> None:
    """Reject an absent model or a non-HTTP endpoint before any call is made."""

    if not isinstance(model, str) or not model.strip():
        raise DecisionModelError("live decision model requires a non-empty model name")
    if not isinstance(endpoint, str) or not endpoint.strip():
        raise DecisionModelError("live decision model requires a non-empty endpoint")
    parsed = urllib.parse.urlparse(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise DecisionModelError(
            f"live decision model endpoint must be an http(s) URL: {endpoint!r}"
        )


def build_systemone_request(
    model: str,
    state: str,
    questions: Sequence[Question],
) -> dict[str, object]:
    """Build the documented System One request body."""

    if not isinstance(model, str) or not model.strip():
        raise ValidationError("a systemone request requires a model name")
    if not isinstance(state, str):
        raise ValidationError("a systemone request state must be a string")
    question_set = validate_questions(questions)
    return {
        "model": model,
        "state": state,
        "questions": {
            question.id: question.to_wire() for question in question_set
        },
    }


def parse_systemone_envelope(payload: object) -> Mapping[str, Mapping[str, object]]:
    """Validate the endpoint envelope, leaving typed answer checks to the parser."""

    if not isinstance(payload, Mapping):
        raise DecisionModelError("systemone response must be a JSON object")
    if "error" in payload:
        raise DecisionModelError(f"systemone endpoint returned an error: {payload['error']}")
    answers = payload.get("answers")
    if not isinstance(answers, Mapping):
        raise DecisionModelError(
            "systemone response is missing an 'answers' mapping"
        )
    for question_id, answer in answers.items():
        if not isinstance(question_id, str) or not question_id:
            raise DecisionModelError(
                "systemone response answer keys must be non-empty question ids"
            )
        if not isinstance(answer, Mapping):
            raise DecisionModelError(
                f"systemone response answer {question_id!r} is not a mapping"
            )
    return answers


class LiveDecisionModel:
    """Call the local Ollama System One endpoint. Used only in opt-in runs."""

    def __init__(
        self,
        model: str = DEFAULT_LIVE_MODEL,
        endpoint: str = DEFAULT_SYSTEMONE_ENDPOINT,
        *,
        timeout: float = 120.0,
        opener: object | None = None,
    ) -> None:
        validate_live_config(model, endpoint)
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout)
            or timeout <= 0
        ):
            raise DecisionModelError("live decision model timeout must be positive")
        if opener is not None and not callable(opener):
            raise DecisionModelError("live decision model opener must be callable")
        self._model = model
        self._endpoint = endpoint
        self._timeout = float(timeout)
        self._opener = urllib.request.urlopen if opener is None else opener

    def ask(self, state: str, questions: Sequence[Question]) -> object:
        request_body = build_systemone_request(self._model, state, questions)
        encoded = json.dumps(
            request_body,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        request = urllib.request.Request(
            self._endpoint,
            data=encoded,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self._opener(request, timeout=self._timeout) as response:  # type: ignore[operator]
                text = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            raise DecisionModelError(
                f"systemone endpoint returned HTTP {exc.code}: {exc.reason}"
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise DecisionModelError(
                f"could not reach the systemone endpoint at {self._endpoint}: {exc}"
            ) from exc
        except UnicodeDecodeError as exc:
            raise DecisionModelError(
                "systemone response was not valid UTF-8"
            ) from exc

        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise DecisionModelError(
                f"systemone response was not valid JSON: {exc}"
            ) from exc
        return parse_systemone_envelope(payload)


class FaultMode(str, Enum):
    """The malformed-answer shapes the fault client can produce."""

    MALFORMED = "malformed"
    TRUNCATED = "truncated"
    MISSING_ANSWER = "missing-answer"
    WRONG_KIND = "wrong-kind"
    PROBABILITIES_DO_NOT_SUM = "probabilities-do-not-sum"
    NON_NUMERIC = "non-numeric"


class FaultInjectionDecisionModel:
    """Return a malformed or truncated answer on demand, to prove fail-loud."""

    def __init__(self, mode: FaultMode | str) -> None:
        try:
            self._mode = FaultMode(mode)
        except ValueError as exc:
            raise ValidationError(f"unknown fault mode: {mode!r}") from exc

    def ask(self, state: str, questions: Sequence[Question]) -> object:
        question_set = validate_questions(questions)
        first = question_set[0]

        if self._mode is FaultMode.MALFORMED:
            return "{this is not json"
        if self._mode is FaultMode.TRUNCATED:
            return {first.id: {"type": first.kind.value}}
        if self._mode is FaultMode.MISSING_ANSWER:
            return {}
        if self._mode is FaultMode.WRONG_KIND:
            if first.kind.value == "noul":
                return {
                    first.id: {
                        "type": "choice",
                        "choice": "none",
                        "probabilities": {"none": 1.0},
                        "confidence": 1.0,
                    }
                }
            return {first.id: {"type": "noul", "noul": 0.5}}
        if self._mode is FaultMode.PROBABILITIES_DO_NOT_SUM:
            return _probabilities_do_not_sum(question_set)
        if self._mode is FaultMode.NON_NUMERIC:
            if first.kind.value == "noul":
                return {first.id: {"type": "noul", "noul": "high"}}
            if first.kind.value == "choice":
                labels = first.labels
                probabilities = {
                    label: (1.0 if index == 0 else 0.0)
                    for index, label in enumerate(labels)
                }
                return {
                    first.id: {
                        "type": "choice",
                        "choice": labels[0],
                        "probabilities": probabilities,
                        "confidence": "high",
                    }
                }
            levels = first.labels
            legend = {str(index): label for index, label in enumerate(levels)}
            probabilities = {
                str(index): (1.0 if index == 0 else 0.0)
                for index in range(len(levels))
            }
            return {
                first.id: {
                    "type": "score",
                    "score": 0.0,
                    "legend": legend,
                    "probabilities": probabilities,
                    "confidence": "high",
                }
            }
        raise FaultInjectionError(f"unsupported fault mode: {self._mode!r}")


def _probabilities_do_not_sum(
    questions: tuple[Question, ...],
) -> dict[str, object]:
    for question in questions:
        if question.kind.value == "choice":
            labels = question.labels
            probabilities = {
                label: (0.1 if index == 0 else 0.0)
                for index, label in enumerate(labels)
            }
            return {
                question.id: {
                    "type": "choice",
                    "choice": labels[0],
                    "probabilities": probabilities,
                    "confidence": 1.0,
                }
            }
        if question.kind.value == "score":
            levels = question.labels
            legend = {str(index): label for index, label in enumerate(levels)}
            probabilities = {
                str(index): (0.1 if index == 0 else 0.0)
                for index in range(len(levels))
            }
            return {
                question.id: {
                    "type": "score",
                    "score": 0.0,
                    "legend": legend,
                    "probabilities": probabilities,
                    "confidence": 1.0,
                }
            }
    raise FaultInjectionError(
        "the probabilities fault requires a choice or score question"
    )
