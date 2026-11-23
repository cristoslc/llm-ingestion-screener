"""Pinned upstream fetches for the committed benchmark-derived corpus.

Every upstream is addressed by a full commit SHA, never a branch or tag. The
script refuses to continue when a pin is missing or malformed. Fetched bytes
are checked against a recorded SHA-256 so a changed upstream file cannot slip
into a regenerated fixture without a reviewer noticing.

This module is a maintenance tool. The test suite never imports it and never
makes a network call.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
import subprocess
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import yaml

RAW_BASE = "https://raw.githubusercontent.com"
FETCH_TIMEOUT_SECONDS = 60
SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")
COMMIT_HEX = re.compile(r"^[0-9a-f]{40}$")

# Pinned 2026-11-23. These are the commits the committed fixtures were
# distilled from. A new corpus change pins a new SHA deliberately.
PINS: Mapping[str, str] = {
    "ethz-spylab/agentdojo": "089ed468cf3ed0322acc66b0211f26d9d90dbf60",
    "microsoft/BIPIA": "a004b69ec0dd446e0afd461d98cb5e96e120a5d0",
    "lzwhehe/benign-instruction-bench": "5d0ae7c438a7b01be2ac0a2e8bc943e45c8f851f",
}

# The source files the distiller reads. Digests are of the pinned blob, not of
# a rendered page.
UPSTREAM_FILES: Mapping[str, tuple[str, ...]] = {
    "ethz-spylab/agentdojo": (
        "src/agentdojo/attacks/important_instructions_attacks.py",
        "src/agentdojo/attacks/baseline_attacks.py",
        "src/agentdojo/default_suites/v1/workspace/injection_tasks.py",
        "src/agentdojo/default_suites/v1/banking/injection_tasks.py",
        "src/agentdojo/default_suites/v1/slack/injection_tasks.py",
        "src/agentdojo/default_suites/v1/travel/injection_tasks.py",
        "src/agentdojo/data/suites/workspace/include/inbox.yaml",
        "src/agentdojo/data/suites/workspace/include/cloud_drive.yaml",
        "src/agentdojo/data/suites/workspace/include/calendar.yaml",
        "src/agentdojo/data/suites/banking/environment.yaml",
        "src/agentdojo/data/suites/travel/environment.yaml",
        "src/agentdojo/data/suites/slack/environment.yaml",
    ),
    "microsoft/BIPIA": (
        "benchmark/text_attack_train.json",
        "benchmark/text_attack_test.json",
        "README.md",
        "LICENSE",
    ),
    "lzwhehe/benign-instruction-bench": (
        "README.md",
        "scripts/build_corpus.py",
        "LICENSE",
    ),
}

UPSTREAM_DIGESTS: Mapping[str, str] = {
    "ethz-spylab/agentdojo/src/agentdojo/attacks/important_instructions_attacks.py": (
        "519f24e0b9d72f43343d665679adacc33758b50cd1b586a81fa53fb098dcfe71"
    ),
    "ethz-spylab/agentdojo/src/agentdojo/attacks/baseline_attacks.py": (
        "0e3f3cec2173524989d67bd3d934d032774ad3fc5995969c9565613efaa21c6d"
    ),
    "ethz-spylab/agentdojo/src/agentdojo/default_suites/v1/workspace/injection_tasks.py": (
        "03e0894ffb544a79fd0bfd2c62cc5f90b19a2b1d429068d800239bfd020b6dcc"
    ),
    "ethz-spylab/agentdojo/src/agentdojo/default_suites/v1/banking/injection_tasks.py": (
        "fa2dedf8e66c95ffadb54f5a26648728b08c56f302858de4ee9a5cc0b3891618"
    ),
    "ethz-spylab/agentdojo/src/agentdojo/default_suites/v1/slack/injection_tasks.py": (
        "d5775da1689e13192b665837e72cee88ed76f622e9b998e9def18b700fdc5afc"
    ),
    "ethz-spylab/agentdojo/src/agentdojo/default_suites/v1/travel/injection_tasks.py": (
        "9252be834b0ae0e28fe06744e052987d71d8ad3666b8d0b1f65f2875f998fca8"
    ),
    "ethz-spylab/agentdojo/src/agentdojo/data/suites/workspace/include/inbox.yaml": (
        "e6fac364bfb0e89d3d0251ef8079ffa2791504673a426029034356b8228f2082"
    ),
    "ethz-spylab/agentdojo/src/agentdojo/data/suites/workspace/include/cloud_drive.yaml": (
        "a9731cd49fe7eb726e43c1727c40eff0d6ca2d85d53728aa744860a8c4214130"
    ),
    "ethz-spylab/agentdojo/src/agentdojo/data/suites/workspace/include/calendar.yaml": (
        "69b0ae96804e986b5a0dba694ad6ca34cf01c8c6b57bb8ceb618d9ed8640b803"
    ),
    "ethz-spylab/agentdojo/src/agentdojo/data/suites/banking/environment.yaml": (
        "3f539da1d97779b244cd122afc683dc69d602f338e1b3c42d126cbde33611c8b"
    ),
    "ethz-spylab/agentdojo/src/agentdojo/data/suites/travel/environment.yaml": (
        "ca8ef591bde5a8d8b9e2efe6830b8e4646c43f633c86f14cb878f588bb4b8a3c"
    ),
    "ethz-spylab/agentdojo/src/agentdojo/data/suites/slack/environment.yaml": (
        "0ea2f9b83e5ffaae0bf50fab2b13d6c8ee59a952f791b16c9554fdc48935c87d"
    ),
    "microsoft/BIPIA/benchmark/text_attack_train.json": (
        "63f95d3e67eac4178cdabdbdaf192cd05f2b6ed0702b578f1d30d556e5155670"
    ),
    "microsoft/BIPIA/benchmark/text_attack_test.json": (
        "75750e7b4e8b34e8f9d88d89b357aeaaf02bd07f9e493ccd37eda74a0cd7c7f8"
    ),
    "microsoft/BIPIA/README.md": (
        "9fce640c22ae3277c83f31711044a90e64627501345c9ceb142b14167f07d47c"
    ),
    "microsoft/BIPIA/LICENSE": (
        "57cf81c45e0929899bc18051cf90134f00e55963ddecc7b37cfc5ea1494b1e8b"
    ),
    "lzwhehe/benign-instruction-bench/README.md": (
        "5d6318e09d748a40a150bb2413538feca33aef1f2dc5068e03b30a33ea755f3d"
    ),
    "lzwhehe/benign-instruction-bench/scripts/build_corpus.py": (
        "c3ef2d2379c0d4cec56f424acde9b2bc8370e28c2c3efc4623fd00f914373d09"
    ),
    "lzwhehe/benign-instruction-bench/LICENSE": (
        "2b185e9a91997eeb0eb17ff9efcb043a9912633983978f00e40dfac27782d394"
    ),
}

# Upstream f-string constants are rendered to inert human-readable values. No
# placeholder resolves to a live host, secret, or executable target.
PLACEHOLDERS: Mapping[str, str] = {
    "_TEXT": "the meeting notes",
    "_RECIPIENT": "the address in the footer",
    "_SUBJECT": "the project update",
    "_FILE_ID": "13",
    "_PARTICIPANT": "the project team",
    "_START_TIME": "May 1st",
    "_TITLE": "Project sync",
    "_SENDER": "the travel agency",
    "_ATTACKER_IBAN": "the account in the footer",
    "ATTACKER_IBAN": "the account in the footer",
    "_NEW_PASSWORD": "a new password",
    "_PHISHING_LINK": "http://example.invalid/link",
    "_ATTACKER_WEB": "http://example.invalid/collect",
    "_TARGET": "the Riverside View Hotel",
    "_ATTACKER_USER": "the new user",
    "_ATTACKER_EMAIL": "new.user@example.invalid",
    "_EMAIL_SUBJECT": "Quarterly summary",
    "_EMAIL_BODY": "Please review the attached summary.",
}


def assert_pins(pins: Mapping[str, str] | None = None) -> None:
    """Refuse to run when any pin is absent or not a full commit SHA."""

    selected = PINS if pins is None else pins
    if not selected:
        raise SystemExit("no upstream pins are configured")
    missing = sorted(set(UPSTREAM_FILES) - set(selected))
    if missing:
        raise SystemExit(
            "upstream pin(s) are missing: " + ", ".join(missing)
        )
    for repository, commit in selected.items():
        if not isinstance(repository, str) or not repository.strip():
            raise SystemExit("every upstream pin needs a repository name")
        if not isinstance(commit, str) or not COMMIT_HEX.match(commit):
            raise SystemExit(
                f"upstream pin for {repository!r} must be a full 40-character "
                f"commit SHA, got {commit!r}"
            )
        if repository not in UPSTREAM_FILES:
            raise SystemExit(f"upstream pin for {repository!r} has no file list")


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_local(source_dir: Path, repository: str, path: str) -> bytes:
    local = source_dir / repository.rsplit("/", 1)[-1] / path
    if not local.is_file():
        raise SystemExit(f"local upstream file is missing: {local}")
    return local.read_bytes()


def _verify_local_head(source_dir: Path, repository: str, commit: str) -> None:
    local = source_dir / repository.rsplit("/", 1)[-1]
    if not (local / ".git").exists():
        raise SystemExit(f"local upstream checkout has no .git: {local}")
    actual = subprocess.run(
        ["git", "-C", str(local), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if actual != commit:
        raise SystemExit(
            f"local upstream {repository} is at {actual}, pinned {commit}"
        )


def _fetch_remote(repository: str, commit: str, path: str) -> bytes:
    url = f"{RAW_BASE}/{repository}/{commit}/{path}"
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "llm-ingestion-screener-corpus-distiller"},
    )
    try:
        with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT_SECONDS) as response:
            return response.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise SystemExit(f"could not fetch {url}: {exc}") from exc


@dataclass(frozen=True)
class Upstream:
    """Read-only access to the pinned upstream material."""

    pins: Mapping[str, str]
    files: Mapping[str, bytes]

    def text(self, repository: str, path: str) -> str:
        key = f"{repository}/{path}"
        if key not in self.files:
            raise SystemExit(f"upstream file was not fetched: {key}")
        return self.files[key].decode("utf-8")

    def json(self, repository: str, path: str) -> object:
        return json.loads(self.text(repository, path))

    def yaml(self, repository: str, path: str) -> object:
        return yaml.safe_load(self.text(repository, path))

    def agentdojo_goal(self, suite: str, task: str) -> str:
        path = (
            f"src/agentdojo/default_suites/v1/{suite}/injection_tasks.py"
        )
        tree = ast.parse(self.text("ethz-spylab/agentdojo", path))
        for node in tree.body:
            if not isinstance(node, ast.ClassDef) or node.name != task:
                continue
            for statement in node.body:
                if not isinstance(statement, ast.Assign):
                    continue
                if not any(
                    isinstance(target, ast.Name) and target.id == "GOAL"
                    for target in statement.targets
                ):
                    continue
                return _render_goal(statement.value)
        raise SystemExit(f"no GOAL found for {suite}/{task}")

    def bipia_attack(self, split: str, category: str, index: int) -> str:
        path = f"benchmark/text_attack_{split}.json"
        payload = self.json("microsoft/BIPIA", path)
        if not isinstance(payload, Mapping) or category not in payload:
            raise SystemExit(f"no BIPIA category {category!r} in {split}")
        samples = payload[category]
        if not isinstance(samples, list) or not 0 <= index < len(samples):
            raise SystemExit(
                f"no BIPIA sample {category}/{index} in {split}"
            )
        sample = samples[index]
        if not isinstance(sample, str):
            raise SystemExit("BIPIA attack samples must be strings")
        return sample


def _render_goal(node: ast.expr) -> str:
    if isinstance(node, ast.Constant):
        return str(node.value)
    if isinstance(node, ast.JoinedStr):
        parts: list[str] = []
        for value in node.values:
            if isinstance(value, ast.Constant):
                parts.append(str(value.value))
            elif isinstance(value, ast.FormattedValue):
                expression = ast.unparse(value.value).strip("{}")
                parts.append(PLACEHOLDERS.get(expression, "the value in the footer"))
        return "".join(parts)
    try:
        return str(ast.literal_eval(node))
    except (ValueError, SyntaxError):
        return ast.unparse(node)


def load_upstream(
    *,
    source_dir: Path | None = None,
    offline: bool = False,
) -> Upstream:
    """Fetch every pinned file, or read a verified local checkout."""

    assert_pins()
    files: dict[str, bytes] = {}
    for repository, commit in PINS.items():
        if source_dir is not None:
            _verify_local_head(source_dir, repository, commit)
        for path in UPSTREAM_FILES[repository]:
            key = f"{repository}/{path}"
            if source_dir is not None:
                data = _read_local(source_dir, repository, path)
            elif offline:
                raise SystemExit(
                    "no --source-dir was supplied and --offline forbids a fetch"
                )
            else:
                data = _fetch_remote(repository, commit, path)
            expected = UPSTREAM_DIGESTS.get(key)
            if expected is None or not SHA256_HEX.match(expected):
                raise SystemExit(f"no recorded digest for upstream file {key}")
            actual = _digest(data)
            if actual != expected:
                raise SystemExit(
                    f"upstream file {key} has digest {actual}, expected {expected}"
                )
            files[key] = data
    return Upstream(pins=dict(PINS), files=files)
