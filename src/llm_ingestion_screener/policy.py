"""Explicit thresholds that map rule hits and typed answers to a verdict."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from llm_ingestion_screener.domain import (
    PolicyEscalation,
    RuleHit,
    Threshold,
    VerdictLevel,
)
from llm_ingestion_screener.errors import ValidationError
from llm_ingestion_screener.questions import Answer, QuestionKind


@dataclass(frozen=True)
class Policy:
    """A recorded threshold set. A choice answer is diagnostic only."""

    noul_flagged_at: float = 0.50
    noul_quarantined_at: float = 0.80
    score_flagged_at: float = 2.0
    score_quarantined_at: float = 3.5

    def __post_init__(self) -> None:
        for name, value in (
            ("noul_flagged_at", self.noul_flagged_at),
            ("noul_quarantined_at", self.noul_quarantined_at),
        ):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValidationError(f"{name} must be a number")
            if not math.isfinite(value) or not 0.0 <= value <= 1.0:
                raise ValidationError(f"{name} must be a probability between 0 and 1")
        for name, value in (
            ("score_flagged_at", self.score_flagged_at),
            ("score_quarantined_at", self.score_quarantined_at),
        ):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValidationError(f"{name} must be a number")
            if not math.isfinite(value):
                raise ValidationError(f"{name} must be finite")
        if self.noul_flagged_at >= self.noul_quarantined_at:
            raise ValidationError(
                "noul_flagged_at must be lower than noul_quarantined_at"
            )
        if self.score_flagged_at >= self.score_quarantined_at:
            raise ValidationError(
                "score_flagged_at must be lower than score_quarantined_at"
            )

    @property
    def thresholds(self) -> tuple[Threshold, ...]:
        return (
            Threshold("noul.flagged_at", ">=", float(self.noul_flagged_at)),
            Threshold("noul.quarantined_at", ">=", float(self.noul_quarantined_at)),
            Threshold("score.flagged_at", ">=", float(self.score_flagged_at)),
            Threshold(
                "score.quarantined_at", ">=", float(self.score_quarantined_at)
            ),
        )

    def decide(
        self,
        rule_hits: Sequence[RuleHit],
        answers: Sequence[Answer],
    ) -> PolicyDecision:
        level = VerdictLevel.CLEAN
        escalations: list[PolicyEscalation] = []

        for hit in rule_hits:
            level = max(level, hit.level)
            escalations.append(
                PolicyEscalation(
                    source_kind="rule",
                    source_id=hit.rule_id,
                    level=hit.level,
                )
            )

        for answer in answers:
            if answer.kind is QuestionKind.NOUL:
                observed = float(answer.value)
                if observed >= self.noul_quarantined_at:
                    level = max(level, VerdictLevel.QUARANTINE)
                    escalations.append(
                        PolicyEscalation(
                            source_kind="answer",
                            source_id=answer.question_id,
                            level=VerdictLevel.QUARANTINE,
                            observed=observed,
                            threshold=float(self.noul_quarantined_at),
                        )
                    )
                elif observed >= self.noul_flagged_at:
                    level = max(level, VerdictLevel.FLAGGED)
                    escalations.append(
                        PolicyEscalation(
                            source_kind="answer",
                            source_id=answer.question_id,
                            level=VerdictLevel.FLAGGED,
                            observed=observed,
                            threshold=float(self.noul_flagged_at),
                        )
                    )
                continue

            if answer.kind is QuestionKind.SCORE:
                observed = float(answer.value)
                if observed >= self.score_quarantined_at:
                    level = max(level, VerdictLevel.QUARANTINE)
                    escalations.append(
                        PolicyEscalation(
                            source_kind="answer",
                            source_id=answer.question_id,
                            level=VerdictLevel.QUARANTINE,
                            observed=observed,
                            threshold=float(self.score_quarantined_at),
                        )
                    )
                elif observed >= self.score_flagged_at:
                    level = max(level, VerdictLevel.FLAGGED)
                    escalations.append(
                        PolicyEscalation(
                            source_kind="answer",
                            source_id=answer.question_id,
                            level=VerdictLevel.FLAGGED,
                            observed=observed,
                            threshold=float(self.score_flagged_at),
                        )
                    )

        return PolicyDecision(level=level, escalations=tuple(escalations))


@dataclass(frozen=True)
class PolicyDecision:
    """The policy's verdict level and the evidence that raised it."""

    level: VerdictLevel
    escalations: tuple[PolicyEscalation, ...]

    def __post_init__(self) -> None:
        implied = max(
            (escalation.level for escalation in self.escalations),
            default=VerdictLevel.CLEAN,
        )
        if self.level is not implied:
            raise ValidationError(
                f"policy level {self.level!r} does not match its escalations "
                f"({implied!r})"
            )
