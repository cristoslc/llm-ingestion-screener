"""Write the Markdown and JSON detection-eval report.

Both artefacts are deterministic: no run timestamps, no unordered sets, no
environment paths that change between two runs of the same checkout.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from llm_ingestion_screener.canonical import canonical_json
from llm_ingestion_screener.errors import EvaluationError
from llm_ingestion_screener.eval.baseline import BaselineDiff
from llm_ingestion_screener.eval.fixtures import Corpus
from llm_ingestion_screener.eval.gates import GateEvaluation, GateRegistry
from llm_ingestion_screener.eval.metrics import MetricsReport
from llm_ingestion_screener.eval.runner import FixtureResult

REPORT_FORMAT = "llm-ingestion-screener/eval-report/v1"
MARKDOWN_NAME = "detection-eval.md"
JSON_NAME = "detection-eval.json"


def render_markdown(
    corpus: Corpus,
    results: Sequence[FixtureResult],
    metrics: MetricsReport,
    registry: GateRegistry,
    evaluation: GateEvaluation,
    baseline_diff: BaselineDiff,
    *,
    cassette_model: str,
    cassette_synthetic: bool,
) -> str:
    lines: list[str] = []
    lines.append("# Detection eval report")
    lines.append("")
    lines.append(
        "Produced by the offline eval harness against the production screening "
        "code path. The recorded decision-model client is synthetic test data, "
        "not measured model output."
    )
    lines.append("")
    lines.append("## Run configuration")
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("|---|---|")
    lines.append(f"| Corpus root | `{_escape(str(corpus.root))}` |")
    lines.append(f"| Fixtures | {len(results)} |")
    lines.append(f"| Cassette model | `{_escape(cassette_model)}` |")
    lines.append(
        f"| Cassette synthetic | {'yes' if cassette_synthetic else 'no'} |"
    )
    gated = sum(1 for rule in registry.rules.values() if rule.status == "gated")
    reported = len(registry.rules) - gated
    lines.append(f"| Gated metrics | {gated} |")
    lines.append(f"| Reported metrics | {reported} |")
    lines.append("")

    lines.append("## Screening log")
    lines.append("")
    lines.append(
        "| Fixture | Corpus | Surface | Label | Expected | Verdict | Rule hits |"
    )
    lines.append("|---|---|---|---|---|---|---|")
    for result in results:
        rules = ", ".join(result.rule_ids) if result.rule_ids else "none"
        lines.append(
            f"| `{_escape(result.fixture_id)}` | {result.corpus} | "
            f"{result.surface} | {result.label} | {result.expect_min_verdict} | "
            f"{result.verdict} | {_escape(rules)} |"
        )
    lines.append("")

    lines.append("## Gated results")
    lines.append("")
    lines.append("| Metric | Value | Gate | Result |")
    lines.append("|---|---|---|---|")
    for result in evaluation.results:
        if result.status != "gated":
            continue
        gate = (
            f"{result.operator} {result.threshold:.4f}"
            if result.operator is not None
            else "must hold"
        )
        verdict = "pass" if result.passed else "FAIL"
        lines.append(
            f"| {_escape(_metric_label(result.metric))} | "
            f"{_format_value(result.value)} | {_escape(gate)} | {verdict} |"
        )
    lines.append("")

    metrics_by_name = metrics.by_name()

    lines.append("## Reported results")
    lines.append("")
    lines.append("| Metric | Value | Detail |")
    lines.append("|---|---|---|")
    for result in evaluation.results:
        if result.status != "reported":
            continue
        metric = metrics_by_name[result.metric]
        if metric.status == "not-applicable":
            value = "not applicable"
        elif metric.value is None:
            value = "see breakdown"
        else:
            value = _format_value(metric.value)
        lines.append(
            f"| {_escape(_metric_label(result.metric))} | "
            f"{_escape(value)} | {_escape(result.detail)} |"
        )
    lines.append("")

    lines.append("## Per-threat-class recall")
    lines.append("")
    lines.append("| Threat class | Caught | Total | Recall |")
    lines.append("|---|---|---|---|")
    classes = _as_mapping(
        metrics_by_name["malicious_recall_by_threat_class"].data.get("classes"),
        "per-class recall data",
    )
    for class_name in sorted(classes):
        block = _as_mapping(classes[class_name], f"class {class_name!r}")
        total = block["total"]
        if total == 0:
            lines.append(f"| `{_escape(str(class_name))}` | 0 | 0 | not applicable |")
            continue
        value = block["value"]
        lines.append(
            f"| `{_escape(str(class_name))}` | {block['caught']} | {total} | "
            f"{_format_value(value)} |"
        )
    lines.append("")

    lines.append("## Per-surface recall and false positives")
    lines.append("")
    lines.append(
        "| Surface | Malicious caught | Malicious total | Recall | Benign FPs | "
        "Benign total | FPR |"
    )
    lines.append("|---|---|---|---|---|---|---|")
    surfaces = _as_mapping(
        metrics_by_name["recall_and_fpr_by_surface"].data.get("surfaces"),
        "per-surface data",
    )
    for surface in sorted(surfaces):
        block = _as_mapping(surfaces[surface], f"surface {surface!r}")
        malicious = _as_mapping(block.get("malicious"), f"surface {surface!r} malicious data")
        lines.append(
            f"| {surface} | {malicious['caught']} | {malicious['total']} | "
            f"{_format_value(malicious['value'])} | "
            f"{block['benign_false_positives']} | {block['benign_total']} | "
            f"{_format_value(block['benign_false_positive_rate'])} |"
        )
    lines.append("")

    lines.append("## Frontier misses")
    lines.append("")
    frontier_misses = [
        result
        for result in results
        if result.corpus == "frontier"
        and result.label == "malicious"
        and not result.caught
    ]
    if frontier_misses:
        lines.append("| Fixture | Threat class | Verdict | Rules |")
        lines.append("|---|---|---|---|")
        for result in frontier_misses:
            rules = ", ".join(result.rule_ids) if result.rule_ids else "none"
            lines.append(
                f"| `{_escape(result.fixture_id)}` | {result.threat_class} | "
                f"{result.verdict} | {_escape(rules)} |"
            )
    else:
        lines.append("No frontier misses.")
    lines.append("")

    lines.append("## Benign false positives")
    lines.append("")
    false_positives = [
        result
        for result in results
        if result.label == "benign" and result.verdict != "clean"
    ]
    if false_positives:
        lines.append("| Fixture | Surface | Verdict | Rules |")
        lines.append("|---|---|---|---|")
        for result in false_positives:
            rules = ", ".join(result.rule_ids) if result.rule_ids else "none"
            lines.append(
                f"| `{_escape(result.fixture_id)}` | {result.surface} | "
                f"{result.verdict} | {_escape(rules)} |"
            )
    else:
        lines.append("No benign false positives.")
    lines.append("")

    lines.append("## Baseline comparison")
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("|---|---|")
    lines.append(f"| Baseline present | {'yes' if baseline_diff.present else 'no'} |")
    lines.append(
        f"| Corpus fingerprint changed | "
        f"{'yes' if baseline_diff.corpus_changed else 'no'} |"
    )
    lines.append(f"| Fixtures added | {len(baseline_diff.added)} |")
    lines.append(f"| Fixtures removed | {len(baseline_diff.removed)} |")
    lines.append(f"| Fixtures with changed content | {len(baseline_diff.content_changed)} |")
    lines.append(
        f"| Golden output regressions | "
        f"{len(baseline_diff.golden_output_regressions)} |"
    )
    lines.append(
        f"| Gated metric regressions | "
        f"{len(baseline_diff.gated_metric_regressions)} |"
    )
    lines.append("")
    for note in baseline_diff.notes:
        lines.append(f"- {note}")
    lines.append("")
    if baseline_diff.golden_output_regressions:
        lines.append("### Golden output regressions")
        lines.append("")
        lines.append("| Fixture | Baseline | Current |")
        lines.append("|---|---|---|")
        for item in baseline_diff.golden_output_regressions:
            lines.append(
                f"| `{_escape(str(item['fixture_id']))}` | "
                f"{item['baseline_verdict']} / "
                f"{_escape(', '.join(item['baseline_rule_ids']) or 'none')} | "
                f"{item['current_verdict']} / "
                f"{_escape(', '.join(item['current_rule_ids']) or 'none')} |"
            )
        lines.append("")
    if baseline_diff.gated_metric_regressions:
        lines.append("### Gated metric regressions")
        lines.append("")
        lines.append("| Metric | Baseline | Current |")
        lines.append("|---|---|---|")
        for item in baseline_diff.gated_metric_regressions:
            lines.append(
                f"| {_escape(_metric_label(str(item['metric'])))} | "
                f"{_format_value(item['baseline'])} | "
                f"{_format_value(item['current'])} |"
            )
        lines.append("")

    lines.append("## Corpus coverage")
    lines.append("")
    coverage = metrics_by_name["corpus_coverage"]
    if coverage.status == "not-applicable":
        lines.append(f"Not applicable: {coverage.reason}")
    else:
        for section in ("directories", "surfaces", "threat_classes"):
            detail = coverage.data.get(section)
            if not isinstance(detail, Mapping):
                continue
            lines.append(f"### {section.replace('_', ' ').title()}")
            lines.append("")
            lines.append("| Key | Count | Floor | Met |")
            lines.append("|---|---|---|---|")
            for key in sorted(detail):
                row = _as_mapping(detail[key], f"coverage {section}.{key}")
                lines.append(
                    f"| `{_escape(str(key))}` | {row['count']} | {row['floor']} | "
                    f"{'yes' if row['met'] else 'no'} |"
                )
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def render_json(
    corpus: Corpus,
    results: Sequence[FixtureResult],
    metrics: MetricsReport,
    evaluation: GateEvaluation,
    baseline_diff: BaselineDiff,
    *,
    cassette_model: str,
    cassette_synthetic: bool,
) -> str:
    payload = {
        "format": REPORT_FORMAT,
        "run": {
            "client": "recorded",
            "cassette_model": cassette_model,
            "cassette_synthetic": cassette_synthetic,
            "corpus_root": str(corpus.root),
            "fixture_count": len(results),
        },
        "metrics": metrics.to_dict(),
        "gates": evaluation.to_dict(),
        "baseline": baseline_diff.to_dict(),
        "fixtures": [result.to_dict() for result in results],
    }
    return canonical_json(payload) + "\n"


def write_reports(
    artifacts_dir: str | Path,
    markdown: str,
    json_text: str,
) -> tuple[Path, Path]:
    """Write both artefacts, or raise. A missing report is a failed command."""

    directory = Path(artifacts_dir)
    try:
        directory.mkdir(parents=True, exist_ok=True)
        markdown_path = directory / MARKDOWN_NAME
        json_path = directory / JSON_NAME
        markdown_path.write_text(markdown, encoding="utf-8")
        json_path.write_text(json_text, encoding="utf-8")
    except OSError as exc:
        raise EvaluationError(
            f"could not write eval report under {directory}: {exc}"
        ) from exc
    return markdown_path, json_path


def _as_mapping(value: object, description: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise EvaluationError(f"report data for {description} is not a mapping")
    return value


def _format_value(value: object) -> str:
    if value is None:
        return "not applicable"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def _escape(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _metric_label(name: str) -> str:
    from llm_ingestion_screener.eval.metrics import METRIC_LABELS

    return METRIC_LABELS.get(name, name)
