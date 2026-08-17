# Pre-merge projection-integrity red team — 2026-08-17

## Decision

PR #64 must not be approved on CI colour alone. A successful production artifact was
red-teamed at the player/projection/source-contract level before architecture freeze.
The review found two production semantics that required repair and one important
validation limitation that must remain explicit.

## 1. Tiny-sample attacking-rate reliability

The successful pre-repair artifact selected Trey Nyoni in the GW1 XI. The transparent
Apex component projected 7.93 GW1 xP from only ~40.9 expected minutes, driven primarily
by a 1.59 xG/90 context rate backed by only 21 prior Premier League minutes. The
ensemble reduced the final number through expert disagreement, but the transparent
model was still allowing a tiny-sample rate to dominate expected value.

A low-sample guard already existed, but its mature-player upper reference used an
unweighted percentile. A player barely above the 270-minute maturity floor could
therefore influence the reference as much as a multi-thousand-minute regular.

### Permanent repair

- keep the existing <270-minute bounded reliability policy;
- do **not** activate the retired global empirical-Bayes shrinkage challenger;
- compute the mature same-position upper reference as a competitive-minutes-weighted
  empirical 90th percentile;
- continue shrinking only extreme tiny-sample xG/90 or xA/90 toward the
  minutes-weighted mature position prior;
- preserve ordinary tiny samples and mature rates exactly;
- retain audit fields for raw rate, prior, mature p90, reliability and adjustment.

This is a reliability repair, not a preference-based cap and not tuning to remove a
specific player.

## 2. Ensemble weight/source semantics

The pre-repair configuration declared 24% Official FPL / 46% Apex / 20% AIrsenal /
10% market. No production market-xP source existed, so the 10% market slot was silently
removed by row-wise normalisation. GW1 effective weights were therefore approximately
26.67% / 51.11% / 22.22% / 0%. After GW1, Official EP is legitimately unavailable and
the surface becomes approximately 69.70% Apex / 30.30% AIrsenal.

### Permanent repair

- market weight is 0 until genuine market xP is configured;
- the three live pre-GW1 weights are explicitly 0.2666666667 Official,
  0.5111111111 Apex and 0.2222222222 AIrsenal;
- these preserve the previous 24:46:20 relative prior exactly, so this repair does not
  retune the team;
- production configured weights must sum to 1 and unknown keys fail;
- a positive market weight without a genuine market surface fails closed.

These are prior policy weights, **not** empirically optimal 2026/27 weights. The
existing calibration promotion contract remains unchanged: genuine sealed outcomes
must reach at least 8 completed Gameweeks / 200 active rows before a learned challenger
can replace them.

## 3. AIrsenal exact-zero role prior

The pinned AIrsenal source was inspected before changing its treatment. Its current
and pinned code uses recent minutes and, before GW1, falls back to previous-season
minutes for the player's current club. When no such history exists it returns `[0]`;
the prediction code then emits exactly 0.0 expected points. The same logic remains on
AIrsenal's current upstream branch as of this review.

The pre-repair Apex artifact contained hundreds of exact-zero AIrsenal rows, including
players for whom both Official FPL EP and Apex's explicit appearance model implied
meaningful participation. Treating such a structural zero exactly like a normal
current-role forecast can suppress transfers/new roles for the wrong reason.

### Permanent repair

An exact-zero AIrsenal row abstains only when two independent current signals contradict
the zero-minute premise:

1. Official FPL EP is at least 1.0; and
2. Apex expected appearance points are at least 1.0.

A conflict established on a current-GW row propagates only to other exact-zero rows for
that player in the horizon. Positive AIrsenal forecasts are never suppressed. Raw
source presence remains visible, `source_usable_airsenal` becomes false for the
conflicted row, and the configured AIrsenal share uses the same explicit transparent
Apex fallback already used for a genuinely missing AIrsenal prediction. Direct and
fallback Apex shares remain separately auditable while the canonical Apex contribution
reconciles additively to total xP.

Exact-zero rows without the independent current-role contradiction remain valid
AIrsenal forecasts and keep their normal weight.

## 4. Minutes and objective policy

No architecture change was justified here. Expected minutes remain an exposure input to
FPL expected points, not a separate safety or nailedness reward. Preseason role evidence
is reliability weighted; a single cameo is capped; repeated starts can supersede stale
history; attributable current evidence can override statistical priors; availability is
a hard ceiling. The final optimiser still maximises raw canonical expected FPL points.
Uncertainty/risk remains diagnostic rather than a hidden penalty.

## 5. Point compression

The pre-repair GW1 artifact showed the ensemble was less dispersed than either the Apex
or AIrsenal expert alone, as expected from averaging partially independent forecasts.
No evidence supports adding an anti-compression multiplier or re-inflating high-end
scores. Doing so before outcome calibration would manufacture upside rather than improve
expected-value accuracy. The correct control is explicit expert provenance/weighting,
not an arbitrary spread target.

The architecture therefore keeps canonical xP as the ensemble mean and records expert
disagreement/uncertainty separately. Future weight or calibration changes must pass the
existing chronological promotion gate.

## 6. What can and cannot be certified before GW1

Can be certified after fresh acceptance:

- official identity/club/position/price/status completeness;
- projection-pair completeness and source provenance;
- scoring/mechanics legality;
- explicit minutes/role evidence semantics;
- additive ensemble decomposition and source fallback semantics;
- exact optimiser/parity behavior;
- fail-closed final publication and final-selector stability.

Cannot honestly be certified yet:

- that these prior expert weights are statistically optimal for 2026/27;
- a guaranteed final rank or points total;
- superiority to the user's 2,160-point prior-season benchmark.

The full-season replay engine exists, but the 2025/26 archive has zero genuine
pre-deadline Apex decision bundles, so a valid 38-GW no-hindsight Apex season score
cannot be reconstructed without hindsight. CI success is not predictive validation.

## Merge acceptance after this repair

Do not merge until a fresh PR-head run proves all governed workflows green and the final
Adaptive artifact is inspected again. The inspection must verify:

- `safe_to_act=true` and `ready_to_act=true`;
- no blockers;
- all-player truth and projection coverage remain complete;
- final squad/XI/captain/vice are legal and reconcile;
- market configured/effective weight is zero without market data;
- AIrsenal role-conflict abstentions are explicit and bounded;
- the selected 15 no longer depends on an uncorrected tiny-sample attacking-rate leak;
- no new projection-integrity warning invalidates the final selector.

Only after that evidence is clean should PR #64 be presented for explicit merge approval.
