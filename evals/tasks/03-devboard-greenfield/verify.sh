#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)"
workspace="${repo_root}/evals/workspaces/03-devboard-greenfield"

if [[ ! -d "${workspace}" ]]; then
  printf 'FAIL: workspace is missing; run setup.sh first\n' >&2
  exit 2
fi
if [[ ! -f "${workspace}/package.json" ]]; then
  printf 'FAIL: package.json is missing\n' >&2
  exit 1
fi

if ! node --version >/dev/null 2>&1 || ! npm --version >/dev/null 2>&1; then
  printf 'FAIL: node and npm are required for the DevBoard verifier\n' >&2
  exit 2
fi

cd -- "${workspace}"
if [[ ! -d node_modules ]]; then
  npm install --no-audit --no-fund --ignore-scripts --yes
fi
npm run build
