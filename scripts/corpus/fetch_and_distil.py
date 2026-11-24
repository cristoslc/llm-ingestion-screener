#!/usr/bin/env python
"""Fetch the pinned upstream benchmarks and rebuild the committed corpus.

The committed corpus is the product. This script is a maintenance tool: a
reviewer runs it by hand with the network available, reviews the diff, and
commits the regenerated fixtures and manifest. The test suite never imports
this script and never depends on the network.

Usage::

    python scripts/corpus/fetch_and_distil.py --prune
    python scripts/corpus/fetch_and_distil.py --check

``--check`` exits non-zero when the committed files differ from what the
pinned upstreams would produce. ``--source-dir`` reads verified local git
checkouts instead of fetching, for development without network.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import yaml

if __package__ in {None, ""}:  # allow ``python scripts/corpus/fetch_and_distil.py``
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.corpus.recipes import Recipe, build_recipes
from scripts.corpus.upstream import PINS, load_upstream

CORPUS_DIRECTORIES = ("golden", "eval", "frontier", "benign", "transforms")
DEFAULT_CORPUS = Path("tests/fixtures/screener-corpus")
MANIFEST_NAME = "manifest.yaml"
MANIFEST_FORMAT = "llm-ingestion-screener/corpus-manifest/v2"
CONTROL_CHARACTERS = frozenset(
    [chr(code) for code in range(0x202A, 0x202F)]
    + [chr(code) for code in range(0x2066, 0x206A)]
    + [chr(code) for code in range(0xE0000, 0xE0080)]
)
EXCLUSIONS = (
    {
        "upstream": "microsoft/BIPIA",
        "tasks": ["WebQA", "Summarization", "EmailQA", "TableQA"],
        "reason": (
            "BIPIA context data carry separate dataset terms: the WebQA and "
            "Summarization tasks require generating context data under the "
            "NewsQA and XSum terms, and the EmailQA and TableQA contexts carry "
            "the WikiTableQuestions and Stack Exchange terms. None of those "
            "terms were read as permitting redistribution of derived fixtures, "
            "so no BIPIA context task is included. Only the MIT-licensed "
            "attack-goal and benign-task JSON is used."
        ),
    },
)


def _scalar(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def render_fixture(recipe: Recipe) -> str:
    """Render one recipe as the reviewable YAML shape of plan section 5.1."""

    lines: list[str] = []
    lines.append(f"id: {_scalar(recipe.id)}")
    lines.append(f"title: {_scalar(recipe.title)}")
    lines.append(f"surface: {recipe.surface}")
    lines.append(f"label: {recipe.label}")
    lines.append(f"expect_min_verdict: {recipe.expect_min_verdict}")
    lines.append(f"threat_class: {recipe.threat_class}")
    lines.append(f"source: {recipe.source}")
    lines.append(f"provenance: {_scalar(recipe.provenance)}")
    lines.append(f"intent: {_scalar(recipe.intent)}")
    if any(character in CONTROL_CHARACTERS for character in recipe.content):
        lines.append(f"content: {json.dumps(recipe.content, ensure_ascii=True)}")
    else:
        lines.append("content: |")
        for line in recipe.content.rstrip("\n").split("\n"):
            lines.append(f"  {line}" if line else "")
    if recipe.expect_any_rule:
        lines.append("expect_any_rule:")
        for rule_id in recipe.expect_any_rule:
            lines.append(f"  - {rule_id}")
    else:
        lines.append("expect_any_rule: []")
    if recipe.derived_from is not None:
        lines.append(f"derived_from: {_scalar(recipe.derived_from)}")
    if recipe.transform is not None:
        lines.append(f"transform: {_scalar(recipe.transform)}")
    if recipe.notes is not None:
        lines.append(f"notes: {_scalar(recipe.notes)}")
    return "\n".join(lines) + "\n"


def render_manifest(recipes: list[Recipe]) -> str:
    payload = {
        "format": MANIFEST_FORMAT,
        "pins": dict(PINS),
        "exclusions": list(EXCLUSIONS),
        "fixtures": [
            {
                "id": recipe.id,
                "path": recipe.path,
                "corpus": recipe.corpus,
                "surface": recipe.surface,
                "label": recipe.label,
                "threat_class": recipe.threat_class,
                "source": recipe.source,
                "upstream": {
                    "repository": recipe.upstream_repository,
                    "commit": recipe.upstream_commit,
                    "sample_id": recipe.upstream_sample_id,
                },
                "derived_from": recipe.derived_from,
                "transform": recipe.transform,
                "sanitisation": list(recipe.sanitisation),
            }
            for recipe in sorted(recipes, key=lambda item: item.path)
        ],
    }
    return yaml.safe_dump(
        payload,
        sort_keys=False,
        allow_unicode=True,
        width=200,
    )


def _expected_files(recipes: list[Recipe]) -> dict[Path, str]:
    return {Path(recipe.path): render_fixture(recipe) for recipe in recipes}


def _existing_files(corpus: Path) -> set[Path]:
    paths: set[Path] = set()
    for directory in CORPUS_DIRECTORIES:
        root = corpus / directory
        if root.is_dir():
            paths.update(
                path.relative_to(corpus)
                for path in root.rglob("*.yaml")
                if path.is_file()
            )
    return paths


def apply(
    corpus: Path,
    recipes: list[Recipe],
    *,
    check: bool,
    dry_run: bool,
    prune: bool,
) -> int:
    expected = _expected_files(recipes)
    existing = _existing_files(corpus)
    created = sorted(path for path in expected if not (corpus / path).exists())
    updated = sorted(
        path
        for path in expected
        if (corpus / path).exists()
        and (corpus / path).read_text(encoding="utf-8") != expected[path]
    )
    unchanged = sorted(set(expected) - set(created) - set(updated))
    stale = sorted(existing - set(expected))

    manifest_path = corpus / MANIFEST_NAME
    manifest = render_manifest(recipes)
    manifest_created = not manifest_path.exists()
    manifest_updated = (
        manifest_path.exists()
        and manifest_path.read_text(encoding="utf-8") != manifest
    )

    print(f"recipes: {len(recipes)}")
    print(f"fixtures created: {len(created)}")
    print(f"fixtures updated: {len(updated)}")
    print(f"fixtures unchanged: {len(unchanged)}")
    print(f"fixtures stale: {len(stale)}")
    if stale:
        for path in stale:
            print(f"  stale: {path}")
    print(
        "manifest: "
        + (
            "created"
            if manifest_created
            else "updated"
            if manifest_updated
            else "unchanged"
        )
    )
    by_directory = Counter(recipe.corpus for recipe in recipes)
    by_class = Counter(recipe.threat_class for recipe in recipes)
    print("by directory: " + ", ".join(
        f"{name}={by_directory[name]}" for name in CORPUS_DIRECTORIES
    ))
    print("by threat class: " + ", ".join(
        f"{name}={count}" for name, count in sorted(by_class.items())
    ))

    changed = bool(created or updated or stale or manifest_created or manifest_updated)
    if check:
        if changed:
            print("check failed: the committed corpus is out of date")
            return 1
        print("check passed: the committed corpus matches the pinned upstreams")
        return 0
    if dry_run:
        print("dry run: no files written")
        return 0

    for path, text in expected.items():
        destination = corpus / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists() or destination.read_text(encoding="utf-8") != text:
            destination.write_text(text, encoding="utf-8")
    if prune:
        for path in stale:
            (corpus / path).unlink()
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(manifest, encoding="utf-8")
    print(f"wrote {len(expected)} fixtures and {manifest_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--corpus",
        type=Path,
        default=DEFAULT_CORPUS,
        help="committed corpus root (default: tests/fixtures/screener-corpus)",
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=None,
        help="directory holding verified local clones of the three upstreams",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="refuse to make a network request",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero when the committed corpus is out of date",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report the changes without writing",
    )
    parser.add_argument(
        "--prune",
        action="store_true",
        help="delete committed fixtures that the recipe no longer produces",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    upstream = load_upstream(source_dir=args.source_dir, offline=args.offline)
    recipes = build_recipes(upstream)
    return apply(
        args.corpus,
        recipes,
        check=args.check,
        dry_run=args.dry_run,
        prune=args.prune,
    )


if __name__ == "__main__":
    raise SystemExit(main())
