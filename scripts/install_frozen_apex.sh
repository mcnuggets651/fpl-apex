#!/usr/bin/env bash
set -euo pipefail

# Build a deterministic Apex Python 3.12 environment from the reviewed lock.
# The caller is responsible for selecting Python 3.12.14 before invoking this script.
venv="${APEX_VENV:-$GITHUB_WORKSPACE/.venv}"
rm -rf "$venv"
python -m venv "$venv"
"$venv/bin/python" -m pip install --no-deps -r requirements.lock
"$venv/bin/python" -m pip install --no-deps --no-build-isolation -e .

python_version="$($venv/bin/python -c 'import platform; print(platform.python_version())')"
if [ "$python_version" != "3.12.14" ]; then
  echo "Expected Apex Python 3.12.14, got $python_version" >&2
  exit 1
fi

if [ -n "${GITHUB_PATH:-}" ]; then
  echo "$venv/bin" >> "$GITHUB_PATH"
fi
if [ -n "${GITHUB_ENV:-}" ]; then
  echo "APEX_CORE_PYTHON=$venv/bin/python" >> "$GITHUB_ENV"
else
  printf 'APEX_CORE_PYTHON=%s\n' "$venv/bin/python"
fi
