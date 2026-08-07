# Apex Pinnacle decision

Generated: 2026-08-07T12:47:25.326109+00:00
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

- WARNING: covariance coefficients are transparent priors until enough 2026/27 deadline outcomes exist
- WARNING: independent solver parity snapshot is not embedded in this run

## Maximum-EV unrestricted

Objective: **303.98**
GW1 captain: **Dasilva**
GW1 vice-captain: **Haaland**
GW1 bench order: **Mheuka → Enes Ünal → Drakes-Thomas** (outfield; GK separate)
GW1 exact-mechanics xP: **54.26**

|   player_id | web_name      | team_name      | position   |   price |   expected_minutes |   start_probability |   appearance_probability | tactical_role                  | tactical_role_source   |   role_confidence |   gw1_xp |   xpts_3 |   xpts_5 |   xpts_8 |   horizon_xp |   projection_confidence | decision_projection_col   |
|------------:|:--------------|:---------------|:-----------|--------:|-------------------:|--------------------:|-------------------------:|:-------------------------------|:-----------------------|------------------:|---------:|---------:|---------:|---------:|-------------:|------------------------:|:--------------------------|
|         447 | Botman        | Newcastle      | DEF        |     5   |            80.7791 |            0.762532 |                 0.886015 | central / defensive defender   | statistical_inference  |          0.750667 |  3.67263 | 10.3417  | 16.1295  |  22.6313 |      22.6313 |                0.494959 | xp                        |
|         391 | Gvardiol      | Man City       | DEF        |     5.5 |            70.0362 |            0.766076 |                 0.887716 | central / defensive defender   | statistical_inference  |          0.736417 |  3.80137 | 10.4055  | 15.7887  |  21.9741 |      21.9741 |                0.556821 | xp                        |
|         449 | Hall          | Newcastle      | DEF        |     5   |            80.1519 |            0.755443 |                 0.882613 | central / defensive defender   | statistical_inference  |          0.72654  |  3.5139  |  9.8571  | 15.3547  |  21.5298 |      21.5298 |                0.522532 | xp                        |
|         393 | Khusanov      | Man City       | DEF        |     5.5 |            80.9408 |            0.748354 |                 0.87921  | central / defensive defender   | statistical_inference  |          0.731733 |  3.69024 | 10.0615  | 15.2554  |  21.2044 |      21.2044 |                0.549807 | xp                        |
|         418 | Maguire       | Man Utd        | DEF        |     5   |            73.5139 |            0.764304 |                 0.886866 | central / defensive defender   | statistical_inference  |          0.73356  |  3.41285 |  9.65104 | 14.4076  |  20.2325 |      20.2325 |                0.55005  | xp                        |
|         411 | Haaland       | Man City       | FWD        |    15.5 |            67.9092 |            0.438819 |                 0.730633 | central striker                | statistical_inference  |          0.8      |  4.16486 | 10.6314  | 15.9387  |  22.1849 |      22.1849 |                0.435755 | xp                        |
|          80 | Enes Ünal     | Bournemouth    | FWD        |     5.5 |            61.396  |            0.664    |                 0.83872  | central striker                | statistical_inference  |          0.601822 |  2.28567 |  5.82743 |  8.89724 |  12.4373 |      12.4373 |                0.419621 | xp                        |
|         169 | Mheuka        | Chelsea        | FWD        |     4.5 |            46.2    |            0.2      |                 0.616    | forward                        | statistical_inference  |          0.474289 |  2.04012 |  5.41258 |  8.37259 |  11.7914 |      11.7914 |                0.390254 | xp                        |
|         467 | Sels          | Nott'm Forest  | GK         |     5   |            75.9423 |            0.758987 |                 0.884314 | goalkeeper                     | statistical_inference  |          0.8      |  4.02879 | 10.5381  | 16.2067  |  22.751  |      22.751  |                0.503838 | xp                        |
|          57 | Petrović      | Bournemouth    | GK         |     4.5 |            76.1557 |            0.757215 |                 0.883463 | goalkeeper                     | statistical_inference  |          0.8      |  3.36358 |  9.97584 | 15.5359  |  21.8575 |      21.8575 |                0.496932 | xp                        |
|         103 | Dasilva       | Brentford      | MID        |     5   |            46.2    |            0.2      |                 0.616    | advanced midfielder / winger   | statistical_inference  |          0.540578 |  5.07019 | 14.065   | 21.9231  |  31.0013 |      31.0013 |                0.16491  | xp                        |
|         426 | B.Fernandes   | Man Utd        | MID        |    12   |            68.1884 |            0.434599 |                 0.728608 | central / balanced midfielder  | statistical_inference  |          0.74     |  4.13546 | 10.6943  | 15.7885  |  21.9577 |      21.9577 |                0.446293 | xp                        |
|         427 | Mbeumo        | Man Utd        | MID        |     8   |            75.9592 |            0.76962  |                 0.889418 | central / balanced midfielder  | statistical_inference  |          0.74     |  3.54606 |  9.58361 | 14.3313  |  20.034  |      20.034  |                0.516838 | xp                        |
|          12 | Saka          | Arsenal        | MID        |     9.5 |            68.5738 |            0.42616  |                 0.724557 | central / balanced midfielder  | statistical_inference  |          0.74     |  3.7391  |  9.34266 | 14.0708  |  19.6735 |      19.6735 |                0.471406 | xp                        |
|         221 | Drakes-Thomas | Crystal Palace | MID        |     4.5 |            60.236  |            0.664    |                 0.83872  | holding / defensive midfielder | statistical_inference  |          0.587378 |  2.21769 |  5.7962  |  8.98359 |  12.6653 |      12.6653 |                0.337105 | xp                        |

