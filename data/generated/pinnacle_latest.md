# Apex Pinnacle decision

Generated: 2026-08-07T14:44:36.241271+00:00
Gameweeks: 1, 2, 3, 4, 5, 6, 7, 8

## Pinnacle gate

- pinnacle_ready: `true`
- base safe_to_act: `true`
- base full_apex_ready: `true`
- deterministic surface: ensemble mean xP
- covariance-aware scenarios: 256
- lower-tail CVaR alpha: 10%
- CVaR objective weight: 20%
- exact captain/vice fallback: `true`
- exact autosub expectation: `true`
- receding-horizon transfer policy: `true`

- WARNING: published captain appears in only 0% of uncertainty re-solves
- WARNING: covariance coefficients are transparent priors until enough 2026/27 deadline outcomes exist
- WARNING: independent solver parity snapshot is not embedded in this run

## Maximum-EV unrestricted

Objective: **345.85**
GW1 captain: **Haaland**
GW1 vice-captain: **B.Fernandes**
GW1 bench order: **Robinson → A.García → Yates** (outfield; GK separate)
GW1 exact-mechanics xP: **54.40**

|   player_id | web_name    | team_name     | position   |   price |   expected_minutes |   start_probability |   appearance_probability | tactical_role                 | tactical_role_source   |   role_confidence |   gw1_xp |   xpts_3 |   xpts_5 |   xpts_8 |   horizon_xp |   projection_confidence | decision_projection_col   |
|------------:|:------------|:--------------|:-----------|--------:|-------------------:|--------------------:|-------------------------:|:------------------------------|:-----------------------|------------------:|---------:|---------:|---------:|---------:|-------------:|------------------------:|:--------------------------|
|         387 | O'Reilly    | Man City      | DEF        |     6.5 |            88.2    |            0.98     |                 0.9904   | central / defensive defender  | statistical_inference  |          0.7386   |  4.52553 | 12.5145  | 18.9192  |  26.2984 |      26.2984 |                0.536823 | xp                        |
|         445 | Thiaw       | Newcastle     | DEF        |     5   |            87.9921 |            0.98     |                 0.9904   | central / defensive defender  | statistical_inference  |          0.7687   |  3.74078 | 10.6082  | 16.6647  |  23.3515 |      23.3515 |                0.501411 | xp                        |
|         130 | Wieffer     | Brighton      | DEF        |     5   |            75.9042 |            0.918357 |                 0.960812 | central / defensive defender  | statistical_inference  |          0.8      |  3.8276  | 10.6058  | 16.2355  |  22.7353 |      22.7353 |                0.491685 | xp                        |
|         254 | Robinson    | Fulham        | DEF        |     4.5 |            85.0123 |            0.971895 |                 0.98651  | central / defensive defender  | statistical_inference  |          0.7623   |  3.53491 | 10.0565  | 15.1846  |  21.8698 |      21.8698 |                0.496961 | xp                        |
|          38 | A.García    | Aston Villa   | DEF        |     4   |            76.5444 |            0.922222 |                 0.962667 | central / defensive defender  | statistical_inference  |          0.552378 |  2.2946  |  6.41356 |  9.98913 |  14.1172 |      14.1172 |                0.365818 | xp                        |
|         411 | Haaland     | Man City      | FWD        |    15.5 |            83.8159 |            0.965033 |                 0.983216 | central striker               | statistical_inference  |          0.8      |  5.66551 | 15.8522  | 24.0529  |  33.6776 |      33.6776 |                0.534828 | xp                        |
|         106 | Thiago      | Brentford     | FWD        |     8   |            86.9286 |            0.98     |                 0.9904   | central striker               | statistical_inference  |          0.8      |  4.54861 | 12.7135  | 19.4485  |  27.281  |      27.281  |                0.533226 | xp                        |
|         138 | Kostoulas   | Brighton      | FWD        |     5.5 |            88.2    |            0.98     |                 0.9904   | central striker               | statistical_inference  |          0.6414   |  3.75737 | 10.3299  | 15.9692  |  22.5196 |      22.5196 |                0.278564 | xp                        |
|         467 | Sels        | Nott'm Forest | GK         |     5   |            83.6872 |            0.9916   |                 0.995968 | goalkeeper                    | statistical_inference  |          0.8      |  3.80751 |  9.82413 | 15.0769  |  21.1043 |      21.1043 |                0.542018 | xp                        |
|          57 | Petrović    | Bournemouth   | GK         |     4.5 |            84.14   |            0.9916   |                 0.995968 | goalkeeper                    | statistical_inference  |          0.8      |  3.08133 |  9.22608 | 14.4023  |  20.2272 |      20.2272 |                0.535589 | xp                        |
|         426 | B.Fernandes | Man Utd       | MID        |    12   |            85.2084 |            0.973016 |                 0.987048 | central / balanced midfielder | statistical_inference  |          0.74     |  5.62914 | 15.4845  | 23.0121  |  32.1553 |      32.1553 |                0.538894 | xp                        |
|          12 | Saka        | Arsenal       | MID        |     9.5 |            86.9456 |            0.98     |                 0.9904   | central / balanced midfielder | statistical_inference  |          0.74     |  5.18351 | 13.786   | 21.0488  |  29.6203 |      29.6203 |                0.517141 | xp                        |
|          74 | Brooks      | Bournemouth   | MID        |     5   |            88.2    |            0.98     |                 0.9904   | advanced midfielder / winger  | statistical_inference  |          0.79244  |  3.63785 | 10.3055  | 16.031   |  22.6499 |      22.6499 |                0.297156 | xp                        |
|         126 | O'Riley     | Brighton      | MID        |     5.5 |            88.2    |            0.98     |                 0.9904   | advanced midfielder / winger  | statistical_inference  |          0.583356 |  3.83125 | 10.4083  | 16.0551  |  22.6148 |      22.6148 |                0.263632 | xp                        |
|         489 | Yates       | Nott'm Forest | MID        |     4.5 |            79.036  |            0.9916   |                 0.995968 | central / balanced midfielder | statistical_inference  |          0.653911 |  2.09807 |  5.65889 |  8.75851 |  12.306  |      12.306  |                0.453831 | xp                        |

