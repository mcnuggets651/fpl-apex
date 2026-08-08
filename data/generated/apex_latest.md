# Apex FPL Report

Generated: 2026-08-08T08:24:11.158167+00:00

## Decision gate

**safe_to_act:** `true`
**full_apex_ready:** `true`

- WARNING: data quality fallback: official_team_strength: 20/20 teams contain zero/non-positive strength values; validated fallback fixture model is active
- WARNING: data quality warning: preseason_evidence: 604 player-match rows; return-stat observation coverage=5.6%

## Data quality

- **official_team_strength** — FALLBACK: 20/20 teams contain zero/non-positive strength values; validated fallback fixture model is active
- **fpl_core_playerstats** — PASS: official-player coverage=99.5%
- **preseason_evidence** — WARNING: 604 player-match rows; return-stat observation coverage=5.6%
- **fixture_projection_surface** — PASS: 160/160 official team-fixture sides have finite goal/clean-sheet priors
- **player_projection_surface** — PASS: 4584/4584 official player/Gameweek pairs have finite projections

## Official snapshot

- ID: `20260808T082401Z-a23bda90`
- Players: 573
- Fixtures: 380
- Bootstrap SHA256: `194e65c6633f6902da372b46da373de08c198c7afc702cfa449f1c0e9d16340c`

## Source health

- **official_fpl** — OK (configured) @ `194e65c6633f`: 573 players; 380 fixtures; snapshot=20260808T082401Z-a23bda90
- **team_state** — OK (configured): FPL entry 63984 (mcnuggets) connected; no 15-player public deadline squad is published yet, so Apex remains in initial-squad mode; pre-GW1 price universe captured
- **fpl_core_playerstats** — OK (configured) @ `911992600f8bb66f1530ebd2ca5d3cdc22420109`: 570 rows
- **fpl_core_previous_season** — OK (configured) @ `911992600f8bb66f1530ebd2ca5d3cdc22420109`: 570 current official IDs; prior playing-time coverage=80.2%
- **fpl_core_preseason** — OK (configured) @ `911992600f8bb66f1530ebd2ca5d3cdc22420109`: 604 player-match rows
- **tactical_inference** — OK (configured): 573 inferred player roles
- **manual_availability** — OK (not configured): not configured
- **tactical_roles** — OK (not configured): no verified overrides
- **news_feeds** — OK (configured): 79 headlines; 4 player matches; 3 source(s) healthy
- **fpl_core_elo** — OK (configured) @ `911992600f8bb66f1530ebd2ca5d3cdc22420109`: 160 team-fixture Elo rows
- **official_team_strength** — WARNING (configured) @ `194e65c6633f`: 20/20 teams contain zero/non-positive strength values
- **understat_team_model** — OK (configured): 1900 completed-match rows across 5 complete seasons; fixture coverage=160/160; promoted/unknown priors=3; mode=shadow; active season 2026 unavailable: UnderstatDataError: Understat EPL 2026 unavailable after 3 attempts; attempt 1: UnderstatDataError: Understat league payload has no teams object | attempt 2: UnderstatDataError: Understat league payload has no teams object | attempt 3: UnderstatDataError: Understat league payload has no teams object
- **fixture_model** — OK (configured): official strength unavailable (20/20 teams contain zero/non-positive strength values); using league goal baselines plus complete reconciled Elo coverage (160/160); Understat challenger mode=shadow
- **airsenal** — OK (configured) @ `8c7e18eba1488dd5a7d4bdb00d4da0a75e895717`: 4584 rows; player coverage={1: 573, 2: 573, 3: 573, 4: 573, 5: 573, 6: 573, 7: 573, 8: 573}; age=0.0h; tag=69fce765-2518-4fb4-af5f-73d3abdbd121
- **market_odds** — OK (not configured): optional endpoint not configured

## Scenario comparison

