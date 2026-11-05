"""The committed baseline and the regression comparison.

The baseline is the last accepted output. A run never writes it unless the
operator asks for it explicitly, and a corpus change is reported separately from
an output regression so the two are not confused.
"""

from __future__ import annotations

import json
import math
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from llm_ingestion_screener.errors import EvaluationError
from llm_ingestion_screener.eval.gates import BOOLEAN_GATES, GateRegistry
from llm_ingestion_screener.eval.metrics import METRIC_NAMES, MetricsReport
from llm_ingestion_screener.eval.runner import FixtureResult

BASELINE_FORMAT = "llm-ingestion-screener/eval-baseline/v1"


@dataclass(frozen=True)
class Baseline:
    corpus_fingerprint: str
    metrics: Mapping[str, Mapping[str, object]]
    fixtures: Mapping[str, Mapping[str, object]]


@dataclass(frozen=True)
class BaselineDiff:
    present: bool
    corpus_fingerprint_before: str | None
    corpus_fingerprint_after: str
    corpus_changed: bool
    added: tuple[str, ...]
    removed: tuple[str, ...]
    content_changed: tuple[str, ...]
    golden_output_regressions: tuple[Mapping[str, object], ...]
    gated_metric_regressions: tuple[Mapping[str, object], ...]
    metric_changes: tuple[Mapping[str, object], ...]
    notes: tuple[str, ...]

    @property
    def has_regressions(self) -> bool:
        return bool(
            self.golden_output_regressions or self.gated_metric_regressions
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "present": self.present,
            "corpus_fingerprint_before": self.corpus_fingerprint_before,
            "corpus_fingerprint_after": self.corpus_fingerprint_after,
            "corpus_changed": self.corpus_changed,
            "added": list(self.added),
            "removed": list(self.removed),
            "content_changed": list(self.content_changed),
            "golden_output_regressions": [
                dict(item) for item in self.golden_output_regressions
            ],
            "gated_metric_regressions": [
                dict(item) for item in self.gated_metric_regressions
            ],
            "metric_changes": [dict(item) for item in self.metric_changes],
            "notes": list(self.notes),
            "has_regressions": self.has_regressions,
        }


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    mapping: dict[str, object] = {}
    for key, value in pairs:
        if key in mapping:
            raise EvaluationError(f"duplicate JSON key {key!r} in baseline")
        mapping[key] = value
    return mapping


def load_baseline(
    path: str | Path,
    *,
    allow_missing: bool = False,
) -> Baseline | None:
    """Load the committed baseline. A missing file is an error unless allowed."""

    baseline_path = Path(path)
    if not baseline_path.exists():
        if allow_missing:
            return None
        raise EvaluationError(f"baseline does not exist: {baseline_path}")
    try:
        text = baseline_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise EvaluationError(f"could not read baseline {baseline_path}: {exc}") from exc
    try:
        raw = json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    except json.JSONDecodeError as exc:
        raise EvaluationError(
            f"baseline {baseline_path} is not valid JSON: {exc}"
        ) from exc
    if not isinstance(raw, Mapping):
        raise EvaluationError(f"baseline {baseline_path} must be a JSON object")
    if raw.get("format") != BASELINE_FORMAT:
        raise EvaluationError(
            f"baseline format must be {BASELINE_FORMAT!r}, got {raw.get('format')!r}"
        )
    fingerprint = raw.get("corpus_fingerprint")
    if not isinstance(fingerprint, str) or len(fingerprint) != 64:
        raise EvaluationError("baseline requires a SHA-256 corpus fingerprint")
    metrics = raw.get("metrics")
    if not isinstance(metrics, Mapping):
        raise EvaluationError("baseline requires a metrics mapping")
    for name in METRIC_NAMES:
        entry = metrics.get(name)
        if not isinstance(entry, Mapping):
            raise EvaluationError(f"baseline is missing metric {name!r}")
        if entry.get("status") not in {"computed", "not-applicable"}:
            raise EvaluationError(
                f"baseline metric {name!r} has an unknown status"
            )
    fixtures = raw.get("fixtures")
    if not isinstance(fixtures, Mapping):
        raise EvaluationError("baseline requires a fixtures mapping")
    for fixture_id, entry in fixtures.items():
        if not isinstance(fixture_id, str) or not fixture_id:
            raise EvaluationError("baseline fixture ids must be non-empty strings")
        if not isinstance(entry, Mapping):
            raise EvaluationError(
                f"baseline fixture {fixture_id!r} must be a mapping"
            )
        for field in ("corpus", "content_sha256", "verdict"):
            if not isinstance(entry.get(field), str):
                raise EvaluationError(
                    f"baseline fixture {fixture_id!r} requires string field {field!r}"
                )
        rules = entry.get("rule_ids")
        if not isinstance(rules, list) or not all(
            isinstance(rule, str) for rule in rules
        ):
            raise EvaluationError(
                f"baseline fixture {fixture_id!r} requires a rule_ids list"
            )
    return Baseline(
        corpus_fingerprint=fingerprint,
        metrics=metrics,
        fixtures=fixtures,
    )


