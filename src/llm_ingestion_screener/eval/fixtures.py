"""Load and validate the committed evaluation fixture corpus.

The corpus is the durable product: every fixture is a sanitised, provenance-
tagged sample with a truth label. This module is the only place that reads the
truth label into the harness, and it hands the runner a fixture whose content
is kept separate from that label.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from llm_ingestion_screener.canonical import canonical_json
from llm_ingestion_screener.domain import IngestionSurface, VerdictLevel
from llm_ingestion_screener.errors import EvaluationError
from llm_ingestion_screener.eval.yamlutil import load_yaml_mapping
from llm_ingestion_screener.rules import DEFAULT_RULE_IDS

CORPUS_DIRECTORIES: tuple[str, ...] = (
    "golden",
    "eval",
    "frontier",
    "benign",
    "transforms",
)

FIXTURE_FIELDS: frozenset[str] = frozenset(
    {
        "id",
        "title",
        "surface",
        "label",
        "expect_min_verdict",
        "threat_class",
        "source",
        "provenance",
        "intent",
        "content",
        "expect_any_rule",
        "derived_from",
        "transform",
        "notes",
    }
)

REQUIRED_FIELDS: tuple[str, ...] = (
    "id",
    "title",
    "surface",
    "label",
    "expect_min_verdict",
    "threat_class",
    "source",
    "intent",
    "content",
)

SOURCES: frozenset[str] = frozenset(
    {
        "synthetic",
        "synthetic-adversarial",
        "real-sanitized",
        "benign-popular",
        "benchmark-derived",
    }
)

SOURCES_REQUIRING_PROVENANCE: frozenset[str] = frozenset(
    {"real-sanitized", "benchmark-derived"}
)

MALICIOUS_THREAT_CLASSES: frozenset[str] = frozenset(
    {
        "agent-directed-imperative",
        "instruction-override",
        "tool-result-injection",
        "exfiltration-request",
        "tool-invocation-lure",
        "task-irrelevant-injection",
        "encoded-obfuscated",
        "non-english",
    }
)

BENIGN_THREAT_CLASSES: frozenset[str] = frozenset(
    {
        "benign-imperative-vocabulary",
        "benign-serialization-markup",
        "benign-legitimate-tool-output",
        "benign-quoted-instruction",
    }
)

_KEBAB_CASE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_URL = re.compile(r"\b(?:https?|ftp)://[^\s)\]>\"']+", re.IGNORECASE)
_IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_EXFILTRATION_OR_C2_TERMS = re.compile(
    r"\b(?:send|post|upload|forward|transmit|exfiltrate|leak|beacon|"
    r"collect|deliver|fetch|callback|drop|c2|command-and-control)\b",
    re.IGNORECASE,
)
_EXAMPLE_HOST_SUFFIX = ".example.invalid"


@dataclass(frozen=True)
class Fixture:
    """One validated fixture. ``label`` is truth and never reaches the screen."""

    id: str
    title: str
    surface: IngestionSurface
    label: str  # "benign" or "malicious"
    expect_min_verdict: VerdictLevel
    threat_class: str
    source: str
    intent: str
    content: str
    corpus: str
    path: Path
    provenance: str | None = None
    expect_any_rule: tuple[str, ...] = ()
    derived_from: str | None = None
    transform: str | None = None
    notes: str | None = None

    @property
    def is_malicious(self) -> bool:
        return self.label == "malicious"

    @property
    def content_sha256(self) -> str:
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()

    def to_index(self) -> dict[str, object]:
        """The stable identity used in the corpus fingerprint."""

        return {
            "id": self.id,
            "corpus": self.corpus,
            "surface": self.surface.value,
            "label": self.label,
            "expect_min_verdict": self.expect_min_verdict.label,
            "threat_class": self.threat_class,
            "source": self.source,
            "provenance": self.provenance,
            "content_sha256": self.content_sha256,
            "expect_any_rule": list(self.expect_any_rule),
            "derived_from": self.derived_from,
            "transform": self.transform,
        }


@dataclass(frozen=True)
class Corpus:
    """Every fixture under one corpus root, in stable path order."""

    root: Path
    fixtures: tuple[Fixture, ...]

    @property
    def by_id(self) -> dict[str, Fixture]:
        return {fixture.id: fixture for fixture in self.fixtures}

    @property
    def fingerprint(self) -> str:
        payload = [fixture.to_index() for fixture in self.fixtures]
        digest = hashlib.sha256(
            canonical_json(payload).encode("utf-8")
        ).hexdigest()
        return digest


def load_corpus(root: str | Path) -> Corpus:
    """Load every fixture under ``root`` or raise :class:`EvaluationError`."""

    corpus_root = Path(root)
    if not corpus_root.exists():
        raise EvaluationError(f"corpus root does not exist: {corpus_root}")
    if not corpus_root.is_dir():
        raise EvaluationError(f"corpus root is not a directory: {corpus_root}")

    loaded: list[Fixture] = []
    for directory in CORPUS_DIRECTORIES:
        corpus_dir = corpus_root / directory
        if not corpus_dir.is_dir():
            raise EvaluationError(
                f"corpus directory {directory!r} is missing at {corpus_dir}"
            )
        paths = sorted(
            path for path in corpus_dir.rglob("*.yaml") if path.is_file()
        )
        if not paths:
            raise EvaluationError(
                f"corpus directory {directory!r} is empty at {corpus_dir}"
            )
        for path in paths:
            loaded.append(_load_fixture(path, directory))

    by_id: dict[str, Fixture] = {}
    for fixture in loaded:
        if fixture.id in by_id:
            other = by_id[fixture.id]
            raise EvaluationError(
                f"duplicate fixture id {fixture.id!r} in "
                f"{other.path} and {fixture.path}"
            )
        by_id[fixture.id] = fixture

    _validate_derivations(by_id)
    return Corpus(root=corpus_root, fixtures=tuple(loaded))


def _load_fixture(path: Path, corpus: str) -> Fixture:
    raw = load_yaml_mapping(path, "fixture")
    return _validate_fixture(raw, path, corpus)


def _validate_fixture(
    raw: Mapping[object, object],
    path: Path,
    corpus: str,
) -> Fixture:
    unknown = sorted(str(key) for key in set(raw) - FIXTURE_FIELDS)
    if unknown:
        raise EvaluationError(
            f"fixture {path} has unknown field(s): {', '.join(unknown)}"
        )
    missing = [field for field in REQUIRED_FIELDS if field not in raw]
    if missing:
        raise EvaluationError(
            f"fixture {path} is missing required field(s): {', '.join(missing)}"
        )

    fixture_id = _required_string(raw, "id", path)
    if not _KEBAB_CASE.match(fixture_id):
        raise EvaluationError(
            f"fixture {path} id {fixture_id!r} must be kebab-case"
        )
    title = _required_string(raw, "title", path)
    surface = _surface(raw["surface"], path)
    label = _label(raw["label"], path)
    expect_min_verdict = _verdict(raw["expect_min_verdict"], path)
    threat_class = _required_string(raw, "threat_class", path)
    source = _source(raw["source"], path)
    intent = _required_string(raw, "intent", path)
    content = _required_string(raw, "content", path)

    provenance = _optional_string(raw, "provenance", path)
    if source in SOURCES_REQUIRING_PROVENANCE and not provenance:
        raise EvaluationError(
            f"fixture {path} source {source!r} requires provenance"
        )

    if label == "benign":
        if expect_min_verdict is not VerdictLevel.CLEAN:
            raise EvaluationError(
                f"fixture {path} is benign but expects verdict "
                f"{expect_min_verdict.label!r}; benign fixtures must expect clean"
            )
        if threat_class != "none" and threat_class not in BENIGN_THREAT_CLASSES:
            raise EvaluationError(
                f"fixture {path} benign threat_class {threat_class!r} is not "
                "a benign class or 'none'"
            )
    else:
        if expect_min_verdict is VerdictLevel.CLEAN:
            raise EvaluationError(
                f"fixture {path} is malicious but expects a clean verdict"
            )
        if threat_class not in MALICIOUS_THREAT_CLASSES:
            raise EvaluationError(
                f"fixture {path} malicious threat_class {threat_class!r} is not "
                "in the malicious taxonomy"
            )

    expect_any_rule = _rule_ids(raw.get("expect_any_rule"), path)
    derived_from = _optional_string(raw, "derived_from", path)
    transform = _optional_string(raw, "transform", path)
    notes = _optional_string(raw, "notes", path)

    if corpus == "transforms":
        if not derived_from or not transform:
            raise EvaluationError(
                f"fixture {path} under transforms/ requires both derived_from "
                "and transform"
            )
    else:
        if derived_from is not None or transform is not None:
            raise EvaluationError(
                f"fixture {path} carries derived_from or transform outside "
                "the transforms/ corpus"
            )

    _assert_no_live_hosts(content, path)

    return Fixture(
        id=fixture_id,
        title=title,
        surface=surface,
        label=label,
        expect_min_verdict=expect_min_verdict,
        threat_class=threat_class,
        source=source,
        intent=intent,
        content=content,
        corpus=corpus,
        path=path,
        provenance=provenance,
        expect_any_rule=expect_any_rule,
        derived_from=derived_from,
        transform=transform,
        notes=notes,
    )


def _validate_derivations(by_id: Mapping[str, Fixture]) -> None:
    for fixture in by_id.values():
        if fixture.derived_from is None:
            continue
        base = by_id.get(fixture.derived_from)
        if base is None:
            raise EvaluationError(
                f"fixture {fixture.id!r} derives from unknown fixture "
                f"{fixture.derived_from!r}"
            )
        if not base.is_malicious:
            raise EvaluationError(
                f"fixture {fixture.id!r} derives from benign fixture "
                f"{base.id!r}"
            )
        if fixture.threat_class != base.threat_class:
            raise EvaluationError(
                f"fixture {fixture.id!r} threat_class {fixture.threat_class!r} "
                f"differs from its base {base.id!r} "
                f"({base.threat_class!r})"
            )


def _assert_no_live_hosts(content: str, path: Path) -> None:
    for match in _URL.finditer(content):
        url = match.group(0).rstrip(".,;")
        host = _host_of(url)
        if host is None:
            continue
        context = content[
            max(0, match.start() - 160): min(len(content), match.end() + 160)
        ]
        if not _EXFILTRATION_OR_C2_TERMS.search(context):
            continue
        if _is_reserved_host(host):
            continue
        raise EvaluationError(
            f"fixture {path} carries a non-example.invalid host {host!r} in an "
            "exfiltration or command-and-control position"
        )
    for match in _IPV4.finditer(content):
        context = content[
            max(0, match.start() - 160): min(len(content), match.end() + 160)
        ]
        if _EXFILTRATION_OR_C2_TERMS.search(context):
            raise EvaluationError(
                f"fixture {path} carries a live IP address {match.group(0)!r} "
                "in an exfiltration or command-and-control position"
            )


def _host_of(url: str) -> str | None:
    from urllib.parse import urlparse

    parsed = urlparse(url)
    host = parsed.hostname
    if not host:
        return None
    return host.lower()


def _is_reserved_host(host: str) -> bool:
    return host == "example.invalid" or host.endswith(_EXAMPLE_HOST_SUFFIX)


def _required_string(
    raw: Mapping[object, object],
    field: str,
    path: Path,
) -> str:
    value = raw.get(field)
    if not isinstance(value, str) or not value.strip():
        raise EvaluationError(
            f"fixture {path} field {field!r} must be a non-empty string"
        )
    return value


def _optional_string(
    raw: Mapping[object, object],
    field: str,
    path: Path,
) -> str | None:
    if field not in raw or raw[field] is None:
        return None
    value = raw[field]
    if not isinstance(value, str) or not value.strip():
        raise EvaluationError(
            f"fixture {path} field {field!r} must be a non-empty string when set"
        )
    return value


def _surface(value: object, path: Path) -> IngestionSurface:
    if not isinstance(value, str):
        raise EvaluationError(f"fixture {path} surface must be a string")
    try:
        return IngestionSurface(value)
    except ValueError as exc:
        raise EvaluationError(
            f"fixture {path} has unknown surface {value!r}"
        ) from exc


def _label(value: object, path: Path) -> str:
    if value not in {"benign", "malicious"}:
        raise EvaluationError(
            f"fixture {path} label must be 'benign' or 'malicious', got {value!r}"
        )
    return str(value)


def _verdict(value: object, path: Path) -> VerdictLevel:
    if not isinstance(value, str) or value not in {
        level.label for level in VerdictLevel
    }:
        raise EvaluationError(
            f"fixture {path} expect_min_verdict must be clean, flagged, or "
            f"quarantine, got {value!r}"
        )
    return VerdictLevel[value.upper()]


def _source(value: object, path: Path) -> str:
    if not isinstance(value, str) or value not in SOURCES:
        raise EvaluationError(
            f"fixture {path} source must be one of "
            f"{', '.join(sorted(SOURCES))}, got {value!r}"
        )
    return value


def _rule_ids(value: object, path: Path) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise EvaluationError(
            f"fixture {path} expect_any_rule must be a list of rule ids"
        )
    rules: list[str] = []
    for item in value:
        if not isinstance(item, str) or item not in DEFAULT_RULE_IDS:
            raise EvaluationError(
                f"fixture {path} expect_any_rule carries unknown rule id "
                f"{item!r}"
            )
        rules.append(item)
    return tuple(rules)
