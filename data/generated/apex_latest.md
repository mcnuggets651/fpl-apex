# Apex FPL Report

Generated: 2026-08-07T14:26:22.480005+00:00

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

- ID: `20260807T142608Z-1459d47c`
- Players: 573
- Fixtures: 380
- Bootstrap SHA256: `cf27ee4d0bfab11c7dd22591f691501ee43e7626b2804cb375af3d49ea76e2b3`

## Source health

- **official_fpl** — OK (configured) @ `cf27ee4d0bfa`: 573 players; 380 fixtures; snapshot=20260807T142608Z-1459d47c
- **team_state** — OK (configured): FPL entry 63984 (mcnuggets) connected; no 15-player public deadline squad is published yet, so Apex remains in initial-squad mode; pre-GW1 price universe captured
- **fpl_core_playerstats** — OK (configured) @ `911992600f8bb66f1530ebd2ca5d3cdc22420109`: 570 rows
- **fpl_core_previous_season** — WARNING (configured) @ `911992600f8bb66f1530ebd2ca5d3cdc22420109`: Merge keys are not unique in right dataset; not a one-to-one merge
- **fpl_core_preseason** — OK (configured) @ `911992600f8bb66f1530ebd2ca5d3cdc22420109`: 604 player-match rows
- **tactical_inference** — OK (configured): 573 inferred player roles
- **manual_availability** — OK (not configured): not configured
- **tactical_roles** — OK (not configured): no verified overrides
- **news_feeds** — OK (configured): 80 headlines; 13 player matches; 3 source(s) healthy
- **fpl_core_elo** — OK (configured) @ `911992600f8bb66f1530ebd2ca5d3cdc22420109`: 160 team-fixture Elo rows
- **official_team_strength** — WARNING (configured) @ `cf27ee4d0bfa`: 20/20 teams contain zero/non-positive strength values
- **understat_team_model** — OK (configured): 1900 completed-match rows across 5 complete seasons; fixture coverage=160/160; promoted/unknown priors=3; mode=shadow; active season 2026 unavailable: UnderstatDataError: Understat EPL 2026 unavailable after 3 attempts; attempt 1: UnderstatDataError: Understat league payload has no teams object | attempt 2: UnderstatDataError: Understat league payload has no teams object | attempt 3: UnderstatDataError: Understat league payload has no teams object
- **fixture_model** — OK (configured): official strength unavailable (20/20 teams contain zero/non-positive strength values); using league goal baselines plus complete reconciled Elo coverage (160/160); Understat challenger mode=shadow
- **airsenal** — OK (configured) @ `8c7e18eba1488dd5a7d4bdb00d4da0a75e895717`: 4584 rows; player coverage={1: 573, 2: 573, 3: 573, 4: 573, 5: 573, 6: 573, 7: 573, 8: 573}; age=0.0h; tag=4008ea19-9731-4745-a7cd-3b1c8800f775
- **market_odds** — OK (not configured): optional endpoint not configured

## Scenario comparison

| scenario     |   cost |   gw1_total_with_captain |   gw1_gap_to_best |   squad_horizon_xp |   horizon_gap_to_best |   mean_squad_confidence |
|:-------------|-------:|-------------------------:|------------------:|-------------------:|----------------------:|------------------------:|
| unrestricted | 100.00 |                    50.76 |              0.00 |             370.63 |                  0.00 |                    0.51 |
| haaland      | 100.00 |                    50.21 |             -0.55 |             369.87 |                 -0.76 |                    0.49 |
| no-haaland   | 100.00 |                    50.76 |              0.00 |             370.63 |                  0.00 |                    0.51 |

## unrestricted
Status: **Optimal**
Solver objective: **117.48**

Captain: **B.Fernandes** — GW xP 5.34 — xMins 85 — confidence 54% — central / balanced midfielder — attacking xG/xA 21.4 xP; minutes / appearance 15.5 xP; bonus/BPS prior 5.0 xP — risk: projection confidence 54%
Vice-captain: **Saka** — GW xP 4.88 — xMins 87 — confidence 52% — central / balanced midfielder — attacking xG/xA 20.6 xP; minutes / appearance 15.6 xP; bonus/BPS prior 4.2 xP — risk: projection confidence 52%

### XI

