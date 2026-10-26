"""Smoke tests for the CLI entry point."""

from __future__ import annotations

import pytest

from llm_ingestion_screener import __version__
from llm_ingestion_screener.cli import main


def test_version_flag_prints_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])
    assert excinfo.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_no_args_prints_help_and_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    assert "usage" in capsys.readouterr().out.lower()
