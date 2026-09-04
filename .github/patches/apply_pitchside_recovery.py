from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8")


def replace_once(path: str, old: str, new: str) -> None:
    text = read(path)
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected exactly one literal match, found {count}")
    write(path, text.replace(old, new, 1))


def regex_once(path: str, pattern: str, replacement: str) -> None:
    text = read(path)
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(f"{path}: expected exactly one regex match, found {count}")
    write(path, updated)


# 1) Content-address each external tournament seal so a later PITCHSIDE
# publication can be sealed against the same immutable production snapshot.
ops_path = "scripts/apex_v2_tournament_ops.py"
ops = read(ops_path)
marker = "\ndef _private_tournament_files(\n"
if ops.count(marker) != 1:
    raise SystemExit("tournament ops: private tournament marker not unique")
helper = r'''

def _candidate_seal_id(
    *,
    run_id: str,
    public_attempt_id: str,
    pitchside_capture: dict[str, Any],
    openfpl_readiness: dict[str, Any] | None,
) -> str:
    """Return a stable identity for materially distinct external evidence.

    Volatile observation timestamps are deliberately excluded so hourly retries of
    unchanged upstream bytes are idempotent. A repaired/new PITCHSIDE publication,
    Official-hash state, or governed OpenFPL readiness state creates a new seal.
    """

    pitchside_basis = {
        "health": str(pitchside_capture.get("health") or ""),
        "dns_code": str(pitchside_capture.get("dns_code") or ""),
        "generated_at": pitchside_capture.get("generated_at"),
        "expected_official_hash": pitchside_capture.get("expected_official_hash"),
        "current_official_hash": pitchside_capture.get("current_official_hash"),
        "post_capture_official_hash": pitchside_capture.get(
            "post_capture_official_hash"
        ),
        "source_bundle_sha256": pitchside_capture.get("source_bundle_sha256"),
        "surface_sha256": pitchside_capture.get("surface_sha256"),
        "qualified_horizons": sorted(
            {int(value) for value in pitchside_capture.get("qualified_horizons") or []}
        ),
        "missing_forecastable_ids_by_horizon": (
            pitchside_capture.get("missing_forecastable_ids_by_horizon") or {}
        ),
    }
    openfpl = openfpl_readiness or {}
    openfpl_basis = {
        "health": str(openfpl.get("health") or ""),
        "state": str(openfpl.get("state") or ""),
        "exact_rule_gameweek_count": openfpl.get("exact_rule_gameweek_count"),
        "minimum_exact_rule_gameweeks": openfpl.get(
            "minimum_exact_rule_gameweeks"
        ),
        "observed_history_commit": openfpl.get("observed_history_commit"),
        "observed_history_manifest_sha256": openfpl.get(
            "observed_history_manifest_sha256"
        ),
    }
    return canonical_sha256(
        {
            "schema_version": 1,
            "run_id": str(run_id),
            "public_attempt_id": str(public_attempt_id),
            "pitchside": pitchside_basis,
            "openfpl": openfpl_basis,
        }
    )
'''
ops = ops.replace(marker, helper + marker, 1)
write(ops_path, ops)

regex_once(
    ops_path,
    r"def _seal_private_tournament_surface\([\s\S]*?\n\ndef _download_candidate\(",
    r'''def _seal_private_tournament_surface(
    *,
    private_store: Any,
    season: str,
    run_id: str,
    seal_id: str,
    pitchside_capture: dict[str, Any],
    public_attempt_id: str,
    target_commitish: str | None,
    workdir: Path,
) -> tuple[str | None, str | None]:
    material = _private_tournament_files(
        pitchside_capture=pitchside_capture,
        public_attempt_id=public_attempt_id,
        run_id=run_id,
        workdir=workdir / "private-tournament",
    )
    if material is None:
        return None, None
    files, expected_attestation = material
    tag = f"{PRIVATE_TOURNAMENT_PREFIX}/{season}/{run_id}/{seal_id}"
    existing = _find_release(private_store.list_releases(), tag)
    if existing is not None:
        _, observed_attestation = _load_private_tournament_surface(
            private_store=private_store,
            release=existing,
            public_attempt_id=public_attempt_id,
            expected_run_id=run_id,
            workdir=workdir / "existing-private-tournament",
        )
        if observed_attestation != expected_attestation:
            raise TournamentContractError(
                "immutable private tournament supplement already exists with different bytes"
            )
        return tag, str(expected_attestation["archive_sha256"])

    private_store.create_once(
        tag,
        files,
        target_commitish=target_commitish,
        name=f"Apex V2 private tournament supplement {season} {run_id} {seal_id[:12]}",
        body=(
            "Predeadline non-serving PITCHSIDE tournament supplement; "
            "no manager state."
        ),
    )
    return tag, str(expected_attestation["archive_sha256"])


def _download_candidate(''',
)

