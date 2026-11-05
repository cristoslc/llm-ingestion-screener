"""Opt-in tests that call the live Ollama System One endpoint.

The default gate deselects this module through the ``model`` marker. If the
endpoint or clef-flash is absent, the test fails loudly rather than skipping.
"""

from __future__ import annotations

import pytest

from llm_ingestion_screener.decision_model import DecisionInquiry, LiveDecisionModel
from llm_ingestion_screener.questions import Question

pytestmark = pytest.mark.model


def test_live_clef_flash_answers_a_noul_question() -> None:
    inquiry = DecisionInquiry(LiveDecisionModel(model="clef-flash"))
    question = Question.noul("q.blue", "Is the sky blue?")

    answers = inquiry.ask("The sky is blue.", [question])

    answer = answers["q.blue"]
    assert answer.kind.value == "noul"
    assert 0.0 <= answer.value <= 1.0
    assert 0.5 <= answer.confidence <= 1.0
    assert set(answer.probabilities) == {"yes", "no"}
