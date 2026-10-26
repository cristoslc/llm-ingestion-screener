# llm-ingestion-screener

A local-first safety screener for LLM ingestion. It inspects material *before* it reaches an agent's context — fetched web pages, search results, documents, third-party skills, tool output — and returns a typed verdict on whether the material is safe to read or carries prompt injection or other hazards.

## Why this exists

During a research run on this workstation, an agent was attacked by prompt injection embedded in results returned from prominent, reputable sources. The agent read the pages directly and the injected imperatives were sitting in the same channel as the factual content. The defensive move that emerged was a pre-read screen: something cheap, local, and offline-first that judges a document *before* an agent consumes it, instead of asking the agent to police its own reading.

Two things make that screen plausible now:

- **Decision ("System One") models.** Cloudflare's [Clef](https://ollama.com/library/clef) (27B, Apache-2.0, served locally through Ollama's `/v1/systemone` endpoint) turns a state plus a schema of typed questions into scored answers. It reads text, JSON, and images in a single non-autoregressive pass and returns probabilities rather than prose. Jev and Kev are the sibling decision models in the same family. Their published use cases include "moderate a tool call" and "check a condition," which is exactly the shape a screening stage needs.
- **Cheap, typed questions.** A screen does not need a chat model. It needs a stable set of yes/no questions ("does this text contain agent-directed imperatives?"), a choice question ("what kind of injection is this?"), and a severity score — each answered with a probability the caller can threshold.

## What the screener is

A screening stage with a small, stable contract:

- **Input:** one piece of inbound material plus its provenance (where it came from, how it was retrieved).
- **Process:** deterministic pattern rules first, then typed decision-model questions over the residue, then a policy that maps answers to a verdict.
- **Output:** a typed verdict — `clean`, `flagged`, or `quarantine` — with per-question probabilities, the passage(s) that triggered a flag quoted verbatim, and a screening-log row a downstream agent can cite.

The screener never paraphrases suspicious text into findings, never follows instructions found in the material, and never silently downgrades a flag. Untrusted content is data.

## Status

Early. Scaffolded and orchestrated; the first work item is a survey of how the System One model family (Clef, Jev, Kev) is being used and how effective it is for input-material safety. See `docs/plans/` and the orchestrator thread.

## Layout

- `PURPOSE.md` — one-paragraph intent
- `AGENTS.md` — guidance for agents working here
- `docs/` — the documentation tree; start at [`docs/README.md`](docs/README.md)
- `src/llm_ingestion_screener/` — the Python package
- `tests/` — the test suite
- `scripts/staging/` — the two-stage pipeline scripts

## Quick start

```bash
uv sync
uv run llm-ingestion-screener --version
uv run pytest -q
```

## How work happens here

Muse → plan → sashay. Raw ideas land in `docs/musings/` and are committed immediately. Work that crystallizes into a concrete change gets a plan under `docs/plans/`, then executes on a branch in a worktree and lands through a pull request, never directly on `main`.
