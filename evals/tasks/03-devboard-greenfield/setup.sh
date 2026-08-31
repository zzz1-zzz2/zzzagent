#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)"
workspace="${repo_root}/evals/workspaces/03-devboard-greenfield"

rm -rf -- "${workspace}"
mkdir -p -- "${workspace}"
printf 'Prepared empty workspace at %s\n' "${workspace}"
