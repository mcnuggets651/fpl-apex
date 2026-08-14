#!/usr/bin/env bash
set -euo pipefail

pip install -e '.[dev]'

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
rm -rf "$checkout"
git clone --filter=blob:none "https://github.com/${AIRSENAL_REPOSITORY}.git" "$checkout"
git -C "$checkout" checkout --detach "$AIRSENAL_SHA"

AIRSENAL_CHECKOUT="$checkout" BPL_REPOSITORY="$BPL_REPOSITORY" BPL_SHA="$BPL_SHA" python - <<'PY'
import os
from pathlib import Path

path = Path(os.environ['AIRSENAL_CHECKOUT']) / 'pyproject.toml'
old = f"bpl @ git+https://github.com/{os.environ['BPL_REPOSITORY']}"
new = old + '@' + os.environ['BPL_SHA']
text = path.read_text(encoding='utf-8')
if old not in text:
    raise SystemExit('Pinned AIrsenal bpl dependency declaration not found')
if new in text:
    raise SystemExit('AIrsenal bpl dependency was already pinned unexpectedly')
path.write_text(text.replace(old, new, 1), encoding='utf-8')
PY

pip install "$checkout"
python - <<'PY'
from importlib.metadata import version

print('Installed AIrsenal:', version('airsenal'))
print('Installed bpl:', version('bpl'))
PY
