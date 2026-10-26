# Domain events

Integration events that cross bounded context boundaries in `llm-ingestion-screener`. Internal domain events within a single context belong in that context's leaf, not here.

Contract specs (payload shape) live under [`events/`](events/README.md).

## `ScreeningRequested`

- **Producing context:** Caller Integration
- **Consuming context:** Screening
- **Payload:** material reference, provenance, requested policy profile
- **Delivery:** in-process function call today; a queue or bus later if screening becomes asynchronous

## `VerdictIssued`

- **Producing context:** Screening
- **Consuming contexts:** Caller Integration, Recall Evaluation
- **Payload:** verdict level, per-question answers with probabilities, rule hits, quarantined passages (verbatim, with source), screening-log row
- **Delivery:** in-process return value; appended to the screening log as a JSON line

## `FixtureRecorded`

- **Producing context:** Recall Evaluation
- **Consuming context:** Screening
- **Payload:** fixture id, material reference, expected verdict
- **Delivery:** in-process; fixtures are files in the evaluation set

## Naming note

Events are named in the past tense and describe a decision or a fact, never a command. `VerdictIssued`, not `IssueVerdict`.
