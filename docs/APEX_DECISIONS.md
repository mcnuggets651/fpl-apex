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

## D006 — Elite 10.0 objective
Elite utility is fixed initially at 35/20/15/10/10/5/5: attack/minutes/captaincy/set pieces/fixtures/bonus+DEFCON/value. Weight changes require benchmark evidence and a documented decision.

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
