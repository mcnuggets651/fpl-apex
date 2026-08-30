from __future__ import annotations
import ast
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src' / 'apex'
errors = []
for path in SRC.rglob('*.py'):
    rel = path.relative_to(ROOT)
    text = path.read_text()
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            mods = [node.module or '']
        else:
            continue
        for mod in mods:
            if mod.startswith('apex_fpl'):
                errors.append(f'{rel}: V2 may not import legacy {mod}')
            if 'domain/' in rel.as_posix() and mod.split('.')[0] in {'requests', 'pandas', 'numpy', 'scipy'}:
                errors.append(f'{rel}: domain layer must stay dependency-pure: {mod}')
            if 'decision/' in rel.as_posix() and (mod.startswith('apex.sources') or mod.startswith('apex.runtime') or mod.startswith('apex.governance') or mod.startswith('apex.forecast.adapters')):
                errors.append(f'{rel}: decision layer crossed architecture boundary: {mod}')
            if rel.as_posix().endswith('src/apex/runtime/solve.py') and (mod.startswith('apex.sources') or mod.split('.')[0] in {'requests', 'urllib', 'httpx'}):
                errors.append(f'{rel}: frozen solve may not import network/source module: {mod}')
    if 'decision/' in rel.as_posix():
        lowered = text.casefold()
        for token in ('shadow_warnings', 'provider_diagnostics', 'research_weight_tournament'):
            if token in lowered:
                errors.append(f'{rel}: decision code contains forbidden diagnostic influence token {token}')
if errors:
    print('\n'.join(errors))
    raise SystemExit(1)
print('Apex V2 architecture boundaries: OK')