| web_name    | team_name   | position   |   price |   expected_minutes | tactical_role                 |   gw1_xp |   xpts_3 |   xpts_5 |   xpts_8 |   projection_confidence | top_drivers                                                                                  | risk_flags                |
|:------------|:------------|:-----------|--------:|-------------------:|:------------------------------|---------:|---------:|---------:|---------:|------------------------:|:---------------------------------------------------------------------------------------------|:--------------------------|
| B.Fernandes | Man Utd     | MID        |   12.00 |              85.21 | central / balanced midfielder |     5.34 |    15.48 |    23.01 |    32.16 |                    0.54 | attacking xG/xA 21.4 xP; minutes / appearance 15.5 xP; bonus/BPS prior 5.0 xP                | projection confidence 54% |
| Saka        | Arsenal     | MID        |    9.50 |              86.95 | central / balanced midfielder |     4.88 |    13.79 |    21.05 |    29.62 |                    0.52 | attacking xG/xA 20.6 xP; minutes / appearance 15.6 xP; bonus/BPS prior 4.2 xP                | projection confidence 52% |
| O'Reilly    | Man City    | DEF        |    6.50 |              88.20 | central / defensive defender  |     4.27 |    12.51 |    18.92 |    26.30 |                    0.54 | minutes / appearance 15.6 xP; attacking xG/xA 12.5 xP; clean-sheet probability 8.4 xP        | projection confidence 54% |
| Thiago      | Brentford   | FWD        |    8.00 |              86.93 | central striker               |     4.25 |    12.71 |    19.45 |    27.28 |                    0.53 | attacking xG/xA 19.7 xP; minutes / appearance 15.6 xP; bonus/BPS prior 4.6 xP                | projection confidence 53% |
| Raya        | Arsenal     | GK         |    6.00 |              88.20 | goalkeeper                    |     3.99 |    10.21 |    15.26 |    21.45 |                    0.60 | minutes / appearance 15.6 xP; clean-sheet probability 8.7 xP; goalkeeper saves 4.2 xP        |                           |
| Guéhi       | Man City    | DEF        |    6.00 |              88.20 | central / defensive defender  |     3.97 |    11.69 |    17.68 |    24.57 |                    0.55 | minutes / appearance 15.6 xP; clean-sheet probability 8.4 xP; attacking xG/xA 7.6 xP         | projection confidence 55% |
| Enzo        | Chelsea     | MID        |    7.00 |              87.19 | central / balanced midfielder |     3.84 |    11.25 |    17.75 |    25.01 |                    0.49 | attacking xG/xA 17.8 xP; minutes / appearance 15.6 xP; bonus/BPS prior 3.8 xP                | projection confidence 49% |
| Watkins     | Aston Villa | FWD        |    8.00 |              81.89 | central striker               |     3.82 |    11.48 |    17.77 |    24.92 |                    0.57 | attacking xG/xA 16.4 xP; minutes / appearance 15.2 xP; bonus/BPS prior 4.1 xP                |                           |
| Schade      | Brentford   | MID        |    6.00 |              81.70 | advanced midfielder / winger  |     3.78 |    11.41 |    17.45 |    24.46 |                    0.52 | attacking xG/xA 17.4 xP; minutes / appearance 15.2 xP; bonus/BPS prior 3.3 xP                | projection confidence 52% |
| O.Dango     | Brentford   | MID        |    6.50 |              88.20 | central / balanced midfielder |     3.76 |    11.17 |    17.05 |    23.87 |                    0.53 | attacking xG/xA 16.2 xP; minutes / appearance 15.6 xP; bonus/BPS prior 3.4 xP                | projection confidence 53% |
| Wieffer     | Brighton    | DEF        |    5.00 |              75.90 | central / defensive defender  |     3.54 |    10.61 |    16.24 |    22.74 |                    0.49 | minutes / appearance 14.5 xP; defensive contributions 9.6 xP; clean-sheet probability 6.8 xP | projection confidence 49% |

### Bench

