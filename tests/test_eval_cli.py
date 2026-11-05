"""The eval CLI exit codes."""

from __future__ import annotations

from pathlib import Path

from llm_ingestion_screener.eval.cli import main
from eval_support import BASELINE, CASSETTE, CORPUS, GATES, gates_with


def test_cli_runs_recorded_mode(tmp_path: Path, capsys) -> None:
    code = main(
        [
            "run",
            "--corpus",
            str(CORPUS),
            "--cassette",
            str(CASSETTE),
            "--gates",
            str(GATES),
            "--baseline",
            str(BASELINE),
            "--artifacts",
            str(tmp_path / "artifacts"),
        ]
    )
    captured = capsys.readouterr()
    assert code == 0
    assert "all gated checks passed" in captured.out
    assert (tmp_path / "artifacts" / "detection-eval.md").is_file()


def test_cli_returns_nonzero_when_a_gate_fails(tmp_path: Path, capsys) -> None:
    broken = gates_with(
        tmp_path,
        lambda payload: payload["metrics"]["malicious_recall"].__setitem__(
            "threshold", 0.99
        ),
    )
    code = main(
        [
            "run",
            "--corpus",
            str(CORPUS),
            "--cassette",
            str(CASSETTE),
            "--gates",
            str(broken),
            "--baseline",
            str(BASELINE),
            "--artifacts",
            str(tmp_path / "artifacts"),
        ]
    )
    captured = capsys.readouterr()
    assert code == 1
    assert "gate failed: malicious_recall" in captured.err


def test_cli_returns_two_on_validation_error(tmp_path: Path, capsys) -> None:
    code = main(
        [
            "run",
            "--corpus",
            str(tmp_path / "absent-corpus"),
            "--cassette",
            str(CASSETTE),
            "--gates",
            str(GATES),
            "--baseline",
            str(BASELINE),
            "--artifacts",
            str(tmp_path / "artifacts"),
        ]
    )
    captured = capsys.readouterr()
    assert code == 2
    assert "eval error:" in captured.err
