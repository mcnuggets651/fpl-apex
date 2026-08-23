# Apex Release Contract

## Status

Slice 0 control-plane contract. V1 remains fail-closed while publication authority moves out of Git.

## Release records

`ReleaseRecord` carries:

- season;
- entry;
- Gameweek when known;
- release ID;
- decision-bundle ID;
- world ID when V2 creates one;
- runtime digest;
- created/valid-until timestamps;
- typed status;
- ready/safe flags;
- immutable artifact-manifest ID;
- supersession field.

A run that fails before the Gameweek is provable may archive a record with `gameweek=null`; it cannot become a current-GW pointer by guessing.

## Status boundary

`V1_ACTIONABLE` is a migration status only. It is deliberately distinct from `CERTIFIED`. Slice 0 does not upgrade V1 readiness booleans into V2 proof.

## Current pointer

The current release is keyed by `(season, entry, gameweek)` and changed only with compare-and-swap. A stale writer whose expected current release differs from the actual pointer is rejected.

The filesystem registry is a reference/local-recovery adapter. Production cutover requires a durable shared ReleaseRegistry backend with equivalent atomicity.

## Source-control boundary

No workflow may publish runtime recommendation state by committing or pushing generated files to `main`. Source SHA identifies the code used by a run; it is not the runtime database.

## Branch protection

Live verification on 23 August 2026 found `main` unprotected. The installed GitHub connector exposes no branch-protection mutation action. The exact external admin action remaining after Slice 0 is:

1. require pull requests for `main`;
2. require current-head Apex CI checks;
3. disable force pushes;
4. disable branch deletion;
5. configure conservative bypass/review policy.

Protection should be enabled after the direct runtime push path is merged away so scheduled production no longer depends on `contents: write`.
