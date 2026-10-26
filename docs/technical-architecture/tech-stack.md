# Tech stack

Overarching language, toolchain, and infrastructure choices for `llm-ingestion-screener`.

## Language and toolchain

| Concern | Choice | Notes |
|---|---|---|
| Language | Python 3.11+ | Targets the interpreter shipped with the workstation; no exotic features beyond 3.11. |
| Project/deps | `uv` | `uv sync` for the environment, `uv run` for the test command, `uv build` for wheels. |
| Tests | `pytest` | Single suite under `tests/`; the test command is the whole gate. |
| Types | `pyright` | Config in `pyrightconfig.json`; typed public API. |
| Build backend | `hatchling` | Wheel from `src/llm_ingestion_screener`. |

## Runtime dependencies

| Concern | Choice | Notes |
|---|---|---|
| Model endpoint | Local Ollama, System One API (`/v1/systemone`) | Offline-first; nothing leaves the machine. |
| Decision models | Clef (primary), Jev, Kev | Apache-2.0 (Clef); selected per the survey findings. |
| HTTP | Standard library `urllib` or a single small client | No heavy framework; the screener makes one shape of call. |

## Infrastructure

- **Host:** the operator's macOS workstation. No GPU assumed; Clef's latency numbers matter for the screening budget.
- **CI/CD:** none yet. Staging and production are both local wheel builds.
- **Observability:** structured screening logs written as JSON lines by the caller; no remote telemetry.

## Open decisions

- Numeric thresholds for the pattern rules and decision-model answers (gated by the survey and by an evaluation harness).
- Whether to ship a bundled local classifier as a second opinion alongside the decision models. See `docs/adr/`.
