# Player identity integrity

Apex treats Official FPL player IDs as exact identifiers, not numeric quantities. Identity validation is therefore deliberately stricter than ordinary CSV numeric coercion.

## Exact ID rule

Every explicit player ID must represent one positive integer exactly. Values such as `10`, `10.0` and the string `"10"` all represent the same exact integer identity and are accepted. Fractional (`10.5`), boolean, null, non-finite, blank and non-numeric values are invalid.

Apex must never implement player identity as `int(float(value))` or an equivalent truncating/rounding conversion. In particular, an explicit malformed ID cannot be discarded and then recovered through name fallback. Name fallback remains available only when an ID is genuinely absent and the independent name witness resolves uniquely without club/position conflict.

The same exact parser is used for:

- the Official FPL identity registry;
- declared roster-complete source coverage;
- external source identity resolution;
- player-scoped IDs found in the canonical recommendation audit.

Roster coverage reports malformed rows separately from missing and unknown IDs so one artifact can expose all identity defects at once.

## AIrsenal witness provenance

A configured AIrsenal export must carry both `source_player_name` and `identity_witness_type` on every row. `identity_witness_type` must be exactly `airsenal_name` after whitespace normalisation. Null values are invalid; they are not removed before validation.

A witness-provenance failure blocks publication but does not suppress other diagnostics. Apex still evaluates exact roster coverage and, when an independent name column exists, row-level identity reconciliation. This makes the audit complete without weakening the gate.

## Recommendation reference audit

Only explicitly player-scoped fields are scanned (`player_id`, captain/vice IDs and player/squad/XI/bench ID lists). Valid IDs are compared against the current sealed Official FPL registry. Malformed explicit references and valid-but-unknown IDs are reported independently. Either condition makes the selected-reference audit not ready.

## Regression requirements

CI must prove at least these cases:

- fractional Official FPL IDs fail before registry construction;
- a fractional explicit source ID cannot fall back to a matching name;
- roster-complete coverage reports a fractional ID as invalid and the displaced Official ID as missing;
- null AIrsenal witness provenance blocks the audit even when roster coverage is complete;
- fractional IDs in a recommendation are reported as malformed and are never truncated into a valid Official ID;
- existing wrong-name, ambiguous-name, unknown-ID, duplicate-ID and club/position conflict cases remain fail-closed.

These are integrity rules. They are not relaxed to make a workflow green.
