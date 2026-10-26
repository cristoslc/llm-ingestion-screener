# Developer workflows

Build, test, deploy, and local-dev practice for `llm-ingestion-screener`. Spoke detail lives under [`developer-workflows/`](developer-workflows/README.md).

## Local setup

```bash
uv sync
```

This creates `.venv` and installs the package in editable mode with the dev dependency group.

## Build

```bash
uv build
```

Produces a wheel and sdist under `dist/`.

## Test

```bash
uv run pytest -q
```

`tests/` holds the suite. The test command is the whole gate: there is no separate lint gate. `pyright` runs on demand for type checking.

## Model endpoint (local prerequisite)

The screener calls a local Ollama endpoint's System One API. To try it locally:

```bash
ollama pull clef            # 27B decision model, ~18-20 GB
ollama run clef:cloud --ask "Is this safe to read?" < sample.txt
```

The screener never reaches a remote model. If the endpoint is missing or the model is absent, the screen fails loudly.

## Deploy (staging vs production)

The project follows the operator's two-stage pipeline mandate:

```bash
scripts/staging/deploy.sh <branch>          # build wheel into dist/staging/<branch>/, install into a venv
scripts/staging/e2e.sh dist/staging/<branch> # run the installed CLI, assert it works
scripts/staging/teardown.sh dist/staging/<branch>
```

Staging identity is the branch name. Production is a tagged release of the same wheel. See [`technical-architecture/c4/deployment.md`](technical-architecture/c4/deployment.md).

## CI/CD

None yet. All gates run locally.

## Branching and worktrees

- `main` is the only branch in the project root; every other branch lives in a worktree under `.worktrees/`.
- Work lands through a pull request. See [`CONTRIBUTING.md`](../CONTRIBUTING.md).

## Secrets

No secrets are required to run the screener locally. The model endpoint is unauthenticated on localhost. If an authenticated endpoint is ever needed, credentials go in a gitignored `.env`, never in the repository.