## Maximum-EV haaland

Objective: **345.85**
GW1 captain: **Haaland**
GW1 vice-captain: **B.Fernandes**
GW1 bench order: **Robinson → A.García → Yates** (outfield; GK separate)
GW1 exact-mechanics xP: **54.40**

|   player_id | web_name    | team_name     | position   |   price |   expected_minutes |   start_probability |   appearance_probability | tactical_role                 | tactical_role_source   |   role_confidence |   gw1_xp |   xpts_3 |   xpts_5 |   xpts_8 |   horizon_xp |   projection_confidence | decision_projection_col   |
|------------:|:------------|:--------------|:-----------|--------:|-------------------:|--------------------:|-------------------------:|:------------------------------|:-----------------------|------------------:|---------:|---------:|---------:|---------:|-------------:|------------------------:|:--------------------------|
|         387 | O'Reilly    | Man City      | DEF        |     6.5 |            88.2    |            0.98     |                 0.9904   | central / defensive defender  | statistical_inference  |          0.7386   |  4.52553 | 12.5145  | 18.9192  |  26.2984 |      26.2984 |                0.536823 | xp                        |
|         445 | Thiaw       | Newcastle     | DEF        |     5   |            87.9921 |            0.98     |                 0.9904   | central / defensive defender  | statistical_inference  |          0.7687   |  3.74078 | 10.6082  | 16.6647  |  23.3515 |      23.3515 |                0.501411 | xp                        |
|         130 | Wieffer     | Brighton      | DEF        |     5   |            75.9042 |            0.918357 |                 0.960812 | central / defensive defender  | statistical_inference  |          0.8      |  3.8276  | 10.6058  | 16.2355  |  22.7353 |      22.7353 |                0.491685 | xp                        |
|         254 | Robinson    | Fulham        | DEF        |     4.5 |            85.0123 |            0.971895 |                 0.98651  | central / defensive defender  | statistical_inference  |          0.7623   |  3.53491 | 10.0565  | 15.1846  |  21.8698 |      21.8698 |                0.496961 | xp                        |
|          38 | A.García    | Aston Villa   | DEF        |     4   |            76.5444 |            0.922222 |                 0.962667 | central / defensive defender  | statistical_inference  |          0.552378 |  2.2946  |  6.41356 |  9.98913 |  14.1172 |      14.1172 |                0.365818 | xp                        |
|         411 | Haaland     | Man City      | FWD        |    15.5 |            83.8159 |            0.965033 |                 0.983216 | central striker               | statistical_inference  |          0.8      |  5.66551 | 15.8522  | 24.0529  |  33.6776 |      33.6776 |                0.534828 | xp                        |
|         106 | Thiago      | Brentford     | FWD        |     8   |            86.9286 |            0.98     |                 0.9904   | central striker               | statistical_inference  |          0.8      |  4.54861 | 12.7135  | 19.4485  |  27.281  |      27.281  |                0.533226 | xp                        |
|         138 | Kostoulas   | Brighton      | FWD        |     5.5 |            88.2    |            0.98     |                 0.9904   | central striker               | statistical_inference  |          0.6414   |  3.75737 | 10.3299  | 15.9692  |  22.5196 |      22.5196 |                0.278564 | xp                        |
|         467 | Sels        | Nott'm Forest | GK         |     5   |            83.6872 |            0.9916   |                 0.995968 | goalkeeper                    | statistical_inference  |          0.8      |  3.80751 |  9.82413 | 15.0769  |  21.1043 |      21.1043 |                0.542018 | xp                        |
|          57 | Petrović    | Bournemouth   | GK         |     4.5 |            84.14   |            0.9916   |                 0.995968 | goalkeeper                    | statistical_inference  |          0.8      |  3.08133 |  9.22608 | 14.4023  |  20.2272 |      20.2272 |                0.535589 | xp                        |
|         426 | B.Fernandes | Man Utd       | MID        |    12   |            85.2084 |            0.973016 |                 0.987048 | central / balanced midfielder | statistical_inference  |          0.74     |  5.62914 | 15.4845  | 23.0121  |  32.1553 |      32.1553 |                0.538894 | xp                        |
|          12 | Saka        | Arsenal       | MID        |     9.5 |            86.9456 |            0.98     |                 0.9904   | central / balanced midfielder | statistical_inference  |          0.74     |  5.18351 | 13.786   | 21.0488  |  29.6203 |      29.6203 |                0.517141 | xp                        |
|          74 | Brooks      | Bournemouth   | MID        |     5   |            88.2    |            0.98     |                 0.9904   | advanced midfielder / winger  | statistical_inference  |          0.79244  |  3.63785 | 10.3055  | 16.031   |  22.6499 |      22.6499 |                0.297156 | xp                        |
|         126 | O'Riley     | Brighton      | MID        |     5.5 |            88.2    |            0.98     |                 0.9904   | advanced midfielder / winger  | statistical_inference  |          0.583356 |  3.83125 | 10.4083  | 16.0551  |  22.6148 |      22.6148 |                0.263632 | xp                        |
|         489 | Yates       | Nott'm Forest | MID        |     4.5 |            79.036  |            0.9916   |                 0.995968 | central / balanced midfielder | statistical_inference  |          0.653911 |  2.09807 |  5.65889 |  8.75851 |  12.306  |      12.306  |                0.453831 | xp                        |

