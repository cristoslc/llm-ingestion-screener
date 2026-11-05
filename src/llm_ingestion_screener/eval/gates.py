"""The committed gate registry: which metrics gate, and which only report."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from llm_ingestion_screener.domain import IngestionSurface
from llm_ingestion_screener.errors import EvaluationError
from llm_ingestion_screener.eval.fixtures import (
    BENIGN_THREAT_CLASSES,
    CORPUS_DIRECTORIES,
    MALICIOUS_THREAT_CLASSES,
)
from llm_ingestion_screener.eval.metrics import (
    METRIC_NAMES,
    Metric,
    MetricsReport,
)
from llm_ingestion_screener.eval.yamlutil import load_yaml_mapping

GATES_FORMAT = "llm-ingestion-screener/eval-gates/v1"
STATUSES = frozenset({"gated", "reported"})
BOOLEAN_GATES = frozenset(
    {"determinism", "malformed_answer_batch_failure", "corpus_coverage"}
)
COVERAGE_SECTIONS = frozenset({"directories", "surfaces", "threat_classes"})


@dataclass(frozen=True)
class GateRule:
    """One metric's registry entry."""

    name: str
    status: str
    operator: str | None = None
    threshold: float | None = None
    corpora: tuple[str, ...] = ()


@dataclass(frozen=True)
class GateRegistry:
    """The parsed registry, including the coverage floors."""

    rules: Mapping[str, GateRule]
    coverage_floors: Mapping[str, Mapping[str, int]]

    def rule(self, name: str) -> GateRule:
        return self.rules[name]

    @property
    def malicious_recall_corpora(self) -> tuple[str, ...]:
        rule = self.rules["malicious_recall"]
        return rule.corpora or ("golden", "eval")


