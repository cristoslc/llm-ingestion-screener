"""Shared paths and helpers for the eval-harness tests."""

from __future__ import annotations

import copy
import shutil
from collections.abc import Mapping
from pathlib import Path

import yaml

from llm_ingestion_screener.questions import Question, QuestionKind

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CORPUS = PROJECT_ROOT / "tests" / "fixtures" / "screener-corpus"
CASSETTE = PROJECT_ROOT / "tests" / "cassettes" / "eval-synthetic.json"
GATES = PROJECT_ROOT / "tests" / "eval" / "gates.yaml"
BASELINE = PROJECT_ROOT / "tests" / "eval" / "baseline.json"


class NeutralModel:
    """A decision-model double with fixed low answers, for runner unit tests."""

    def ask(self, state: str, questions) -> dict[str, object]:
        return {question.id: neutral_answer(question) for question in questions}


def neutral_answer(question: Question) -> dict[str, object]:
    if question.kind is QuestionKind.NOUL:
        return {"type": "noul", "noul": 0.01}
    if question.kind is QuestionKind.CHOICE:
        labels = question.labels
        probabilities = {label: (0.0 if index else 1.0) for index, label in enumerate(labels)}
        return {
            "type": "choice",
            "choice": labels[0],
            "probabilities": probabilities,
            "confidence": 1.0,
        }
    levels = question.labels
    legend = {str(index): label for index, label in enumerate(levels)}
    probabilities = {
        str(index): (1.0 if index == 0 else 0.0) for index in range(len(levels))
    }
    return {
        "type": "score",
        "score": 0.0,
        "legend": legend,
        "probabilities": probabilities,
        "confidence": 1.0,
    }


def copy_corpus(tmp_path: Path) -> Path:
    destination = tmp_path / "corpus"
    shutil.copytree(CORPUS, destination)
    return destination


def load_yaml(path: Path) -> dict[str, object]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def write_yaml(path: Path, payload: Mapping[str, object]) -> None:
    path.write_text(
        yaml.safe_dump(dict(payload), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def mutate_yaml(path: Path, mutate) -> None:
    payload = copy.deepcopy(load_yaml(path))
    mutate(payload)
    write_yaml(path, payload)


def gates_with(tmp_path: Path, mutate) -> Path:
    payload = copy.deepcopy(load_yaml(GATES))
    mutate(payload)
    destination = tmp_path / "gates.yaml"
    write_yaml(destination, payload)
    return destination