## Maximum-EV haaland

Objective: **303.98**
GW1 captain: **Dasilva**
GW1 vice-captain: **Haaland**
GW1 bench order: **Mheuka → Enes Ünal → Drakes-Thomas** (outfield; GK separate)
GW1 exact-mechanics xP: **54.26**

|   player_id | web_name      | team_name      | position   |   price |   expected_minutes |   start_probability |   appearance_probability | tactical_role                  | tactical_role_source   |   role_confidence |   gw1_xp |   xpts_3 |   xpts_5 |   xpts_8 |   horizon_xp |   projection_confidence | decision_projection_col   |
|------------:|:--------------|:---------------|:-----------|--------:|-------------------:|--------------------:|-------------------------:|:-------------------------------|:-----------------------|------------------:|---------:|---------:|---------:|---------:|-------------:|------------------------:|:--------------------------|
|         447 | Botman        | Newcastle      | DEF        |     5   |            80.7791 |            0.762532 |                 0.886015 | central / defensive defender   | statistical_inference  |          0.750667 |  3.67263 | 10.3417  | 16.1295  |  22.6313 |      22.6313 |                0.494959 | xp                        |
|         391 | Gvardiol      | Man City       | DEF        |     5.5 |            70.0362 |            0.766076 |                 0.887716 | central / defensive defender   | statistical_inference  |          0.736417 |  3.80137 | 10.4055  | 15.7887  |  21.9741 |      21.9741 |                0.556821 | xp                        |
|         449 | Hall          | Newcastle      | DEF        |     5   |            80.1519 |            0.755443 |                 0.882613 | central / defensive defender   | statistical_inference  |          0.72654  |  3.5139  |  9.8571  | 15.3547  |  21.5298 |      21.5298 |                0.522532 | xp                        |
|         393 | Khusanov      | Man City       | DEF        |     5.5 |            80.9408 |            0.748354 |                 0.87921  | central / defensive defender   | statistical_inference  |          0.731733 |  3.69024 | 10.0615  | 15.2554  |  21.2044 |      21.2044 |                0.549807 | xp                        |
|         418 | Maguire       | Man Utd        | DEF        |     5   |            73.5139 |            0.764304 |                 0.886866 | central / defensive defender   | statistical_inference  |          0.73356  |  3.41285 |  9.65104 | 14.4076  |  20.2325 |      20.2325 |                0.55005  | xp                        |
|         411 | Haaland       | Man City       | FWD        |    15.5 |            67.9092 |            0.438819 |                 0.730633 | central striker                | statistical_inference  |          0.8      |  4.16486 | 10.6314  | 15.9387  |  22.1849 |      22.1849 |                0.435755 | xp                        |
|          80 | Enes Ünal     | Bournemouth    | FWD        |     5.5 |            61.396  |            0.664    |                 0.83872  | central striker                | statistical_inference  |          0.601822 |  2.28567 |  5.82743 |  8.89724 |  12.4373 |      12.4373 |                0.419621 | xp                        |
|         169 | Mheuka        | Chelsea        | FWD        |     4.5 |            46.2    |            0.2      |                 0.616    | forward                        | statistical_inference  |          0.474289 |  2.04012 |  5.41258 |  8.37259 |  11.7914 |      11.7914 |                0.390254 | xp                        |
|         467 | Sels          | Nott'm Forest  | GK         |     5   |            75.9423 |            0.758987 |                 0.884314 | goalkeeper                     | statistical_inference  |          0.8      |  4.02879 | 10.5381  | 16.2067  |  22.751  |      22.751  |                0.503838 | xp                        |
|          57 | Petrović      | Bournemouth    | GK         |     4.5 |            76.1557 |            0.757215 |                 0.883463 | goalkeeper                     | statistical_inference  |          0.8      |  3.36358 |  9.97584 | 15.5359  |  21.8575 |      21.8575 |                0.496932 | xp                        |
|         103 | Dasilva       | Brentford      | MID        |     5   |            46.2    |            0.2      |                 0.616    | advanced midfielder / winger   | statistical_inference  |          0.540578 |  5.07019 | 14.065   | 21.9231  |  31.0013 |      31.0013 |                0.16491  | xp                        |
|         426 | B.Fernandes   | Man Utd        | MID        |    12   |            68.1884 |            0.434599 |                 0.728608 | central / balanced midfielder  | statistical_inference  |          0.74     |  4.13546 | 10.6943  | 15.7885  |  21.9577 |      21.9577 |                0.446293 | xp                        |
|         427 | Mbeumo        | Man Utd        | MID        |     8   |            75.9592 |            0.76962  |                 0.889418 | central / balanced midfielder  | statistical_inference  |          0.74     |  3.54606 |  9.58361 | 14.3313  |  20.034  |      20.034  |                0.516838 | xp                        |
|          12 | Saka          | Arsenal        | MID        |     9.5 |            68.5738 |            0.42616  |                 0.724557 | central / balanced midfielder  | statistical_inference  |          0.74     |  3.7391  |  9.34266 | 14.0708  |  19.6735 |      19.6735 |                0.471406 | xp                        |
|         221 | Drakes-Thomas | Crystal Palace | MID        |     4.5 |            60.236  |            0.664    |                 0.83872  | holding / defensive midfielder | statistical_inference  |          0.587378 |  2.21769 |  5.7962  |  8.98359 |  12.6653 |      12.6653 |                0.337105 | xp                        |

