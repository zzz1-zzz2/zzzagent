#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)"
workspace="${repo_root}/evals/workspaces/01-tqdm-bugfix"
revision="8cc777fe8401a05d07f2c97e65d15e4460feab88"
source_repo="https://github.com/tqdm/tqdm.git"

rm -rf -- "${workspace}"
mkdir -p -- "$(dirname -- "${workspace}")"
git clone --quiet --no-tags "${source_repo}" "${workspace}"
git -C "${workspace}" checkout --quiet --detach "${revision}"

# Keep the generated checkout focused on the task and avoid carrying local state.
git -C "${workspace}" clean -fdx --quiet

# The legacy tests use nose helpers; keep their dependencies inside the generated
# workspace instead of changing the developer's global Python environment.
uv venv --quiet "${workspace}/.eval-venv"
uv pip install --python "${workspace}/.eval-venv/bin/python" \
  --quiet pytest nose

printf 'Prepared %s at %s\n' "${workspace}" "${revision}"