| scenario     |   cost |   gw1_total_with_captain |   gw1_gap_to_best |   squad_horizon_xp |   horizon_gap_to_best |   mean_squad_confidence |
|:-------------|-------:|-------------------------:|------------------:|-------------------:|----------------------:|------------------------:|
| unrestricted | 100.00 |                    47.39 |              0.00 |             337.73 |                  0.00 |                    0.55 |
| haaland      | 100.00 |                    46.53 |             -0.86 |             335.13 |                 -2.60 |                    0.55 |
| no-haaland   | 100.00 |                    47.39 |              0.00 |             337.73 |                  0.00 |                    0.55 |

## unrestricted
Status: **Optimal**
Solver objective: **108.18**

Captain: **B.Fernandes** — GW xP 5.17 — xMins 81 — confidence 56% — central / balanced midfielder — attacking xG/xA 20.3 xP; minutes / appearance 14.8 xP; bonus/BPS prior 4.7 xP
Vice-captain: **Thiago** — GW xP 4.23 — xMins 86 — confidence 54% — central striker — attacking xG/xA 19.6 xP; minutes / appearance 15.5 xP; bonus/BPS prior 4.5 xP — risk: projection confidence 54%

### XI

| web_name    | team_name   | position   |   price |   expected_minutes | tactical_role                 |   gw1_xp |   xpts_3 |   xpts_5 |   xpts_8 |   projection_confidence | top_drivers                                                                                  | risk_flags                     |
|:------------|:------------|:-----------|--------:|-------------------:|:------------------------------|---------:|---------:|---------:|---------:|------------------------:|:---------------------------------------------------------------------------------------------|:-------------------------------|
| B.Fernandes | Man Utd     | MID        |   12.00 |              80.66 | central / balanced midfielder |     5.17 |    14.90 |    22.12 |    30.88 |                    0.56 | attacking xG/xA 20.3 xP; minutes / appearance 14.8 xP; bonus/BPS prior 4.7 xP                |                                |
| Thiago      | Brentford   | FWD        |    8.00 |              86.37 | central striker               |     4.23 |    12.66 |    19.36 |    27.16 |                    0.54 | attacking xG/xA 19.6 xP; minutes / appearance 15.5 xP; bonus/BPS prior 4.5 xP                | projection confidence 54%      |
| Raya        | Arsenal     | GK         |    6.00 |              87.63 | goalkeeper                    |     3.97 |    10.17 |    15.20 |    21.36 |                    0.60 | minutes / appearance 15.5 xP; clean-sheet probability 8.7 xP; goalkeeper saves 4.2 xP        |                                |
| Guéhi       | Man City    | DEF        |    6.00 |              82.89 | central / defensive defender  |     3.81 |    11.12 |    16.80 |    23.33 |                    0.56 | minutes / appearance 14.8 xP; clean-sheet probability 7.8 xP; attacking xG/xA 7.1 xP         |                                |
| Mbeumo      | Man Utd     | MID        |    8.00 |              76.77 | central / balanced midfielder |     3.73 |    10.84 |    16.17 |    22.60 |                    0.56 | minutes / appearance 14.6 xP; attacking xG/xA 12.0 xP; bonus/BPS prior 2.9 xP                |                                |
| Enzo        | Chelsea     | MID        |    7.00 |              81.95 | central / balanced midfielder |     3.69 |    10.77 |    16.96 |    23.89 |                    0.51 | attacking xG/xA 16.7 xP; minutes / appearance 14.8 xP; bonus/BPS prior 3.6 xP                | projection confidence 51%      |
| Virgil      | Liverpool   | DEF        |    6.50 |              90.00 | central / defensive defender  |     3.65 |    11.26 |    17.14 |    23.71 |                    0.52 | minutes / appearance 15.9 xP; clean-sheet probability 8.2 xP; defensive contributions 6.4 xP | projection confidence 52%      |
| O'Reilly    | Man City    | DEF        |    6.50 |              69.25 | central / defensive defender  |     3.64 |    10.38 |    15.60 |    21.61 |                    0.56 | minutes / appearance 12.3 xP; attacking xG/xA 9.8 xP; clean-sheet probability 5.7 xP         | minutes security moderate (69) |
| Watkins     | Aston Villa | FWD        |    8.00 |              74.55 | central striker               |     3.62 |    10.78 |    16.67 |    23.36 |                    0.55 | attacking xG/xA 15.0 xP; minutes / appearance 13.9 xP; bonus/BPS prior 3.8 xP                | projection confidence 55%      |
| Schade      | Brentford   | MID        |    6.00 |              72.21 | advanced midfielder / winger  |     3.49 |    10.43 |    15.91 |    22.28 |                    0.57 | attacking xG/xA 15.4 xP; minutes / appearance 13.4 xP; bonus/BPS prior 2.9 xP                |                                |
| Ndiaye      | Everton     | MID        |    6.00 |              73.18 | central / balanced midfielder |     3.21 |     9.40 |    14.70 |    20.52 |                    0.58 | minutes / appearance 13.5 xP; attacking xG/xA 9.9 xP; bonus/BPS prior 2.6 xP                 |                                |

