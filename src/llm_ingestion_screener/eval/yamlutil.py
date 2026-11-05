"""Strict YAML loading for committed eval state files."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import yaml

from llm_ingestion_screener.errors import EvaluationError


class StrictLoader(yaml.SafeLoader):
    """A SafeLoader that rejects duplicate mapping keys instead of hiding them."""


def _construct_mapping(loader: StrictLoader, node: yaml.Node) -> dict[object, object]:
    mapping: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=True)
        if key in mapping:
            raise EvaluationError(
                f"duplicate YAML key {key!r} at line {key_node.start_mark.line + 1}"
            )
        mapping[key] = loader.construct_object(value_node, deep=True)
    return mapping


StrictLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping,
)


def load_yaml_mapping(path: str | Path, description: str) -> Mapping[object, object]:
    """Read one YAML mapping, raising :class:`EvaluationError` on any problem."""

    yaml_path = Path(path)
    try:
        text = yaml_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise EvaluationError(
            f"could not read {description} {yaml_path}: {exc}"
        ) from exc
    try:
        raw = yaml.load(text, Loader=StrictLoader)  # noqa: S506 - SafeLoader subclass
    except EvaluationError:
        raise
    except yaml.YAMLError as exc:
        raise EvaluationError(
            f"{description} {yaml_path} is not valid YAML: {exc}"
        ) from exc
    if not isinstance(raw, Mapping):
        raise EvaluationError(f"{description} {yaml_path} must be a YAML mapping")
    return raw