def build_baseline(
    report: MetricsReport,
    results: Sequence[FixtureResult],
    corpus_fingerprint: str,
) -> dict[str, object]:
    return {
        "format": BASELINE_FORMAT,
        "corpus_fingerprint": corpus_fingerprint,
        "metrics": {
            metric.name: {"status": metric.status, "value": metric.value}
            for metric in report.metrics
        },
        "fixtures": {
            result.fixture_id: {
                "corpus": result.corpus,
                "content_sha256": result.content_sha256,
                "verdict": result.verdict,
                "rule_ids": list(result.rule_ids),
            }
            for result in results
        },
    }


def write_baseline(path: str | Path, payload: Mapping[str, object]) -> None:
    """Write the baseline deliberately. Never called by an ordinary run."""

    baseline_path = Path(path)
    temporary = baseline_path.with_suffix(baseline_path.suffix + ".tmp")
    try:
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, baseline_path)
    except OSError as exc:
        raise EvaluationError(
            f"could not write baseline {baseline_path}: {exc}"
        ) from exc


def compare_baseline(
    baseline: Baseline | None,
    report: MetricsReport,
    results: Sequence[FixtureResult],
    registry: GateRegistry,
    corpus_fingerprint: str,
) -> BaselineDiff:
    """Compare current output with the accepted baseline."""

    if baseline is None:
        return BaselineDiff(
            present=False,
            corpus_fingerprint_before=None,
            corpus_fingerprint_after=corpus_fingerprint,
            corpus_changed=True,
            added=tuple(sorted(result.fixture_id for result in results)),
            removed=(),
            content_changed=(),
            golden_output_regressions=(),
            gated_metric_regressions=(),
            metric_changes=(),
            notes=("No baseline was present; this run establishes the first one.",),
        )

    current_by_id = {result.fixture_id: result for result in results}
    baseline_ids = set(baseline.fixtures)
    current_ids = set(current_by_id)
    added = tuple(sorted(current_ids - baseline_ids))
    removed = tuple(sorted(baseline_ids - current_ids))
    content_changed = tuple(
        sorted(
            fixture_id
            for fixture_id in current_ids & baseline_ids
            if baseline.fixtures[fixture_id]["content_sha256"]
            != current_by_id[fixture_id].content_sha256
        )
    )
    corpus_changed = baseline.corpus_fingerprint != corpus_fingerprint

    golden_regressions: list[Mapping[str, object]] = []
    for fixture_id in sorted(current_ids & baseline_ids):
        if fixture_id in content_changed:
            continue
        current = current_by_id[fixture_id]
        if current.corpus != "golden":
            continue
        previous = baseline.fixtures[fixture_id]
        if (
            previous["verdict"] != current.verdict
            or tuple(previous["rule_ids"]) != current.rule_ids
        ):
            golden_regressions.append(
                {
                    "fixture_id": fixture_id,
                    "baseline_verdict": previous["verdict"],
                    "current_verdict": current.verdict,
                    "baseline_rule_ids": list(previous["rule_ids"]),
                    "current_rule_ids": list(current.rule_ids),
                }
            )

    current_by_metric = report.by_name()
    metric_changes: list[Mapping[str, object]] = []
    gated_regressions: list[Mapping[str, object]] = []
    for name in METRIC_NAMES:
        before = baseline.metrics[name].get("value")
        after_metric = current_by_metric[name]
        after = after_metric.value
        if not _same_value(before, after):
            change = {
                "metric": name,
                "baseline": before,
                "current": after,
                "corpus_changed": corpus_changed,
            }
            metric_changes.append(change)
            rule = registry.rule(name)
            if rule.status != "gated" or corpus_changed:
                continue
            if _is_regression(name, rule.operator, before, after):
                gated_regressions.append(
                    {
                        "metric": name,
                        "baseline": before,
                        "current": after,
                        "operator": rule.operator,
                        "threshold": rule.threshold,
                    }
                )

    notes: list[str] = []
    if corpus_changed:
        notes.append(
            "The corpus fingerprint changed. Metric deltas are corpus changes, "
            "not regressions; the gates still apply to this run."
        )
    if added or removed or content_changed:
        notes.append(
            "Fixture set changed: "
            f"{len(added)} added, {len(removed)} removed, "
            f"{len(content_changed)} with changed content."
        )
    if not notes:
        notes.append("The corpus fingerprint is unchanged.")

    return BaselineDiff(
        present=True,
        corpus_fingerprint_before=baseline.corpus_fingerprint,
        corpus_fingerprint_after=corpus_fingerprint,
        corpus_changed=corpus_changed,
        added=added,
        removed=removed,
        content_changed=content_changed,
        golden_output_regressions=tuple(golden_regressions),
        gated_metric_regressions=tuple(gated_regressions),
        metric_changes=tuple(metric_changes),
        notes=tuple(notes),
    )


def _same_value(before: object, after: object) -> bool:
    if isinstance(before, bool) or isinstance(after, bool):
        return before is after
    if isinstance(before, (int, float)) and isinstance(after, (int, float)):
        return math.isclose(float(before), float(after), rel_tol=0.0, abs_tol=0.0)
    return before == after


def _is_regression(
    name: str,
    operator: str | None,
    before: object,
    after: object,
) -> bool:
    if name in BOOLEAN_GATES:
        return before is True and after is not True
    if (
        isinstance(before, bool)
        or isinstance(after, bool)
        or not isinstance(before, (int, float))
        or not isinstance(after, (int, float))
    ):
        return False
    baseline_value = float(before)
    current_value = float(after)
    if operator == ">=":
        return current_value < baseline_value
    if operator == "<":
        return current_value > baseline_value
    return False