### Bench

| web_name   | team_name   | position   |   price |   expected_minutes | tactical_role                |   gw1_xp |   xpts_3 |   xpts_5 |   xpts_8 |   projection_confidence | top_drivers                                                                           | risk_flags                |
|:-----------|:------------|:-----------|--------:|-------------------:|:-----------------------------|---------:|---------:|---------:|---------:|------------------------:|:--------------------------------------------------------------------------------------|:--------------------------|
| Verbruggen | Brighton    | GK         |    4.50 |              90.00 | goalkeeper                   |     3.22 |     9.68 |    14.85 |    20.80 |                    0.52 | minutes / appearance 15.9 xP; clean-sheet probability 7.9 xP; goalkeeper saves 7.4 xP | projection confidence 52% |
| Thiaw      | Newcastle   | DEF        |    5.00 |              77.97 | central / defensive defender |     3.14 |     9.50 |    14.90 |    20.85 |                    0.56 | minutes / appearance 14.1 xP; attacking xG/xA 6.9 xP; clean-sheet probability 6.7 xP  |                           |
| Kayode     | Brentford   | DEF        |    4.50 |              85.74 | central / defensive defender |     2.94 |     8.79 |    13.30 |    18.44 |                    0.52 | minutes / appearance 15.5 xP; clean-sheet probability 7.7 xP; attacking xG/xA 3.6 xP  | projection confidence 52% |
| Evanilson  | Bournemouth | FWD        |    6.00 |              77.39 | forward                      |     2.60 |     7.83 |    12.07 |    16.94 |                    0.54 | minutes / appearance 14.7 xP; attacking xG/xA 7.0 xP; bonus/BPS prior 2.3 xP          | projection confidence 54% |

## haaland
Status: **Optimal**
Solver objective: **106.85**

Captain: **Haaland** — GW xP 5.15 — xMins 78 — confidence 55% — central striker — attacking xG/xA 25.9 xP; minutes / appearance 14.3 xP; bonus/BPS prior 5.2 xP
Vice-captain: **Thiago** — GW xP 4.23 — xMins 86 — confidence 54% — central striker — attacking xG/xA 19.6 xP; minutes / appearance 15.5 xP; bonus/BPS prior 4.5 xP — risk: projection confidence 54%

### XI

