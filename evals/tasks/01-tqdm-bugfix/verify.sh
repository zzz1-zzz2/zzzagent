#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)"
workspace="${repo_root}/evals/workspaces/01-tqdm-bugfix"

if [[ ! -d "${workspace}/.git" ]]; then
  printf 'FAIL: workspace is missing; run setup.sh first\n' >&2
  exit 2
fi

cd -- "${workspace}"
python_bin="${workspace}/.eval-venv/bin/python"
if [[ ! -x "${python_bin}" ]]; then
  printf 'FAIL: task environment is missing; rerun setup.sh\n' >&2
  exit 2
fi
"${python_bin}" -m pytest -q tqdm/tests/tests_contrib.py::test_enumerate

# The historical test file predates this regression, so keep the acceptance
# assertion here rather than trusting a mutable test inside the workspace.
"${python_bin}" - <<'PY'
from tqdm.contrib import tenumerate

assert list(tenumerate(range(3), 42)) == [(42, 0), (43, 1), (44, 2)]
PY
