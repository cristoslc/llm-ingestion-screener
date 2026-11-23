"""The committed corpus manifest is the offline audit trail."""

from __future__ import annotations

from pathlib import Path

import pytest

from llm_ingestion_screener.errors import EvaluationError
from llm_ingestion_screener.eval.fixtures import load_corpus
from llm_ingestion_screener.eval.manifest import (
    MANIFEST_FORMAT,
    load_manifest,
)
from eval_support import CORPUS, copy_corpus, load_yaml, write_yaml

MANIFEST = CORPUS / "manifest.yaml"


def test_committed_manifest_covers_every_fixture_and_no_others() -> None:
    corpus = load_corpus(CORPUS)
    manifest = load_manifest(MANIFEST)
    assert manifest.pins
    assert set(manifest.entries) == set(corpus.by_id)
    for entry in manifest.entries.values():
        assert (CORPUS / entry.path).is_file()
        assert len(entry.upstream_commit) == 40 or entry.upstream_commit == "none"


def test_rejects_a_manifest_that_misses_a_fixture(tmp_path: Path) -> None:
    root = copy_corpus(tmp_path)
    manifest_path = root / "manifest.yaml"
    payload = load_yaml(manifest_path)
    payload["fixtures"] = payload["fixtures"][1:]
    write_yaml(manifest_path, payload)
    with pytest.raises(EvaluationError, match="does not cover fixture"):
        load_corpus(root)


def test_rejects_a_manifest_entry_for_a_missing_fixture(tmp_path: Path) -> None:
    root = copy_corpus(tmp_path)
    manifest_path = root / "manifest.yaml"
    payload = load_yaml(manifest_path)
    extra = dict(payload["fixtures"][0])
    extra["id"] = "extra-manifest-row"
    extra["path"] = "benign/extra-manifest-row.yaml"
    payload["fixtures"].append(extra)
    write_yaml(manifest_path, payload)
    with pytest.raises(EvaluationError, match="do not exist"):
        load_corpus(root)


def test_rejects_a_benchmark_fixture_without_a_pinned_upstream(
    tmp_path: Path,
) -> None:
    root = copy_corpus(tmp_path)
    manifest_path = root / "manifest.yaml"
    payload = load_yaml(manifest_path)
    entry = next(
        item
        for item in payload["fixtures"]
        if item["source"] == "benchmark-derived"
    )
    entry["upstream"] = {
        "repository": "none",
        "commit": "none",
        "sample_id": "synthetic/none",
    }
    write_yaml(manifest_path, payload)
    with pytest.raises(EvaluationError, match="names no upstream repository"):
        load_corpus(root)


def test_rejects_a_manifest_commit_that_is_not_the_pin(tmp_path: Path) -> None:
    root = copy_corpus(tmp_path)
    manifest_path = root / "manifest.yaml"
    payload = load_yaml(manifest_path)
    entry = next(
        item
        for item in payload["fixtures"]
        if item["upstream"]["repository"] != "none"
    )
    entry["upstream"]["commit"] = "0" * 40
    write_yaml(manifest_path, payload)
    with pytest.raises(EvaluationError, match="does not match the pin"):
        load_corpus(root)


def test_rejects_a_provenance_line_without_its_pinned_commit(
    tmp_path: Path,
) -> None:
    root = copy_corpus(tmp_path)
    manifest_path = root / "manifest.yaml"
    payload = load_yaml(manifest_path)
    entry = next(
        item
        for item in payload["fixtures"]
        if item["source"] == "benchmark-derived"
    )
    fixture_path = root / entry["path"]
    fixture = load_yaml(fixture_path)
    fixture["provenance"] = "A generic provenance line with no commit."
    write_yaml(fixture_path, fixture)
    with pytest.raises(EvaluationError, match="provenance does not name"):
        load_corpus(root)


def test_rejects_a_duplicate_manifest_id(tmp_path: Path) -> None:
    root = copy_corpus(tmp_path)
    manifest_path = root / "manifest.yaml"
    payload = load_yaml(manifest_path)
    payload["fixtures"].append(dict(payload["fixtures"][0]))
    write_yaml(manifest_path, payload)
    with pytest.raises(EvaluationError, match="repeats fixture id"):
        load_corpus(root)


def test_rejects_a_missing_manifest(tmp_path: Path) -> None:
    root = copy_corpus(tmp_path)
    (root / "manifest.yaml").unlink()
    with pytest.raises(EvaluationError, match="manifest is missing"):
        load_corpus(root)


def test_manifest_format_is_stable() -> None:
    payload = load_yaml(MANIFEST)
    assert payload["format"] == MANIFEST_FORMAT


def test_manifest_records_the_bipia_context_exclusion() -> None:
    manifest = load_manifest(MANIFEST)
    assert manifest.exclusions
    assert any(
        exclusion.upstream == "microsoft/BIPIA"
        and "WebQA" in exclusion.tasks
        and "separate dataset terms" in exclusion.reason
        for exclusion in manifest.exclusions
    )