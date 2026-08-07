#!/usr/bin/env bash
set -euo pipefail
ROOT="${1:-workers}"
mkdir -p "$ROOT"
python - "$ROOT" <<'PY'
import json, pathlib, subprocess, sys
root = pathlib.Path(sys.argv[1])
lock = json.loads(pathlib.Path('upstreams.lock.json').read_text())
required = {'airsenal', 'fpl_core_insights', 'open_fpl_solver', 'fpl_optimization_tools'}
for name, spec in lock['repositories'].items():
    if name not in required:
        continue
    dest = root / name
    if not dest.exists():
        subprocess.run(['git','clone','--filter=blob:none','--no-checkout',spec['url'],str(dest)], check=True)
    subprocess.run(['git','-C',str(dest),'fetch','--depth','1','origin',spec['commit']], check=True)
    subprocess.run(['git','-C',str(dest),'checkout','--detach',spec['commit']], check=True)
    print(f"{name}: {spec['commit']}")
PY
