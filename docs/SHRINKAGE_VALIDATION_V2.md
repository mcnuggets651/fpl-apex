# Shrinkage Validation V2 — Model Card

## Decision

The corrected chronological evidence gate passes for xG90 and xA90. The
candidate remains **dormant and shadow-only**.

This result does not authorise production activation. The 2024/25 and 2025/26
evaluation seasons were inspected during earlier PR #14 iterations, so they are
not independent final holdouts. DEFCON fails its separate evidence gate and is
excluded.

## Defect withdrawn from PR #14

The original validator selected players with known future rates and at least 90
future minutes before calculating price terciles and empirical priors. That made
the prediction cohort depend on the target window and differed from live roster
calculation.

V2:

- constructs each prediction from the complete roster visible at the cutoff;
- calculates live-price terciles and hierarchical leave-one-out priors before
  applying future scoring eligibility;
- excludes the target player at tier, position and league fallback levels;
- includes pre-GW1, GW1-5 and GW6+ timing strata;
- shares the price-tier grouping helper with the candidate model;
- freezes one full-roster prediction per hyperparameter value before scoring
  positions.

## Data and split

- calibration seasons: 2022/23 and 2023/24;
- chronological evaluation seasons: 2024/25 and 2025/26;
- Vaastav revision: `8c97b2adb123863c3dd581e730f1360e89815ac2`;
- FPL Core revision: `911992600f8bb66f1530ebd2ca5d3cdc22420109`;
- outcome window: four Gameweeks;
- cutoffs: pre-GW1, GW1, GW2, GW3, GW4, then every four Gameweeks from GW6;
- bootstrap unit: player-season cluster.

Hyperparameters are selected on the calibration seasons only. Evaluation outcomes
are applied only after each cutoff's predictions are frozen.

## Corrected results

| Metric | Season | Rows | Players | Raw RMSE | Shrunk RMSE | Ratio |
|---|---:|---:|---:|---:|---:|---:|
| xG90 | 2024/25 | 3,658 | 462 | 0.155735 | 0.143828 | 0.923542 |
| xG90 | 2025/26 | 3,661 | 447 | 0.190018 | 0.138993 | 0.731473 |
| xA90 | 2024/25 | 3,679 | 462 | 0.103094 | 0.085905 | 0.833267 |
| xA90 | 2025/26 | 3,673 | 447 | 0.088635 | 0.081255 | 0.916736 |

All four attacking-rate evaluations pass the predeclared low-evidence,
overall-RMSE, established-player-harm and timing-stratum gates.

Timing-stratum RMSE ratios:

| Metric | Season | Pre-GW1 | GW1-5 | GW6+ |
|---|---:|---:|---:|---:|
| xG90 | 2024/25 | 0.956927 | 0.871473 | 0.949985 |
| xG90 | 2025/26 | 0.927800 | 0.526820 | 0.956110 |
| xA90 | 2024/25 | 0.987870 | 0.689394 | 0.946588 |
| xA90 | 2025/26 | 0.922152 | 0.840480 | 0.953174 |

DEFCON's blocked 2025/26 test fails because pre-GW1/GW1-5 evidence cannot be
validated from an equivalent prior-season field. It remains excluded.

## Candidate equivalent prior minutes

| Metric | Default | GK | DEF | MID | FWD |
|---|---:|---:|---:|---:|---:|
| xG90 | 360 | 2,400 | 1,200 | 180 | 720 |
| xA90 | 360 | 2,400 | 180 | 360 | 540 |

These are candidate research parameters, not production defaults.

## Remaining blockers

- The evaluation seasons have been adaptively reused during model development.
- Production pipeline activation and canonical pre/post decision parity are not
  part of this clean research change.
- Posterior uncertainty and captain-frequency thresholds are uncalibrated.
- DEFCON has not passed equivalent historical validation.
- The true independent test is the frozen prospective 2026/27 deadline archive.

A separate activation PR may be considered only after the dormant research PR is
reviewed, the canonical pipeline is rerun at one frozen SHA, and the prospective
archive policy is locked.