## Maximum-EV no-haaland

Objective: **301.61**
GW1 captain: **Dasilva**
GW1 vice-captain: **B.Fernandes**
GW1 bench order: **Watkins → Hall → Mheuka** (outfield; GK separate)
GW1 exact-mechanics xP: **55.16**

|   player_id | web_name    | team_name     | position   |   price |   expected_minutes |   start_probability |   appearance_probability | tactical_role                 | tactical_role_source   |   role_confidence |   gw1_xp |   xpts_3 |   xpts_5 |   xpts_8 |   horizon_xp |   projection_confidence | decision_projection_col   |
|------------:|:------------|:--------------|:-----------|--------:|-------------------:|--------------------:|-------------------------:|:------------------------------|:-----------------------|------------------:|---------:|---------:|---------:|---------:|-------------:|------------------------:|:--------------------------|
|         447 | Botman      | Newcastle     | DEF        |     5   |            80.7791 |            0.762532 |                 0.886015 | central / defensive defender  | statistical_inference  |          0.750667 |  3.67263 | 10.3417  | 16.1295  |  22.6313 |      22.6313 |                0.494959 | xp                        |
|         391 | Gvardiol    | Man City      | DEF        |     5.5 |            70.0362 |            0.766076 |                 0.887716 | central / defensive defender  | statistical_inference  |          0.736417 |  3.80137 | 10.4055  | 15.7887  |  21.9741 |      21.9741 |                0.556821 | xp                        |
|         449 | Hall        | Newcastle     | DEF        |     5   |            80.1519 |            0.755443 |                 0.882613 | central / defensive defender  | statistical_inference  |          0.72654  |  3.5139  |  9.8571  | 15.3547  |  21.5298 |      21.5298 |                0.522532 | xp                        |
|         393 | Khusanov    | Man City      | DEF        |     5.5 |            80.9408 |            0.748354 |                 0.87921  | central / defensive defender  | statistical_inference  |          0.731733 |  3.69024 | 10.0615  | 15.2554  |  21.2044 |      21.2044 |                0.549807 | xp                        |
|         229 | Tarkowski   | Everton       | DEF        |     6   |            78.3984 |            0.757215 |                 0.883463 | central / defensive defender  | statistical_inference  |          0.74604  |  3.69077 |  9.56174 | 14.8278  |  20.4832 |      20.4832 |                0.522807 | xp                        |
|         106 | Thiago      | Brentford     | FWD        |     8   |            68.5634 |            0.42616  |                 0.724557 | central striker               | statistical_inference  |          0.8      |  3.28176 |  8.53858 | 12.9523  |  18.0486 |      18.0486 |                0.477975 | xp                        |
|          55 | Watkins     | Aston Villa   | FWD        |     8   |            67.4585 |            0.443038 |                 0.732658 | central striker               | statistical_inference  |          0.7988   |  3.04356 |  7.95231 | 12.1956  |  17.0469 |      17.0469 |                0.442207 | xp                        |
|         169 | Mheuka      | Chelsea       | FWD        |     4.5 |            46.2    |            0.2      |                 0.616    | forward                       | statistical_inference  |          0.474289 |  2.04012 |  5.41258 |  8.37259 |  11.7914 |      11.7914 |                0.390254 | xp                        |
|         467 | Sels        | Nott'm Forest | GK         |     5   |            75.9423 |            0.758987 |                 0.884314 | goalkeeper                    | statistical_inference  |          0.8      |  4.02879 | 10.5381  | 16.2067  |  22.751  |      22.751  |                0.503838 | xp                        |
|          57 | Petrović    | Bournemouth   | GK         |     4.5 |            76.1557 |            0.757215 |                 0.883463 | goalkeeper                    | statistical_inference  |          0.8      |  3.36358 |  9.97584 | 15.5359  |  21.8575 |      21.8575 |                0.496932 | xp                        |
|         103 | Dasilva     | Brentford     | MID        |     5   |            46.2    |            0.2      |                 0.616    | advanced midfielder / winger  | statistical_inference  |          0.540578 |  5.07019 | 14.065   | 21.9231  |  31.0013 |      31.0013 |                0.16491  | xp                        |
|         426 | B.Fernandes | Man Utd       | MID        |    12   |            68.1884 |            0.434599 |                 0.728608 | central / balanced midfielder | statistical_inference  |          0.74     |  4.13546 | 10.6943  | 15.7885  |  21.9577 |      21.9577 |                0.446293 | xp                        |
|         427 | Mbeumo      | Man Utd       | MID        |     8   |            75.9592 |            0.76962  |                 0.889418 | central / balanced midfielder | statistical_inference  |          0.74     |  3.54606 |  9.58361 | 14.3313  |  20.034  |      20.034  |                0.516838 | xp                        |
|         397 | Semenyo     | Man City      | MID        |     8.5 |            75.5255 |            0.764304 |                 0.886866 | central / balanced midfielder | statistical_inference  |          0.74     |  3.57804 |  9.41543 | 14.1899  |  19.793  |      19.793  |                0.454206 | xp                        |
|          12 | Saka        | Arsenal       | MID        |     9.5 |            68.5738 |            0.42616  |                 0.724557 | central / balanced midfielder | statistical_inference  |          0.74     |  3.7391  |  9.34266 | 14.0708  |  19.6735 |      19.6735 |                0.471406 | xp                        |