| web_name   | team_name   | position   |   price |   expected_minutes | tactical_role                |   gw1_xp |   xpts_3 |   xpts_5 |   xpts_8 |   projection_confidence | top_drivers                                                                           | risk_flags                                                       |
|:-----------|:------------|:-----------|--------:|-------------------:|:-----------------------------|---------:|---------:|---------:|---------:|------------------------:|:--------------------------------------------------------------------------------------|:-----------------------------------------------------------------|
| Thiaw      | Newcastle   | DEF        |    5.00 |              87.99 | central / defensive defender |     3.46 |    10.61 |    16.66 |    23.35 |                    0.50 | minutes / appearance 15.6 xP; clean-sheet probability 7.9 xP; attacking xG/xA 7.7 xP  | projection confidence 50%                                        |
| Kostoulas  | Brighton    | FWD        |    5.50 |              88.20 | central striker              |     3.33 |    10.33 |    15.97 |    22.52 |                    0.28 | attacking xG/xA 21.3 xP; minutes / appearance 15.6 xP; bonus/BPS prior 6.5 xP         | projection confidence 28% | projection models disagree (SD 2.23) |
| Robinson   | Fulham      | DEF        |    4.50 |              85.01 | central / defensive defender |     3.24 |    10.06 |    15.18 |    21.87 |                    0.50 | minutes / appearance 15.5 xP; clean-sheet probability 7.8 xP; attacking xG/xA 5.0 xP  | projection confidence 50%                                        |
| Verbruggen | Brighton    | GK         |    4.50 |              88.20 | goalkeeper                   |     3.18 |     9.55 |    14.65 |    20.52 |                    0.53 | minutes / appearance 15.6 xP; clean-sheet probability 7.7 xP; goalkeeper saves 7.3 xP | projection confidence 53%                                        |

## haaland
Status: **Optimal**
Solver objective: **116.79**

Captain: **Haaland** — GW xP 5.37 — xMins 84 — confidence 53% — central striker — attacking xG/xA 28.0 xP; minutes / appearance 15.4 xP; bonus/BPS prior 5.6 xP — risk: projection confidence 53%
Vice-captain: **Saka** — GW xP 4.88 — xMins 87 — confidence 52% — central / balanced midfielder — attacking xG/xA 20.6 xP; minutes / appearance 15.6 xP; bonus/BPS prior 4.2 xP — risk: projection confidence 52%

### XI

| web_name   | team_name   | position   |   price |   expected_minutes | tactical_role                 |   gw1_xp |   xpts_3 |   xpts_5 |   xpts_8 |   projection_confidence | top_drivers                                                                                  | risk_flags                |
|:-----------|:------------|:-----------|--------:|-------------------:|:------------------------------|---------:|---------:|---------:|---------:|------------------------:|:---------------------------------------------------------------------------------------------|:--------------------------|
| Haaland    | Man City    | FWD        |   15.50 |              83.82 | central striker               |     5.37 |    15.85 |    24.05 |    33.68 |                    0.53 | attacking xG/xA 28.0 xP; minutes / appearance 15.4 xP; bonus/BPS prior 5.6 xP                | projection confidence 53% |
| Saka       | Arsenal     | MID        |    9.50 |              86.95 | central / balanced midfielder |     4.88 |    13.79 |    21.05 |    29.62 |                    0.52 | attacking xG/xA 20.6 xP; minutes / appearance 15.6 xP; bonus/BPS prior 4.2 xP                | projection confidence 52% |
| O'Reilly   | Man City    | DEF        |    6.50 |              88.20 | central / defensive defender  |     4.27 |    12.51 |    18.92 |    26.30 |                    0.54 | minutes / appearance 15.6 xP; attacking xG/xA 12.5 xP; clean-sheet probability 8.4 xP        | projection confidence 54% |
| Thiago     | Brentford   | FWD        |    8.00 |              86.93 | central striker               |     4.25 |    12.71 |    19.45 |    27.28 |                    0.53 | attacking xG/xA 19.7 xP; minutes / appearance 15.6 xP; bonus/BPS prior 4.6 xP                | projection confidence 53% |
| Guéhi      | Man City    | DEF        |    6.00 |              88.20 | central / defensive defender  |     3.97 |    11.69 |    17.68 |    24.57 |                    0.55 | minutes / appearance 15.6 xP; clean-sheet probability 8.4 xP; attacking xG/xA 7.6 xP         | projection confidence 55% |
| Enzo       | Chelsea     | MID        |    7.00 |              87.19 | central / balanced midfielder |     3.84 |    11.25 |    17.75 |    25.01 |                    0.49 | attacking xG/xA 17.8 xP; minutes / appearance 15.6 xP; bonus/BPS prior 3.8 xP                | projection confidence 49% |
| Schade     | Brentford   | MID        |    6.00 |              81.70 | advanced midfielder / winger  |     3.78 |    11.41 |    17.45 |    24.46 |                    0.52 | attacking xG/xA 17.4 xP; minutes / appearance 15.2 xP; bonus/BPS prior 3.3 xP                | projection confidence 52% |
| O.Dango    | Brentford   | MID        |    6.50 |              88.20 | central / balanced midfielder |     3.76 |    11.17 |    17.05 |    23.87 |                    0.53 | attacking xG/xA 16.2 xP; minutes / appearance 15.6 xP; bonus/BPS prior 3.4 xP                | projection confidence 53% |
| Pickford   | Everton     | GK         |    5.50 |              88.20 | goalkeeper                    |     3.73 |    10.08 |    15.54 |    21.44 |                    0.57 | minutes / appearance 15.6 xP; clean-sheet probability 7.7 xP; goalkeeper saves 6.9 xP        |                           |
| Wieffer    | Brighton    | DEF        |    5.00 |              75.90 | central / defensive defender  |     3.54 |    10.61 |    16.24 |    22.74 |                    0.49 | minutes / appearance 14.5 xP; defensive contributions 9.6 xP; clean-sheet probability 6.8 xP | projection confidence 49% |
| Thiaw      | Newcastle   | DEF        |    5.00 |              87.99 | central / defensive defender  |     3.46 |    10.61 |    16.66 |    23.35 |                    0.50 | minutes / appearance 15.6 xP; clean-sheet probability 7.9 xP; attacking xG/xA 7.7 xP         | projection confidence 50% |

