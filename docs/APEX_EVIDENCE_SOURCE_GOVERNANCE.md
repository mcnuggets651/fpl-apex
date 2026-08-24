# Apex V2 Evidence and Source Governance

## Authority boundary

External football/news text is retained as immutable data. It is never executable authority and never directly writes player identity, price, club, xP, minutes, tactical role or optimisation instructions.

Only a constrained `StructuredEvidenceInput` may become an `EvidenceClaim`. The ingestion boundary requires:

- an exact current Official FPL integer player ID present in the sealed identity registry;
- a registered source + capability pair;
- a source URL whose host matches the registered provenance hosts;
- a verified immutable raw source artifact;
- valid bitemporal timestamps and optional expiry/supersession;
- contextual reliability keyed by source × claim type × horizon × recency.

## Source admission

Source capabilities have explicit criticality and admission state. New or migrated feeds enter `SHADOW`. A healthy shadow source is still observe-only.

Promotion to `QUALIFIED` requires a registered admission policy plus immutable shadow evidence measuring at least:

- observation/sample volume;
- overlap with reference evidence;
- timeliness;
- schema stability;
- outcome consistency;
- marginal value;
- security incidents.

Thresholds are policy data backed by an immutable artifact; they are not hard-coded constitutional truth. A successful promotion emits a content-addressed qualification decision artifact. Production ingestion re-verifies that artifact at runtime.

The V1 feeds migrated from PR #66 are intentionally registered as `SHADOW` in `config/sources_v2.yaml` until V2 qualification exists.

## Multidimensional health and degradation

`SourceHealth` preserves seven independent dimensions:

1. availability;
2. freshness;
3. coverage;
4. integrity;
5. schema validity;
6. semantic validity;
7. identity validity.

A single readiness boolean cannot hide a failed or unknown dimension.

`HARD_REQUIRED` failures block. `MODEL_REQUIRED` and `QUALITY_REQUIRED` failures can degrade only through a registered, prequalified degradation profile whose validation artifact verifies at runtime. Optional/advisory failures are observe-only rather than silently promoted into production substitutes.

## Deadline-relative freshness

Freshness policy receives explicit source age and seconds-to-deadline; domain logic reads no wall clock. Policies are keyed by capability and source criticality. Missing or unverified qualification produces `UNKNOWN`, not an implicit fresh/pass result.

Slice 5 intentionally ships `config/evidence_freshness_v2.yaml` without invented production thresholds. Replay/learning may later qualify policies with immutable evidence.

## Contextual reliability

Reliability is never one permanent number for a source. `ReliabilityContext` is specific to:

- source;
- claim type;
- Gameweek horizon;
- recency bucket.

An unknown/unqualified context has `reliability_bps = null` and cannot be weighted. A qualified context requires a non-zero calibration sample plus an immutable qualification artifact. Slice 5 intentionally starts `config/source_reliability_v2.yaml` empty.

## Append-only evidence ledger

`EvidenceLedger` is immutable. Stored ledger envelopes are content-addressed and parent-linked. Appending a correction creates a new child ledger; the parent bytes remain valid forever.

Supersession is constrained to an earlier claim from the same source, player and claim type, and the correction cannot become known before the claim it supersedes. Replay at a historical cutoff uses `first_known_at` and the supersession chain to prevent hindsight leakage.

## Security / prompt injection

Raw text can contain arbitrary statements such as “ignore previous instructions” without gaining authority. The ingestion code never interprets raw bytes. The raw artifact is only verified and referenced; a separate typed extraction supplies the bounded fields permitted by the schema.

Source labels cannot impersonate another publisher because `source_url` must match the registered host set. Player names cannot establish identity because evidence attaches only to an exact Official FPL integer ID already known by the sealed identity registry.

## Release proof

Slice 5 adds required proof obligations:

- `PO-SOURCE-GOVERNANCE-001`;
- `PO-EVIDENCE-RELIABILITY-001`;
- `PO-EVIDENCE-LEDGER-001`.

They trace through `REQ-EVIDENCE-SOURCE-GOVERNANCE` and the named constitutional invariants in `docs/APEX_INVARIANTS.md`.

This slice does **not** claim that any migrated media/specialist source is already production-qualified. Qualification is empirical work for the later replay/learning path; until then those feeds remain shadow evidence.
