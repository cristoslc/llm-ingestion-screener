"""Command-line runner for the deterministic detection eval harness."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from llm_ingestion_screener.errors import EvaluationError
from llm_ingestion_screener.eval.harness import run_eval

DEFAULT_CORPUS = Path("tests/fixtures/screener-corpus")
DEFAULT_CASSETTE = Path("tests/cassettes/eval-synthetic.json")
DEFAULT_GATES = Path("tests/eval/gates.yaml")
DEFAULT_BASELINE = Path("tests/eval/baseline.json")
DEFAULT_ARTIFACTS = Path("screening-artifacts/eval")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m llm_ingestion_screener.eval",
        description="Run the offline detection eval harness.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)
    run = subcommands.add_parser("run", help="screen the corpus and write reports")
    run.add_argument("--mode", choices=["recorded"], default="recorded")
    run.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    run.add_argument("--cassette", type=Path, default=DEFAULT_CASSETTE)
    run.add_argument("--gates", type=Path, default=DEFAULT_GATES)
    run.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    run.add_argument("--artifacts", type=Path, default=DEFAULT_ARTIFACTS)
    run.add_argument(
        "--update-baseline",
        action="store_true",
        help="deliberately replace the committed baseline with this run",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        run = run_eval(
            corpus_root=args.corpus,
            cassette_path=args.cassette,
            gates_path=args.gates,
            baseline_path=args.baseline,
            artifacts_dir=args.artifacts,
            update_baseline=args.update_baseline,
        )
    except EvaluationError as exc:
        print(f"eval error: {exc}", file=sys.stderr)
        return 2

    print(f"report: {run.markdown_path}")
    print(f"report: {run.json_path}")
    if run.failures:
        for failure in run.failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print("all gated checks passed")
    return 0
