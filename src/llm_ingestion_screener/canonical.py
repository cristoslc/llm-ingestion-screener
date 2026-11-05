"""Canonical JSON used for cassette keys and byte-deterministic records."""

from __future__ import annotations

import json


def canonical_json(value: object) -> str:
    """Return a stable JSON encoding, or raise on values JSON cannot carry."""

    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
