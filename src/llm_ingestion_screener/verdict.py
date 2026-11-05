"""Immutable verdict assembly."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from llm_ingestion_screener.domain import (
    PolicyEscalation,
    QuarantinedPassage,
    RuleHit,
    Threshold,
    VerdictLevel,
)
from llm_ingestion_screener.errors import ValidationError
from llm_ingestion_screener.questions import Answer


@dataclass(frozen=True)
class Verdict:
    """The screener's typed output, with the evidence that produced it."""

    level: VerdictLevel
    rule_hits: tuple[RuleHit, ...]
    answers: tuple[Answer, ...]
    quarantined_passages: tuple[QuarantinedPassage, ...]
    thresholds: tuple[Threshold, ...]
    escalations: tuple[PolicyEscalation, ...]

    def __post_init__(self) -> None:
        try:
            level = VerdictLevel(self.level)
        except ValueError as exc:
            raise ValidationError(f"unknown verdict level: {self.level!r}") from exc
        object.__setattr__(self, "level", level)
        object.__setattr__(self, "rule_hits", tuple(self.rule_hits))
        object.__setattr__(self, "answers", tuple(self.answers))
        object.__setattr__(self, "quarantined_passages", tuple(self.quarantined_passages))
        object.__setattr__(self, "thresholds", tuple(self.thresholds))
        object.__setattr__(self, "escalations", tuple(self.escalations))

        if not all(isinstance(hit, RuleHit) for hit in self.rule_hits):
            raise ValidationError("verdict rule hits must be RuleHit values")
        if not all(isinstance(answer, Answer) for answer in self.answers):
            raise ValidationError("verdict answers must be Answer values")
        if not all(
            isinstance(passage, QuarantinedPassage)
            for passage in self.quarantined_passages
        ):
            raise ValidationError(
                "verdict quarantined passages must be QuarantinedPassage values"
            )
        if not all(isinstance(threshold, Threshold) for threshold in self.thresholds):
            raise ValidationError("verdict thresholds must be Threshold values")
        if not all(
            isinstance(escalation, PolicyEscalation)
            for escalation in self.escalations
        ):
            raise ValidationError(
                "verdict escalations must be PolicyEscalation values"
            )

        implied = VerdictLevel.CLEAN
        for hit in self.rule_hits:
            implied = max(implied, hit.level)
        for escalation in self.escalations:
            implied = max(implied, escalation.level)
        if level is not implied:
            raise ValidationError(
                f"verdict level {level.label!r} is below the level implied by "
                f"its rules and answers ({implied.label!r})"
            )

        question_ids = [answer.question_id for answer in self.answers]
        if len(set(question_ids)) != len(question_ids):
            raise ValidationError("a verdict cannot carry duplicate answers")

        if level is VerdictLevel.QUARANTINE and not self.quarantined_passages:
            raise ValidationError("a quarantine verdict requires a quarantined passage")

        if not self.thresholds:
            raise ValidationError("a verdict must record the thresholds in force")

        passage_flags = {
            passage.flagged_by for passage in self.quarantined_passages
        }
        for escalation in self.escalations:
            if escalation.level is not VerdictLevel.QUARANTINE:
                continue
            if escalation.source_kind == "rule":
                expected_flag = escalation.source_id
            else:
                expected_flag = f"answer:{escalation.source_id}"
            if expected_flag not in passage_flags:
                raise ValidationError(
                    f"quarantine escalation {expected_flag!r} has no "
                    "quarantined passage"
                )

    @property
    def rule_ids(self) -> tuple[str, ...]:
        return tuple(hit.rule_id for hit in self.rule_hits)

    def to_dict(self) -> dict[str, object]:
        return {
            "level": self.level.label,
            "rule_hits": [hit.to_dict() for hit in self.rule_hits],
            "answers": [answer.to_dict() for answer in self.answers],
            "quarantined_passages": [
                passage.to_dict() for passage in self.quarantined_passages
            ],
            "thresholds": [threshold.to_dict() for threshold in self.thresholds],
            "escalations": [
                escalation.to_dict() for escalation in self.escalations
            ],
        }
