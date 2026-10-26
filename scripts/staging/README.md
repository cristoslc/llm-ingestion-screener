# scripts/staging/

Two-stage pipeline scripts for `llm-ingestion-screener`.

The screener ships as a Python CLI/library, so it has no long-running service to
deploy. Its release candidate is a **built wheel installed into an isolated
virtual environment**, which is what these scripts stand up.

| Script | Purpose |
|---|---|
| `deploy.sh <branch>` | Builds a wheel from the working tree into `dist/staging/<branch>/` and installs it into a fresh venv. Prints the staging directory. |
| `e2e.sh <staging-dir>` | Runs the installed CLI in the staging venv and asserts it reports a version. Exits non-zero on failure. |
| `teardown.sh <staging-dir>` | Removes the staging directory. |

Staging identity is the branch name, per the operator's two-stage pipeline
mandate (`~/.agents/agents-md-detail/two-stage-pipelines.md`). Production is a
tagged release of the same wheel; there is no separate production host yet.

## Manual run

```bash
scripts/staging/deploy.sh my-branch
scripts/staging/e2e.sh dist/staging/my-branch
scripts/staging/teardown.sh dist/staging/my-branch
```