| web_name   | team_name   | position   |   price |   expected_minutes | tactical_role                  |   gw1_xp |   xpts_3 |   xpts_5 |   xpts_8 |   projection_confidence | top_drivers                                                                                  | risk_flags                |
|:-----------|:------------|:-----------|--------:|-------------------:|:-------------------------------|---------:|---------:|---------:|---------:|------------------------:|:---------------------------------------------------------------------------------------------|:--------------------------|
| Haaland    | Man City    | FWD        |   15.50 |              77.71 | central striker                |     5.15 |    15.09 |    22.86 |    31.99 |                    0.55 | attacking xG/xA 25.9 xP; minutes / appearance 14.3 xP; bonus/BPS prior 5.2 xP                |                           |
| Thiago     | Brentford   | FWD        |    8.00 |              86.37 | central striker                |     4.23 |    12.66 |    19.36 |    27.16 |                    0.54 | attacking xG/xA 19.6 xP; minutes / appearance 15.5 xP; bonus/BPS prior 4.5 xP                | projection confidence 54% |
| Guéhi      | Man City    | DEF        |    6.00 |              82.89 | central / defensive defender   |     3.81 |    11.12 |    16.80 |    23.33 |                    0.56 | minutes / appearance 14.8 xP; clean-sheet probability 7.8 xP; attacking xG/xA 7.1 xP         |                           |
| Pickford   | Everton     | GK         |    5.50 |              90.00 | goalkeeper                     |     3.77 |    10.21 |    15.75 |    21.73 |                    0.56 | minutes / appearance 15.9 xP; clean-sheet probability 7.9 xP; goalkeeper saves 7.0 xP        |                           |
| Enzo       | Chelsea     | MID        |    7.00 |              81.95 | central / balanced midfielder  |     3.69 |    10.77 |    16.96 |    23.89 |                    0.51 | attacking xG/xA 16.7 xP; minutes / appearance 14.8 xP; bonus/BPS prior 3.6 xP                | projection confidence 51% |
| Virgil     | Liverpool   | DEF        |    6.50 |              90.00 | central / defensive defender   |     3.65 |    11.26 |    17.14 |    23.71 |                    0.52 | minutes / appearance 15.9 xP; clean-sheet probability 8.2 xP; defensive contributions 6.4 xP | projection confidence 52% |
| Watkins    | Aston Villa | FWD        |    8.00 |              74.55 | central striker                |     3.62 |    10.78 |    16.67 |    23.36 |                    0.55 | attacking xG/xA 15.0 xP; minutes / appearance 13.9 xP; bonus/BPS prior 3.8 xP                | projection confidence 55% |
| Rice       | Arsenal     | MID        |    7.50 |              81.39 | holding / defensive midfielder |     3.60 |    10.08 |    15.35 |    21.57 |                    0.59 | minutes / appearance 14.8 xP; attacking xG/xA 8.0 xP; defensive contributions 3.8 xP         |                           |
| Schade     | Brentford   | MID        |    6.00 |              72.21 | advanced midfielder / winger   |     3.49 |    10.43 |    15.91 |    22.28 |                    0.57 | attacking xG/xA 15.4 xP; minutes / appearance 13.4 xP; bonus/BPS prior 2.9 xP                |                           |
| Ndiaye     | Everton     | MID        |    6.00 |              73.18 | central / balanced midfielder  |     3.21 |     9.40 |    14.70 |    20.52 |                    0.58 | minutes / appearance 13.5 xP; attacking xG/xA 9.9 xP; bonus/BPS prior 2.6 xP                 |                           |
| Thiaw      | Newcastle   | DEF        |    5.00 |              77.97 | central / defensive defender   |     3.14 |     9.50 |    14.90 |    20.85 |                    0.56 | minutes / appearance 14.1 xP; attacking xG/xA 6.9 xP; clean-sheet probability 6.7 xP         |                           |

### Bench