regex_once(
    ops_path,
    r"def seal_github_run\([\s\S]*?\n\ndef _load_selection\(",
    r'''def seal_github_run(
    *,
    repo: str,
    token: str,
    private_repo: str,
    private_token: str,
    season: str,
    run_id: str,
    control_plane_sha: str,
    openfpl_readiness_path: Path,
    output: Path | None = None,
) -> dict[str, Any]:
    from apex.runtime.releases import GitHubReleaseStore

    public_store = GitHubReleaseStore(repo, token)
    private_store = GitHubReleaseStore(private_repo, private_token)
    source_tag = f"apex-v2/final/{season}/{run_id}"
    private_base_tag = f"apex-v2/private-evaluation/{season}/{run_id}"

    public_releases = public_store.list_releases()
    source_release = _find_release(public_releases, source_tag)
    private_releases = private_store.list_releases()
    private_base_release = _find_release(
        private_releases,
        private_base_tag,
    )
    if source_release is None:
        raise TournamentContractError(
            f"source production final missing: {source_tag}"
        )
    if private_base_release is None:
        raise TournamentContractError(
            f"source private evaluation release missing: {private_base_tag}"
        )
    if (
        source_release.get("immutable") is not True
        or private_base_release.get("immutable") is not True
    ):
        raise TournamentContractError(
            "source release pair must both be immutable"
        )

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        internal, internal_hashes, public_files, public_attempt = (
            _load_internal_private_surfaces(
                public_store=public_store,
                private_store=private_store,
                public_release=source_release,
                private_release=private_base_release,
                workdir=root,
            )
        )
        if str(public_attempt.get("run_id") or "") != str(run_id):
            raise TournamentContractError("source run identity mismatch")
        if str(public_attempt.get("season") or "") != str(season):
            raise TournamentContractError("source season mismatch")

        governance = _load_json(public_files["governance.json"])
        deadline = _parse_utc(
            str(
                (public_attempt.get("certification") or {}).get(
                    "valid_until"
                )
                or ""
            )
        )
        pitchside = capture_pitchside(
            season=season,
            target_gameweek=int(public_attempt["target_gameweek"]),
            expected_official_hash=str(
                public_attempt["official_snapshot_sha256"]
            ),
            deadline=deadline,
            output=root / "pitchside_capture.json",
        )
        openfpl = _load_json(openfpl_readiness_path)
        seal_id = _candidate_seal_id(
            run_id=run_id,
            public_attempt_id=str(public_attempt["public_attempt_id"]),
            pitchside_capture=pitchside,
            openfpl_readiness=openfpl,
        )
        candidate_tag = f"{CANDIDATE_PREFIX}/{season}/{run_id}/{seal_id}"

        # Rechecking unchanged upstream bytes is intentionally idempotent. Only a
        # materially different external-evidence identity creates another seal.
        existing_candidate = _find_release(public_releases, candidate_tag)
        if existing_candidate is not None:
            readiness = _download_candidate(
                public_store,
                existing_candidate,
                root / "existing-candidate",
            )
            seal = readiness.get("common_seal") or {}
            if str(seal.get("run_id") or "") != str(run_id):
                raise TournamentContractError(
                    "existing candidate run identity mismatch"
                )
            if str(seal.get("seal_id") or "") != seal_id:
                raise TournamentContractError(
                    "existing candidate seal identity mismatch"
                )
            if output:
                _write_json(output, readiness)
            return readiness

        private_tournament_tag, supplement_sha = (
            _seal_private_tournament_surface(
                private_store=private_store,
                season=season,
                run_id=run_id,
                seal_id=seal_id,
                pitchside_capture=pitchside,
                public_attempt_id=str(public_attempt["public_attempt_id"]),
                target_commitish=None,
                workdir=root,
            )
        )
        readiness = build_readiness(
            public_attempt,
            governance,
            internal,
            source_release=source_release,
            internal_surface_sha256=internal_hashes,
            pitchside_capture=pitchside,
            openfpl_readiness=openfpl,
            private_base_release_tag=private_base_tag,
            private_tournament_release_tag=private_tournament_tag,
        )
        readiness["control_plane_sha"] = str(control_plane_sha)
        readiness["private_tournament_supplement_sha256"] = supplement_sha
        readiness["common_seal"]["seal_id"] = seal_id
        readiness["common_seal"]["candidate_release_tag"] = candidate_tag
        readiness["readiness_sha256"] = canonical_sha256(
            {
                key: value
                for key, value in readiness.items()
                if key != "readiness_sha256"
            }
        )
        readiness_path = _write_json(
            root / "tournament_readiness.json",
            readiness,
        )
        attestation = {
            "schema_version": 1,
            "scope": "PUBLIC_TOURNAMENT_CANDIDATE",
            "run_id": run_id,
            "seal_id": seal_id,
            "public_attempt_id": public_attempt.get("public_attempt_id"),
            "readiness_sha256": sha256_path(readiness_path),
            "private_supplement_sha256": supplement_sha,
            "production_influence": "NONE",
        }
        attestation_path = _write_json(
            root / "tournament_attestation.json",
            attestation,
        )

        public_store.create_once(
            candidate_tag,
            {
                "tournament_readiness.json": readiness_path,
                "tournament_attestation.json": attestation_path,
            },
            target_commitish=control_plane_sha,
            name=(
                f"Apex V2 tournament candidate {season} {run_id} "
                f"{seal_id[:12]}"
            ),
            body=(
                "Prospective non-serving tournament candidate. Raw provider "
                "forecasts remain private; this release cannot change "
                "production serving authority."
            ),
        )
        if output:
            _write_json(output, readiness)
        return readiness


def _load_selection(''',
)

