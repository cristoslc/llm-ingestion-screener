"""Hand-rolled evaluation metrics over fixture results.

Every metric in the plan's table is either computed here or returned with an
explicit not-applicable status and a reason. The arithmetic is counts and
ratios only: no numpy, no scikit-learn, no hidden threshold sweep.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from llm_ingestion_screener.domain import IngestionSurface, VerdictLevel
from llm_ingestion_screener.errors import EvaluationError
from llm_ingestion_screener.eval.fixtures import (
    BENIGN_THREAT_CLASSES,
    CORPUS_DIRECTORIES,
    MALICIOUS_THREAT_CLASSES,
)
from llm_ingestion_screener.eval.runner import FixtureResult

METRIC_NAMES: tuple[str, ...] = (
    "malicious_recall",
    "malicious_recall_by_threat_class",
    "benign_false_positive_rate",
    "blocked_task_share",
    "detection_at_fixed_fpr",
    "evasion_transform_blocked_rate",
    "evasion_transform_rule_retention",
    "determinism",
    "latency",
    "calibration",
    "frontier_recall",
    "ood_recall",
    "recall_and_fpr_by_surface",
    "rules_only_versus_rules_plus_model_lift",
    "evidence_record_well_formedness",
    "malformed_answer_batch_failure",
    "format_sensitivity",
    "threshold_sensitivity",
    "corpus_coverage",
)

METRIC_LABELS: Mapping[str, str] = {
    "malicious_recall": "Malicious recall (golden and eval)",
    "malicious_recall_by_threat_class": "Malicious recall per threat class",
    "benign_false_positive_rate": "Benign false-positive rate",
    "blocked_task_share": "Blocked-task share",
    "detection_at_fixed_fpr": "Detection at a fixed false-positive rate",
    "evasion_transform_blocked_rate": "Evasion-transform blocked rate",
    "evasion_transform_rule_retention": "Evasion-transform rule retention",
    "determinism": "Determinism and repeatability",
    "latency": "Latency and throughput",
    "calibration": "Calibration of model probabilities",
    "frontier_recall": "Frontier recall",
    "ood_recall": "Out-of-distribution recall",
    "recall_and_fpr_by_surface": "Recall and false-positive rate by surface",
    "rules_only_versus_rules_plus_model_lift": "Rule-only versus rules-plus-model lift",
    "evidence_record_well_formedness": "Evidence-record well-formedness",
    "malformed_answer_batch_failure": "Malformed-answer batch failure",
    "format_sensitivity": "Format sensitivity",
    "threshold_sensitivity": "Threshold sensitivity",
    "corpus_coverage": "Corpus coverage",
}


@dataclass(frozen=True)
class Metric:
    """One metric's value, or a documented not-applicable result."""

    name: str
    status: str  # "computed" or "not-applicable"
    value: float | bool | None
    detail: str
    data: Mapping[str, object] = field(default_factory=dict)
    reason: str | None = None

    @property
    def label(self) -> str:
        return METRIC_LABELS[self.name]

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "name": self.name,
            "label": self.label,
            "status": self.status,
            "value": self.value,
            "detail": self.detail,
            "data": dict(self.data),
        }
        if self.reason is not None:
            payload["reason"] = self.reason
        return payload


@dataclass(frozen=True)
class MetricsReport:
    metrics: tuple[Metric, ...]

    def by_name(self) -> dict[str, Metric]:
        return {metric.name: metric for metric in self.metrics}

    def value(self, name: str) -> float | bool | None:
        return self.by_name()[name].value

    def to_dict(self) -> dict[str, object]:
        return {
            "metrics": [metric.to_dict() for metric in self.metrics],
        }


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def _not_applicable(name: str, reason: str, detail: str) -> Metric:
    return Metric(
        name=name,
        status="not-applicable",
        value=None,
        detail=detail,
        reason=reason,
    )


def _recall_block(results: Sequence[FixtureResult]) -> dict[str, object]:
    total = len(results)
    caught = sum(1 for result in results if result.caught)
    return {
        "caught": caught,
        "total": total,
        "value": _ratio(caught, total),
    }


