"""Top-level eval run: load, screen twice, measure, gate, compare, report."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from llm_ingestion_screener.decision_model import RecordedDecisionModel
from llm_ingestion_screener.eval.baseline import (
    BaselineDiff,
    build_baseline,
    compare_baseline,
    load_baseline,
    write_baseline,
)
from llm_ingestion_screener.eval.fixtures import Corpus, load_corpus
from llm_ingestion_screener.eval.gates import (
    GateEvaluation,
    GateRegistry,
    evaluate_gates,
    load_gates,
)
from llm_ingestion_screener.eval.metrics import MetricsReport, compute_metrics
from llm_ingestion_screener.eval.report import render_json, render_markdown, write_reports
from llm_ingestion_screener.eval.runner import (
    FixtureResult,
    check_malformed_answer_fails_batch,
    results_are_byte_identical,
    run_corpus,
)


@dataclass(frozen=True)
class EvalRun:
    corpus: Corpus
    results: tuple[FixtureResult, ...]
    metrics: MetricsReport
    registry: GateRegistry
    evaluation: GateEvaluation
    baseline_diff: BaselineDiff
    markdown: str
    report_json: str
    markdown_path: Path
    json_path: Path
    failures: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.failures


def run_eval(
    *,
    corpus_root: str | Path,
    cassette_path: str | Path,
    gates_path: str | Path,
    baseline_path: str | Path,
    artifacts_dir: str | Path,
    update_baseline: bool = False,
) -> EvalRun:
    """Run the deterministic harness and write both report artefacts."""

    corpus = load_corpus(corpus_root)
    model = RecordedDecisionModel.from_file(cassette_path)
    first = run_corpus(corpus, model)
    second = run_corpus(corpus, model)
    deterministic = results_are_byte_identical(first, second)
    malformed_holds = check_malformed_answer_fails_batch(corpus.fixtures[0])

    registry = load_gates(gates_path)
    metrics = compute_metrics(
        first,
        gate_corpora=registry.malicious_recall_corpora,
        deterministic=deterministic,
        malformed_answer_fails_batch=malformed_holds,
        coverage_floors=registry.coverage_floors,
    )
    evaluation = evaluate_gates(registry, metrics)

    baseline = load_baseline(baseline_path, allow_missing=update_baseline)
    baseline_diff = compare_baseline(
        baseline,
        metrics,
        first,
        registry,
        corpus.fingerprint,
    )

    markdown = render_markdown(
        corpus,
        first,
        metrics,
        registry,
        evaluation,
        baseline_diff,
        cassette_model=model.cassette.model,
        cassette_synthetic=model.cassette.synthetic,
    )
    report_json = render_json(
        corpus,
        first,
        metrics,
        evaluation,
        baseline_diff,
        cassette_model=model.cassette.model,
        cassette_synthetic=model.cassette.synthetic,
    )
    markdown_path, json_path = write_reports(artifacts_dir, markdown, report_json)

    if update_baseline:
        # Written after both report artefacts exist, so a report failure cannot
        # leave a silently advanced baseline behind.
        write_baseline(
            baseline_path,
            build_baseline(metrics, first, corpus.fingerprint),
        )

    failures: list[str] = [f"gate failed: {name}" for name in evaluation.failures]
    if not update_baseline:
        for item in baseline_diff.golden_output_regressions:
            failures.append(
                f"golden output regression: {item['fixture_id']}"
            )
        for item in baseline_diff.gated_metric_regressions:
            failures.append(
                f"gated metric regression: {item['metric']} "
                f"({item['baseline']!r} -> {item['current']!r})"
            )

    return EvalRun(
        corpus=corpus,
        results=first,
        metrics=metrics,
        registry=registry,
        evaluation=evaluation,
        baseline_diff=baseline_diff,
        markdown=markdown,
        report_json=report_json,
        markdown_path=markdown_path,
        json_path=json_path,
        failures=tuple(failures),
    )