@dataclass(frozen=True)
class GateResult:
    """The outcome of applying one registry entry to the current metrics."""

    metric: str
    status: str
    value: float | bool | None
    operator: str | None
    threshold: float | None
    passed: bool | None
    detail: str

    def to_dict(self) -> dict[str, object]:
        return {
            "metric": self.metric,
            "status": self.status,
            "value": self.value,
            "operator": self.operator,
            "threshold": self.threshold,
            "passed": self.passed,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class GateEvaluation:
    results: tuple[GateResult, ...]

    @property
    def failures(self) -> tuple[str, ...]:
        return tuple(
            result.metric
            for result in self.results
            if result.status == "gated" and result.passed is False
        )

    def to_dict(self) -> dict[str, object]:
        return {"results": [result.to_dict() for result in self.results]}


def load_gates(path: str | Path) -> GateRegistry:
    """Load and validate the committed gate registry."""

    raw = load_yaml_mapping(path, "gate registry")
    if raw.get("format") != GATES_FORMAT:
        raise EvaluationError(
            f"gate registry format must be {GATES_FORMAT!r}, got {raw.get('format')!r}"
        )
    metrics_raw = raw.get("metrics")
    if not isinstance(metrics_raw, Mapping):
        raise EvaluationError("gate registry requires a 'metrics' mapping")

    unknown = sorted(str(name) for name in set(metrics_raw) - set(METRIC_NAMES))
    if unknown:
        raise EvaluationError(
            f"gate registry names unknown metric(s): {', '.join(unknown)}"
        )
    missing = [name for name in METRIC_NAMES if name not in metrics_raw]
    if missing:
        raise EvaluationError(
            f"gate registry is missing metric(s): {', '.join(missing)}"
        )

    rules: dict[str, GateRule] = {}
    for name in METRIC_NAMES:
        entry = metrics_raw[name]
        if not isinstance(entry, Mapping):
            raise EvaluationError(f"gate registry entry {name!r} must be a mapping")
        unknown_keys = sorted(
            str(key) for key in set(entry) - {"status", "operator", "threshold", "corpora"}
        )
        if unknown_keys:
            raise EvaluationError(
                f"gate registry entry {name!r} has unknown key(s): "
                f"{', '.join(unknown_keys)}"
            )
        status = entry.get("status")
        if status not in STATUSES:
            raise EvaluationError(
                f"gate registry entry {name!r} status must be gated or reported, "
                f"got {status!r}"
            )
        if status == "reported":
            if "operator" in entry or "threshold" in entry:
                raise EvaluationError(
                    f"reported metric {name!r} must not carry an operator or threshold"
                )
            rules[name] = GateRule(name=name, status="reported")
            continue

        if name in BOOLEAN_GATES:
            if "operator" in entry or "threshold" in entry:
                raise EvaluationError(
                    f"boolean gate {name!r} must not carry an operator or threshold"
                )
            rules[name] = GateRule(name=name, status="gated")
            continue

        operator = entry.get("operator")
        if operator not in {">=", "<"}:
            raise EvaluationError(
                f"gated metric {name!r} operator must be '>=' or '<', "
                f"got {operator!r}"
            )
        threshold = entry.get("threshold")
        if (
            isinstance(threshold, bool)
            or not isinstance(threshold, (int, float))
            or not math.isfinite(float(threshold))
        ):
            raise EvaluationError(
                f"gated metric {name!r} requires a finite numeric threshold"
            )
        corpora: tuple[str, ...] = ()
        if "corpora" in entry:
            corpora = _corpora(entry["corpora"], name)
        rules[name] = GateRule(
            name=name,
            status="gated",
            operator=str(operator),
            threshold=float(threshold),
            corpora=corpora,
        )

    coverage_raw = raw.get("coverage")
    if not isinstance(coverage_raw, Mapping):
        raise EvaluationError("gate registry requires a 'coverage' mapping")
    unknown_sections = sorted(
        str(section) for section in set(coverage_raw) - COVERAGE_SECTIONS
    )
    if unknown_sections:
        raise EvaluationError(
            f"gate registry coverage has unknown section(s): "
            f"{', '.join(unknown_sections)}"
        )
    missing_sections = [
        section for section in COVERAGE_SECTIONS if section not in coverage_raw
    ]
    if missing_sections:
        raise EvaluationError(
            f"gate registry coverage is missing section(s): "
            f"{', '.join(missing_sections)}"
        )

    coverage_floors: dict[str, dict[str, int]] = {}
    for section in sorted(COVERAGE_SECTIONS):
        payload = coverage_raw[section]
        if not isinstance(payload, Mapping):
            raise EvaluationError(
                f"gate registry coverage section {section!r} must be a mapping"
            )
        allowed = _coverage_keys(section)
        floors: dict[str, int] = {}
        for key, value in payload.items():
            if key not in allowed:
                raise EvaluationError(
                    f"gate registry coverage section {section!r} names unknown "
                    f"key {key!r}"
                )
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise EvaluationError(
                    f"gate registry coverage floor {section}.{key} must be a "
                    "non-negative integer"
                )
            floors[str(key)] = value
        coverage_floors[section] = floors

    return GateRegistry(
        rules=rules,
        coverage_floors=coverage_floors,
    )


def _corpora(value: object, name: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or not value:
        raise EvaluationError(
            f"gated metric {name!r} corpora must be a non-empty list"
        )
    corpora = tuple(value)
    for corpus in corpora:
        if corpus not in CORPUS_DIRECTORIES:
            raise EvaluationError(
                f"gated metric {name!r} names unknown corpus {corpus!r}"
            )
    if len(set(corpora)) != len(corpora):
        raise EvaluationError(f"gated metric {name!r} repeats a corpus")
    return corpora


def _coverage_keys(section: str) -> frozenset[str]:
    if section == "directories":
        return frozenset(CORPUS_DIRECTORIES)
    if section == "surfaces":
        return frozenset(surface.value for surface in IngestionSurface)
    return frozenset(MALICIOUS_THREAT_CLASSES | BENIGN_THREAT_CLASSES | {"none"})


def evaluate_gates(
    registry: GateRegistry,
    report: MetricsReport,
) -> GateEvaluation:
    """Apply every registry entry. A gated metric that cannot be computed fails."""

    by_name = report.by_name()
    results: list[GateResult] = []
    for name in METRIC_NAMES:
        rule = registry.rule(name)
        metric = by_name[name]
        if rule.status == "reported":
            results.append(
                GateResult(
                    metric=name,
                    status="reported",
                    value=metric.value,
                    operator=None,
                    threshold=None,
                    passed=None,
                    detail=metric.detail,
                )
            )
            continue
        results.append(_apply_gated(rule, metric))
    return GateEvaluation(results=tuple(results))


def _apply_gated(rule: GateRule, metric: Metric) -> GateResult:
    if metric.status != "computed" or metric.value is None:
        return GateResult(
            metric=rule.name,
            status="gated",
            value=metric.value,
            operator=rule.operator,
            threshold=rule.threshold,
            passed=False,
            detail=(
                f"gated metric is not applicable: {metric.reason or metric.detail}"
            ),
        )

    if rule.name in BOOLEAN_GATES:
        passed = metric.value is True
        return GateResult(
            metric=rule.name,
            status="gated",
            value=metric.value,
            operator=None,
            threshold=None,
            passed=passed,
            detail=metric.detail,
        )

    if isinstance(metric.value, bool) or not isinstance(metric.value, (int, float)):
        raise EvaluationError(
            f"gated metric {rule.name!r} produced a non-numeric value "
            f"{metric.value!r}"
        )
    value = float(metric.value)
    if rule.operator == ">=":
        passed = value >= float(rule.threshold)
    elif rule.operator == "<":
        passed = value < float(rule.threshold)
    else:  # pragma: no cover - load_gates rejects this
        raise EvaluationError(
            f"gated metric {rule.name!r} has unsupported operator {rule.operator!r}"
        )
    return GateResult(
        metric=rule.name,
        status="gated",
        value=value,
        operator=rule.operator,
        threshold=rule.threshold,
        passed=passed,
        detail=(
            f"{value:.4f} {rule.operator} {float(rule.threshold):.4f}: "
            f"{'pass' if passed else 'fail'}"
        ),
    )