def compute_metrics(
    results: Sequence[FixtureResult],
    *,
    gate_corpora: Sequence[str] = ("golden", "eval"),
    deterministic: bool,
    malformed_answer_fails_batch: bool,
    coverage_floors: Mapping[str, Mapping[str, int]] | None = None,
) -> MetricsReport:
    """Compute every metric from fixture results.

    ``deterministic`` and ``malformed_answer_fails_batch`` are measured by the
    runner and passed in so this module stays pure arithmetic over results.
    """

    ordered = tuple(results)
    if not ordered:
        raise EvaluationError("cannot compute metrics over an empty result set")

    metrics: list[Metric] = []

    # 1. Malicious recall over the gated corpora.
    gate_results = tuple(
        result
        for result in ordered
        if result.label == "malicious" and result.corpus in gate_corpora
    )
    if not gate_results:
        raise EvaluationError(
            "gated malicious recall has no malicious fixtures in corpora "
            f"{tuple(gate_corpora)!r}"
        )
    gate_block = _recall_block(gate_results)
    by_corpus = {
        corpus: _recall_block(
            [
                result
                for result in ordered
                if result.label == "malicious" and result.corpus == corpus
            ]
        )
        for corpus in CORPUS_DIRECTORIES
    }
    metrics.append(
        Metric(
            name="malicious_recall",
            status="computed",
            value=gate_block["value"],
            detail=(
                f"{gate_block['caught']} of {gate_block['total']} malicious "
                f"fixtures caught in {', '.join(gate_corpora)}"
            ),
            data={
                "caught": gate_block["caught"],
                "total": gate_block["total"],
                "gate_corpora": list(gate_corpora),
                "by_corpus": by_corpus,
            },
        )
    )

    # 2. Malicious recall per threat class.
    malicious = [result for result in ordered if result.label == "malicious"]
    class_names = sorted(MALICIOUS_THREAT_CLASSES | {r.threat_class for r in malicious})
    per_class: dict[str, object] = {}
    for class_name in class_names:
        block = _recall_block(
            [result for result in malicious if result.threat_class == class_name]
        )
        if block["total"] == 0:
            block["status"] = "not-applicable"
            block["reason"] = "no fixtures in this threat class"
        per_class[class_name] = block
    metrics.append(
        Metric(
            name="malicious_recall_by_threat_class",
            status="computed",
            value=None,
            detail="Per-class recall so one strong class cannot mask a blind spot.",
            data={"classes": per_class},
        )
    )

    # 3. Benign false-positive rate.
    benign = [result for result in ordered if result.label == "benign"]
    false_positives = sum(
        1 for result in benign if VerdictLevel[result.verdict.upper()] > VerdictLevel.CLEAN
    )
    metrics.append(
        Metric(
            name="benign_false_positive_rate",
            status="computed",
            value=_ratio(false_positives, len(benign)),
            detail=(
                f"{false_positives} of {len(benign)} benign fixtures produced a "
                "verdict above clean"
            ),
            data={"false_positives": false_positives, "total": len(benign)},
        )
    )

    # 4. Blocked-task share: the schema has no task grouping in Phase 2.
    metrics.append(
        _not_applicable(
            "blocked_task_share",
            "The Phase 2 fixture schema carries no task id, so fixtures cannot "
            "be grouped into tasks.",
            "Blocked-task share needs task-grouped fixtures (Phase 3).",
        )
    )

    # 5. Detection at a fixed FPR: the production verdict is ordinal.
    metrics.append(
        _not_applicable(
            "detection_at_fixed_fpr",
            "The production screen emits an ordinal verdict, not a continuous "
            "score, so a threshold curve cannot be drawn without inventing a "
            "score model the screen does not ship.",
            "TPR at 1% FPR belongs to the Phase 5 head-to-head.",
        )
    )

    # 6 and 7. Evasion transforms.
    transforms = [result for result in ordered if result.corpus == "transforms"]
    if transforms:
        blocked = sum(1 for result in transforms if result.caught)
        metrics.append(
            Metric(
                name="evasion_transform_blocked_rate",
                status="computed",
                value=_ratio(blocked, len(transforms)),
                detail=f"{blocked} of {len(transforms)} transformed fixtures still caught",
                data={"blocked": blocked, "total": len(transforms)},
            )
        )
        lookup = {result.fixture_id: result for result in ordered}
        retained = 0
        base_hits = 0
        pairs: list[dict[str, object]] = []
        for result in transforms:
            if result.derived_from is None:
                raise EvaluationError(
                    f"transform fixture {result.fixture_id!r} has no derived_from"
                )
            base = lookup.get(result.derived_from)
            if base is None:
                raise EvaluationError(
                    f"transform fixture {result.fixture_id!r} derives from "
                    f"unknown result {result.derived_from!r}"
                )
            base_rules = set(base.rule_ids)
            if not base_rules:
                pairs.append(
                    {
                        "fixture_id": result.fixture_id,
                        "base_id": base.fixture_id,
                        "base_rule_ids": [],
                        "derived_rule_ids": list(result.rule_ids),
                        "retained": None,
                    }
                )
                continue
            surviving = base_rules & set(result.rule_ids)
            retained += len(surviving)
            base_hits += len(base_rules)
            pairs.append(
                {
                    "fixture_id": result.fixture_id,
                    "base_id": base.fixture_id,
                    "base_rule_ids": sorted(base_rules),
                    "derived_rule_ids": list(result.rule_ids),
                    "retained": sorted(surviving),
                }
            )
        if base_hits == 0:
            metrics.append(
                _not_applicable(
                    "evasion_transform_rule_retention",
                    "No base fixture produced a rule hit to retain.",
                    "Rule retention needs a base fixture that fires at least one rule.",
                )
            )
        else:
            metrics.append(
                Metric(
                    name="evasion_transform_rule_retention",
                    status="computed",
                    value=retained / base_hits,
                    detail=(
                        f"{retained} of {base_hits} base rule hits survive the "
                        "transform"
                    ),
                    data={"retained": retained, "base_hits": base_hits, "pairs": pairs},
                )
            )
    else:
        metrics.append(
            _not_applicable(
                "evasion_transform_blocked_rate",
                "The corpus has no transforms/ fixtures.",
                "No transformed fixtures to measure.",
            )
        )
        metrics.append(
            _not_applicable(
                "evasion_transform_rule_retention",
                "The corpus has no transforms/ fixtures.",
                "No transformed fixtures to measure.",
            )
        )

    # 8. Determinism.
    metrics.append(
        Metric(
            name="determinism",
            status="computed",
            value=deterministic,
            detail=(
                "two recorded batches produced byte-identical results"
                if deterministic
                else "two recorded batches differed"
            ),
            data={"runs": 2, "byte_identical": deterministic},
        )
    )

    # 9. Latency: a recorded run does no real inference.
    metrics.append(
        _not_applicable(
            "latency",
            "The default run replays a recorded client and measures no live "
            "inference latency.",
            "Latency is measured only by the opt-in live run (Phase 5).",
        )
    )

    # 10. Calibration: no single calibrated probability per fixture.
    metrics.append(
        _not_applicable(
            "calibration",
            "The verdict combines several typed answers and a rule floor, so no "
            "single model probability per fixture exists to calibrate in Phase 2.",
            "Brier and ECE belong to the Phase 5 threshold work.",
        )
    )

    # 11. Frontier recall.
    frontier = [
        result
        for result in ordered
        if result.corpus == "frontier" and result.label == "malicious"
    ]
    if frontier:
        block = _recall_block(frontier)
        metrics.append(
            Metric(
                name="frontier_recall",
                status="computed",
                value=block["value"],
                detail=f"{block['caught']} of {block['total']} frontier fixtures caught",
                data=block,
            )
        )
    else:
        metrics.append(
            _not_applicable(
                "frontier_recall",
                "The corpus has no frontier/ malicious fixtures.",
                "No frontier fixtures to measure.",
            )
        )

    # 12. Out-of-distribution recall.
    metrics.append(
        _not_applicable(
            "ood_recall",
            "The Phase 2 schema records a source but no held-out split, so an "
            "out-of-distribution slice cannot be identified without inventing one.",
            "OOD recall needs the Phase 3 sourced corpora.",
        )
    )

    # 13. Recall and FPR by surface.
    per_surface: dict[str, object] = {}
    for surface in IngestionSurface:
        surface_results = [r for r in ordered if r.surface == surface.value]
        surface_malicious = [r for r in surface_results if r.label == "malicious"]
        surface_benign = [r for r in surface_results if r.label == "benign"]
        surface_fp = sum(
            1
            for result in surface_benign
            if VerdictLevel[result.verdict.upper()] > VerdictLevel.CLEAN
        )
        per_surface[surface.value] = {
            "malicious": _recall_block(surface_malicious),
            "benign_false_positives": surface_fp,
            "benign_total": len(surface_benign),
            "benign_false_positive_rate": _ratio(surface_fp, len(surface_benign)),
        }
    metrics.append(
        Metric(
            name="recall_and_fpr_by_surface",
            status="computed",
            value=None,
            detail="Per-surface recall and false-positive rate.",
            data={"surfaces": per_surface},
        )
    )

    # 14. Rule-only versus rules-plus-model lift.
    metrics.append(
        _not_applicable(
            "rules_only_versus_rules_plus_model_lift",
            "A rule-only control run is a deliberate second screen configuration "
            "and is not part of the Phase 2 runner.",
            "The lift comparison belongs to the Phase 5 head-to-head.",
        )
    )

    # 15. Evidence-record well-formedness.
    cited = [result for result in ordered if result.verdict != "clean"]
    if cited:
        well_formed = sum(1 for result in cited if result.evidence_ok)
        metrics.append(
            Metric(
                name="evidence_record_well_formedness",
                status="computed",
                value=well_formed / len(cited),
                detail=(
                    f"{well_formed} of {len(cited)} flagged or quarantined "
                    "verdicts carry citable evidence"
                ),
                data={"well_formed": well_formed, "total": len(cited)},
            )
        )
    else:
        metrics.append(
            _not_applicable(
                "evidence_record_well_formedness",
                "No flagged or quarantined verdict exists to cite.",
                "A corpus that never flags cannot demonstrate evidence records.",
            )
        )

    # 16. Malformed-answer batch failure.
    metrics.append(
        Metric(
            name="malformed_answer_batch_failure",
            status="computed",
            value=malformed_answer_fails_batch,
            detail=(
                "a malformed decision-model answer raised instead of producing "
                "a verdict"
                if malformed_answer_fails_batch
                else "a malformed answer did not fail the batch"
            ),
            data={"holds": malformed_answer_fails_batch},
        )
    )

    # 17. Format sensitivity.
    metrics.append(
        _not_applicable(
            "format_sensitivity",
            "No serialisation-stripping normalisation pre-pass exists in Phase 2.",
            "The format ablation belongs to the Phase 5 head-to-head.",
        )
    )

    # 18. Threshold sensitivity.
    metrics.append(
        _not_applicable(
            "threshold_sensitivity",
            "The production verdict is ordinal and the policy thresholds are "
            "not swept by the Phase 2 runner.",
            "The threshold curve belongs to the Phase 5 head-to-head.",
        )
    )

    # 19. Corpus coverage.
    metrics.append(_coverage_metric(ordered, coverage_floors))

    return MetricsReport(metrics=tuple(metrics))