## Maximum-EV no-haaland

Objective: **342.59**
GW1 captain: **B.Fernandes**
GW1 vice-captain: **Saka**
GW1 bench order: **Kostoulas → Thiaw → Robinson** (outfield; GK separate)
GW1 exact-mechanics xP: **54.54**

|   player_id | web_name    | team_name     | position   |   price |   expected_minutes |   start_probability |   appearance_probability | tactical_role                 | tactical_role_source   |   role_confidence |   gw1_xp |   xpts_3 |   xpts_5 |   xpts_8 |   horizon_xp |   projection_confidence | decision_projection_col   |
|------------:|:------------|:--------------|:-----------|--------:|-------------------:|--------------------:|-------------------------:|:------------------------------|:-----------------------|------------------:|---------:|---------:|---------:|---------:|-------------:|------------------------:|:--------------------------|
|         387 | O'Reilly    | Man City      | DEF        |     6.5 |            88.2    |            0.98     |                 0.9904   | central / defensive defender  | statistical_inference  |           0.7386  |  4.52553 | 12.5145  |  18.9192 |  26.2984 |      26.2984 |                0.536823 | xp                        |
|         388 | Guéhi       | Man City      | DEF        |     6   |            88.2    |            0.98     |                 0.9904   | central / defensive defender  | statistical_inference  |           0.7594  |  4.22452 | 11.6874  |  17.6779 |  24.5694 |      24.5694 |                0.54603  | xp                        |
|         445 | Thiaw       | Newcastle     | DEF        |     5   |            87.9921 |            0.98     |                 0.9904   | central / defensive defender  | statistical_inference  |           0.7687  |  3.74078 | 10.6082  |  16.6647 |  23.3515 |      23.3515 |                0.501411 | xp                        |
|         130 | Wieffer     | Brighton      | DEF        |     5   |            75.9042 |            0.918357 |                 0.960812 | central / defensive defender  | statistical_inference  |           0.8     |  3.8276  | 10.6058  |  16.2355 |  22.7353 |      22.7353 |                0.491685 | xp                        |
|         254 | Robinson    | Fulham        | DEF        |     4.5 |            85.0123 |            0.971895 |                 0.98651  | central / defensive defender  | statistical_inference  |           0.7623  |  3.53491 | 10.0565  |  15.1846 |  21.8698 |      21.8698 |                0.496961 | xp                        |
|         106 | Thiago      | Brentford     | FWD        |     8   |            86.9286 |            0.98     |                 0.9904   | central striker               | statistical_inference  |           0.8     |  4.54861 | 12.7135  |  19.4485 |  27.281  |      27.281  |                0.533226 | xp                        |
|          55 | Watkins     | Aston Villa   | FWD        |     8   |            81.8885 |            0.953872 |                 0.977859 | central striker               | statistical_inference  |           0.7988  |  4.08208 | 11.4805  |  17.7737 |  24.9219 |      24.9219 |                0.572224 | xp                        |
|         138 | Kostoulas   | Brighton      | FWD        |     5.5 |            88.2    |            0.98     |                 0.9904   | central striker               | statistical_inference  |           0.6414  |  3.75737 | 10.3299  |  15.9692 |  22.5196 |      22.5196 |                0.278564 | xp                        |
|         467 | Sels        | Nott'm Forest | GK         |     5   |            83.6872 |            0.9916   |                 0.995968 | goalkeeper                    | statistical_inference  |           0.8     |  3.80751 |  9.82413 |  15.0769 |  21.1043 |      21.1043 |                0.542018 | xp                        |
|          57 | Petrović    | Bournemouth   | GK         |     4.5 |            84.14   |            0.9916   |                 0.995968 | goalkeeper                    | statistical_inference  |           0.8     |  3.08133 |  9.22608 |  14.4023 |  20.2272 |      20.2272 |                0.535589 | xp                        |
|         426 | B.Fernandes | Man Utd       | MID        |    12   |            85.2084 |            0.973016 |                 0.987048 | central / balanced midfielder | statistical_inference  |           0.74    |  5.62914 | 15.4845  |  23.0121 |  32.1553 |      32.1553 |                0.538894 | xp                        |
|          12 | Saka        | Arsenal       | MID        |     9.5 |            86.9456 |            0.98     |                 0.9904   | central / balanced midfielder | statistical_inference  |           0.74    |  5.18351 | 13.786   |  21.0488 |  29.6203 |      29.6203 |                0.517141 | xp                        |
|         155 | Enzo        | Chelsea       | MID        |     7   |            87.192  |            0.98     |                 0.9904   | central / balanced midfielder | statistical_inference  |           0.74    |  4.1203  | 11.2542  |  17.746  |  25.0131 |      25.0131 |                0.485306 | xp                        |
|         399 | Cherki      | Man City      | MID        |     7.5 |            88.2    |            0.98     |                 0.9904   | creative midfielder           | statistical_inference  |           0.794   |  4.22783 | 11.6761  |  17.7841 |  24.9322 |      24.9322 |                0.379825 | xp                        |
|          94 | Schade      | Brentford     | MID        |     6   |            81.7007 |            0.952778 |                 0.977333 | advanced midfielder / winger  | statistical_inference  |           0.75926 |  4.07414 | 11.4058  |  17.4467 |  24.4574 |      24.4574 |                0.521893 | xp                        |

