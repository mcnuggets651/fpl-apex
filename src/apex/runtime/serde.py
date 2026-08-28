from __future__ import annotations
from apex.domain.models import *

def official_from_dict(d):
    return OfficialSnapshot(int(d['schema_version']), d['season'], d['acquired_at'], d['source_hash'], tuple((OfficialPlayer(int(p['element_id']), p['web_name'], int(p['team_id']), Position(p['position']), int(p['price_tenths']), p['status'], bool(p.get('can_transact', True))) for p in d['players'])), tuple((OfficialFixture(int(f['fixture_id']), int(f['gameweek']) if f.get('gameweek') is not None else None, int(f['home_team_id']), int(f['away_team_id']), f.get('kickoff_time')) for f in d.get('fixtures', []))), {int(k): v for k, v in d.get('deadlines', {}).items()})

def projection_from_dict(d):
    rows = tuple((ProjectionRow(int(r['element_id']), int(r['gameweek']), int(r['horizon']), float(r['expected_points']) if r.get('expected_points') is not None else None, tuple(map(int, r.get('fixture_ids', []))), int(r.get('n_fixtures', 0)), r.get('player_status_at_forecast'), float(r['expected_minutes']) if r.get('expected_minutes') is not None else None, float(r['p_appearance']) if r.get('p_appearance') is not None else None, float(r['p_start']) if r.get('p_start') is not None else None, float(r['p_60']) if r.get('p_60') is not None else None, CoverageStatus(r.get('coverage_status', 'FORECAST')), r.get('coverage_reason'), r.get('metadata', {})) for r in d['rows']))
    return ProjectionSurface(int(d['schema_version']), d['provider_id'], d['provider_version'], d['generated_at'], d['season'], d['source_snapshot'], d['scoring_rules_version'], tuple(map(int, d['supported_horizons'])), tuple(d.get('runtime_dependencies', [])), rows)

def team_from_dict(d):
    return TeamState(int(d['schema_version']), int(d['entry_id']), int(d['published_gw']), tuple(map(int, d['squad_ids'])), int(d['bank_tenths']), int(d['free_transfers']), {int(k): int(v) for k, v in d.get('purchase_prices_tenths', {}).items()}, {int(k): int(v) for k, v in d.get('selling_prices_tenths', {}).items()}, d.get('active_chip'), bool(d.get('state_complete_for_transfers', False)))
