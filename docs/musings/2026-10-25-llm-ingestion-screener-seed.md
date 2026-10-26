# 2026-10-25 — Seed: an ingestion screener built on System One models

## Where this came from

The operator asked for a new project, `llm-ingestion-screener`, inspired by two things at once:

1. **Clef** (https://ollama.com/library/clef) — Cloudflare's 27B multimodal decision model on Ollama, Apache-2.0, served through the `/v1/systemone` endpoint. You hand it a `state` and a schema of typed `questions` (`noul` for yes/no, `choice` for labels, `score` for levels) and it answers every option of every question jointly in one non-autoregressive pass, returning probabilities. Its documented uses include routing, condition checks, policy application, document reading, and **"moderate a tool call"** — judging whether a call is harmful before it runs. Jev and Kev are the siblings in the same decision-model family.

2. **A firsthand incident.** In thread `thr_etqsy4sqzx` (Learning Systems Orchestrator), a research agent hit prompt injection embedded in results returned from prominent sources. The operator's standing response was a mandatory pre-read safety screen: subagents read and screen pages, and the orchestrator only ever reads screened summaries. That manual protocol is exactly what a screener productises.

## The idea in one line

A local, cheap screening stage that judges inbound material (fetched pages, search results, documents, third-party skills, tool output) with typed decision-model questions plus deterministic rules, and returns a typed verdict — `clean`, `flagged`, or `quarantine` — before an agent reads it.

## Open threads to pull

- **Does the model family actually earn its keep here?** Hence the first work item: a depth:3 survey of how Clef, Jev, Kev, and other System One models are being used and how effective they are for input-material safety.
- **What is the question schema?** A small, stable set of `noul`/`choice`/`score` questions is the core design artifact. Rules first, model on the residue.
- **Where is the boundary between rules and model?** Rules for known markers, model for novel phrasing.
- **What is the caller contract?** One call, one verdict, with evidence; failed screens are loud.
- **Thresholds need an evaluation harness.** Fixtures with known verdicts, scored over time.

## Related prior art on this workstation

- `~/Documents/code/jev-thread-classifiers/` — a research project on embedding Jev-like classifiers inside a bb thread workflow. Same model family, different application (workflow triage rather than safety screening).
- `~/.agents/agents-md-detail/tool-usage/llm-vision-dispatch.md` — the operator's pattern for routing non-vision work to a vision model; a similar "route the cheap decision" shape.