# Candidate attestation verifier must bind the optional new seal ID while
# retaining backward compatibility with already-immutable GW3 candidates.
replace_once(
    ops_path,
    '''    if str(attestation.get("public_attempt_id") or "") != str(
        (readiness.get("common_seal") or {}).get("public_attempt_id") or ""
    ):
        raise TournamentContractError(
            "candidate attestation public identity mismatch"
        )
    return readiness
''',
    '''    if str(attestation.get("public_attempt_id") or "") != str(
        (readiness.get("common_seal") or {}).get("public_attempt_id") or ""
    ):
        raise TournamentContractError(
            "candidate attestation public identity mismatch"
        )
    attested_seal_id = str(attestation.get("seal_id") or "")
    readiness_seal_id = str(
        (readiness.get("common_seal") or {}).get("seal_id") or ""
    )
    if attested_seal_id and attested_seal_id != readiness_seal_id:
        raise TournamentContractError("candidate attestation seal identity mismatch")
    return readiness
''',
)

# 2) Canonical selection must mean latest tournament seal, not latest production
# snapshot. The latter is identical for repeated external captures of one run.
contract_path = "scripts/apex_v2_tournament_contract.py"
replace_once(
    contract_path,
    '''    selected = max(
        eligible,
        key=lambda row: _parse_utc(
            str((row.get("common_seal") or {})["snapshot_frozen_at"])
        ),
    )
''',
    '''    selected = max(
        eligible,
        key=lambda row: (
            _parse_utc(
                str(
                    (row.get("common_seal") or {}).get("tournament_sealed_at")
                    or (row.get("common_seal") or {})["snapshot_frozen_at"]
                )
            ),
            _parse_utc(
                str((row.get("common_seal") or {})["snapshot_frozen_at"])
            ),
            str(
                (row.get("common_seal") or {}).get("candidate_release_tag")
                or ""
            ),
        ),
    )
''',
)

