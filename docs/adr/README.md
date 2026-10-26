# Architecture decision records

Numbered records of decisions that shaped `llm-ingestion-screener`, one file per decision.

## Convention

- Filename: `NNNN-decision-title.md`, four-digit zero-padded number, kebab-case title.
- Each record holds: status, context, options considered, decision, and consequences.
- Status lifecycle: `Proposed` → `Adopted` → `Superseded by NNNN`.

## Index

| ADR | Title | Status |
|---|---|---|
| [0001](0001-typed-decision-screening-stage.md) | Screen inbound material with typed decision-model questions | Proposed |
| [0002](0002-detection-eval-harness-and-filter-posture.md) | Adopt a two-corpus detection eval harness; screen as a filter | Adopted |
