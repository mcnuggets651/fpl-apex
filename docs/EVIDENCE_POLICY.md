# Apex production evidence policy

This policy is mechanical and is applied before every production solve.

## Player states

1. Current credible negative evidence applies the bounded availability effect and
   removes XI/captain eligibility when the evidence state requires it.
2. A material unresolved contradiction, or high quantitative uncertainty without
   decision-grade support, removes XI and captain eligibility. The player may
   remain squad/bench eligible.
3. A player with stable quantitative minutes/role evidence, no adverse signal and
   no current article remains eligible. Silence is not suspicion.

Official evidence is decision-grade. Trusted media requires two independent
publishers describing two distinct underlying events; copied or syndicated stories
count once. Claims are bound to the sentence naming the player, preventing an
adjacent claim about another player from being assigned across the article.

## Numerical source-health gate

The news layer is healthy only when all of these fixed conditions pass:

- at least 2 configured sources;
- at least 2 sources retrieved successfully;
- at least two thirds of configured sources retrieved successfully;
- at least 1 timestamped item is no older than 120 hours.

If this gate fails, absence of adverse reporting is not meaningful and the complete
recommendation is withheld. Other residual withholding conditions remain
mechanical: no legal evidence-constrained XI, no two eligible captain/vice options,
or failure of an existing data/bundle/solver/publication integrity gate.

## Manual official transcription

Manual ingestion is allowed only for an identifiable official club or league
source. It requires the exact URL, publication and retrieval times, expiry, relevant
excerpt, SHA-256 content hash and transcriber identity. It has the same influence as
automated evidence of the same official source tier and claim type; manual entry
cannot promote trusted media to official status or directly lock, ban or assign
minutes to a player outside the normal bounded evidence mechanism.
