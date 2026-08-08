# Apex FPL — Decision Register

This is the permanent record of important project decisions. New decisions are appended; old decisions are not silently rewritten.

## D001 — Official FPL is canonical
Official FPL owns player identity, FPL position, club, price, status and fixtures. External sources enrich but do not override identity silently.

## D002 — AIrsenal is an expert, not the whole model
Pinned genuine AIrsenal projections are an independent expected-points input. They must be mapped through official FPL IDs and combined with other evidence rather than used alone.

## D003 — FPL Core Insights is a major evidence layer
Use current underlying stats, preseason evidence, Elo/strength and defensive-contribution context where validated.

## D004 — Maximum EV remains auditable ground truth
Pinnacle ensemble `xp` remains the canonical expected-points forecast. Risk and alternative utilities are measured separately so the model does not double-count risk.

## D005 — Do not optimise points-per-million alone
Cheap efficiency may break ties but must not flood the XI with low-ceiling picks at the expense of premium captaincy and elite attacking routes.

## D006 — Elite 10.0 evidence profile
Elite evidence is fixed initially at 35/20/15/10/10/5/5: attack/minutes/captaincy/set pieces/fixtures/bonus+DEFCON/value. Weight changes require benchmark evidence and a documented decision.

## D007 — Elite does not replace Pinnacle
Every Elite squad must be re-scored on raw ensemble xP and its exact EV regret versus maximum-EV Pinnacle must be reported.

## D008 — Minutes are first class
Expected minutes, start probability and appearance probability materially affect selection. High per-90 rates do not compensate automatically for uncertain minutes.

## D009 — Captaincy has independent strategic value
Premiums can justify price through captaincy ceiling even when their points-per-million is lower. Captain and vice must be optimised with fallback mechanics.

## D010 — DEFCON/bonus are additional scoring routes, not the primary objective
Defensive contributions and bonus improve floor and repeatability, but Elite caps their combined strategic weight at 5% so attack does not get crowded out.

## D011 — News is verification, not selection
Official club updates, manager interviews, transfer confirmations and credible news can change availability/minutes assumptions. They should not substitute for the projection stack.

## D012 — Receding horizon over static transfer scripts
Optimise multiple GWs, execute only the current action, then refresh and re-solve. Later moves are contingencies, not commitments.

## D013 — Independent checks are mandatory
Use CVaR, force/ban regret, captain/bench mechanics and independent solver parity to detect fragile recommendations.

## D014 — No-hindsight learning
Store pre-deadline forecasts before outcomes are known. Attach official results later. Do not promote model changes from one lucky Gameweek.

## D015 — Personal entry state
Entry `63984` is the production personal team. Before GW1, unpublished drafts are not visible through public FPL; after deadlines, public picks can synchronise state. Private next-deadline transfers require manual override until published.

## D016 — Project Brain is canonical continuity
Future Apex work must load `CURRENT_STATE.md`, `APEX_MASTER_CONTEXT.md` and this decision register before making recommendations or architecture changes.

## D017 — Proposed Meta layer must earn promotion
A future Meta selector may compare Pinnacle, Elite, Safety, Aggressive/Differential and Value candidates, but it must not be promoted merely because it looks sophisticated. It must beat or improve robustness against benchmarks without unacceptable EV regret.

## D018 — Elite is lexicographic, not a synthetic xP forecast
The first Elite implementation optimised a percentile/rank utility directly. The first correction proposed multiplying raw xP by a bounded ±5% modifier. Review showed that even this still mixes forecast construction with decision preference. Production direction is therefore an epsilon-constraint / lexicographic design: first solve the relevant scenario for maximum canonical Pinnacle xP; then maximise the 35/20/15/10/10/5/5 Elite utility only among solutions that retain at least 99.5% of that scenario's maximum raw-xP objective. The 0.5% regret band is provisional and must be benchmarked. The selected 15 may come from the Elite secondary objective, but XI, captain and vice are re-optimised on raw xP. Elite never manufactures or modifies expected points.

## D019 — Core team selection is probabilistic xPts-first
Apex accepts the core principle that a probabilistic expected-points model feeding a legal optimiser is more defensible than a single weighted linear selection score. Team-strength modelling may use Dixon-Coles/Poisson as an independent component or challenger, but not as the sole fixture truth. Player attacking xPts should use direct player rates, expected minutes, role and set-piece evidence rather than allocating team xG mechanically by a single historical share. Ownership is excluded from the objective when the goal is maximum FPL points; it may be used only in an explicit rank-management mode or as a documented tiebreak. Uncertainty simulation must preserve team/player/minutes correlation rather than sampling players independently around a mean.

## D020 — Small-sample player rates require shrinkage
Direct xG90/xA90 and related player rates are not trustworthy merely because they are player-specific. Apex must shrink small-sample rates toward position/role priors with strength determined by evidence volume, especially for transfers, new roles and injury returns. The current preseason blend is not a substitute for formal sample-size shrinkage. This is the next projection-model upgrade ahead of adding a Dixon-Coles fixture expert.

## D021 — Elite epsilon must be audited as a frontier
The 0.5% Elite regret band is not treated as calibrated truth. Every live Elite run must expose unrestricted sensitivity at 0%, 0.25%, 0.5% and 1.0% raw-xP regret allowance. If materially different squads appear from tiny epsilon changes, maximum-EV remains the canonical recommendation until no-hindsight evidence supports a stable band. The sensitivity output is decision evidence, not another weighted forecast.

## D022 — Epsilon convergence is machine-readable, not eyeballed
Elite may influence the canonical recommendation only when each of the 0.25%, 0.50% and 1.00% unrestricted frontier solutions retains at least 13 of the 15 maximum-EV squad members and preserves the same captain as maximum-EV. This threshold is explicit to prevent subjective visual interpretation of a frontier. If any required frontier point fails either condition, the layer must fall back to maximum-EV. The 13/15 rule itself is a provisional operational rule and should be revisited only with benchmark/no-hindsight evidence.

## D023 — One Apex team, one production contract
Apex must expose exactly one user-facing recommendation path. `scripts/run_apex.py` is the canonical production command and `data/generated/apex_recommendation_latest.json` is the canonical team source. Maximum-EV/Pinnacle, Elite, CVaR, regret, solver parity and scenario outputs remain necessary internal evidence layers, but they are not separate Apex recommendations. Historical standalone approaches are archived conceptually under `archive/selection_approaches/`. When the user asks for the Apex team, the operator/assistant must read the unified contract first and present that recommendation if `ready_to_act` is true; if it is false, report blockers rather than choose manually among diagnostic teams.
