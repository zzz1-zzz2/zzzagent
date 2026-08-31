#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)"
workspace="${repo_root}/evals/workspaces/02-sanic-bugfix"
revision="e7001b00747b659f7042b0534802b936ee8a53e0"
source_repo="https://github.com/huge-success/sanic.git"

rm -rf -- "${workspace}"
mkdir -p -- "$(dirname -- "${workspace}")"
git clone --quiet --no-tags "${source_repo}" "${workspace}"
git -C "${workspace}" checkout --quiet --detach "${revision}"
git -C "${workspace}" clean -fdx --quiet

# The legacy checkout has old test dependencies. Keep them in the generated
# workspace and use non-interactive installation for reproducible setup.
uv venv --quiet "${workspace}/.eval-venv"
uv pip install --python "${workspace}/.eval-venv/bin/python" \
  --quiet \
  'pytest<6' 'httpx<0.12' 'httpcore<0.4' 'websockets<8' \
  'httptools<0.2' 'multidict<5' 'aiofiles<0.6'

# The 2020 checkout has optional native dependencies. Keep setup non-interactive.
printf 'Prepared %s at %s\n' "${workspace}" "${revision}"
