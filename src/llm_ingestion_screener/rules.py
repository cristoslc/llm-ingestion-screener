"""Deterministic screening rules with stable, documented ids."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from llm_ingestion_screener.domain import RuleHit, VerdictLevel
from llm_ingestion_screener.errors import ValidationError

RULE_AGENT_DIRECTED_IMPERATIVE = "rule.agent-directed-imperative"
RULE_INSTRUCTION_OVERRIDE = "rule.instruction-override"
RULE_EXFILTRATION_REQUEST = "rule.exfiltration-request"
RULE_TOOL_INVOCATION_LURE = "rule.tool-invocation-lure"
RULE_TOOL_RESULT_INJECTION = "rule.tool-result-injection"
RULE_HIDDEN_UNICODE_TAGS = "rule.hidden-unicode-tags"
RULE_BIDI_OVERRIDE = "rule.bidi-override"
RULE_ENCODED_EXECUTION = "rule.encoded-execution"
RULE_SYSTEM_PROMPT_EXFILTRATION = "rule.system-prompt-exfiltration"

DEFAULT_RULE_IDS: frozenset[str] = frozenset(
    {
        RULE_AGENT_DIRECTED_IMPERATIVE,
        RULE_INSTRUCTION_OVERRIDE,
        RULE_EXFILTRATION_REQUEST,
        RULE_TOOL_INVOCATION_LURE,
        RULE_TOOL_RESULT_INJECTION,
        RULE_HIDDEN_UNICODE_TAGS,
        RULE_BIDI_OVERRIDE,
        RULE_ENCODED_EXECUTION,
        RULE_SYSTEM_PROMPT_EXFILTRATION,
    }
)


@dataclass(frozen=True)
class Rule:
    """One deterministic check. A hit is a floor no model answer can lower."""

    id: str
    level: VerdictLevel
    description: str
    pattern: re.Pattern[str]

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.startswith("rule."):
            raise ValidationError("rule ids must start with 'rule.'")
        if self.level is VerdictLevel.CLEAN:
            raise ValidationError("a rule cannot imply clean")
        if not isinstance(self.description, str) or not self.description.strip():
            raise ValidationError("a rule requires a non-empty description")
        if not isinstance(self.pattern, re.Pattern):
            raise ValidationError("a rule requires a compiled regular expression")


class RuleEngine:
    """Scans untrusted material for every registered rule."""

    def __init__(self, rules: Sequence[Rule] | None = None) -> None:
        selected = tuple(DEFAULT_RULES if rules is None else rules)
        if not selected:
            raise ValidationError("a rule engine requires at least one rule")
        ids = [rule.id for rule in selected]
        if len(set(ids)) != len(ids):
            duplicates = sorted({rule_id for rule_id in ids if ids.count(rule_id) > 1})
            raise ValidationError(f"duplicate rule id: {', '.join(duplicates)}")
        self._rules = selected

    @property
    def rules(self) -> tuple[Rule, ...]:
        return self._rules

    def scan(self, content: str) -> tuple[RuleHit, ...]:
        if not isinstance(content, str):
            raise ValidationError("material content must be a string")

        hits: list[RuleHit] = []
        for rule in self._rules:
            for match in rule.pattern.finditer(content):
                hits.append(
                    RuleHit(
                        rule_id=rule.id,
                        level=rule.level,
                        excerpt=match.group(0),
                        start=match.start(),
                        end=match.end(),
                    )
                )
        hits.sort(key=lambda hit: (hit.start, hit.end, hit.rule_id))
        return tuple(hits)


_AGENT_ADDRESS = (
    r"(?:\b(?:dear|attention|note\s+to|message\s+(?:to|for)|for)\s+"
    r"(?:the\s+)?(?:ai|a\.i\.|assistant|agent|llm|model|chatbot)s?\b"
    r"|\b(?:if|when)\s+you(?:'re|\s+are)\s+an?\s+"
    r"(?:ai|assistant|agent|llm|language model)\b"
    r"|\b(?:ai|assistant|agent)s?\s+(?:reading|processing)\s+this\b)"
)
_AGENT_IMPERATIVE = (
    r"\b(?:ignore|disregard|send|upload|forward|visit|click|call|run|"
    r"execute|reveal|print|delete)\b"
)

DEFAULT_RULES: tuple[Rule, ...] = (
    Rule(
        id=RULE_AGENT_DIRECTED_IMPERATIVE,
        level=VerdictLevel.QUARANTINE,
        description=(
            "Text addresses an AI assistant or agent and directs it to act in "
            "the same sentence."
        ),
        pattern=re.compile(
            _AGENT_ADDRESS + r"[^.\n]{0,120}" + _AGENT_IMPERATIVE,
            re.IGNORECASE,
        ),
    ),
    Rule(
        id=RULE_INSTRUCTION_OVERRIDE,
        level=VerdictLevel.QUARANTINE,
        description=(
            "Text tells the reader to ignore, replace, or bypass existing "
            "instructions."
        ),
        pattern=re.compile(
            r"\b(?:ignore|disregard|forget|override|bypass|drop)\b"
            r"[^.\n]{0,40}"
            r"\b(?:previous|prior|above|earlier|foregoing|system|developer|"
            r"original|initial)\b"
            r"[^.\n]{0,20}"
            r"\b(?:instructions?|prompts?|directions?|rules?|guidelines?|"
            r"messages?)\b",
            re.IGNORECASE,
        ),
    ),
    Rule(
        id=RULE_EXFILTRATION_REQUEST,
        level=VerdictLevel.QUARANTINE,
        description=(
            "Text directs a named data object to be sent, uploaded, or "
            "forwarded to an external URL."
        ),
        pattern=re.compile(
            r"\b(?:send|post|upload|forward|transmit|exfiltrate|leak)\s+"
            r"(?:the|all|any|this|these|your|my|our|their|it|them)\b"
            r"[^.\n]{0,80}"
            r"\bhttps?://[^\s)\]>\"']+",
            re.IGNORECASE,
        ),
    ),
    Rule(
        id=RULE_TOOL_INVOCATION_LURE,
        level=VerdictLevel.FLAGGED,
        description=(
            "Text directs the reader to call a named, listed, or substituted "
            "tool or function."
        ),
        pattern=re.compile(
            r"\b(?:call|invoke|run|execute|use)\s+(?:the\s+)?"
            r"(?:tool|function|command|api)\s+"
            r"(?:named|called|below|instead|following)\b",
            re.IGNORECASE,
        ),
    ),
    Rule(
        id=RULE_TOOL_RESULT_INJECTION,
        level=VerdictLevel.FLAGGED,
        description=(
            "Text describes a tool result instructing the assistant, or tells "
            "the assistant it must act."
        ),
        pattern=re.compile(
            r"(?:\b(?:tool|function)\s+(?:output|result|response)s?\b"
            r"[^.\n]{0,80}"
            r"\b(?:instruct|direct|tell|ask)s?\s+(?:the\s+)?"
            r"(?:assistant|agent|model|reader)\b"
            r"|\b(?:the\s+)?(?:assistant|agent|model)\s+"
            r"(?:must|should|shall)\s+(?:now\s+)?"
            r"(?:call|send|run|execute|read|open|forward|ignore|reveal)\b)",
            re.IGNORECASE,
        ),
    ),
    Rule(
        id=RULE_HIDDEN_UNICODE_TAGS,
        level=VerdictLevel.QUARANTINE,
        description="Text carries invisible Unicode tag characters (U+E0000-U+E007F).",
        pattern=re.compile(r"[\U000E0000-\U000E007F]"),
    ),
    Rule(
        id=RULE_BIDI_OVERRIDE,
        level=VerdictLevel.FLAGGED,
        description="Text carries a bidirectional override or isolate control.",
        pattern=re.compile(r"[\u202A-\u202E\u2066-\u2069]"),
    ),
    Rule(
        id=RULE_ENCODED_EXECUTION,
        level=VerdictLevel.FLAGGED,
        description=(
            "Text carries a decode-and-execute primitive or a base64 decode "
            "command."
        ),
        pattern=re.compile(
            r"\b(?:eval|exec|atob|fromCharCode|decodeURIComponent)\s*\("
            r"|\bbase64\s+(?:-d|--decode)\b",
            re.IGNORECASE,
        ),
    ),
    Rule(
        id=RULE_SYSTEM_PROMPT_EXFILTRATION,
        level=VerdictLevel.QUARANTINE,
        description=(
            "Text asks the reader to reveal or repeat its system, developer, "
            "or hidden instructions."
        ),
        pattern=re.compile(
            r"\b(?:reveal|print|show|output|repeat|display|leak)\b"
            r"[^.\n]{0,40}"
            r"\b(?:your|the)\s+(?:system|developer|hidden|initial|original)\s+"
            r"(?:prompt|instructions?|message)\b",
            re.IGNORECASE,
        ),
    ),
)
