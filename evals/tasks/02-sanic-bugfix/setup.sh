#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)"
workspace="${repo_root}/evals/workspaces/02-sanic-bugfix"
revision="e7001b00747b659f7042b0534802b936ee8a53e0"
source_repo="https://github.com/huge-success/sanic.git"

rm -rf -- "${workspace}"
mkdir -p -- "$(dirname -- "${workspace}")"
printf '[1/3] Fetching pinned Sanic revision...\n'
git init --quiet "${workspace}"
git -C "${workspace}" remote add origin "${source_repo}"
for attempt in 1 2 3; do
  if git -C "${workspace}" -c http.version=HTTP/1.1 fetch \
    --no-tags --depth=1 origin "${revision}"; then
    break
  fi
  if [[ "${attempt}" == 3 ]]; then
    printf 'Failed to fetch Sanic revision after %s attempts.\n' "${attempt}" >&2
    exit 1
  fi
  printf 'Fetch interrupted; retrying (%s/3)...\n' "$((attempt + 1))" >&2
done
git -C "${workspace}" checkout --quiet --detach FETCH_HEAD
git -C "${workspace}" clean -fdx --quiet

# The legacy checkout has old test dependencies. Keep them in the generated
# workspace and use non-interactive installation for reproducible setup.
printf '[2/3] Creating isolated Python environment...\n'
uv venv --quiet "${workspace}/.eval-venv"
printf '[3/3] Installing legacy test dependencies...\n'
uv pip install --python "${workspace}/.eval-venv/bin/python" \
  'pytest<6' 'httpx<0.12' 'httpcore<0.4' 'websockets<8' \
  'httptools<0.2' 'multidict<5' 'aiofiles<0.6'

# The 2020 checkout has optional native dependencies. Keep setup non-interactive.
printf 'Prepared %s at %s\n' "${workspace}" "${revision}"