# 3) The existing hourly schedule must attempt a seal before maintenance so a
# PITCHSIDE DNS can recover without another production run or manual dispatch.
workflow_path = ".github/workflows/apex-v2-prospective-tournament.yml"
replace_once(
    workflow_path,
    '''      (github.event_name == 'workflow_run' && github.event.workflow_run.conclusion == 'success') ||
      github.event_name == 'workflow_dispatch' ||
      github.event_name == 'push'
''',
    '''      (github.event_name == 'workflow_run' && github.event.workflow_run.conclusion == 'success') ||
      github.event_name == 'workflow_dispatch' ||
      github.event_name == 'push' ||
      github.event_name == 'schedule'
''',
)

# 4) Regression tests: same-run content-addressed recovery, schedule participation,
# and canonical selection by external seal time.
test_path = "ops_tests/test_apex_v2_tournament_ops.py"
replace_once(
    test_path,
    '''import apex_v2_tournament_common as common  # noqa: E402
import apex_v2_tournament_contract as contract  # noqa: E402
import apex_v2_tournament_scoring as scoring  # noqa: E402
''',
    '''import apex_v2_tournament_common as common  # noqa: E402
import apex_v2_tournament_contract as contract  # noqa: E402
import apex_v2_tournament_ops as ops  # noqa: E402
import apex_v2_tournament_scoring as scoring  # noqa: E402
''',
)
replace_once(
    test_path,
    '''    def test_latest_valid_predeadline_candidate_wins(self):
        first = readiness()
        second = json.loads(json.dumps(first))
        first["common_seal"]["snapshot_frozen_at"] = (
            "2026-09-01T12:00:00+00:00"
        )
        second["common_seal"]["snapshot_frozen_at"] = (
            "2026-09-04T15:00:00+00:00"
        )
        selected = contract.select_latest_valid_common_seal(
            [first, second], gameweek=3
        )
        self.assertEqual(
            selected["common_seal"]["snapshot_frozen_at"],
            "2026-09-04T15:00:00+00:00",
        )
''',
    '''    def test_latest_valid_predeadline_tournament_seal_wins(self):
        first = readiness()
        second = json.loads(json.dumps(first))
        first["common_seal"]["snapshot_frozen_at"] = (
            "2026-09-04T15:00:00+00:00"
        )
        first["common_seal"]["tournament_sealed_at"] = (
            "2026-09-04T15:10:00+00:00"
        )
        second["common_seal"]["snapshot_frozen_at"] = (
            "2026-09-04T13:00:00+00:00"
        )
        second["common_seal"]["tournament_sealed_at"] = (
            "2026-09-04T16:20:00+00:00"
        )
        selected = contract.select_latest_valid_common_seal(
            [first, second], gameweek=3
        )
        self.assertEqual(
            selected["common_seal"]["tournament_sealed_at"],
            "2026-09-04T16:20:00+00:00",
        )

    def test_pitchside_recovery_creates_new_seal_but_recheck_is_idempotent(self):
        args = list(base_inputs())
        healthy = json.loads(json.dumps(args[4]))
        healthy["checked_at"] = "2026-09-04T15:00:00Z"
        same_bytes_later = json.loads(json.dumps(healthy))
        same_bytes_later["checked_at"] = "2026-09-04T16:00:00Z"
        dns = json.loads(json.dumps(healthy))
        dns["health"] = "INCOMPLETE"
        dns["dns_code"] = common.DNS_INCOMPLETE_UNIVERSE
        dns["qualified_horizons"] = []
        dns["surface"] = None
        dns["surface_sha256"] = None
        dns["missing_forecastable_ids_by_horizon"]["1"] = [3]

        healthy_id = ops._candidate_seal_id(
            run_id=args[0]["run_id"],
            public_attempt_id=args[0]["public_attempt_id"],
            pitchside_capture=healthy,
            openfpl_readiness=args[5],
        )
        later_id = ops._candidate_seal_id(
            run_id=args[0]["run_id"],
            public_attempt_id=args[0]["public_attempt_id"],
            pitchside_capture=same_bytes_later,
            openfpl_readiness=args[5],
        )
        dns_id = ops._candidate_seal_id(
            run_id=args[0]["run_id"],
            public_attempt_id=args[0]["public_attempt_id"],
            pitchside_capture=dns,
            openfpl_readiness=args[5],
        )
        self.assertEqual(healthy_id, later_id)
        self.assertNotEqual(healthy_id, dns_id)

    def test_hourly_schedule_attempts_candidate_seal(self):
        workflow = (
            ROOT / ".github/workflows/apex-v2-prospective-tournament.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("github.event_name == 'schedule'", workflow)
''',
)

