#!/usr/bin/env python
"""Build the synthetic recorded cassette for the starter eval corpus.

The answers are fixed neutral values, not measured model output. They exist so
the default run exercises the recorded-client path offline and byte for byte.
Run this script only when the corpus or the question set changes deliberately.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from llm_ingestion_screener.decision_model import CASSETTE_FORMAT, cassette_key
from llm_ingestion_screener.eval.fixtures import load_corpus
from llm_ingestion_screener.questions import Question, QuestionKind, questions_for_surface

COMMENT = (
    "SYNTHETIC CASSETTE. Every answer is a fixed neutral value written for the "
    "starter eval corpus; these are not measured clef-flash output and must not "
    "be read as a benchmark result. The material is sanitised with "
    "example.invalid hosts and no live payload."
)


def neutral_answer(question: Question) -> dict[str, object]:
    if question.kind is QuestionKind.NOUL:
        return {"type": "noul", "noul": 0.05}
    if question.kind is QuestionKind.CHOICE:
        labels = question.labels
        remainder = 0.15 / (len(labels) - 1)
        probabilities = {
            label: (0.85 if index == 0 else remainder)
            for index, label in enumerate(labels)
        }
        return {
            "type": "choice",
            "choice": labels[0],
            "probabilities": probabilities,
            "confidence": 0.9,
        }
    levels = question.labels
    remainder = 0.15 / (len(levels) - 1)
    legend = {str(index): label for index, label in enumerate(levels)}
    probabilities = {
        str(index): (0.85 if index == 0 else remainder)
        for index in range(len(levels))
    }
    return {
        "type": "score",
        "score": 0.0,
        "legend": legend,
        "probabilities": probabilities,
        "confidence": 0.9,
    }


def build(corpus_root: Path) -> dict[str, object]:
    corpus = load_corpus(corpus_root)
    entries: dict[str, object] = {}
    for fixture in corpus.fixtures:
        for question in questions_for_surface(fixture.surface):
            key = cassette_key(fixture.content, question)
            if key in entries:
                raise SystemExit(
                    f"duplicate cassette key for {fixture.id!r} and {question.id!r}"
                )
            entries[key] = {
                "question_id": question.id,
                "question": question.to_dict(),
                "answer": neutral_answer(question),
            }
    return {
        "format": CASSETTE_FORMAT,
        "model": "clef-flash",
        "synthetic": True,
        "comment": COMMENT,
        "entries": entries,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--corpus",
        type=Path,
        default=Path("tests/fixtures/screener-corpus"),
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("tests/cassettes/eval-synthetic.json"),
    )
    args = parser.parse_args()
    payload = build(args.corpus)
    # sort_keys makes the committed file stable; indentation keeps it reviewable.
    args.out.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {len(payload['entries'])} entries to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