### Bench

| web_name   | team_name   | position   |   price |   expected_minutes | tactical_role                |   gw1_xp |   xpts_3 |   xpts_5 |   xpts_8 |   projection_confidence | top_drivers                                                                           | risk_flags                                                       |
|:-----------|:------------|:-----------|--------:|-------------------:|:-----------------------------|---------:|---------:|---------:|---------:|------------------------:|:--------------------------------------------------------------------------------------|:-----------------------------------------------------------------|
| Kostoulas  | Brighton    | FWD        |    5.50 |              88.20 | central striker              |     3.33 |    10.33 |    15.97 |    22.52 |                    0.28 | attacking xG/xA 21.3 xP; minutes / appearance 15.6 xP; bonus/BPS prior 6.5 xP         | projection confidence 28% | projection models disagree (SD 2.23) |
| Robinson   | Fulham      | DEF        |    4.50 |              85.01 | central / defensive defender |     3.24 |    10.06 |    15.18 |    21.87 |                    0.50 | minutes / appearance 15.5 xP; clean-sheet probability 7.8 xP; attacking xG/xA 5.0 xP  | projection confidence 50%                                        |
| Brooks     | Bournemouth | MID        |    5.00 |              88.20 | advanced midfielder / winger |     3.21 |    10.31 |    16.03 |    22.65 |                    0.30 | attacking xG/xA 25.2 xP; minutes / appearance 15.6 xP; bonus/BPS prior 4.4 xP         | projection confidence 30% | projection models disagree (SD 2.23) |
| Verbruggen | Brighton    | GK         |    4.50 |              88.20 | goalkeeper                   |     3.18 |     9.55 |    14.65 |    20.52 |                    0.53 | minutes / appearance 15.6 xP; clean-sheet probability 7.7 xP; goalkeeper saves 7.3 xP | projection confidence 53%                                        |

## no-haaland
Status: **Optimal**
Solver objective: **117.48**

Captain: **B.Fernandes** — GW xP 5.34 — xMins 85 — confidence 54% — central / balanced midfielder — attacking xG/xA 21.4 xP; minutes / appearance 15.5 xP; bonus/BPS prior 5.0 xP — risk: projection confidence 54%
Vice-captain: **Saka** — GW xP 4.88 — xMins 87 — confidence 52% — central / balanced midfielder — attacking xG/xA 20.6 xP; minutes / appearance 15.6 xP; bonus/BPS prior 4.2 xP — risk: projection confidence 52%

### XI