## Robust CVaR unrestricted

Blended objective: **340.63**
Scenario mean: **346.63**
Lower-tail CVaR: **316.62**
Maximum-EV/robust squad overlap: **12/15**

|   player_id | web_name    | team_name     | position   |   price |   expected_minutes |   start_probability |   appearance_probability | tactical_role                 | tactical_role_source   |   role_confidence |   gw1_xp |   xpts_3 |   xpts_5 |   xpts_8 |   horizon_xp |   projection_confidence |
|------------:|:------------|:--------------|:-----------|--------:|-------------------:|--------------------:|-------------------------:|:------------------------------|:-----------------------|------------------:|---------:|---------:|---------:|---------:|-------------:|------------------------:|
|         387 | O'Reilly    | Man City      | DEF        |     6.5 |            88.2    |            0.98     |                 0.9904   | central / defensive defender  | statistical_inference  |          0.7386   |  4.26622 | 12.5145  | 18.9192  |  26.2984 |      26.2984 |                0.536823 |
|         388 | Guéhi       | Man City      | DEF        |     6   |            88.2    |            0.98     |                 0.9904   | central / defensive defender  | statistical_inference  |          0.7594   |  3.97297 | 11.6874  | 17.6779  |  24.5694 |      24.5694 |                0.54603  |
|         445 | Thiaw       | Newcastle     | DEF        |     5   |            87.9921 |            0.98     |                 0.9904   | central / defensive defender  | statistical_inference  |          0.7687   |  3.4571  | 10.6082  | 16.6647  |  23.3515 |      23.3515 |                0.501411 |
|         130 | Wieffer     | Brighton      | DEF        |     5   |            75.9042 |            0.918357 |                 0.960812 | central / defensive defender  | statistical_inference  |          0.8      |  3.5404  | 10.6058  | 16.2355  |  22.7353 |      22.7353 |                0.491685 |
|          38 | A.García    | Aston Villa   | DEF        |     4   |            76.5444 |            0.922222 |                 0.962667 | central / defensive defender  | statistical_inference  |          0.552378 |  2.01053 |  6.41356 |  9.98913 |  14.1172 |      14.1172 |                0.365818 |
|         411 | Haaland     | Man City      | FWD        |    15.5 |            83.8159 |            0.965033 |                 0.983216 | central striker               | statistical_inference  |          0.8      |  5.37105 | 15.8522  | 24.0529  |  33.6776 |      33.6776 |                0.534828 |
|         138 | Kostoulas   | Brighton      | FWD        |     5.5 |            88.2    |            0.98     |                 0.9904   | central striker               | statistical_inference  |          0.6414   |  3.32742 | 10.3299  | 15.9692  |  22.5196 |      22.5196 |                0.278564 |
|         168 | Marc Guiu   | Chelsea       | FWD        |     5   |            88.2    |            0.98     |                 0.9904   | central striker               | statistical_inference  |          0.616556 |  2.71294 |  8.25699 | 12.9725  |  18.2774 |      18.2774 |                0.31915  |
|         467 | Sels        | Nott'm Forest | GK         |     5   |            83.6872 |            0.9916   |                 0.995968 | goalkeeper                    | statistical_inference  |          0.8      |  3.57061 |  9.82413 | 15.0769  |  21.1043 |      21.1043 |                0.542018 |
|          57 | Petrović    | Bournemouth   | GK         |     4.5 |            84.14   |            0.9916   |                 0.995968 | goalkeeper                    | statistical_inference  |          0.8      |  2.84102 |  9.22608 | 14.4023  |  20.2272 |      20.2272 |                0.535589 |
|         426 | B.Fernandes | Man Utd       | MID        |    12   |            85.2084 |            0.973016 |                 0.987048 | central / balanced midfielder | statistical_inference  |          0.74     |  5.3369  | 15.4845  | 23.0121  |  32.1553 |      32.1553 |                0.538894 |
|          12 | Saka        | Arsenal       | MID        |     9.5 |            86.9456 |            0.98     |                 0.9904   | central / balanced midfielder | statistical_inference  |          0.74     |  4.87848 | 13.786   | 21.0488  |  29.6203 |      29.6203 |                0.517141 |
|          94 | Schade      | Brentford     | MID        |     6   |            81.7007 |            0.952778 |                 0.977333 | advanced midfielder / winger  | statistical_inference  |          0.75926  |  3.7811  | 11.4058  | 17.4467  |  24.4574 |      24.4574 |                0.521893 |
|          74 | Brooks      | Bournemouth   | MID        |     5   |            88.2    |            0.98     |                 0.9904   | advanced midfielder / winger  | statistical_inference  |          0.79244  |  3.20591 | 10.3055  | 16.031   |  22.6499 |      22.6499 |                0.297156 |
|         126 | O'Riley     | Brighton      | MID        |     5.5 |            88.2    |            0.98     |                 0.9904   | advanced midfielder / winger  | statistical_inference  |          0.583356 |  3.39351 | 10.4083  | 16.0551  |  22.6148 |      22.6148 |                0.263632 |

