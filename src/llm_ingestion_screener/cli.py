"""Command-line entry point for the ingestion screener.

At this stage the CLI exposes only ``--version``: the screening contract is
still being designed and this module is deliberately not a stub that pretends
to screen anything.
"""

from __future__ import annotations

import argparse

from llm_ingestion_screener import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="llm-ingestion-screener",
        description="Pre-read safety screener for material entering an LLM context.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"llm-ingestion-screener {__version__}",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    parser.parse_args(argv)
    parser.print_help()
    return 0
