#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)"
workspace="${repo_root}/evals/workspaces/01-tqdm-bugfix"
revision="8cc777fe8401a05d07f2c97e65d15e4460feab88"
source_repo="https://github.com/tqdm/tqdm.git"

rm -rf -- "${workspace}"
mkdir -p -- "$(dirname -- "${workspace}")"
git init --quiet "${workspace}"
git -C "${workspace}" remote add origin "${source_repo}"

# The evaluation is pinned to one commit, so avoid downloading the repository's
# complete history. HTTP/1.1 is more reliable through common local proxies, and
# a short retry loop makes the recording setup resilient to transient drops.
for attempt in 1 2 3; do
  if git -C "${workspace}" -c http.version=HTTP/1.1 fetch \
    --quiet --no-tags --depth=1 origin "${revision}"; then
    break
  fi
  if [[ "${attempt}" == 3 ]]; then
    printf 'Failed to fetch tqdm revision after %s attempts.\n' "${attempt}" >&2
    exit 1
  fi
  printf 'Fetch interrupted; retrying (%s/3)...\n' "$((attempt + 1))" >&2
done
git -C "${workspace}" checkout --quiet --detach FETCH_HEAD

# Keep the generated checkout focused on the task and avoid carrying local state.
git -C "${workspace}" clean -fdx --quiet

# The legacy tests use nose helpers; keep their dependencies inside the generated
# workspace instead of changing the developer's global Python environment.
uv venv --quiet "${workspace}/.eval-venv"
uv pip install --python "${workspace}/.eval-venv/bin/python" \
  --quiet pytest nose

printf 'Prepared %s at %s\n' "${workspace}" "${revision}"