| web_name   | team_name   | position   |   price |   expected_minutes | tactical_role                 |   gw1_xp |   xpts_3 |   xpts_5 |   xpts_8 |   projection_confidence | top_drivers                                                                           | risk_flags                |
|:-----------|:------------|:-----------|--------:|-------------------:|:------------------------------|---------:|---------:|---------:|---------:|------------------------:|:--------------------------------------------------------------------------------------|:--------------------------|
| Verbruggen | Brighton    | GK         |    4.50 |              90.00 | goalkeeper                    |     3.22 |     9.68 |    14.85 |    20.80 |                    0.52 | minutes / appearance 15.9 xP; clean-sheet probability 7.9 xP; goalkeeper saves 7.4 xP | projection confidence 52% |
| Kayode     | Brentford   | DEF        |    4.50 |              85.74 | central / defensive defender  |     2.94 |     8.79 |    13.30 |    18.44 |                    0.52 | minutes / appearance 15.5 xP; clean-sheet probability 7.7 xP; attacking xG/xA 3.6 xP  | projection confidence 52% |
| F.Kadıoğlu | Brighton    | DEF        |    4.50 |              81.72 | central / defensive defender  |     2.80 |     8.41 |    12.88 |    18.03 |                    0.55 | minutes / appearance 14.5 xP; clean-sheet probability 6.9 xP; attacking xG/xA 4.7 xP  | projection confidence 55% |
| Iwobi      | Fulham      | MID        |    5.50 |              76.63 | central / balanced midfielder |     2.76 |     8.08 |    12.26 |    17.46 |                    0.54 | minutes / appearance 14.3 xP; attacking xG/xA 4.2 xP; bonus/BPS prior 2.5 xP          | projection confidence 54% |

## no-haaland
Status: **Optimal**
Solver objective: **108.18**

Captain: **B.Fernandes** — GW xP 5.17 — xMins 81 — confidence 56% — central / balanced midfielder — attacking xG/xA 20.3 xP; minutes / appearance 14.8 xP; bonus/BPS prior 4.7 xP
Vice-captain: **Thiago** — GW xP 4.23 — xMins 86 — confidence 54% — central striker — attacking xG/xA 19.6 xP; minutes / appearance 15.5 xP; bonus/BPS prior 4.5 xP — risk: projection confidence 54%

### XI

| web_name    | team_name   | position   |   price |   expected_minutes | tactical_role                 |   gw1_xp |   xpts_3 |   xpts_5 |   xpts_8 |   projection_confidence | top_drivers                                                                                  | risk_flags                     |
|:------------|:------------|:-----------|--------:|-------------------:|:------------------------------|---------:|---------:|---------:|---------:|------------------------:|:---------------------------------------------------------------------------------------------|:-------------------------------|
| B.Fernandes | Man Utd     | MID        |   12.00 |              80.66 | central / balanced midfielder |     5.17 |    14.90 |    22.12 |    30.88 |                    0.56 | attacking xG/xA 20.3 xP; minutes / appearance 14.8 xP; bonus/BPS prior 4.7 xP                |                                |
| Thiago      | Brentford   | FWD        |    8.00 |              86.37 | central striker               |     4.23 |    12.66 |    19.36 |    27.16 |                    0.54 | attacking xG/xA 19.6 xP; minutes / appearance 15.5 xP; bonus/BPS prior 4.5 xP                | projection confidence 54%      |
| Raya        | Arsenal     | GK         |    6.00 |              87.63 | goalkeeper                    |     3.97 |    10.17 |    15.20 |    21.36 |                    0.60 | minutes / appearance 15.5 xP; clean-sheet probability 8.7 xP; goalkeeper saves 4.2 xP        |                                |
| Guéhi       | Man City    | DEF        |    6.00 |              82.89 | central / defensive defender  |     3.81 |    11.12 |    16.80 |    23.33 |                    0.56 | minutes / appearance 14.8 xP; clean-sheet probability 7.8 xP; attacking xG/xA 7.1 xP         |                                |
| Mbeumo      | Man Utd     | MID        |    8.00 |              76.77 | central / balanced midfielder |     3.73 |    10.84 |    16.17 |    22.60 |                    0.56 | minutes / appearance 14.6 xP; attacking xG/xA 12.0 xP; bonus/BPS prior 2.9 xP                |                                |
| Enzo        | Chelsea     | MID        |    7.00 |              81.95 | central / balanced midfielder |     3.69 |    10.77 |    16.96 |    23.89 |                    0.51 | attacking xG/xA 16.7 xP; minutes / appearance 14.8 xP; bonus/BPS prior 3.6 xP                | projection confidence 51%      |
| Virgil      | Liverpool   | DEF        |    6.50 |              90.00 | central / defensive defender  |     3.65 |    11.26 |    17.14 |    23.71 |                    0.52 | minutes / appearance 15.9 xP; clean-sheet probability 8.2 xP; defensive contributions 6.4 xP | projection confidence 52%      |
| O'Reilly    | Man City    | DEF        |    6.50 |              69.25 | central / defensive defender  |     3.64 |    10.38 |    15.60 |    21.61 |                    0.56 | minutes / appearance 12.3 xP; attacking xG/xA 9.8 xP; clean-sheet probability 5.7 xP         | minutes security moderate (69) |
| Watkins     | Aston Villa | FWD        |    8.00 |              74.55 | central striker               |     3.62 |    10.78 |    16.67 |    23.36 |                    0.55 | attacking xG/xA 15.0 xP; minutes / appearance 13.9 xP; bonus/BPS prior 3.8 xP                | projection confidence 55%      |
| Schade      | Brentford   | MID        |    6.00 |              72.21 | advanced midfielder / winger  |     3.49 |    10.43 |    15.91 |    22.28 |                    0.57 | attacking xG/xA 15.4 xP; minutes / appearance 13.4 xP; bonus/BPS prior 2.9 xP                |                                |
| Ndiaye      | Everton     | MID        |    6.00 |              73.18 | central / balanced midfielder |     3.21 |     9.40 |    14.70 |    20.52 |                    0.58 | minutes / appearance 13.5 xP; attacking xG/xA 9.9 xP; bonus/BPS prior 2.6 xP                 |                                |

