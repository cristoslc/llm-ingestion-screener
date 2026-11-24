"""Load and cross-check the committed corpus manifest.

The manifest is the offline audit trail for the corpus. It records, for every
committed fixture, the upstream repository, the pinned commit, the upstream
sample id, the threat class, and the sanitisation applied. A fixture with no
manifest row, a row with no fixture, or a benchmark-derived fixture without a
pinned commit is an error, never a warning.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from llm_ingestion_screener.domain import IngestionSurface
from llm_ingestion_screener.errors import EvaluationError
from llm_ingestion_screener.eval.fixtures import (
    BENIGN_THREAT_CLASSES,
    CORPUS_DIRECTORIES,
    MALICIOUS_THREAT_CLASSES,
    SOURCES,
    SOURCES_REQUIRING_PROVENANCE,
    TRANSFORM_NAMES,
)
from llm_ingestion_screener.eval.yamlutil import load_yaml_mapping

if TYPE_CHECKING:  # pragma: no cover - typing only
    from llm_ingestion_screener.eval.fixtures import Fixture

MANIFEST_NAME = "manifest.yaml"
MANIFEST_FORMAT = "llm-ingestion-screener/corpus-manifest/v2"
COMMIT_HEX = re.compile(r"^[0-9a-f]{40}$")
ENTRY_FIELDS = frozenset(
    {
        "id",
        "path",
        "corpus",
        "surface",
        "label",
        "threat_class",
        "source",
        "upstream",
        "derived_from",
        "transform",
        "sanitisation",
    }
)
UPSTREAM_FIELDS = frozenset({"repository", "commit", "sample_id"})
UNKNOWN = "none"


@dataclass(frozen=True)
class ManifestEntry:
    """One fixture's audit record."""

    id: str
    path: str
    corpus: str
    surface: str
    label: str
    threat_class: str
    source: str
    upstream_repository: str
    upstream_commit: str
    upstream_sample_id: str
    sanitisation: tuple[str, ...]
    derived_from: str | None = None
    transform: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "path": self.path,
            "corpus": self.corpus,
            "surface": self.surface,
            "label": self.label,
            "threat_class": self.threat_class,
            "source": self.source,
            "upstream": {
                "repository": self.upstream_repository,
                "commit": self.upstream_commit,
                "sample_id": self.upstream_sample_id,
            },
            "derived_from": self.derived_from,
            "transform": self.transform,
            "sanitisation": list(self.sanitisation),
        }


@dataclass(frozen=True)
class Exclusion:
    """An upstream task or dataset deliberately left out of the corpus."""

    upstream: str
    tasks: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class CorpusManifest:
    """The parsed manifest, keyed by fixture id."""

    pins: Mapping[str, str]
    entries: Mapping[str, ManifestEntry]
    exclusions: tuple[Exclusion, ...] = ()


def load_manifest(path: str | Path) -> CorpusManifest:
    """Read and validate one manifest file."""

    manifest_path = Path(path)
    raw = load_yaml_mapping(manifest_path, "corpus manifest")
    if raw.get("format") != MANIFEST_FORMAT:
        raise EvaluationError(
            f"corpus manifest format must be {MANIFEST_FORMAT!r}, "
            f"got {raw.get('format')!r}"
        )

    pins_raw = raw.get("pins")
    if not isinstance(pins_raw, Mapping) or not pins_raw:
        raise EvaluationError("corpus manifest requires a non-empty 'pins' mapping")
    pins: dict[str, str] = {}
    for repository, commit in pins_raw.items():
        if not isinstance(repository, str) or not repository.strip():
            raise EvaluationError("corpus manifest pin names must be non-empty")
        if not isinstance(commit, str) or not COMMIT_HEX.match(commit):
            raise EvaluationError(
                f"corpus manifest pin {repository!r} must be a full commit SHA"
            )
        pins[repository] = commit

    fixtures_raw = raw.get("fixtures")
    if not isinstance(fixtures_raw, list) or not fixtures_raw:
        raise EvaluationError("corpus manifest requires a non-empty 'fixtures' list")

    entries: dict[str, ManifestEntry] = {}
    paths: set[str] = set()
    for index, item in enumerate(fixtures_raw):
        if not isinstance(item, Mapping):
            raise EvaluationError(
                f"corpus manifest fixture {index} must be a mapping"
            )
        unknown = sorted(str(key) for key in set(item) - ENTRY_FIELDS)
        if unknown:
            raise EvaluationError(
                f"corpus manifest fixture {index} has unknown field(s): "
                f"{', '.join(unknown)}"
            )
        missing = [field for field in ENTRY_FIELDS if field not in item]
        if missing:
            raise EvaluationError(
                f"corpus manifest fixture {index} is missing field(s): "
                f"{', '.join(sorted(missing))}"
            )
        entry = _entry(item, pins, manifest_path, index)
        if entry.id in entries:
            raise EvaluationError(
                f"corpus manifest repeats fixture id {entry.id!r}"
            )
        if entry.path in paths:
            raise EvaluationError(
                f"corpus manifest repeats fixture path {entry.path!r}"
            )
        entries[entry.id] = entry
        paths.add(entry.path)

    exclusions = _exclusions(raw.get("exclusions", []), manifest_path)
    return CorpusManifest(pins=pins, entries=entries, exclusions=exclusions)