| web_name    | team_name   | position   |   price |   expected_minutes | tactical_role                 |   gw1_xp |   xpts_3 |   xpts_5 |   xpts_8 |   projection_confidence | top_drivers                                                                                  | risk_flags                |
|:------------|:------------|:-----------|--------:|-------------------:|:------------------------------|---------:|---------:|---------:|---------:|------------------------:|:---------------------------------------------------------------------------------------------|:--------------------------|
| B.Fernandes | Man Utd     | MID        |   12.00 |              85.21 | central / balanced midfielder |     5.34 |    15.48 |    23.01 |    32.16 |                    0.54 | attacking xG/xA 21.4 xP; minutes / appearance 15.5 xP; bonus/BPS prior 5.0 xP                | projection confidence 54% |
| Saka        | Arsenal     | MID        |    9.50 |              86.95 | central / balanced midfielder |     4.88 |    13.79 |    21.05 |    29.62 |                    0.52 | attacking xG/xA 20.6 xP; minutes / appearance 15.6 xP; bonus/BPS prior 4.2 xP                | projection confidence 52% |
| O'Reilly    | Man City    | DEF        |    6.50 |              88.20 | central / defensive defender  |     4.27 |    12.51 |    18.92 |    26.30 |                    0.54 | minutes / appearance 15.6 xP; attacking xG/xA 12.5 xP; clean-sheet probability 8.4 xP        | projection confidence 54% |
| Thiago      | Brentford   | FWD        |    8.00 |              86.93 | central striker               |     4.25 |    12.71 |    19.45 |    27.28 |                    0.53 | attacking xG/xA 19.7 xP; minutes / appearance 15.6 xP; bonus/BPS prior 4.6 xP                | projection confidence 53% |
| Raya        | Arsenal     | GK         |    6.00 |              88.20 | goalkeeper                    |     3.99 |    10.21 |    15.26 |    21.45 |                    0.60 | minutes / appearance 15.6 xP; clean-sheet probability 8.7 xP; goalkeeper saves 4.2 xP        |                           |
| Guéhi       | Man City    | DEF        |    6.00 |              88.20 | central / defensive defender  |     3.97 |    11.69 |    17.68 |    24.57 |                    0.55 | minutes / appearance 15.6 xP; clean-sheet probability 8.4 xP; attacking xG/xA 7.6 xP         | projection confidence 55% |
| Enzo        | Chelsea     | MID        |    7.00 |              87.19 | central / balanced midfielder |     3.84 |    11.25 |    17.75 |    25.01 |                    0.49 | attacking xG/xA 17.8 xP; minutes / appearance 15.6 xP; bonus/BPS prior 3.8 xP                | projection confidence 49% |
| Watkins     | Aston Villa | FWD        |    8.00 |              81.89 | central striker               |     3.82 |    11.48 |    17.77 |    24.92 |                    0.57 | attacking xG/xA 16.4 xP; minutes / appearance 15.2 xP; bonus/BPS prior 4.1 xP                |                           |
| Schade      | Brentford   | MID        |    6.00 |              81.70 | advanced midfielder / winger  |     3.78 |    11.41 |    17.45 |    24.46 |                    0.52 | attacking xG/xA 17.4 xP; minutes / appearance 15.2 xP; bonus/BPS prior 3.3 xP                | projection confidence 52% |
| O.Dango     | Brentford   | MID        |    6.50 |              88.20 | central / balanced midfielder |     3.76 |    11.17 |    17.05 |    23.87 |                    0.53 | attacking xG/xA 16.2 xP; minutes / appearance 15.6 xP; bonus/BPS prior 3.4 xP                | projection confidence 53% |
| Wieffer     | Brighton    | DEF        |    5.00 |              75.90 | central / defensive defender  |     3.54 |    10.61 |    16.24 |    22.74 |                    0.49 | minutes / appearance 14.5 xP; defensive contributions 9.6 xP; clean-sheet probability 6.8 xP | projection confidence 49% |

### Bench

| web_name   | team_name   | position   |   price |   expected_minutes | tactical_role                |   gw1_xp |   xpts_3 |   xpts_5 |   xpts_8 |   projection_confidence | top_drivers                                                                           | risk_flags                                                       |
|:-----------|:------------|:-----------|--------:|-------------------:|:-----------------------------|---------:|---------:|---------:|---------:|------------------------:|:--------------------------------------------------------------------------------------|:-----------------------------------------------------------------|
| Thiaw      | Newcastle   | DEF        |    5.00 |              87.99 | central / defensive defender |     3.46 |    10.61 |    16.66 |    23.35 |                    0.50 | minutes / appearance 15.6 xP; clean-sheet probability 7.9 xP; attacking xG/xA 7.7 xP  | projection confidence 50%                                        |
| Kostoulas  | Brighton    | FWD        |    5.50 |              88.20 | central striker              |     3.33 |    10.33 |    15.97 |    22.52 |                    0.28 | attacking xG/xA 21.3 xP; minutes / appearance 15.6 xP; bonus/BPS prior 6.5 xP         | projection confidence 28% | projection models disagree (SD 2.23) |
| Robinson   | Fulham      | DEF        |    4.50 |              85.01 | central / defensive defender |     3.24 |    10.06 |    15.18 |    21.87 |                    0.50 | minutes / appearance 15.5 xP; clean-sheet probability 7.8 xP; attacking xG/xA 5.0 xP  | projection confidence 50%                                        |
| Verbruggen | Brighton    | GK         |    4.50 |              88.20 | goalkeeper                   |     3.18 |     9.55 |    14.65 |    20.52 |                    0.53 | minutes / appearance 15.6 xP; clean-sheet probability 7.7 xP; goalkeeper saves 7.3 xP | projection confidence 53%                                        |