## Robust CVaR haaland

Blended objective: **340.63**
Scenario mean: **346.63**
Lower-tail CVaR: **316.62**
Maximum-EV/robust squad overlap: **12/15**

|   player_id | web_name    | team_name     | position   |   price |   expected_minutes |   start_probability |   appearance_probability | tactical_role                 | tactical_role_source   |   role_confidence |   gw1_xp |   xpts_3 |   xpts_5 |   xpts_8 |   horizon_xp |   projection_confidence |
|------------:|:------------|:--------------|:-----------|--------:|-------------------:|--------------------:|-------------------------:|:------------------------------|:-----------------------|------------------:|---------:|---------:|---------:|---------:|-------------:|------------------------:|
|         387 | O'Reilly    | Man City      | DEF        |     6.5 |            88.2    |            0.98     |                 0.9904   | central / defensive defender  | statistical_inference  |          0.7386   |  4.26622 | 12.5145  | 18.9192  |  26.2984 |      26.2984 |                0.536823 |
|         388 | Guéhi       | Man City      | DEF        |     6   |            88.2    |            0.98     |                 0.9904   | central / defensive defender  | statistical_inference  |          0.7594   |  3.97297 | 11.6874  | 17.6779  |  24.5694 |      24.5694 |                0.54603  |
|         445 | Thiaw       | Newcastle     | DEF        |     5   |            87.9921 |            0.98     |                 0.9904   | central / defensive defender  | statistical_inference  |          0.7687   |  3.4571  | 10.6082  | 16.6647  |  23.3515 |      23.3515 |                0.501411 |
|         130 | Wieffer     | Brighton      | DEF        |     5   |            75.9042 |            0.918357 |                 0.960812 | central / defensive defender  | statistical_inference  |          0.8      |  3.5404  | 10.6058  | 16.2355  |  22.7353 |      22.7353 |                0.491685 |
|          38 | A.García    | Aston Villa   | DEF        |     4   |            76.5444 |            0.922222 |                 0.962667 | central / defensive defender  | statistical_inference  |          0.552378 |  2.01053 |  6.41356 |  9.98913 |  14.1172 |      14.1172 |                0.365818 |
|         411 | Haaland     | Man City      | FWD        |    15.5 |            83.8159 |            0.965033 |                 0.983216 | central striker               | statistical_inference  |          0.8      |  5.37105 | 15.8522  | 24.0529  |  33.6776 |      33.6776 |                0.534828 |
|         138 | Kostoulas   | Brighton      | FWD        |     5.5 |            88.2    |            0.98     |                 0.9904   | central striker               | statistical_inference  |          0.6414   |  3.32742 | 10.3299  | 15.9692  |  22.5196 |      22.5196 |                0.278564 |
|         168 | Marc Guiu   | Chelsea       | FWD        |     5   |            88.2    |            0.98     |                 0.9904   | central striker               | statistical_inference  |          0.616556 |  2.71294 |  8.25699 | 12.9725  |  18.2774 |      18.2774 |                0.31915  |
|         467 | Sels        | Nott'm Forest | GK         |     5   |            83.6872 |            0.9916   |                 0.995968 | goalkeeper                    | statistical_inference  |          0.8      |  3.57061 |  9.82413 | 15.0769  |  21.1043 |      21.1043 |                0.542018 |
|          57 | Petrović    | Bournemouth   | GK         |     4.5 |            84.14   |            0.9916   |                 0.995968 | goalkeeper                    | statistical_inference  |          0.8      |  2.84102 |  9.22608 | 14.4023  |  20.2272 |      20.2272 |                0.535589 |
|         426 | B.Fernandes | Man Utd       | MID        |    12   |            85.2084 |            0.973016 |                 0.987048 | central / balanced midfielder | statistical_inference  |          0.74     |  5.3369  | 15.4845  | 23.0121  |  32.1553 |      32.1553 |                0.538894 |
|          12 | Saka        | Arsenal       | MID        |     9.5 |            86.9456 |            0.98     |                 0.9904   | central / balanced midfielder | statistical_inference  |          0.74     |  4.87848 | 13.786   | 21.0488  |  29.6203 |      29.6203 |                0.517141 |
|          94 | Schade      | Brentford     | MID        |     6   |            81.7007 |            0.952778 |                 0.977333 | advanced midfielder / winger  | statistical_inference  |          0.75926  |  3.7811  | 11.4058  | 17.4467  |  24.4574 |      24.4574 |                0.521893 |
|          74 | Brooks      | Bournemouth   | MID        |     5   |            88.2    |            0.98     |                 0.9904   | advanced midfielder / winger  | statistical_inference  |          0.79244  |  3.20591 | 10.3055  | 16.031   |  22.6499 |      22.6499 |                0.297156 |
|         126 | O'Riley     | Brighton      | MID        |     5.5 |            88.2    |            0.98     |                 0.9904   | advanced midfielder / winger  | statistical_inference  |          0.583356 |  3.39351 | 10.4083  | 16.0551  |  22.6148 |      22.6148 |                0.263632 |

