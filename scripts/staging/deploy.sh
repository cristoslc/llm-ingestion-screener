#!/usr/bin/env bash
# Deploy the current branch to staging.
#
# Staging identity is the branch name. For this project the "staging target" is
# a built wheel plus an isolated virtual environment, not a running service:
# the screener ships as a CLI/library, so a release candidate is a wheel that
# installs and runs in a clean environment.
#
# Usage: scripts/staging/deploy.sh <branch>
# Prints the staging artifact identifier (a directory path) to stdout.
set -euo pipefail

branch="${1:?usage: deploy.sh <branch>}"
safe_branch="$(printf '%s' "$branch" | tr '/' '-' | tr -cd 'A-Za-z0-9._-')"

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
staging_dir="$repo_root/dist/staging/$safe_branch"

rm -rf "$staging_dir"
mkdir -p "$staging_dir"

cd "$repo_root"
uv build --wheel --out-dir "$staging_dir"

wheel="$(find "$staging_dir" -maxdepth 1 -name '*.whl' | head -n 1)"
if [ -z "$wheel" ]; then
  echo "deploy.sh: no wheel produced in $staging_dir" >&2
  exit 1
fi

uv venv --clear "$staging_dir/venv"
uv pip install --python "$staging_dir/venv/bin/python" "$wheel"

echo "$staging_dir"
