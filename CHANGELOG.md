# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Project scaffold: PURPOSE, README, AGENTS, docs tree (technical and domain surfaces), Python package skeleton, test suite, and the two-stage staging scripts.
- `llm-ingestion-screener --version` CLI entry point.
- Survey and addendum on how the System One decision-model family is used for input-material safety, the baseline tooling to benchmark against, and drydock's detection eval harness as prior art (`docs/surveys/`). Committed payload text is sanitised; live payload strings are withheld.
- ADR-0002: adopt a two-corpus detection eval harness (drydock's shape, two starting gates) and define the screener as a filter, with the matching `PURPOSE.md` posture line.
- Accepted the detection eval-harness plan (`docs/plans/2026-10-29-ingestion-screener-eval-harness.md`): a pytest-native, offline-by-default harness with five gates, recall gated on the golden and eval corpora, and the frontier set reported separately.
- Screener core (Phase 1): a deterministic rule engine with stable documented rule ids, the typed `noul`/`choice`/`score` question schema, an explicit-threshold policy, immutable verdict assembly with verbatim quarantined passages, and an append-only screening log.
- Decision-model clients (Phase 1): recorded cassette replay, a live Ollama `/v1/systemone` client for clef-flash, and a fault-injection client; one clearly synthetic cassette; the `model` pytest marker is registered and deselected by default so `uv run pytest -q` stays offline.
- Detection eval harness (Phase 2): a YAML fixture loader and validator, a runner that drives the production `screen()` through the recorded client, a hand-rolled metrics engine, the committed gate registry at `tests/eval/gates.yaml`, the committed baseline at `tests/eval/baseline.json`, a Markdown and JSON report writer, the `python -m llm_ingestion_screener.eval run` CLI, and a sanitised starter corpus with per-fixture provenance.
- `PyYAML` in the `dev` dependency group for fixture parsing; the runtime dependency list stays empty.
- Phase 3 corpus: 115 committed-derived fixtures (5 golden, 56 eval, 20 frontier, 32 benign, 2 transforms) distilled from pinned AgentDojo, BIPIA, and benign-instruction-bench revisions, with every malicious taxonomy class at eight samples or more and every benign class at six or more.
- A pinned fetch-and-distil maintenance script under `scripts/corpus/`, a committed corpus manifest at `tests/fixtures/screener-corpus/manifest.yaml`, and a corpus README that records the directory jobs, sanitisation policy, and the BIPIA context-task exclusion.
- Manifest-aware corpus loading: a missing or extra row, an unpinned benchmark fixture, or a provenance line that does not name its commit fails the run loudly.
- Raised corpus-coverage floors in `tests/eval/gates.yaml` and a regenerated baseline and synthetic eval cassette for the Phase 3 corpus.
- Phase 4 evasion transforms: all four named transforms (`split-string-literals`, `bracketify-member-access`, `base64-wrap`, `push-past-window`) at eight derived fixtures each, produced by named rewrites in the corpus distiller from real base fixtures, and a corpus floor of 32 in `tests/eval/gates.yaml`.
- Per-transform evasion reporting: blocked rate, rule retention, defeated rule ids, and still-firing rules for each transform, in the Markdown report and the JSON metrics; the corpus README and eval-harness doc explain how to read both numbers. No rule or threshold changed.
- Corpus manifest format `v2`: every row records `derived_from` and `transform`, the loader cross-checks them against the fixture, and an unknown transform name or a transform row without its base is rejected.
- Loader rejects an unknown transform name, a transform fixture stored under the wrong transform directory, and a transform derived from a benign or missing base; a regenerated baseline and synthetic eval cassette cover the Phase 4 corpus.

### Changed

- Hardened `rule.exfiltration-request`: the directive frame now reaches a destination assembled from adjacent `+`-joined pieces, with single-quoted, double-quoted, bare, or variable fragments and an optionally split scheme, as well as a contiguous URL. The rule id, level, and directive frame are unchanged.
- Hardened `rule.encoded-execution`: a decode or execute primitive reached through a bracket index on `window`, `globalThis`, `self`, or `global` now matches, with a quoted, variable, or numeric key. The plain call forms and the base64 decode command still match. The rule id and level are unchanged.
- Regenerated the 16 transform fixtures whose notes and `expect_any_rule` recorded the old defeats, and regenerated the baseline. The two transforms now block 8 of 8 with full rule retention, so the overall evasion blocked rate is 1.0000 (32 of 32) and rule retention is 1.0000 (34 of 34). No gate value moved.