## Robust CVaR no-haaland

Blended objective: **336.32**
Scenario mean: **341.81**
Lower-tail CVaR: **314.36**
Maximum-EV/robust squad overlap: **15/15**

|   player_id | web_name    | team_name     | position   |   price |   expected_minutes |   start_probability |   appearance_probability | tactical_role                 | tactical_role_source   |   role_confidence |   gw1_xp |   xpts_3 |   xpts_5 |   xpts_8 |   horizon_xp |   projection_confidence |
|------------:|:------------|:--------------|:-----------|--------:|-------------------:|--------------------:|-------------------------:|:------------------------------|:-----------------------|------------------:|---------:|---------:|---------:|---------:|-------------:|------------------------:|
|         387 | O'Reilly    | Man City      | DEF        |     6.5 |            88.2    |            0.98     |                 0.9904   | central / defensive defender  | statistical_inference  |           0.7386  |  4.26622 | 12.5145  |  18.9192 |  26.2984 |      26.2984 |                0.536823 |
|         388 | Guéhi       | Man City      | DEF        |     6   |            88.2    |            0.98     |                 0.9904   | central / defensive defender  | statistical_inference  |           0.7594  |  3.97297 | 11.6874  |  17.6779 |  24.5694 |      24.5694 |                0.54603  |
|         445 | Thiaw       | Newcastle     | DEF        |     5   |            87.9921 |            0.98     |                 0.9904   | central / defensive defender  | statistical_inference  |           0.7687  |  3.4571  | 10.6082  |  16.6647 |  23.3515 |      23.3515 |                0.501411 |
|         130 | Wieffer     | Brighton      | DEF        |     5   |            75.9042 |            0.918357 |                 0.960812 | central / defensive defender  | statistical_inference  |           0.8     |  3.5404  | 10.6058  |  16.2355 |  22.7353 |      22.7353 |                0.491685 |
|         254 | Robinson    | Fulham        | DEF        |     4.5 |            85.0123 |            0.971895 |                 0.98651  | central / defensive defender  | statistical_inference  |           0.7623  |  3.24188 | 10.0565  |  15.1846 |  21.8698 |      21.8698 |                0.496961 |
|         106 | Thiago      | Brentford     | FWD        |     8   |            86.9286 |            0.98     |                 0.9904   | central striker               | statistical_inference  |           0.8     |  4.25026 | 12.7135  |  19.4485 |  27.281  |      27.281  |                0.533226 |
|          55 | Watkins     | Aston Villa   | FWD        |     8   |            81.8885 |            0.953872 |                 0.977859 | central striker               | statistical_inference  |           0.7988  |  3.82168 | 11.4805  |  17.7737 |  24.9219 |      24.9219 |                0.572224 |
|         138 | Kostoulas   | Brighton      | FWD        |     5.5 |            88.2    |            0.98     |                 0.9904   | central striker               | statistical_inference  |           0.6414  |  3.32742 | 10.3299  |  15.9692 |  22.5196 |      22.5196 |                0.278564 |
|         467 | Sels        | Nott'm Forest | GK         |     5   |            83.6872 |            0.9916   |                 0.995968 | goalkeeper                    | statistical_inference  |           0.8     |  3.57061 |  9.82413 |  15.0769 |  21.1043 |      21.1043 |                0.542018 |
|          57 | Petrović    | Bournemouth   | GK         |     4.5 |            84.14   |            0.9916   |                 0.995968 | goalkeeper                    | statistical_inference  |           0.8     |  2.84102 |  9.22608 |  14.4023 |  20.2272 |      20.2272 |                0.535589 |
|         426 | B.Fernandes | Man Utd       | MID        |    12   |            85.2084 |            0.973016 |                 0.987048 | central / balanced midfielder | statistical_inference  |           0.74    |  5.3369  | 15.4845  |  23.0121 |  32.1553 |      32.1553 |                0.538894 |
|          12 | Saka        | Arsenal       | MID        |     9.5 |            86.9456 |            0.98     |                 0.9904   | central / balanced midfielder | statistical_inference  |           0.74    |  4.87848 | 13.786   |  21.0488 |  29.6203 |      29.6203 |                0.517141 |
|         155 | Enzo        | Chelsea       | MID        |     7   |            87.192  |            0.98     |                 0.9904   | central / balanced midfielder | statistical_inference  |           0.74    |  3.83601 | 11.2542  |  17.746  |  25.0131 |      25.0131 |                0.485306 |
|         399 | Cherki      | Man City      | MID        |     7.5 |            88.2    |            0.98     |                 0.9904   | creative midfielder           | statistical_inference  |           0.794   |  3.88763 | 11.6761  |  17.7841 |  24.9322 |      24.9322 |                0.379825 |
|          94 | Schade      | Brentford     | MID        |     6   |            81.7007 |            0.952778 |                 0.977333 | advanced midfielder / winger  | statistical_inference  |           0.75926 |  3.7811  | 11.4058  |  17.4467 |  24.4574 |      24.4574 |                0.521893 |

