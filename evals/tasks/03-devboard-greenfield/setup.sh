#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)"
workspace="${repo_root}/evals/workspaces/03-devboard-greenfield"

mkdir -p -- "${workspace}"
# Preserve the workspace directory itself so running setup from inside it does
# not leave the caller's shell attached to a deleted directory inode.
find "${workspace}" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
printf 'Prepared empty workspace at %s\n' "${workspace}"