# 5) Runbook: document the content-addressed reseal semantics and namespace.
doc_path = "docs/APEX_V2_PROSPECTIVE_TOURNAMENT.md"
replace_once(
    doc_path,
    '''No forecast can be regenerated after seeing an outcome. A postdeadline manual replay may be diagnostic, but it cannot become a prospective candidate or canonical win/loss.
''',
    '''No forecast can be regenerated after seeing an outcome. A postdeadline manual replay may be diagnostic, but it cannot become a prospective candidate or canonical win/loss.

### PITCHSIDE predeadline recovery

A PITCHSIDE DNS is not terminal while the Official deadline is still in the future. The hourly tournament schedule resolves the latest eligible immutable production final, re-captures PITCHSIDE against that exact production Official hash, and content-addresses the external evidence. Unchanged upstream bytes reuse the same seal; a materially different PITCHSIDE publication or governed external-readiness state creates a new immutable seal for the same production run. This allows an early `INCOMPLETE`, `STALE` or transient-unavailable PITCHSIDE state to recover to `ENTERED` before deadline without rerunning production or mutating prior evidence.

Canonicalization chooses the latest valid `tournament_sealed_at` before the Official deadline. `snapshot_frozen_at` remains the immutable production snapshot time and is only a deterministic secondary tie-breaker; it must never be rewritten to simulate a later external capture.
''',
)
replace_once(
    doc_path,
    '''- `apex-v2/tournament-candidate/{season}/{run_id}`
- `apex-v2/tournament-selection/{season}/gw{gw}`
''',
    '''- `apex-v2/tournament-candidate/{season}/{run_id}/{seal_id}`
- `apex-v2/tournament-selection/{season}/gw{gw}`
''',
)
replace_once(
    doc_path,
    '''- `apex-v2/private-tournament/{season}/{run_id}`
''',
    '''- `apex-v2/private-tournament/{season}/{run_id}/{seal_id}`
''',
)
replace_once(
    doc_path,
    '''- hourly maintenance retains GW2 diagnostics, canonicalizes any deadline-passed observation, scores newly completed horizons and materializes the public status artifact.
''',
    '''- hourly maintenance first attempts a content-addressed predeadline reseal of the latest eligible immutable production final, then retains GW2 diagnostics, canonicalizes any deadline-passed observation, scores newly completed horizons and materializes the public status artifact.
''',
)
replace_once(
    doc_path,
    '''among all immutable ready candidates for that Gameweek. The selected record becomes:
''',
    '''among all immutable ready candidates for that Gameweek, ordered first by the latest valid `tournament_sealed_at` and then by deterministic production/tag tie-breakers. The selected record becomes:
''',
)