def _coverage_metric(
    results: Sequence[FixtureResult],
    floors: Mapping[str, Mapping[str, int]] | None,
) -> Metric:
    directory_counts = {
        corpus: sum(1 for result in results if result.corpus == corpus)
        for corpus in CORPUS_DIRECTORIES
    }
    surface_counts = {
        surface.value: sum(1 for result in results if result.surface == surface.value)
        for surface in IngestionSurface
    }
    class_counts: dict[str, int] = {}
    for result in results:
        class_counts[result.threat_class] = class_counts.get(result.threat_class, 0) + 1
    for class_name in sorted(MALICIOUS_THREAT_CLASSES | BENIGN_THREAT_CLASSES | {"none"}):
        class_counts.setdefault(class_name, 0)

    if floors is None:
        return _not_applicable(
            "corpus_coverage",
            "No coverage floors were supplied.",
            "The gate registry supplies the corpus-coverage floors.",
        )

    sections = {
        "directories": directory_counts,
        "surfaces": surface_counts,
        "threat_classes": class_counts,
    }
    data: dict[str, object] = {}
    all_met = True
    for section, counts in sections.items():
        section_floors = floors.get(section, {})
        if not isinstance(section_floors, Mapping):
            raise EvaluationError(
                f"coverage floors section {section!r} must be a mapping"
            )
        detail: dict[str, object] = {}
        for key, floor in section_floors.items():
            if isinstance(floor, bool) or not isinstance(floor, int) or floor < 0:
                raise EvaluationError(
                    f"coverage floor {section}.{key} must be a non-negative integer"
                )
            count = counts.get(str(key), 0)
            met = count >= floor
            all_met = all_met and met
            detail[str(key)] = {"count": count, "floor": floor, "met": met}
        data[section] = detail

    return Metric(
        name="corpus_coverage",
        status="computed",
        value=all_met,
        detail=(
            "every configured coverage floor is met"
            if all_met
            else "at least one coverage floor is not met"
        ),
        data=data,
    )
