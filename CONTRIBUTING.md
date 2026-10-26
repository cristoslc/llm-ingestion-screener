# Contributing to llm-ingestion-screener

This project is owned by the operator and follows the operator's standards. This file is the source of truth for how contributions are made; both human and agent contributors follow it.

## Before you start

- Read [`PURPOSE.md`](PURPOSE.md) and [`AGENTS.md`](AGENTS.md).
- Read [`docs/agents-detail/contribution-guidelines.md`](docs/agents-detail/contribution-guidelines.md) if you are an agent.

## Test command

Every change must pass the project test command before it is proposed:

```bash
uv run pytest -q
```

## Remotes

Two remotes, following the operator's forge convention (`~/.agents/agents-md-detail/cove.md`):

- `origin` — <https://github.com/cristoslc/llm-ingestion-screener> — the primary collaboration forge. Issues and pull requests live here.
- `fj` — `ssh://git@git.cove.local:2222/cristos/llm-ingestion-screener.git` — the local Cove/Forgejo mirror and backup.

`main` tracks `origin/main`. Push to `origin` first, then mirror to `fj`:

```bash
git push origin <branch> && git push fj <branch>
```

## How to open an issue

- **Bugs** use the bug report template (`.github/ISSUE_TEMPLATE/bug_report.yml`). A bug report must include the environment, reproduction steps, the expected result, the actual result, and any workarounds. A section with nothing to report is filled with "None", never omitted.
- **Features and enhancements** use the feature request template (`.github/ISSUE_TEMPLATE/feature_request.yml`). Problem leads; the solution follows.
- Behaviour that contradicts the documentation is a bug, not a feature request.

## How to open a pull request

- Work on a branch, never directly on `main`. Branches live in worktrees under `.worktrees/`.
- Name branches descriptively (`feat/…`, `fix/…`, `docs/…`, `chore/…`).
- Follow the pull request template (`.github/PULL_REQUEST_TEMPLATE.md`).
- Add a `CHANGELOG.md` entry under `[Unreleased]` for every user-visible change.
- Keep commits focused; write commit messages in the imperative mood.
- Do not weaken or skip pre-commit hooks.

## Agent contributions

- Agent-originated fixes MUST arrive with reproduction steps and a failing test written before the fix.
- The project test command must be run before the pull request is proposed, and its result stated in the PR body.
- Agents must not merge, mark ready for human review, request reviewers, or close issues without explicit operator authorization.

## Review and merge policy

- The operator reviews and merges. A pull request is proposed, not merged, by its author.
- A contribution is merged when the test command passes, the changelog entry exists, and the operator approves.

## Sign-off

This project does not require a DCO or CLA sign-off today. If that changes, it is recorded here and in an ADR.
