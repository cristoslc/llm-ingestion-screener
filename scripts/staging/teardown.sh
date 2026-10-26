#!/usr/bin/env bash
# Destroy a staging instance created by deploy.sh.
#
# Usage: scripts/staging/teardown.sh <staging-dir>
set -euo pipefail

staging_dir="${1:?usage: teardown.sh <staging-dir>}"

if [ ! -d "$staging_dir" ]; then
  echo "teardown.sh: nothing to remove at $staging_dir"
  exit 0
fi

rm -rf "$staging_dir"
echo "teardown: removed $staging_dir"
