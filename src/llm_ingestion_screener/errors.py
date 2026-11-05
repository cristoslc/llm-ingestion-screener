"""Fail-loud errors for the screening core.

Every exception here means a screen did not produce a trustworthy verdict. The
caller must treat it as an error, never as a clean result.
"""

from __future__ import annotations


class ScreenerError(Exception):
    """Base class for every screener error."""


class ValidationError(ScreenerError, ValueError):
    """A domain value violates one of its invariants."""


class DecisionModelError(ScreenerError):
    """The decision model could not be reached or returned an envelope error."""


class MalformedAnswerError(ScreenerError):
    """An answer is missing, truncated, or violates the typed-answer schema."""


class CassetteError(ScreenerError):
    """A recorded cassette is missing, malformed, or does not match the request."""


class ScreeningError(ScreenerError):
    """A screen cannot run, or its log cannot be written."""


class FaultInjectionError(ScreenerError):
    """A fault-injection request is invalid for the question set."""
