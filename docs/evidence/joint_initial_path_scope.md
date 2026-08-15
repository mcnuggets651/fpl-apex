# Adaptive GW1 Launch and Weekly Strategy Policy

Apex must not select the opening 15 as though the same squad will be held for the
whole eight-Gameweek forecast window. FPL is managed deadline by deadline: new
minutes, roles, attacking threat, defensive-contribution evidence, injuries, prices
and fixtures arrive before every later action.

## Pre-GW1 authority

The launch selector therefore treats exact GW1 expected points as the primary
objective. The existing `exact_near_equivalent_points` threshold (currently 0.25)
is a hard floor: no frozen GW2-GW8 forecast may displace a squad by more than that
amount of GW1 expected points.

Only launch squads inside that GW1 band are compared with the legal future transfer
planner. That secondary comparison values the actual remaining bank, one free
transfer for GW2, rolled free-transfer states and explicit hit costs. It is option
value, not a commitment to hold today's long-horizon forecast.

Candidate-limit sensitivity must select the same launch 15 before the adaptive
policy is allowed to publish. A material gain versus the former static eight-week
selector is not required; the architecture is promoted because it represents the
correct decision problem, even when the live optimal 15 happens to be unchanged.

## In-season authority

Once a real FPL squad has been published, Apex starts from that permanent 15, its
bank, selling prices and free-transfer balance. The receding-horizon transfer model
re-solves on the latest projection surface, but only the first action is executable.
The resulting current-Gameweek squad is exact-rescored for XI, captain, vice-captain
and autosub/bench mechanics before it becomes canonical.

Every stored later move is a contingency. Before the next deadline Apex must refresh
the evidence and projections and solve again. A stored GW3/GW4/GW5 move can never
be executed merely because it appeared in an earlier packet.

## Non-scope

This policy does not change player projections, minutes weights, fixture decay,
Understat, AIrsenal, Official EP, transfer rules or price forecasting. The current
GW1 projection-compression audit remains diagnostic-only because there is not yet a
clean aligned no-hindsight archive of all active experts that would justify changing
ensemble weights by inspection.