## Robust CVaR unrestricted

Blended objective: **294.83**
Scenario mean: **303.23**
Lower-tail CVaR: **261.21**
Maximum-EV/robust squad overlap: **13/15**

|   player_id | web_name      | team_name      | position   |   price |   expected_minutes |   start_probability |   appearance_probability | tactical_role                  | tactical_role_source   |   role_confidence |   gw1_xp |   xpts_3 |   xpts_5 |   xpts_8 |   horizon_xp |   projection_confidence |
|------------:|:--------------|:---------------|:-----------|--------:|-------------------:|--------------------:|-------------------------:|:-------------------------------|:-----------------------|------------------:|---------:|---------:|---------:|---------:|-------------:|------------------------:|
|         447 | Botman        | Newcastle      | DEF        |     5   |            80.7791 |            0.762532 |                 0.886015 | central / defensive defender   | statistical_inference  |          0.750667 |  3.38405 | 10.3417  | 16.1295  | 22.6313  |     22.6313  |                0.494959 |
|         391 | Gvardiol      | Man City       | DEF        |     5.5 |            70.0362 |            0.766076 |                 0.887716 | central / defensive defender   | statistical_inference  |          0.736417 |  3.55074 | 10.4055  | 15.7887  | 21.9741  |     21.9741  |                0.556821 |
|         449 | Hall          | Newcastle      | DEF        |     5   |            80.1519 |            0.755443 |                 0.882613 | central / defensive defender   | statistical_inference  |          0.72654  |  3.24837 |  9.8571  | 15.3547  | 21.5298  |     21.5298  |                0.522532 |
|         393 | Khusanov      | Man City       | DEF        |     5.5 |            80.9408 |            0.748354 |                 0.87921  | central / defensive defender   | statistical_inference  |          0.731733 |  3.45379 | 10.0615  | 15.2554  | 21.2044  |     21.2044  |                0.549807 |
|         229 | Tarkowski     | Everton        | DEF        |     6   |            78.3984 |            0.757215 |                 0.883463 | central / defensive defender   | statistical_inference  |          0.74604  |  3.45839 |  9.56174 | 14.8278  | 20.4832  |     20.4832  |                0.522807 |
|         411 | Haaland       | Man City       | FWD        |    15.5 |            67.9092 |            0.438819 |                 0.730633 | central striker                | statistical_inference  |          0.8      |  3.90591 | 10.6314  | 15.9387  | 22.1849  |     22.1849  |                0.435755 |
|         169 | Mheuka        | Chelsea        | FWD        |     4.5 |            46.2    |            0.2      |                 0.616    | forward                        | statistical_inference  |          0.474289 |  1.76096 |  5.41258 |  8.37259 | 11.7914  |     11.7914  |                0.390254 |
|         466 | Neave         | Newcastle      | FWD        |     4.5 |            65.224  |            0.664    |                 0.83872  | forward                        | statistical_inference  |          0.510111 |  1.40386 |  4.17068 |  6.41414 |  9.00298 |      9.00298 |                0.474887 |
|         467 | Sels          | Nott'm Forest  | GK         |     5   |            75.9423 |            0.758987 |                 0.884314 | goalkeeper                     | statistical_inference  |          0.8      |  3.76011 | 10.5381  | 16.2067  | 22.751   |     22.751   |                0.503838 |
|          57 | Petrović      | Bournemouth    | GK         |     4.5 |            76.1557 |            0.757215 |                 0.883463 | goalkeeper                     | statistical_inference  |          0.8      |  3.07806 |  9.97584 | 15.5359  | 21.8575  |     21.8575  |                0.496932 |
|         103 | Dasilva       | Brentford      | MID        |     5   |            46.2    |            0.2      |                 0.616    | advanced midfielder / winger   | statistical_inference  |          0.540578 |  4.36232 | 14.065   | 21.9231  | 31.0013  |     31.0013  |                0.16491  |
|         426 | B.Fernandes   | Man Utd        | MID        |    12   |            68.1884 |            0.434599 |                 0.728608 | central / balanced midfielder  | statistical_inference  |          0.74     |  3.8816  | 10.6943  | 15.7885  | 21.9577  |     21.9577  |                0.446293 |
|         427 | Mbeumo        | Man Utd        | MID        |     8   |            75.9592 |            0.76962  |                 0.889418 | central / balanced midfielder  | statistical_inference  |          0.74     |  3.32573 |  9.58361 | 14.3313  | 20.034   |     20.034   |                0.516838 |
|          12 | Saka          | Arsenal        | MID        |     9.5 |            68.5738 |            0.42616  |                 0.724557 | central / balanced midfielder  | statistical_inference  |          0.74     |  3.48557 |  9.34266 | 14.0708  | 19.6735  |     19.6735  |                0.471406 |
|         221 | Drakes-Thomas | Crystal Palace | MID        |     4.5 |            60.236  |            0.664    |                 0.83872  | holding / defensive midfielder | statistical_inference  |          0.587378 |  1.86921 |  5.7962  |  8.98359 | 12.6653  |     12.6653  |                0.337105 |

