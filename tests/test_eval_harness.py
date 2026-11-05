"""End-to-end harness: gates, baseline, determinism, and report artefacts."""

from __future__ import annotations

import shutil
import json
from pathlib import Path

import pytest

from llm_ingestion_screener.errors import EvaluationError
from llm_ingestion_screener.eval.harness import run_eval
from eval_support import (
    BASELINE,
    CASSETTE,
    CORPUS,
    GATES,
    copy_corpus,
    gates_with,
    load_yaml,
    write_yaml,
)


def run_default(tmp_path: Path, *, baseline: Path = BASELINE, gates: Path = GATES):
    return run_eval(
        corpus_root=CORPUS,
        cassette_path=CASSETTE,
        gates_path=gates,
        baseline_path=baseline,
        artifacts_dir=tmp_path / "artifacts",
    )


def test_the_default_run_passes_every_gate(tmp_path: Path) -> None:
    run = run_default(tmp_path)
    assert run.failures == ()
    assert run.markdown_path.is_file()
    assert run.json_path.is_file()
    assert len(run.metrics.metrics) == 19
    report = json.loads(run.json_path.read_text(encoding="utf-8"))
    evidence = {
        item["fixture_id"]: item["evidence"] for item in report["fixtures"]
    }
    assert evidence["web-page-agent-directed-imperative"]["rule_hits"]
    assert evidence["web-page-agent-directed-imperative"]["answers"]
    assert evidence["web-page-agent-directed-imperative"]["quarantined_passages"]
    markdown = run.markdown_path.read_text(encoding="utf-8")
    for heading in (
        "## Screening log",
        "## Gated results",
        "## Reported results",
        "## Per-threat-class recall",
        "## Per-surface recall and false positives",
        "## Frontier misses",
        "## Benign false positives",
        "## Baseline comparison",
        "## Corpus coverage",
    ):
        assert heading in markdown


def test_the_report_is_byte_deterministic(tmp_path: Path) -> None:
    first = run_default(tmp_path / "a")
    second = run_default(tmp_path / "b")
    assert first.report_json == second.report_json
    assert first.markdown == second.markdown


def test_a_broken_gate_fails_the_run(tmp_path: Path) -> None:
    broken = gates_with(
        tmp_path,
        lambda payload: payload["metrics"]["malicious_recall"].__setitem__(
            "threshold", 0.99
        ),
    )
    run = run_default(tmp_path, gates=broken)
    assert "gate failed: malicious_recall" in run.failures
    assert run.markdown_path.is_file()


def test_a_report_write_failure_raises(tmp_path: Path) -> None:
    blocker = tmp_path / "artifacts"
    blocker.write_text("not a directory", encoding="utf-8")
    with pytest.raises(EvaluationError, match="could not write eval report"):
        run_eval(
            corpus_root=CORPUS,
            cassette_path=CASSETTE,
            gates_path=GATES,
            baseline_path=BASELINE,
            artifacts_dir=blocker,
        )


def test_a_normal_run_does_not_update_the_baseline(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    shutil.copy(BASELINE, baseline)
    before = baseline.read_bytes()
    run_default(tmp_path, baseline=baseline)
    assert baseline.read_bytes() == before


def test_a_golden_output_change_is_a_regression(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    payload = json.loads(BASELINE.read_text(encoding="utf-8"))
    golden = payload["fixtures"]["web-page-agent-directed-imperative"]
    golden["verdict"] = "clean"
    golden["rule_ids"] = []
    baseline.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    run = run_default(tmp_path, baseline=baseline)
    assert (
        "golden output regression: web-page-agent-directed-imperative"
        in run.failures
    )


def test_a_gated_metric_regression_is_distinguished_from_a_corpus_change(
    tmp_path: Path,
) -> None:
    baseline = tmp_path / "baseline.json"
    payload = json.loads(BASELINE.read_text(encoding="utf-8"))
    payload["metrics"]["malicious_recall"]["value"] = 0.99
    baseline.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    run = run_default(tmp_path, baseline=baseline)
    assert not run.baseline_diff.corpus_changed
    assert any(
        failure.startswith("gated metric regression: malicious_recall")
        for failure in run.failures
    )


def test_a_missing_baseline_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(EvaluationError, match="baseline does not exist"):
        run_default(tmp_path, baseline=tmp_path / "absent.json")


def test_updating_the_baseline_is_deliberate(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    run = run_eval(
        corpus_root=CORPUS,
        cassette_path=CASSETTE,
        gates_path=GATES,
        baseline_path=baseline,
        artifacts_dir=tmp_path / "artifacts",
        update_baseline=True,
    )
    assert run.failures == ()
    assert baseline.is_file()
    second = run_default(tmp_path, baseline=baseline)
    assert second.failures == ()


def test_a_deleted_corpus_directory_is_caught(tmp_path: Path) -> None:
    root = copy_corpus(tmp_path)
    shutil.rmtree(root / "benign")
    with pytest.raises(EvaluationError, match="benign.*missing"):
        run_eval(
            corpus_root=root,
            cassette_path=CASSETTE,
            gates_path=GATES,
            baseline_path=BASELINE,
            artifacts_dir=tmp_path / "artifacts",
        )


def test_a_corpus_change_is_not_a_metric_regression(tmp_path: Path) -> None:
    root = copy_corpus(tmp_path)
    extra = root / "benign" / "extra-benign.yaml"
    payload = load_yaml(root / "benign" / "web-page-imperative-vocabulary.yaml")
    payload["id"] = "extra-benign"
    payload["title"] = "An extra benign page"
    write_yaml(extra, payload)
    baseline = tmp_path / "baseline.json"
    shutil.copy(BASELINE, baseline)
    run = run_eval(
        corpus_root=root,
        cassette_path=CASSETTE,
        gates_path=GATES,
        baseline_path=baseline,
        artifacts_dir=tmp_path / "artifacts",
    )
    assert run.baseline_diff.corpus_changed
    assert "extra-benign" in run.baseline_diff.added
    assert not any(
        failure.startswith("gated metric regression") for failure in run.failures
    )