### Bench

| web_name   | team_name   | position   |   price |   expected_minutes | tactical_role                |   gw1_xp |   xpts_3 |   xpts_5 |   xpts_8 |   projection_confidence | top_drivers                                                                           | risk_flags                |
|:-----------|:------------|:-----------|--------:|-------------------:|:-----------------------------|---------:|---------:|---------:|---------:|------------------------:|:--------------------------------------------------------------------------------------|:--------------------------|
| Verbruggen | Brighton    | GK         |    4.50 |              90.00 | goalkeeper                   |     3.22 |     9.68 |    14.85 |    20.80 |                    0.52 | minutes / appearance 15.9 xP; clean-sheet probability 7.9 xP; goalkeeper saves 7.4 xP | projection confidence 52% |
| Thiaw      | Newcastle   | DEF        |    5.00 |              77.97 | central / defensive defender |     3.14 |     9.50 |    14.90 |    20.85 |                    0.56 | minutes / appearance 14.1 xP; attacking xG/xA 6.9 xP; clean-sheet probability 6.7 xP  |                           |
| Kayode     | Brentford   | DEF        |    4.50 |              85.74 | central / defensive defender |     2.94 |     8.79 |    13.30 |    18.44 |                    0.52 | minutes / appearance 15.5 xP; clean-sheet probability 7.7 xP; attacking xG/xA 3.6 xP  | projection confidence 52% |
| Evanilson  | Bournemouth | FWD        |    6.00 |              77.39 | forward                      |     2.60 |     7.83 |    12.07 |    16.94 |                    0.54 | minutes / appearance 14.7 xP; attacking xG/xA 7.0 xP; bonus/BPS prior 2.3 xP          | projection confidence 54% |

## Highest current player risks