## Robust CVaR haaland

Blended objective: **294.83**
Scenario mean: **303.23**
Lower-tail CVaR: **261.21**
Maximum-EV/robust squad overlap: **13/15**

|   player_id | web_name      | team_name      | position   |   price |   expected_minutes |   start_probability |   appearance_probability | tactical_role                  | tactical_role_source   |   role_confidence |   gw1_xp |   xpts_3 |   xpts_5 |   xpts_8 |   horizon_xp |   projection_confidence |
|------------:|:--------------|:---------------|:-----------|--------:|-------------------:|--------------------:|-------------------------:|:-------------------------------|:-----------------------|------------------:|---------:|---------:|---------:|---------:|-------------:|------------------------:|
|         447 | Botman        | Newcastle      | DEF        |     5   |            80.7791 |            0.762532 |                 0.886015 | central / defensive defender   | statistical_inference  |          0.750667 |  3.38405 | 10.3417  | 16.1295  | 22.6313  |     22.6313  |                0.494959 |
|         391 | Gvardiol      | Man City       | DEF        |     5.5 |            70.0362 |            0.766076 |                 0.887716 | central / defensive defender   | statistical_inference  |          0.736417 |  3.55074 | 10.4055  | 15.7887  | 21.9741  |     21.9741  |                0.556821 |
|         449 | Hall          | Newcastle      | DEF        |     5   |            80.1519 |            0.755443 |                 0.882613 | central / defensive defender   | statistical_inference  |          0.72654  |  3.24837 |  9.8571  | 15.3547  | 21.5298  |     21.5298  |                0.522532 |
|         393 | Khusanov      | Man City       | DEF        |     5.5 |            80.9408 |            0.748354 |                 0.87921  | central / defensive defender   | statistical_inference  |          0.731733 |  3.45379 | 10.0615  | 15.2554  | 21.2044  |     21.2044  |                0.549807 |
|         229 | Tarkowski     | Everton        | DEF        |     6   |            78.3984 |            0.757215 |                 0.883463 | central / defensive defender   | statistical_inference  |          0.74604  |  3.45839 |  9.56174 | 14.8278  | 20.4832  |     20.4832  |                0.522807 |
|         411 | Haaland       | Man City       | FWD        |    15.5 |            67.9092 |            0.438819 |                 0.730633 | central striker                | statistical_inference  |          0.8      |  3.90591 | 10.6314  | 15.9387  | 22.1849  |     22.1849  |                0.435755 |
|         169 | Mheuka        | Chelsea        | FWD        |     4.5 |            46.2    |            0.2      |                 0.616    | forward                        | statistical_inference  |          0.474289 |  1.76096 |  5.41258 |  8.37259 | 11.7914  |     11.7914  |                0.390254 |
|         466 | Neave         | Newcastle      | FWD        |     4.5 |            65.224  |            0.664    |                 0.83872  | forward                        | statistical_inference  |          0.510111 |  1.40386 |  4.17068 |  6.41414 |  9.00298 |      9.00298 |                0.474887 |
|         467 | Sels          | Nott'm Forest  | GK         |     5   |            75.9423 |            0.758987 |                 0.884314 | goalkeeper                     | statistical_inference  |          0.8      |  3.76011 | 10.5381  | 16.2067  | 22.751   |     22.751   |                0.503838 |
|          57 | Petrović      | Bournemouth    | GK         |     4.5 |            76.1557 |            0.757215 |                 0.883463 | goalkeeper                     | statistical_inference  |          0.8      |  3.07806 |  9.97584 | 15.5359  | 21.8575  |     21.8575  |                0.496932 |
|         103 | Dasilva       | Brentford      | MID        |     5   |            46.2    |            0.2      |                 0.616    | advanced midfielder / winger   | statistical_inference  |          0.540578 |  4.36232 | 14.065   | 21.9231  | 31.0013  |     31.0013  |                0.16491  |
|         426 | B.Fernandes   | Man Utd        | MID        |    12   |            68.1884 |            0.434599 |                 0.728608 | central / balanced midfielder  | statistical_inference  |          0.74     |  3.8816  | 10.6943  | 15.7885  | 21.9577  |     21.9577  |                0.446293 |
|         427 | Mbeumo        | Man Utd        | MID        |     8   |            75.9592 |            0.76962  |                 0.889418 | central / balanced midfielder  | statistical_inference  |          0.74     |  3.32573 |  9.58361 | 14.3313  | 20.034   |     20.034   |                0.516838 |
|          12 | Saka          | Arsenal        | MID        |     9.5 |            68.5738 |            0.42616  |                 0.724557 | central / balanced midfielder  | statistical_inference  |          0.74     |  3.48557 |  9.34266 | 14.0708  | 19.6735  |     19.6735  |                0.471406 |
|         221 | Drakes-Thomas | Crystal Palace | MID        |     4.5 |            60.236  |            0.664    |                 0.83872  | holding / defensive midfielder | statistical_inference  |          0.587378 |  1.86921 |  5.7962  |  8.98359 | 12.6653  |     12.6653  |                0.337105 |

