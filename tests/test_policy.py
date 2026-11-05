"""The explicit policy thresholds and the verdict ladder they produce."""

from __future__ import annotations

import pytest

from llm_ingestion_screener.domain import RuleHit, VerdictLevel
from llm_ingestion_screener.errors import ValidationError
from llm_ingestion_screener.policy import Policy
from llm_ingestion_screener.questions import Answer, QuestionKind


def _noul(probability: float, question_id: str = "q.noul") -> Answer:
    return Answer(
        question_id=question_id,
        kind=QuestionKind.NOUL,
        value=probability,
        probabilities={"yes": probability, "no": 1.0 - probability},
        confidence=max(probability, 1.0 - probability),
    )


def _score(score: float) -> Answer:
    return Answer(
        question_id="q.score",
        kind=QuestionKind.SCORE,
        value=score,
        probabilities={"none": 0.1, "low": 0.2, "high": 0.7},
        confidence=0.7,
    )


def _choice(label: str = "attack") -> Answer:
    return Answer(
        question_id="q.choice",
        kind=QuestionKind.CHOICE,
        value=label,
        probabilities={"none": 0.1, "attack": 0.9},
        confidence=0.8,
    )


def _hit(level: VerdictLevel, rule_id: str = "rule.test") -> RuleHit:
    return RuleHit(
        rule_id=rule_id,
        level=level,
        excerpt="needle",
        start=0,
        end=6,
    )


def test_default_thresholds_are_explicit_and_recorded() -> None:
    policy = Policy()

    assert {
        threshold.metric: (threshold.op, threshold.value)
        for threshold in policy.thresholds
    } == {
        "noul.flagged_at": (">=", 0.50),
        "noul.quarantined_at": (">=", 0.80),
        "score.flagged_at": (">=", 2.0),
        "score.quarantined_at": (">=", 3.5),
    }


@pytest.mark.parametrize(
    ("probability", "expected"),
    [
        (0.0, VerdictLevel.CLEAN),
        (0.49, VerdictLevel.CLEAN),
        (0.50, VerdictLevel.FLAGGED),
        (0.79, VerdictLevel.FLAGGED),
        (0.80, VerdictLevel.QUARANTINE),
        (1.0, VerdictLevel.QUARANTINE),
    ],
)
def test_noul_threshold_boundaries(
    probability: float, expected: VerdictLevel
) -> None:
    assert Policy().decide((), (_noul(probability),)).level is expected


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (0.0, VerdictLevel.CLEAN),
        (1.99, VerdictLevel.CLEAN),
        (2.0, VerdictLevel.FLAGGED),
        (3.49, VerdictLevel.FLAGGED),
        (3.5, VerdictLevel.QUARANTINE),
    ],
)
def test_score_threshold_boundaries(
    score: float, expected: VerdictLevel
) -> None:
    assert Policy().decide((), (_score(score),)).level is expected


def test_rule_hit_is_a_floor_no_answer_can_lower() -> None:
    decision = Policy().decide(
        (_hit(VerdictLevel.QUARANTINE),),
        (_noul(0.0), _score(0.0), _choice("none")),
    )

    assert decision.level is VerdictLevel.QUARANTINE


def test_verdict_takes_the_maximum_of_rule_and_answer_levels() -> None:
    decision = Policy().decide(
        (_hit(VerdictLevel.FLAGGED),),
        (_noul(0.95),),
    )

    assert decision.level is VerdictLevel.QUARANTINE
    assert {escalation.level for escalation in decision.escalations} == {
        VerdictLevel.FLAGGED,
        VerdictLevel.QUARANTINE,
    }


def test_choice_is_diagnostic_and_does_not_escalate() -> None:
    decision = Policy().decide((), (_choice("attack"),))

    assert decision.level is VerdictLevel.CLEAN
    assert decision.escalations == ()


def test_clean_when_nothing_fires() -> None:
    decision = Policy().decide((), (_noul(0.1), _score(0.1), _choice("none")))

    assert decision.level is VerdictLevel.CLEAN
    assert decision.escalations == ()


def test_thresholds_must_be_ordered() -> None:
    with pytest.raises(ValidationError, match="noul"):
        Policy(noul_flagged_at=0.9, noul_quarantined_at=0.8)

    with pytest.raises(ValidationError, match="score"):
        Policy(score_flagged_at=4.0, score_quarantined_at=3.5)


@pytest.mark.parametrize("field", ["noul_flagged_at", "noul_quarantined_at"])
def test_noul_thresholds_must_be_probabilities(field: str) -> None:
    with pytest.raises(ValidationError, match=field):
        Policy(**{field: 1.1})


def test_policy_records_the_answer_threshold_that_crossed() -> None:
    decision = Policy().decide((), (_noul(0.95),))
    escalation = decision.escalations[0]

    assert escalation.source_kind == "answer"
    assert escalation.source_id == "q.noul"
    assert escalation.level is VerdictLevel.QUARANTINE
    assert escalation.observed == pytest.approx(0.95)
    assert escalation.threshold == pytest.approx(0.80)