## GW1-GW5 contingency route

Starting bank: **0.00**

Before every later deadline, refresh official fixtures, prices, injuries, minutes, news and all required forecasts. Execute only the newly re-solved first action if the strict Pinnacle gate remains green; never execute a stored future move from this packet.

- GW2 contingency: Sels → Kelleher; hit -0; bank 0.00
- GW3 contingency: none → none; hit -0; bank 0.00
- GW4 contingency: Kelleher → Henderson; hit -0; bank 0.00
- GW5 contingency: Wieffer, Henderson → Botman, Sels; hit -0; bank 0.00

## Initial chip policy

Recommended chip: **hold**
A GW1-window score cannot measure the opportunity cost of using a chip before later blanks, doubles and fixture swings are known.

## Selection-regret stress test

|   player_id | web_name    | selected   | stress_type       |   baseline_objective |   constrained_objective |   objective_regret | constrained_status   |
|------------:|:------------|:-----------|:------------------|---------------------:|------------------------:|-------------------:|:---------------------|
|         411 | Haaland     | True       | ban_selected      |              345.847 |                 342.59  |          3.25683   | Optimal              |
|         426 | B.Fernandes | True       | ban_selected      |              345.847 |                 343.562 |          2.28482   | Optimal              |
|         387 | O'Reilly    | True       | ban_selected      |              345.847 |                 344.829 |          1.01738   | Optimal              |
|          12 | Saka        | True       | ban_selected      |              345.847 |                 345.056 |          0.790215  | Optimal              |
|          74 | Brooks      | True       | ban_selected      |              345.847 |                 345.138 |          0.70895   | Optimal              |
|         445 | Thiaw       | True       | ban_selected      |              345.847 |                 345.176 |          0.67036   | Optimal              |
|         138 | Kostoulas   | True       | ban_selected      |              345.847 |                 345.615 |          0.231687  | Optimal              |
|         254 | Robinson    | True       | ban_selected      |              345.847 |                 345.642 |          0.204371  | Optimal              |
|          57 | Petrović    | True       | ban_selected      |              345.847 |                 345.642 |          0.204263  | Optimal              |
|         106 | Thiago      | True       | ban_selected      |              345.847 |                 345.648 |          0.198437  | Optimal              |
|         130 | Wieffer     | True       | ban_selected      |              345.847 |                 345.648 |          0.198437  | Optimal              |
|         467 | Sels        | True       | ban_selected      |              345.847 |                 345.658 |          0.188986  | Optimal              |
|          38 | A.García    | True       | ban_selected      |              345.847 |                 345.681 |          0.165439  | Optimal              |
|         126 | O'Riley     | True       | ban_selected      |              345.847 |                 345.729 |          0.117966  | Optimal              |
|         489 | Yates       | True       | ban_selected      |              345.847 |                 345.833 |          0.0136496 | Optimal              |
|         397 | Semenyo     | False      | force_alternative |              345.847 |                 341.377 |          4.46969   | Optimal              |
|         427 | Mbeumo      | False      | force_alternative |              345.847 |                 342.238 |          3.60823   | Optimal              |
|         428 | Cunha       | False      | force_alternative |              345.847 |                 342.326 |          3.52036   | Optimal              |
|          55 | Watkins     | False      | force_alternative |              345.847 |                 343.443 |          2.40383   | Optimal              |
|         356 | Virgil      | False      | force_alternative |              345.847 |                 344.021 |          1.82565   | Optimal              |
|          14 | Eze         | False      | force_alternative |              345.847 |                 344.023 |          1.82369   | Optimal              |
|          95 | O.Dango     | False      | force_alternative |              345.847 |                 344.541 |          1.30536   | Optimal              |
|         399 | Cherki      | False      | force_alternative |              345.847 |                 344.567 |          1.27955   | Optimal              |
|         155 | Enzo        | False      | force_alternative |              345.847 |                 345.056 |          0.790215  | Optimal              |
|         388 | Guéhi       | False      | force_alternative |              345.847 |                 345.648 |          0.198437  | Optimal              |
|          94 | Schade      | False      | force_alternative |              345.847 |                 345.648 |          0.198437  | Optimal              |
|          20 | Dowman      | False      | force_alternative |              345.847 |                 345.729 |          0.117966  | Optimal              |