## Robust CVaR no-haaland

Blended objective: **292.54**
Scenario mean: **300.75**
Lower-tail CVaR: **259.71**
Maximum-EV/robust squad overlap: **15/15**

|   player_id | web_name    | team_name     | position   |   price |   expected_minutes |   start_probability |   appearance_probability | tactical_role                 | tactical_role_source   |   role_confidence |   gw1_xp |   xpts_3 |   xpts_5 |   xpts_8 |   horizon_xp |   projection_confidence |
|------------:|:------------|:--------------|:-----------|--------:|-------------------:|--------------------:|-------------------------:|:------------------------------|:-----------------------|------------------:|---------:|---------:|---------:|---------:|-------------:|------------------------:|
|         447 | Botman      | Newcastle     | DEF        |     5   |            80.7791 |            0.762532 |                 0.886015 | central / defensive defender  | statistical_inference  |          0.750667 |  3.38405 | 10.3417  | 16.1295  |  22.6313 |      22.6313 |                0.494959 |
|         391 | Gvardiol    | Man City      | DEF        |     5.5 |            70.0362 |            0.766076 |                 0.887716 | central / defensive defender  | statistical_inference  |          0.736417 |  3.55074 | 10.4055  | 15.7887  |  21.9741 |      21.9741 |                0.556821 |
|         449 | Hall        | Newcastle     | DEF        |     5   |            80.1519 |            0.755443 |                 0.882613 | central / defensive defender  | statistical_inference  |          0.72654  |  3.24837 |  9.8571  | 15.3547  |  21.5298 |      21.5298 |                0.522532 |
|         393 | Khusanov    | Man City      | DEF        |     5.5 |            80.9408 |            0.748354 |                 0.87921  | central / defensive defender  | statistical_inference  |          0.731733 |  3.45379 | 10.0615  | 15.2554  |  21.2044 |      21.2044 |                0.549807 |
|         229 | Tarkowski   | Everton       | DEF        |     6   |            78.3984 |            0.757215 |                 0.883463 | central / defensive defender  | statistical_inference  |          0.74604  |  3.45839 |  9.56174 | 14.8278  |  20.4832 |      20.4832 |                0.522807 |
|         106 | Thiago      | Brentford     | FWD        |     8   |            68.5634 |            0.42616  |                 0.724557 | central striker               | statistical_inference  |          0.8      |  3.03941 |  8.53858 | 12.9523  |  18.0486 |      18.0486 |                0.477975 |
|          55 | Watkins     | Aston Villa   | FWD        |     8   |            67.4585 |            0.443038 |                 0.732658 | central striker               | statistical_inference  |          0.7988   |  2.81165 |  7.95231 | 12.1956  |  17.0469 |      17.0469 |                0.442207 |
|         169 | Mheuka      | Chelsea       | FWD        |     4.5 |            46.2    |            0.2      |                 0.616    | forward                       | statistical_inference  |          0.474289 |  1.76096 |  5.41258 |  8.37259 |  11.7914 |      11.7914 |                0.390254 |
|         467 | Sels        | Nott'm Forest | GK         |     5   |            75.9423 |            0.758987 |                 0.884314 | goalkeeper                    | statistical_inference  |          0.8      |  3.76011 | 10.5381  | 16.2067  |  22.751  |      22.751  |                0.503838 |
|          57 | Petrović    | Bournemouth   | GK         |     4.5 |            76.1557 |            0.757215 |                 0.883463 | goalkeeper                    | statistical_inference  |          0.8      |  3.07806 |  9.97584 | 15.5359  |  21.8575 |      21.8575 |                0.496932 |
|         103 | Dasilva     | Brentford     | MID        |     5   |            46.2    |            0.2      |                 0.616    | advanced midfielder / winger  | statistical_inference  |          0.540578 |  4.36232 | 14.065   | 21.9231  |  31.0013 |      31.0013 |                0.16491  |
|         426 | B.Fernandes | Man Utd       | MID        |    12   |            68.1884 |            0.434599 |                 0.728608 | central / balanced midfielder | statistical_inference  |          0.74     |  3.8816  | 10.6943  | 15.7885  |  21.9577 |      21.9577 |                0.446293 |
|         427 | Mbeumo      | Man Utd       | MID        |     8   |            75.9592 |            0.76962  |                 0.889418 | central / balanced midfielder | statistical_inference  |          0.74     |  3.32573 |  9.58361 | 14.3313  |  20.034  |      20.034  |                0.516838 |
|         397 | Semenyo     | Man City      | MID        |     8.5 |            75.5255 |            0.764304 |                 0.886866 | central / balanced midfielder | statistical_inference  |          0.74     |  3.33872 |  9.41543 | 14.1899  |  19.793  |      19.793  |                0.454206 |
|          12 | Saka        | Arsenal       | MID        |     9.5 |            68.5738 |            0.42616  |                 0.724557 | central / balanced midfielder | statistical_inference  |          0.74     |  3.48557 |  9.34266 | 14.0708  |  19.6735 |      19.6735 |                0.471406 |

