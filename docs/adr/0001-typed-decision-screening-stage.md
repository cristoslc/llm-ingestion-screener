# ADR-0001: Screen inbound material with typed decision-model questions

- **Status:** Proposed
- **Date:** 2026-10-25

## Context

An agent on this workstation was attacked by prompt injection embedded in results returned from prominent sources: the injected imperatives arrived in the same channel as the factual content, so an agent reading the page could not separate them by provenance alone. The defensive move that emerged was a pre-read safety screen over inbound material.

A screen has to run on every inbound document, which makes a chat-model judge expensive and slow. Meanwhile a family of decision ("System One") models — Clef, Jev, Kev — turns a state plus a schema of typed questions into scored answers in a single pass, at a reported median latency of a couple of hundred milliseconds, and its documented use cases include "moderate a tool call" and "check a condition". That is the shape a screen needs.

## Options considered

1. **Chat-model judge per document.** Flexible, but slow and costly per call, and it returns prose that must be parsed.
2. **Rules only.** Fast and deterministic, but brittle: it catches known patterns and misses novel phrasing.
3. **Typed decision-model questions, with rules first.** Rules take the cheap, high-precision passes; the decision model answers a small fixed schema of typed questions over the residue; a policy maps both to a verdict.
4. **A dedicated classifier model (injection-specific).** Potentially fast and cheap, but needs training data and maintenance, and is a separate stack to operate.

## Decision

Adopt option 3 as the screening architecture: deterministic rules first, then typed decision-model questions, then an explicit policy that maps evidence to a verdict level (`clean` | `flagged` | `quarantine`). The screener is a local-first Python component that never paraphrases suspicious text and never acts on it.

## Consequences

- The verdict schema is stable and machine-consumable, which makes screening cheap for callers.
- The whole system depends on a local decision-model endpoint; the endpoint becomes a workstation prerequisite.
- Thresholds become the main tuning surface, and they need an evaluation harness (fixtures with known verdicts) to tune responsibly.
- Whether the decision-model family actually earns its place for this task is the question the first work item — a survey of how System One models are used and how effective they are for input-material safety — must answer. If the survey says otherwise, this ADR is superseded.

## Open questions

- Which model in the family (Clef vs Jev vs Kev vs a smaller variant) is the right default for a screen budget.
- Whether a second, independent signal (a small classifier) materially improves recall on novel injections.
