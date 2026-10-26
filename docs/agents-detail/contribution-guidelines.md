# Contribution guidelines (agents)

What an agent must do differently when contributing to `llm-ingestion-screener`. The human-facing source of truth is [`CONTRIBUTING.md`](../../CONTRIBUTING.md); this spoke adds the agent-specific rules.

## Before you propose a change

1. Read [`AGENTS.md`](../../AGENTS.md), especially the rules about untrusted content and quarantine.
2. Confirm the change belongs to the **Screening** context or a clearly supporting one; do not leak model-API shapes outside **Decision Inquiry**.

## Test command before every pull request

Run the project test command and state its result in the PR body:

```bash
uv run pytest -q
```

A bug fix MUST arrive with a failing test written before the fix, plus reproduction steps.

## Worktree discipline

- `main` in the project root only; every branch lives in a worktree under `.worktrees/`.
- Never commit directly to `main`.

## Pull request conventions

- Follow `.github/PULL_REQUEST_TEMPLATE.md`.
- Add a `CHANGELOG.md` entry under `[Unreleased]`.
- Title in the imperative mood; body states what changed, why, and the test evidence.

## Untrusted-content handling in contributions

- Never commit raw hostile material. Quarantine fixtures are sanitised (or defanged) before they enter the repository.
- Do not paste a live injection payload into an issue, a PR description, or a chronicle comment without operator confirmation.

## What agents must not do without explicit operator authorization

- Merge a pull request, mark one ready for human review, request reviewers, or close an issue.
- Change a screening rule or threshold.
- Add or remove a dependency that fetches from the network at screen time.