## Selection-regret stress test

|   player_id | web_name      | selected   | stress_type       |   baseline_objective |   constrained_objective |   objective_regret | constrained_status   |
|------------:|:--------------|:-----------|:------------------|---------------------:|------------------------:|-------------------:|:---------------------|
|         103 | Dasilva       | True       | ban_selected      |              303.978 |                 277.728 |        26.2494     | Optimal              |
|         447 | Botman        | True       | ban_selected      |              303.978 |                 301.41  |         2.56823    | Optimal              |
|         411 | Haaland       | True       | ban_selected      |              303.978 |                 301.613 |         2.36478    | Optimal              |
|         426 | B.Fernandes   | True       | ban_selected      |              303.978 |                 301.643 |         2.33441    | Optimal              |
|         449 | Hall          | True       | ban_selected      |              303.978 |                 302.612 |         1.36557    | Optimal              |
|         391 | Gvardiol      | True       | ban_selected      |              303.978 |                 302.822 |         1.15579    | Optimal              |
|         427 | Mbeumo        | True       | ban_selected      |              303.978 |                 302.934 |         1.0435     | Optimal              |
|         467 | Sels          | True       | ban_selected      |              303.978 |                 303.006 |         0.971423   | Optimal              |
|          57 | Petrović      | True       | ban_selected      |              303.978 |                 303.366 |         0.611323   | Optimal              |
|          12 | Saka          | True       | ban_selected      |              303.978 |                 303.65  |         0.32735    | Optimal              |
|         393 | Khusanov      | True       | ban_selected      |              303.978 |                 303.65  |         0.32735    | Optimal              |
|         169 | Mheuka        | True       | ban_selected      |              303.978 |                 303.72  |         0.257723   | Optimal              |
|         221 | Drakes-Thomas | True       | ban_selected      |              303.978 |                 303.802 |         0.175952   | Optimal              |
|          80 | Enes Ünal     | True       | ban_selected      |              303.978 |                 303.969 |         0.00888687 | Optimal              |
|         418 | Maguire       | True       | ban_selected      |              303.978 |                 303.969 |         0.00888687 | Optimal              |
|         384 | Donnarumma    | False      | force_alternative |              303.978 |                 302.619 |         1.35917    | Optimal              |
|         351 | Mamardashvili | False      | force_alternative |              303.978 |                 302.784 |         1.1941     | Optimal              |
|          61 | Truffert      | False      | force_alternative |              303.978 |                 302.822 |         1.15603    | Optimal              |
|         496 | Kinsky        | False      | force_alternative |              303.978 |                 303.166 |         0.811403   | Optimal              |
|         529 | Roefs         | False      | force_alternative |              303.978 |                 303.177 |         0.800429   | Optimal              |
|         532 | Ballard       | False      | force_alternative |              303.978 |                 303.189 |         0.788832   | Optimal              |
|         202 | Richards      | False      | force_alternative |              303.978 |                 303.273 |         0.705048   | Optimal              |
|         533 | Mukiele       | False      | force_alternative |              303.978 |                 303.291 |         0.687057   | Optimal              |
|         140 | Sánchez       | False      | force_alternative |              303.978 |                 303.366 |         0.611323   | Optimal              |
|         397 | Semenyo       | False      | force_alternative |              303.978 |                 303.65  |         0.32735    | Optimal              |
|         469 | N.Williams    | False      | force_alternative |              303.978 |                 303.721 |         0.257026   | Optimal              |
|         229 | Tarkowski     | False      | force_alternative |              303.978 |                 303.969 |         0.00888687 | Optimal              |