def _exclusions(value: object, manifest_path: Path) -> tuple[Exclusion, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise EvaluationError(
            f"corpus manifest {manifest_path} exclusions must be a list"
        )
    allowed = {"upstream", "tasks", "reason"}
    exclusions: list[Exclusion] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise EvaluationError(
                f"corpus manifest exclusion {index} must be a mapping"
            )
        unknown = sorted(str(key) for key in set(item) - allowed)
        if unknown:
            raise EvaluationError(
                f"corpus manifest exclusion {index} has unknown field(s): "
                f"{', '.join(unknown)}"
            )
        upstream = item.get("upstream")
        tasks = item.get("tasks")
        reason = item.get("reason")
        if not isinstance(upstream, str) or not upstream.strip():
            raise EvaluationError(
                f"corpus manifest exclusion {index} requires an upstream"
            )
        if not isinstance(tasks, list) or not tasks or not all(
            isinstance(task, str) and task.strip() for task in tasks
        ):
            raise EvaluationError(
                f"corpus manifest exclusion {index} requires a non-empty tasks list"
            )
        if not isinstance(reason, str) or not reason.strip():
            raise EvaluationError(
                f"corpus manifest exclusion {index} requires a reason"
            )
        exclusions.append(
            Exclusion(upstream=upstream, tasks=tuple(tasks), reason=reason)
        )
    return tuple(exclusions)


def _optional_nullable(
    item: Mapping[object, object],
    field: str,
    fixture_id: str,
) -> str | None:
    value = item.get(field)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise EvaluationError(
            f"corpus manifest fixture {fixture_id!r} field {field!r} must be "
            "a non-empty string or null"
        )
    return value


def _entry(
    item: Mapping[object, object],
    pins: Mapping[str, str],
    manifest_path: Path,
    index: int,
) -> ManifestEntry:
    def string(field: str) -> str:
        value = item.get(field)
        if not isinstance(value, str) or not value.strip():
            raise EvaluationError(
                f"corpus manifest fixture {index} field {field!r} must be a "
                "non-empty string"
            )
        return value

    fixture_id = string("id")
    path = string("path")
    corpus = string("corpus")
    surface = string("surface")
    label = string("label")
    threat_class = string("threat_class")
    source = string("source")

    if corpus not in CORPUS_DIRECTORIES:
        raise EvaluationError(
            f"corpus manifest fixture {fixture_id!r} names unknown corpus "
            f"{corpus!r}"
        )
    try:
        IngestionSurface(surface)
    except ValueError as exc:
        raise EvaluationError(
            f"corpus manifest fixture {fixture_id!r} names unknown surface "
            f"{surface!r}"
        ) from exc
    if label not in {"benign", "malicious"}:
        raise EvaluationError(
            f"corpus manifest fixture {fixture_id!r} has unknown label {label!r}"
        )
    if source not in SOURCES:
        raise EvaluationError(
            f"corpus manifest fixture {fixture_id!r} has unknown source {source!r}"
        )
    if threat_class != UNKNOWN and threat_class not in (
        MALICIOUS_THREAT_CLASSES | BENIGN_THREAT_CLASSES
    ):
        raise EvaluationError(
            f"corpus manifest fixture {fixture_id!r} has unknown threat class "
            f"{threat_class!r}"
        )
    if Path(path).is_absolute() or ".." in Path(path).parts:
        raise EvaluationError(
            f"corpus manifest fixture {fixture_id!r} path must be relative to "
            "the corpus root"
        )
    if not path.startswith(f"{corpus}/"):
        raise EvaluationError(
            f"corpus manifest fixture {fixture_id!r} path {path!r} is outside "
            f"the {corpus!r} corpus"
        )

    upstream_raw = item.get("upstream")
    if not isinstance(upstream_raw, Mapping):
        raise EvaluationError(
            f"corpus manifest fixture {fixture_id!r} requires an 'upstream' mapping"
        )
    unknown = sorted(str(key) for key in set(upstream_raw) - UPSTREAM_FIELDS)
    if unknown:
        raise EvaluationError(
            f"corpus manifest fixture {fixture_id!r} upstream has unknown "
            f"field(s): {', '.join(unknown)}"
        )
    missing = [field for field in UPSTREAM_FIELDS if field not in upstream_raw]
    if missing:
        raise EvaluationError(
            f"corpus manifest fixture {fixture_id!r} upstream is missing "
            f"field(s): {', '.join(sorted(missing))}"
        )
    repository = upstream_raw.get("repository")
    commit = upstream_raw.get("commit")
    sample_id = upstream_raw.get("sample_id")
    for field, value in (
        ("repository", repository),
        ("commit", commit),
        ("sample_id", sample_id),
    ):
        if not isinstance(value, str) or not value.strip():
            raise EvaluationError(
                f"corpus manifest fixture {fixture_id!r} upstream {field!r} "
                "must be a non-empty string"
            )
    if repository == UNKNOWN:
        if commit != UNKNOWN:
            raise EvaluationError(
                f"corpus manifest fixture {fixture_id!r} has no upstream "
                "repository but a commit"
            )
    else:
        if repository not in pins:
            raise EvaluationError(
                f"corpus manifest fixture {fixture_id!r} names unpinned "
                f"repository {repository!r}"
            )
        if commit != pins[repository]:
            raise EvaluationError(
                f"corpus manifest fixture {fixture_id!r} commit {commit!r} "
                f"does not match the pin for {repository!r}"
            )

    sanitisation_raw = item.get("sanitisation")
    if not isinstance(sanitisation_raw, list) or not sanitisation_raw:
        raise EvaluationError(
            f"corpus manifest fixture {fixture_id!r} requires a non-empty "
            "'sanitisation' list"
        )
    derived_from = _optional_nullable(item, "derived_from", fixture_id)
    transform = _optional_nullable(item, "transform", fixture_id)
    if corpus == "transforms":
        if not derived_from or not transform:
            raise EvaluationError(
                f"corpus manifest fixture {fixture_id!r} under transforms/ "
                "requires both derived_from and transform"
            )
        if transform not in TRANSFORM_NAMES:
            raise EvaluationError(
                f"corpus manifest fixture {fixture_id!r} names unknown "
                f"transform {transform!r}"
            )
    elif derived_from is not None or transform is not None:
        raise EvaluationError(
            f"corpus manifest fixture {fixture_id!r} carries derived_from or "
            "transform outside the transforms/ corpus"
        )

    sanitisation: list[str] = []
    for step in sanitisation_raw:
        if not isinstance(step, str) or not step.strip():
            raise EvaluationError(
                f"corpus manifest fixture {fixture_id!r} sanitisation steps "
                "must be non-empty strings"
            )
        sanitisation.append(step)

    return ManifestEntry(
        id=fixture_id,
        path=path,
        corpus=corpus,
        surface=surface,
        label=label,
        threat_class=threat_class,
        source=source,
        upstream_repository=repository,
        upstream_commit=commit,
        upstream_sample_id=sample_id,
        sanitisation=tuple(sanitisation),
        derived_from=derived_from,
        transform=transform,
    )


def validate_manifest(
    corpus_root: str | Path,
    fixtures: Sequence[Fixture],
    manifest: CorpusManifest,
) -> None:
    """Cross-check the manifest against the loaded fixtures."""

    root = Path(corpus_root)
    by_id = {fixture.id: fixture for fixture in fixtures}
    missing = sorted(set(by_id) - set(manifest.entries))
    if missing:
        raise EvaluationError(
            "corpus manifest does not cover fixture(s): " + ", ".join(missing)
        )
    extra = sorted(set(manifest.entries) - set(by_id))
    if extra:
        raise EvaluationError(
            "corpus manifest names fixture(s) that do not exist: "
            + ", ".join(extra)
        )

    for fixture_id, entry in manifest.entries.items():
        fixture = by_id[fixture_id]
        relative = fixture.path.relative_to(root).as_posix()
        if entry.path != relative:
            raise EvaluationError(
                f"corpus manifest fixture {fixture_id!r} path {entry.path!r} "
                f"does not match {relative!r}"
            )
        for field, expected in (
            ("corpus", fixture.corpus),
            ("surface", fixture.surface.value),
            ("label", fixture.label),
            ("threat_class", fixture.threat_class),
            ("source", fixture.source),
            ("derived_from", fixture.derived_from),
            ("transform", fixture.transform),
        ):
            actual = getattr(entry, field)
            if actual != expected:
                raise EvaluationError(
                    f"corpus manifest fixture {fixture_id!r} {field} "
                    f"{actual!r} does not match fixture {expected!r}"
                )
        if fixture.source in SOURCES_REQUIRING_PROVENANCE:
            if entry.upstream_repository == UNKNOWN:
                raise EvaluationError(
                    f"corpus manifest fixture {fixture_id!r} is "
                    f"{fixture.source!r} but names no upstream repository"
                )
            if entry.upstream_commit not in manifest.pins.values():
                raise EvaluationError(
                    f"corpus manifest fixture {fixture_id!r} commit is not a pin"
                )
            if fixture.provenance is None or (
                entry.upstream_commit not in fixture.provenance
                and entry.upstream_commit[:12] not in fixture.provenance
            ):
                raise EvaluationError(
                    f"corpus manifest fixture {fixture_id!r} provenance does not "
                    "name its pinned commit"
                )
