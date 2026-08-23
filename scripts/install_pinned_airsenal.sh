#!/usr/bin/env bash
set -euo pipefail

# Apex core remains on its own frozen Python 3.12 environment. AIrsenal executes
# in an isolated Python 3.14.7 environment created strictly from its upstream uv.lock.
readarray -t pins < <(python - <<'PY'
import json

lock = json.load(open('upstreams.lock.json', encoding='utf-8'))['sources']
for key in ('airsenal', 'bpl'):
    source = lock[key]
    print(source['repository'])
    print(source['commit'])
PY
)

AIRSENAL_REPOSITORY="${pins[0]}"
AIRSENAL_SHA="${pins[1]}"
BPL_REPOSITORY="${pins[2]}"
BPL_SHA="${pins[3]}"

checkout="${RUNNER_TEMP:-/tmp}/apex-pinned-airsenal"
uv_venv="${RUNNER_TEMP:-/tmp}/apex-worker-uv-bootstrap"
rm -rf "$checkout" "$uv_venv"
git clone --filter=blob:none "https://github.com/${AIRSENAL_REPOSITORY}.git" "$checkout"
git -C "$checkout" checkout --detach "$AIRSENAL_SHA"

# The upstream lock is part of the worker runtime contract. Verify Apex's explicit
# transitive BPL pin agrees with the exact revision resolved by that lock.
AIRSENAL_CHECKOUT="$checkout" BPL_REPOSITORY="$BPL_REPOSITORY" BPL_SHA="$BPL_SHA" python - <<'PY'
import os
from pathlib import Path

lock = (Path(os.environ['AIRSENAL_CHECKOUT']) / 'uv.lock').read_text(encoding='utf-8')
needle = f"https://github.com/{os.environ['BPL_REPOSITORY']}#{os.environ['BPL_SHA']}"
if needle not in lock:
    raise SystemExit(
        "AIrsenal uv.lock BPL revision disagrees with Apex upstreams.lock.json: " + needle
    )
PY

python -m venv "$uv_venv"
"$uv_venv/bin/python" -m pip install --no-deps uv==0.12.3
"$uv_venv/bin/uv" python install 3.14.7
"$uv_venv/bin/uv" sync \
  --frozen \
  --project "$checkout" \
  --python 3.14.7 \
  --no-dev

worker_python="$checkout/.venv/bin/python"
worker_bin="$checkout/.venv/bin"
test -x "$worker_python"
"$worker_python" - <<'PY'
import sys
from importlib.metadata import version

if sys.version_info[:3] != (3, 14, 7):
    raise SystemExit(f"unexpected AIrsenal worker Python: {sys.version}")
print('Isolated AIrsenal:', version('airsenal'))
print('Isolated bpl:', version('bpl'))
PY

if [ -n "${GITHUB_ENV:-}" ]; then
  {
    echo "AIRSENAL_WORKER_PYTHON=$worker_python"
    echo "AIRSENAL_WORKER_BIN=$worker_bin"
    echo "AIRSENAL_WORKER_SOURCE_SHA=$AIRSENAL_SHA"
    echo "AIRSENAL_WORKER_UV_LOCK=$checkout/uv.lock"
  } >> "$GITHUB_ENV"
else
  printf 'AIRSENAL_WORKER_PYTHON=%s\n' "$worker_python"
  printf 'AIRSENAL_WORKER_BIN=%s\n' "$worker_bin"
  printf 'AIRSENAL_WORKER_SOURCE_SHA=%s\n' "$AIRSENAL_SHA"
  printf 'AIRSENAL_WORKER_UV_LOCK=%s\n' "$checkout/uv.lock"
fi
