from __future__ import annotations
from pathlib import Path
import hashlib, json, tarfile
import pandas as pd, requests
from apex.governance.evaluation import score_predictions
from apex.runtime.releases import GitHubReleaseStore, download_release_asset, verify_attested_release
BASE = 'https://fantasy.premierleague.com/api'

def _hash(payload) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

def _official_finished_events(http=None):
    http = http or requests.Session()
    r = http.get(f'{BASE}/bootstrap-static/', timeout=30)
    r.raise_for_status()
    b = r.json()
    return ({int(e['id']): bool(e.get('finished')) for e in b.get('events', [])}, b)

def _live(gw, http=None):
    http = http or requests.Session()
    r = http.get(f'{BASE}/event/{gw}/live/', timeout=30)
    r.raise_for_status()
    p = r.json()
    actual = {}
    minutes = {}
    for e in p.get('elements', []):
        pid = int(e['id'])
        stats = e.get('stats', {})
        actual[pid] = float(stats.get('total_points', 0))
        minutes[pid] = float(stats.get('minutes', 0))
    return (p, actual, minutes)

def _provider_metrics(snapshot_root: Path, gw: int, actual: dict[int, float], minutes: dict[int, float]) -> dict:
    out = {}
    for path in sorted((snapshot_root / 'providers').glob('*.json')):
        d = json.loads(path.read_text())
        rows = []
        for r in d.get('rows', []):
            if int(r.get('gameweek', -1)) != gw or int(r.get('horizon', -1)) != 1 or r.get('coverage_status', 'FORECAST') != 'FORECAST' or (r.get('expected_points') is None):
                continue
            pid = int(r['element_id'])
            if pid in actual:
                rows.append({'gameweek': gw, 'element_id': pid, 'predicted_points': float(r['expected_points']), 'actual_points': actual[pid], 'actual_minutes': minutes.get(pid, 0)})
        frame = pd.DataFrame(rows)
        if frame.empty:
            continue
        allm = score_predictions(frame)
        starters = frame[frame.actual_minutes >= 60]
        out[d['provider_id']] = {'all': allm.to_dict(), 'starters_60plus': score_predictions(starters).to_dict() if not starters.empty else None, 'coverage_rows': len(frame)}
    return out

def evaluate_completed_attempts(store: GitHubReleaseStore, *, season: str, target_commitish: str, prefix='apex-v2', workdir: Path=Path('artifacts/v2/evaluation')) -> list[str]:
    releases = store.list_releases()
    by_tag = {r['tag_name']: r for r in releases}
    finished, _ = _official_finished_events()
    published = []
    finals = [r for r in releases if str(r.get('tag_name', '')).startswith(f'{prefix}/final/{season}/') and (not r.get('draft'))]
    for release in finals:
        run_id = release['tag_name'].split(f'{prefix}/final/{season}/', 1)[1]
        eval_tag = f'{prefix}/evaluation/{season}/{run_id}'
        if eval_tag in by_tag:
            continue
        attempt = Path(workdir) / run_id
        attempt.mkdir(parents=True, exist_ok=True)
        decision_path = download_release_asset(store, release, 'decision_bundle.json', attempt / 'decision_bundle.json')
        decision = json.loads(decision_path.read_text())
        gw = int(decision['manifest']['target_gameweek'])
        if not finished.get(gw, False):
            continue
        verify_attested_release(store, release, attempt)
        bundle = attempt / 'bundle.tar.gz'
        extract = attempt / 'extracted'
        extract.mkdir(exist_ok=True)
        with tarfile.open(bundle, 'r:gz') as tar:
            tar.extractall(extract, filter='data')
        live, actual, minutes = _live(gw)
        metrics = _provider_metrics(extract / 'snapshot', gw, actual, minutes)
        outcomes = {'schema_version': 1, 'season': season, 'gameweek': gw, 'run_id': run_id, 'official_live_hash': _hash(live), 'actual_points': actual, 'actual_minutes': minutes}
        metrics_payload = {'schema_version': 1, 'season': season, 'gameweek': gw, 'run_id': run_id, 'providers': metrics, 'automatic_promotion': False, 'note': 'Evaluation evidence only. Provider promotion requires explicit governed approval.'}
        op = attempt / 'outcomes.json'
        mp = attempt / 'metrics.json'
        op.write_text(json.dumps(outcomes, indent=2, sort_keys=True) + '\n')
        mp.write_text(json.dumps(metrics_payload, indent=2, sort_keys=True, allow_nan=False) + '\n')
        store.create_once(f'{prefix}/outcome/{season}/{run_id}', {'outcomes.json': op}, target_commitish=target_commitish, name=f'Apex V2 outcome {season} GW{gw} {run_id}')
        store.create_once(eval_tag, {'metrics.json': mp}, target_commitish=target_commitish, name=f'Apex V2 evaluation {season} GW{gw} {run_id}', body='Prospective scoring only; this release never changes serving-provider authority.')
        published.append(eval_tag)
    return published
