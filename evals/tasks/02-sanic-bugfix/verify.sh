#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)"
workspace="${repo_root}/evals/workspaces/02-sanic-bugfix"

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

"${python_bin}" - <<'PY'
try:
    import httpx
    import httptools
    import websockets
except ImportError as exc:
    raise SystemExit(f"missing dependency: {exc}")
PY

# The pinned test file predates the regression test. Verify the application
# registry directly so this check remains independent of a mutable test file
# and of the legacy HTTP client's network event loop.
PYTHONPATH="${workspace}${PYTHONPATH:+:${PYTHONPATH}}" \
  "${python_bin}" - <<'PY'
from collections import deque

from sanic import Sanic
from sanic.blueprints import Blueprint
from sanic.response import text

app = Sanic("eval_bp_order")
blueprint = Blueprint("eval_bp_order")

@blueprint.middleware("response")
def response_one(request, response):
    return response

@blueprint.middleware("response")
def response_two(request, response):
    return response

@blueprint.middleware("response")
def response_three(request, response):
    return response

@blueprint.route("/")
def handler(request):
    return text("OK")

app.blueprint(blueprint)
registered = next(iter(app.named_response_middleware.values()))
assert isinstance(registered, deque)
assert list(registered) == [response_three, response_two, response_one], registered
PY