## Highest current player risks

| web_name   | team_name     | position   |   expected_minutes |   projection_confidence |   risk_score | risk_flags                                                                                                                                |
|:-----------|:--------------|:-----------|-------------------:|------------------------:|-------------:|:------------------------------------------------------------------------------------------------------------------------------------------|
| J.Timber   | Arsenal       | DEF        |               0.00 |                    0.32 |         1.00 | official FPL status=i | expected minutes only 0 | start probability 0% | projection confidence 32% | projection models disagree (SD 2.02) |
| Carvalho   | Brentford     | MID        |              22.05 |                    0.45 |         1.00 | official FPL status=d | expected minutes only 22 | start probability 24% | projection confidence 45%                                      |
| Milambo    | Brentford     | MID        |              16.88 |                    0.53 |         1.00 | official FPL status=d | expected minutes only 17 | start probability 38% | projection confidence 53% | tactical-role confidence 49%       |
| Garner     | Everton       | MID        |               0.00 |                    0.41 |         1.00 | official FPL status=i | expected minutes only 0 | start probability 0% | projection confidence 41%                                        |
| Andersen   | Fulham        | DEF        |               0.00 |                    0.44 |         1.00 | official FPL status=s | expected minutes only 0 | start probability 0% | projection confidence 44%                                        |
| Jacob      | Hull City     | DEF        |              35.59 |                    0.48 |         1.00 | official FPL status=d | expected minutes only 36 | start probability 50% | projection confidence 48% | tactical-role confidence 48%       |
| L.Miley    | Newcastle     | MID        |               0.00 |                    0.45 |         1.00 | official FPL status=i | expected minutes only 0 | start probability 0% | projection confidence 45%                                        |
| Fofana     | Chelsea       | DEF        |               0.00 |                    0.47 |         1.00 | official FPL status=s | expected minutes only 0 | start probability 0% | projection confidence 47%                                        |
| Rudoni     | Coventry City | MID        |               9.75 |                    0.49 |         1.00 | official FPL status=d | expected minutes only 10 | start probability 15% | projection confidence 49% | tactical-role confidence 48%       |
| Emegha     | Chelsea       | FWD        |               9.75 |                    0.50 |         1.00 | official FPL status=d | expected minutes only 10 | start probability 15% | projection confidence 50% | tactical-role confidence 47%       |
| Abraham    | Aston Villa   | FWD        |               0.00 |                    0.48 |         1.00 | official FPL status=i | expected minutes only 0 | start probability 0% | projection confidence 48%                                        |
| Christie   | Bournemouth   | MID        |               0.00 |                    0.54 |         1.00 | official FPL status=s | expected minutes only 0 | start probability 0% | projection confidence 54%                                        |
| Baleba     | Brighton      | MID        |               0.00 |                    0.54 |         1.00 | official FPL status=i | expected minutes only 0 | start probability 0% | projection confidence 54%                                        |
| Harrison   | Leeds         | MID        |               0.00 |                    0.58 |         1.00 | official FPL status=u | expected minutes only 0 | start probability 0%                                                                    |
| Gomez      | Liverpool     | DEF        |               0.00 |                    0.62 |         1.00 | official FPL status=i | expected minutes only 0 | start probability 0%                                                                    |
| Burstow    | Hull City     | FWD        |               0.00 |                    0.54 |         1.00 | official FPL status=u | expected minutes only 0 | start probability 0% | projection confidence 54% | tactical-role confidence 47%         |
| Rodrigo    | Man City      | MID        |               0.00 |                    0.64 |         1.00 | official FPL status=i | expected minutes only 0 | start probability 0%                                                                    |
| Taylor     | Ipswich Town  | MID        |               0.00 |                    0.54 |         1.00 | official FPL status=i | expected minutes only 0 | start probability 0% | projection confidence 54% | tactical-role confidence 48%         |
| Jaros      | Liverpool     | GK         |               0.00 |                    0.55 |         1.00 | official FPL status=i | expected minutes only 0 | start probability 0% | tactical-role confidence 54%                                     |
| Ekitiké    | Liverpool     | FWD        |               0.00 |                    0.64 |         1.00 | official FPL status=i | expected minutes only 0 | start probability 0%                                                                    |
