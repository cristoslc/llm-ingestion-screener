#!/usr/bin/env bash
# Run E2E checks against a staging instance created by deploy.sh.
#
# Usage: scripts/staging/e2e.sh <staging-dir>
# Exits 0 on pass, non-zero on failure.
set -euo pipefail

staging_dir="${1:?usage: e2e.sh <staging-dir>}"

if [ ! -x "$staging_dir/venv/bin/llm-ingestion-screener" ]; then
  echo "e2e.sh: no installed screener CLI under $staging_dir/venv" >&2
  exit 1
fi

output="$("$staging_dir/venv/bin/llm-ingestion-screener" --version)"
echo "e2e: $output"

case "$output" in
  "llm-ingestion-screener "*) ;;
  *)
    echo "e2e.sh: unexpected --version output: $output" >&2
    exit 1
    ;;
esac

echo "e2e: pass"
