"""Core domain values shared by the screening core."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, IntEnum

from llm_ingestion_screener.errors import ValidationError


class VerdictLevel(IntEnum):
    """The total order a verdict obeys: clean < flagged < quarantine."""

    CLEAN = 0
    FLAGGED = 1
    QUARANTINE = 2

    @property
    def label(self) -> str:
        return self.name.lower()

    def __str__(self) -> str:
        return self.label


class IngestionSurface(str, Enum):
    """The ingestion surface a piece of material models."""

    WEB_PAGE = "web-page"
    SEARCH_RESULT = "search-result"
    DOCUMENT = "document"
    THIRD_PARTY_SKILL = "third-party-skill"
    TOOL_OUTPUT = "tool-output"


@dataclass(frozen=True)
class Material:
    """One inbound document. Its content is data, never instructions."""

    content: str
    media_type: str = "text/plain"

    def __post_init__(self) -> None:
        if not isinstance(self.content, str):
            raise ValidationError("material content must be a string")
        if not isinstance(self.media_type, str) or not self.media_type.strip():
            raise ValidationError("material media_type must be a non-empty string")

    @property
    def content_sha256(self) -> str:
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Provenance:
    """Where material came from. Provenance never lowers the screen."""

    retriever: str
    retrieved_at: datetime
    source_url: str | None = None
    referrer: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.retriever, str) or not self.retriever.strip():
            raise ValidationError("provenance requires a non-empty retriever")
        if not isinstance(self.retrieved_at, datetime):
            raise ValidationError("provenance retrieved_at must be a datetime")
        if self.retrieved_at.tzinfo is None:
            raise ValidationError("provenance retrieved_at must be timezone-aware")
        if self.source_url is not None and (
            not isinstance(self.source_url, str) or not self.source_url.strip()
        ):
            raise ValidationError("provenance source_url must be non-empty when set")
        if self.referrer is not None and (
            not isinstance(self.referrer, str) or not self.referrer.strip()
        ):
            raise ValidationError("provenance referrer must be non-empty when set")

    @property
    def source(self) -> str:
        """The source a quarantined passage is tagged with."""

        return self.source_url or self.retriever


@dataclass(frozen=True)
class RuleHit:
    """One deterministic rule match, with its verbatim excerpt and position."""

    rule_id: str
    level: VerdictLevel
    excerpt: str
    start: int
    end: int

    def __post_init__(self) -> None:
        if not isinstance(self.rule_id, str) or not self.rule_id.strip():
            raise ValidationError("rule hit requires a non-empty rule id")
        try:
            level = VerdictLevel(self.level)
        except ValueError as exc:
            raise ValidationError(f"unknown verdict level: {self.level!r}") from exc
        if level is VerdictLevel.CLEAN:
            raise ValidationError("a rule hit cannot imply clean")
        object.__setattr__(self, "level", level)
        if not isinstance(self.excerpt, str):
            raise ValidationError("rule hit excerpt must be a string")
        if not isinstance(self.start, int) or not isinstance(self.end, int):
            raise ValidationError("rule hit offsets must be integers")
        if self.start < 0 or self.end <= self.start:
            raise ValidationError("rule hit offsets must be a non-empty range")
        if self.end - self.start != len(self.excerpt):
            raise ValidationError("rule hit excerpt must match its offsets")

    def to_dict(self) -> dict[str, object]:
        return {
            "rule_id": self.rule_id,
            "level": self.level.label,
            "excerpt": self.excerpt,
            "start": self.start,
            "end": self.end,
        }


@dataclass(frozen=True)
class QuarantinedPassage:
    """A verbatim span isolated with its source and the evidence that flagged it."""

    text: str
    source: str
    flagged_by: str
    start: int
    end: int

    def __post_init__(self) -> None:
        if not isinstance(self.text, str):
            raise ValidationError("quarantined passage text must be a string")
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValidationError("quarantined passage requires a source")
        if not isinstance(self.flagged_by, str) or not self.flagged_by.strip():
            raise ValidationError("quarantined passage requires a flagging source")
        if not isinstance(self.start, int) or not isinstance(self.end, int):
            raise ValidationError("quarantined passage offsets must be integers")
        if self.start < 0 or self.end < self.start:
            raise ValidationError("quarantined passage offsets are invalid")
        if self.end - self.start != len(self.text):
            raise ValidationError("quarantined passage text must match its offsets")

    def to_dict(self) -> dict[str, object]:
        return {
            "text": self.text,
            "source": self.source,
            "flagged_by": self.flagged_by,
            "start": self.start,
            "end": self.end,
        }


@dataclass(frozen=True)
class Threshold:
    """An explicit, recorded policy threshold."""

    metric: str
    op: str
    value: float

    def __post_init__(self) -> None:
        if not isinstance(self.metric, str) or not self.metric.strip():
            raise ValidationError("threshold requires a non-empty metric")
        if self.op not in {">=", ">"}:
            raise ValidationError(f"unsupported threshold operator: {self.op!r}")
        if isinstance(self.value, bool) or not isinstance(self.value, (int, float)):
            raise ValidationError("threshold value must be a number")
        if not math.isfinite(self.value):
            raise ValidationError("threshold value must be finite")

    def to_dict(self) -> dict[str, object]:
        return {"metric": self.metric, "op": self.op, "value": self.value}


@dataclass(frozen=True)
class PolicyEscalation:
    """Why the policy raised the verdict for one rule or answer."""

    source_kind: str
    source_id: str
    level: VerdictLevel
    observed: float | None = None
    threshold: float | None = None

    def __post_init__(self) -> None:
        if self.source_kind not in {"rule", "answer"}:
            raise ValidationError(
                f"policy escalation source_kind must be rule or answer: "
                f"{self.source_kind!r}"
            )
        if not isinstance(self.source_id, str) or not self.source_id.strip():
            raise ValidationError("policy escalation requires a source id")
        try:
            level = VerdictLevel(self.level)
        except ValueError as exc:
            raise ValidationError(f"unknown verdict level: {self.level!r}") from exc
        if level is VerdictLevel.CLEAN:
            raise ValidationError("policy escalation cannot imply clean")
        object.__setattr__(self, "level", level)
        for name, value in (
            ("observed", self.observed),
            ("threshold", self.threshold),
        ):
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValidationError(f"policy escalation {name} must be a number")
            if not math.isfinite(value):
                raise ValidationError(f"policy escalation {name} must be finite")

    def to_dict(self) -> dict[str, object]:
        return {
            "source_kind": self.source_kind,
            "source_id": self.source_id,
            "level": self.level.label,
            "observed": self.observed,
            "threshold": self.threshold,
        }