# 6) Canonical master ledger: repair stale PR #158 status and record this bounded
# research-operations defect/repair without changing machine authority.
master_path = "docs/FPL_APEX_MASTER_STATE.md"
replace_once(
    master_path,
    '''**State snapshot:** 4 September 2026, after PR #157 merged the two-phase auth durability repair and a fresh browser refresh re-seed runtime-proved exchange + exact manager verification, exposing one final same-run draft-list activation race  
''',
    '''**State snapshot:** 4 September 2026, after PR #158 merged the exact-ID auth activation-race repair and the GW3 PITCHSIDE postmortem exposed a bounded prospective-tournament reseal defect now being repaired on `agent/pitchside-predeadline-recovery`  
''',
)
replace_once(
    master_path,
    '''That failure does **not** mean the user must extract another token. The consumed bootstrap parent produced a durable staged child by design. Bounded branch `agent/auth-stage-activation-race` closes only the observed activation race: staging retains the exact release ID and upload SHA-256 map returned by GitHub; after manager match, same-run activation publishes that exact release ID after private-store asset/digest verification instead of re-listing; crash recovery remains list + re-download/decrypt based; wrong-manager same-run cleanup uses the exact returned release ID. Regression tests explicitly hide newly created drafts from `list_releases()` while requiring exact-ID activation and purge to succeed.

Canonical production run `33850307770-1` remains the accepted serving proof. AIrsenal remains sole serving provider H1–H8. Dastan and PITCHSIDE remain research-only. None of the Draft/auth work changes model authority, optimiser semantics, research influence or frozen PR #90.
''',
    '''That failure did **not** require another token. PR #158, **Fix same-run FPL refresh draft activation race**, merged at `8efaa70b1172b0a0c6d20357d5d528a5a65ac8b7` from exact head `4528715a625adc94a60a249e1fb4df42c5811bae` after Apex CI `33913733476` and Apex V2 Ops Contract `33913733468` passed. Same-run activation now uses the exact staged release ID/upload digests; cross-run recovery remains list + re-download/decrypt based. Any remaining auth health claim must come from fresh runtime evidence rather than the pre-merge failure.

Canonical production run `33850307770-1` remains the accepted serving proof. AIrsenal remains sole serving provider H1–H8. Dastan and PITCHSIDE remain research-only. The GW3 postmortem identified a separate research-only defect: one immutable tournament candidate per production `run_id` plus schedule-only maintenance meant a PITCHSIDE DNS could not recover automatically if the external source became complete later before deadline. `agent/pitchside-predeadline-recovery` makes external seals content-addressed, lets the existing hourly schedule reseal the same immutable production run when evidence changes, and selects the latest valid `tournament_sealed_at`. Production authority, optimiser semantics, research influence and frozen PR #90 remain unchanged.
''',
)
replace_once(
    master_path,
    '''- PR #157, **Harden FPL owner-auth refresh rotation durability**, exact head `e0a0f5c4a62f07ef10ad17f544bd7b08b63f19f7`, passed Apex CI `33911107334` and Ops Contract `33911107378`, merged at current public `main` `1219861f3b9c3d707f6c80f94fa6f26325bab4a1`;
- fresh browser re-seed acceptance attempt: Keepalive run `33911608442`, attempt-2 job `101151219540`, reached verified staged-child activation and failed only on immediate release-list rediscovery;
- active bounded repair branch: `agent/auth-stage-activation-race`;
''',
    '''- PR #157, **Harden FPL owner-auth refresh rotation durability**, exact head `e0a0f5c4a62f07ef10ad17f544bd7b08b63f19f7`, passed Apex CI `33911107334` and Ops Contract `33911107378`, merged at `1219861f3b9c3d707f6c80f94fa6f26325bab4a1`;
- fresh browser re-seed acceptance attempt: Keepalive run `33911608442`, attempt-2 job `101151219540`, reached verified staged-child activation and failed only on immediate release-list rediscovery;
- PR #158, **Fix same-run FPL refresh draft activation race**, exact head `4528715a625adc94a60a249e1fb4df42c5811bae`, passed Apex CI `33913733476` and Ops Contract `33913733468`, merged at current public `main` `8efaa70b1172b0a0c6d20357d5d528a5a65ac8b7`;
- active bounded research-operations repair branch: `agent/pitchside-predeadline-recovery`;
''',
)
replace_once(
    master_path,
    '''33. **Do not make same-run activation depend on immediate `list_releases()` visibility.** Use the exact release ID/upload digests returned by the successful stage call; reserve list + re-download for cross-run recovery.
''',
    '''33. **Do not make same-run activation depend on immediate `list_releases()` visibility.** Use the exact release ID/upload digests returned by the successful stage call; reserve list + re-download for cross-run recovery.
34. **Do not treat an external-provider DNS as terminal before the deadline.** PITCHSIDE must be re-captured prospectively against the same Official hash and a materially changed source must be allowed to create a new immutable seal for the same production run.
35. **Do not select repeated external captures by `snapshot_frozen_at`.** Canonical prospective selection is by latest valid `tournament_sealed_at`; the production snapshot timestamp remains immutable evidence, not a reseal clock.
''',
)
regex_once(
    master_path,
    r"## 11\. Next actions[\s\S]*?\n---\n\n## 12\. Change-control protocol for all future work",
    '''## 11. Next actions — close PITCHSIDE reseal recovery and verify live runtime state from evidence

The serving production and Classic owner-query system remain accepted. PR #158 has merged the bounded exact-ID auth activation code. Current auth/Draft runtime health must be verified from fresh runs before making new owner-specific claims; do not infer it from the earlier pre-merge failure.

Immediate bounded PITCHSIDE closure:

1. finish `agent/pitchside-predeadline-recovery` with `GOV-002`, `GOV-004`, `PROD-006` and `RES-001` only if the exact changed-path semantic checker agrees;
2. require regression proof that unchanged PITCHSIDE bytes are idempotent, DNS→healthy evidence creates a distinct seal, scheduled hourly execution participates in sealing and canonical selection uses `tournament_sealed_at`;
3. require Apex CI and Apex V2 Ops Contract to pass on the exact final PR head; do not weaken no-hindsight, immutability, privacy, common-Official-hash or research-only gates;
4. merge only after live `main`, machine authority and frozen PR #90 are reverified unchanged;
5. accept live recovery on the next still-predeadline Gameweek only when the scheduled tournament path can retain an earlier DNS and later seal a materially changed valid PITCHSIDE publication against the same immutable production run/hash;
6. never backfill GW3 after the deadline; its already-sealed/canonical evidence remains immutable historical prospective evidence.

Normal operations remain: keep the private runner healthy, verify current auth/Draft state from governed runtime evidence, keep Deadline Watch/auth/production workflows healthy, obtain fresh Official FPL/provider state each deadline, use private `latest` for Classic owner retrieval, keep research non-serving, keep PR #90 frozen and update this ledger whenever substantive state changes.

---

## 12. Change-control protocol for all future work''',
)
replace_once(
    master_path,
    '''## 13. Changelog for this ledger

''',
    '''## 13. Changelog for this ledger

### 2026-09-04 — PITCHSIDE same-run predeadline recovery defect bounded after PR #158 merge

- PR #158 merged at `8efaa70b1172b0a0c6d20357d5d528a5a65ac8b7` from exact head `4528715a625adc94a60a249e1fb4df42c5811bae` after Apex CI `33913733476` and Apex V2 Ops Contract `33913733468` passed, closing the same-run auth draft-list activation code defect;
- GW3 tournament inspection then showed PITCHSIDE could be explicit DNS correctly yet remain unable to recover automatically before deadline because scheduled runs performed maintenance only and the candidate/private supplement namespace was one immutable object per production `run_id`;
- the selector also used `snapshot_frozen_at`, which cannot distinguish repeated external captures against one immutable production snapshot;
- bounded `agent/pitchside-predeadline-recovery` content-addresses materially distinct external evidence, allows the existing hourly schedule to attempt a predeadline reseal, preserves unchanged-byte idempotency and selects by latest valid `tournament_sealed_at`;
- the repair does not rerun production, alter Official hashes, fill missing forecasts, backfill GW3, change AIrsenal serving authority, change machine authority or touch frozen PR #90;
- OpenFPL remains governed by its separate 10-completed-exact-rule-GW readiness policy and is not made artificially eligible by this PITCHSIDE repair.

''',
)

# 7) Remove the temporary applicator and workflow from the final tree. The running
# workflow has already loaded them, so deletion is safe before its validation/commit.
for temporary in (
    ROOT / ".github/patches/apply_pitchside_recovery.py",
    ROOT / ".github/workflows/_temporary-pitchside-patch.yml",
):
    if temporary.exists():
        temporary.unlink()

print("PITCHSIDE recovery patch applied successfully")