| web_name   | team_name     | position   |   expected_minutes |   projection_confidence |   risk_score | risk_flags                                                                                                                                |
|:-----------|:--------------|:-----------|-------------------:|------------------------:|-------------:|:------------------------------------------------------------------------------------------------------------------------------------------|
| Šeško      | Man Utd       | FWD        |              31.48 |                    0.55 |         1.00 | official FPL status=d | expected minutes only 31 | start probability 34% | projection confidence 55%                                      |
| Kudus      | Spurs         | MID        |              30.30 |                    0.45 |         1.00 | official FPL status=d | expected minutes only 30 | start probability 38% | projection confidence 45%                                      |
| Martinez   | Man Utd       | DEF        |              23.85 |                    0.44 |         1.00 | official FPL status=d | expected minutes only 24 | start probability 26% | projection confidence 44%                                      |
| Livramento | Newcastle     | DEF        |              25.72 |                    0.45 |         1.00 | official FPL status=d | expected minutes only 26 | start probability 28% | projection confidence 45%                                      |
| J.Timber   | Arsenal       | DEF        |               0.00 |                    0.32 |         1.00 | official FPL status=i | expected minutes only 0 | start probability 0% | projection confidence 32% | projection models disagree (SD 2.02) |
| Grealish   | Man City      | MID        |              32.06 |                    0.51 |         1.00 | official FPL status=d | expected minutes only 32 | start probability 36% | projection confidence 51%                                      |
| Garner     | Everton       | MID        |               0.00 |                    0.41 |         1.00 | official FPL status=i | expected minutes only 0 | start probability 0% | projection confidence 41%                                        |
| Tzimas     | Brighton      | FWD        |               2.32 |                    0.50 |         1.00 | official FPL status=d | expected minutes only 2 | start probability 2% | projection confidence 50% | tactical-role confidence 51%         |
| Endo       | Liverpool     | MID        |               2.80 |                    0.52 |         1.00 | official FPL status=d | expected minutes only 3 | start probability 2% | projection confidence 52%                                        |
| Andersen   | Fulham        | DEF        |               0.00 |                    0.44 |         1.00 | official FPL status=s | expected minutes only 0 | start probability 0% | projection confidence 44%                                        |
| Jacob      | Hull City     | DEF        |              35.59 |                    0.48 |         1.00 | official FPL status=d | expected minutes only 36 | start probability 50% | projection confidence 48% | tactical-role confidence 48%       |
| L.Miley    | Newcastle     | MID        |               0.00 |                    0.45 |         1.00 | official FPL status=i | expected minutes only 0 | start probability 0% | projection confidence 45%                                        |
| Milambo    | Brentford     | MID        |               0.89 |                    0.51 |         1.00 | official FPL status=d | expected minutes only 1 | start probability 2% | projection confidence 51% | tactical-role confidence 49%         |
| Fofana     | Chelsea       | DEF        |               0.00 |                    0.47 |         1.00 | official FPL status=s | expected minutes only 0 | start probability 0% | projection confidence 47%                                        |
| Rudoni     | Coventry City | MID        |               9.75 |                    0.49 |         1.00 | official FPL status=d | expected minutes only 10 | start probability 15% | projection confidence 49% | tactical-role confidence 48%       |
| Emegha     | Chelsea       | FWD        |               9.75 |                    0.50 |         1.00 | official FPL status=d | expected minutes only 10 | start probability 15% | projection confidence 50% | tactical-role confidence 47%       |
| Christie   | Bournemouth   | MID        |               0.00 |                    0.54 |         1.00 | official FPL status=s | expected minutes only 0 | start probability 0% | projection confidence 54%                                        |
| Baleba     | Brighton      | MID        |               0.00 |                    0.54 |         1.00 | official FPL status=i | expected minutes only 0 | start probability 0% | projection confidence 54%                                        |
| Kroupi.Jr  | Bournemouth   | MID        |               0.00 |                    0.63 |         1.00 | official FPL status=i | expected minutes only 0 | start probability 0%                                                                    |
| Kulusevski | Spurs         | MID        |               0.00 |                    0.54 |         1.00 | official FPL status=i | expected minutes only 0 | start probability 0% | projection confidence 54% | tactical-role confidence 48%         |
