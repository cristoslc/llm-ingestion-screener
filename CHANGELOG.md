# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Project scaffold: PURPOSE, README, AGENTS, docs tree (technical and domain surfaces), Python package skeleton, test suite, and the two-stage staging scripts.
- `llm-ingestion-screener --version` CLI entry point.
- Survey and addendum on how the System One decision-model family is used for input-material safety, the baseline tooling to benchmark against, and drydock's detection eval harness as prior art (`docs/surveys/`). Committed payload text is sanitised; live payload strings are withheld.
- ADR-0002: adopt a two-corpus detection eval harness (drydock's shape, two starting gates) and define the screener as a filter, with the matching `PURPOSE.md` posture line.
