from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8")


def replace_once(path: str, old: str, new: str) -> None:
    text = read(path)
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one match, found {count}: {old[:140]!r}")
    write(path, text.replace(old, new, 1))


def insert_before_once(path: str, marker: str, insertion: str) -> None:
    text = read(path)
    if insertion in text:
        return
    count = text.count(marker)
    if count != 1:
        raise SystemExit(f"{path}: expected one insertion marker, found {count}: {marker[:140]!r}")
    write(path, text.replace(marker, insertion + marker, 1))


def replace_section(path: str, heading: str, next_heading: str, body: str) -> None:
    text = read(path)
    start = text.find(heading)
    if start < 0:
        raise SystemExit(f"{path}: missing section heading {heading!r}")
    end = text.find(next_heading, start + len(heading))
    if end < 0:
        raise SystemExit(f"{path}: missing next section heading {next_heading!r}")
    replacement = heading + "\n\n" + body.rstrip() + "\n\n"
    write(path, text[:start] + replacement + text[end:])


# Constitutional invariant.
invariant = (
    "- **INV-PRODUCTION-CHAMPION-AUTHORITY** — production publication and answer authority require one immutable point-in-time `ProductionChampionGeneration` that independently replays the exact forecast-model promotion evidence and exact reviewed DecisionPolicy/scenario-generator/scenario-policy admissions against the schema-v2 planning bundle; qualification or mutable configuration alone never confers champion status, future review/authorization cannot leak backward, and runtime publication paths are verifier-only.\n"
)
insert_before_once(
    "docs/APEX_INVARIANTS.md",
    "- **INV-PRODUCTION-BACKEND-QUALIFIED**",
    invariant,
)

# Production requirement owns the authority chain explicitly.
replace_once(
    "config/requirements.yaml",
    "    requirement: V2 production publication is an explicit proof-derived atomic transition from a complete constitutional AssuranceCase and blocker-free ReleaseCertificate onto the exact backend-identity-bound qualified durable shared ArtifactStore/ReleaseRegistry; mandatory ProofClass, typed empirical release-subject evidence and replay-valid planning-v2 reference-solver parity are pinned to the exact content-addressed schema-v2 ProductionPlanningBundle and its PlanningResultId; publication authorization binds runtime identity and a timezone-aware non-null validity window, filesystem reference adapters remain structurally non-production, post-attempt report/CAS evidence audits rather than circularly authorizes the attempt, and only the exact current unexpired verified V2 PUBLISHED release may expose that replayed planning recommendation bundle.\n",
    "    requirement: V2 production publication is an explicit proof-derived atomic transition from a complete constitutional AssuranceCase and blocker-free ReleaseCertificate onto the exact backend-identity-bound qualified durable shared ArtifactStore/ReleaseRegistry; mandatory ProofClass, typed empirical release-subject evidence, replay-derived point-in-time champion authority and replay-valid planning-v2 reference-solver parity are pinned to the exact content-addressed schema-v2 ProductionPlanningBundle and its PlanningResultId; publication authorization binds the exact champion-generation artifact, runtime identity and a timezone-aware non-null validity window, filesystem reference adapters remain structurally non-production, post-attempt report/CAS evidence audits rather than circularly authorizes the attempt, and only the exact current unexpired verified V2 PUBLISHED release may expose that replayed planning recommendation bundle.\n",
)
replace_once(
    "config/requirements.yaml",
    "    invariants: [INV-PRODUCTION-CERTIFICATE-ONLY, INV-PRODUCTION-BACKEND-QUALIFIED, INV-PRODUCTION-CAS-ATOMIC, INV-PRODUCTION-WITHHELD-NON-ACTIONABLE, INV-PRODUCTION-ANSWER-CURRENT-ONLY, INV-PRODUCTION-AUTHORITY-TIME-BOUNDED, INV-PRODUCTION-REPLAY-EXACT, INV-PRODUCTION-PROOF-CLASS-PINNED, INV-PRODUCTION-PLANNING-AUTHORITY, INV-PLANNING-REFERENCE-PARITY, INV-EMPIRICAL-QUALIFICATION-TYPED, INV-EMPIRICAL-RELEASE-SUBJECT-BOUND, INV-ASSURANCE-DERIVES-RELEASE, INV-CAS-CURRENT-POINTER, INV-IMMUTABLE-RELEASE]\n",
    "    invariants: [INV-PRODUCTION-CERTIFICATE-ONLY, INV-PRODUCTION-PLANNING-AUTHORITY, INV-PRODUCTION-CHAMPION-AUTHORITY, INV-PRODUCTION-BACKEND-QUALIFIED, INV-PRODUCTION-CAS-ATOMIC, INV-PRODUCTION-WITHHELD-NON-ACTIONABLE, INV-PRODUCTION-ANSWER-CURRENT-ONLY, INV-PRODUCTION-AUTHORITY-TIME-BOUNDED, INV-PRODUCTION-REPLAY-EXACT, INV-PRODUCTION-PROOF-CLASS-PINNED, INV-PLANNING-REFERENCE-PARITY, INV-EMPIRICAL-QUALIFICATION-TYPED, INV-EMPIRICAL-RELEASE-SUBJECT-BOUND, INV-ASSURANCE-DERIVES-RELEASE, INV-CAS-CURRENT-POINTER, INV-IMMUTABLE-RELEASE]\n",
)
replace_once(
    "config/requirements.yaml",
    "    implementation: [src/apex_fpl/core/production.py, src/apex_fpl/core/production_authority.py, src/apex_fpl/core/production_proof_contract.py, src/apex_fpl/core/production_bundle.py, src/apex_fpl/core/planning.py, src/apex_fpl/core/reference_solver_planning_assurance.py, src/apex_fpl/core/experiments.py, src/apex_fpl/control/artifact_store.py, src/apex_fpl/control/experiment_registry.py, src/apex_fpl/control/empirical_qualification_admission.py, src/apex_fpl/control/decision_policy_store.py, src/apex_fpl/control/forecast_model_store.py, src/apex_fpl/control/production_planning_bundle.py, src/apex_fpl/control/production_reference_solver_binding.py, src/apex_fpl/control/reference_solver_planning_qualification.py, src/apex_fpl/control/production_backend_qualification.py, src/apex_fpl/control/production_cutover.py, src/apex_fpl/control/production_authority.py, src/apex_fpl/control/release_registry.py, docs/APEX_PRODUCTION_CUTOVER_V2.md, docs/APEX_RECEDING_HORIZON_PLANNER_V2.md, docs/APEX_EMPIRICAL_QUALIFICATION_V2.md]\n",
    "    implementation: [src/apex_fpl/core/production.py, src/apex_fpl/core/production_authority.py, src/apex_fpl/core/production_proof_contract.py, src/apex_fpl/core/production_bundle.py, src/apex_fpl/core/planning.py, src/apex_fpl/core/reference_solver_planning_assurance.py, src/apex_fpl/core/experiments.py, src/apex_fpl/core/champion_authority.py, src/apex_fpl/control/artifact_store.py, src/apex_fpl/control/experiment_registry.py, src/apex_fpl/control/empirical_qualification_admission.py, src/apex_fpl/control/decision_policy_store.py, src/apex_fpl/control/forecast_model_store.py, src/apex_fpl/control/champion_authority.py, src/apex_fpl/control/learning_promotion_replay.py, src/apex_fpl/control/production_planning_bundle.py, src/apex_fpl/control/production_reference_solver_binding.py, src/apex_fpl/control/reference_solver_planning_qualification.py, src/apex_fpl/control/production_backend_qualification.py, src/apex_fpl/control/production_cutover.py, src/apex_fpl/control/production_authority.py, src/apex_fpl/control/release_registry.py, docs/APEX_PRODUCTION_CUTOVER_V2.md, docs/APEX_CHAMPION_AUTHORITY_V2.md, docs/APEX_RECEDING_HORIZON_PLANNER_V2.md, docs/APEX_EMPIRICAL_QUALIFICATION_V2.md]\n",
)
replace_once(
    "config/requirements.yaml",
    "    tests: [tests/test_v2_production_cutover.py, tests/test_v2_production_authority.py, tests/test_v2_production_planning_bundle.py, tests/test_v2_reference_solver_planning.py, tests/test_v2_reference_solver_planning_qualification.py, tests/test_v2_production_architecture.py, tests/test_v2_production_traceability.py, tests/test_v2_empirical_qualification_plane.py, tests/test_v2_empirical_qualification_edges.py, tests/test_v2_empirical_qualification_traceability.py]\n",
    "    tests: [tests/test_v2_champion_authority.py, tests/test_v2_production_cutover.py, tests/test_v2_production_authority.py, tests/test_v2_production_planning_bundle.py, tests/test_v2_reference_solver_planning.py, tests/test_v2_reference_solver_planning_qualification.py, tests/test_v2_production_architecture.py, tests/test_v2_production_traceability.py, tests/test_v2_empirical_qualification_plane.py, tests/test_v2_empirical_qualification_edges.py, tests/test_v2_empirical_qualification_traceability.py]\n",
)

# Champion authority design now records replay derivation and chronology.
replace_section(
    "docs/APEX_CHAMPION_AUTHORITY_V2.md",
    "## Forecast-model authority",
    "## DecisionPolicy, scenario-generator and scenario-policy authority",
    """Forecast authority reuses the existing learning-governance chain rather than inventing a second model registry:

`production evaluation -> exact comparison -> ModelPromotionCertificate -> ModelRegistryGeneration -> forecast champion`

A retained `PROMOTE` label is not sufficient. Runtime replay locates the exact retained candidate and incumbent `ModelEvaluationReport` artifacts, the exact `ModelComparisonReport`, and the exact retained qualified champion `LearningPolicyRegistry` used by the promotion. It reconstructs those typed objects, reconciles their semantic identities and common-truth lineage, checks the comparison rows against the retained evaluation metrics, replays the learning policy at the generation authorization time, and re-runs the existing promotion threshold/interval logic. The registry champion is accepted only when that independent replay derives the same promotion identity and still derives `PROMOTE` for the exact candidate named as champion.

A hand-authored promotion certificate, a model evaluation, a comparison, a QUALIFIED model artifact or an arbitrary registry row therefore cannot establish forecast champion authority.""",
)
replace_section(
    "docs/APEX_CHAMPION_AUTHORITY_V2.md",
    "## ProductionChampionGeneration",
    "## Bundle reconciliation",
    """The four authorities are composed into one immutable `ProductionChampionGeneration`. Each generation records:

- exact season;
- generation number;
- optional parent generation artifact;
- exact forecast model-registry generation and resulting model champion;
- exact admission artifacts and candidate identities for DecisionPolicy, scenario generator and scenario policy;
- retained change-control evidence;
- authorizer identity, timezone-aware authorization time and reason.

Generation creation is stale-writer-safe. If a current generation exists, the caller must supply the exact expected parent semantic identity. A stale writer cannot create the next authoritative generation.

Authority is also point-in-time. Review and generation authorization timestamps must be timezone-aware. An admission cannot replay before its own review time; a generation cannot replay before its own authorization time; and every component admission plus the parent generation must already have been valid at the child generation's authorization time. Future review or authorization evidence cannot leak backward into an earlier production decision.

Replay verifies recursive parent continuity, season, retained change-control evidence, independently re-derived forecast promotion lineage, and all three reviewed admissions with their typed empirical qualifications.""",
)

# D036 is permanent decision authority; strengthen it instead of adding a new decision.
old_d036 = "A SHADOW or QUALIFIED candidate is never the production champion merely because its qualification artifact exists or a registry/configuration row names it. Forecast-model champion authority is inherited only from the existing learning-governance chain: an immutable `ModelPromotionCertificate` whose decision is exactly `PROMOTE`, retained as the exact source of the `ModelRegistryGeneration` that names the champion. DecisionPolicy, scenario-generator and scenario-policy authority each require exact typed empirical qualification plus a separate immutable reviewed `ChampionAdmissionCertificate` with retained review evidence. The four authorities are composed into one parent-linked `ProductionChampionGeneration`; stale writers cannot create the next generation without the exact expected parent. Production cutover and answer authority are verifier-only for this chain: they independently replay the generation and exact-match all four identities against the schema-v2 production planning bundle. Runtime publication code cannot issue admissions, create generations or silently fall back to repository configuration. Missing, corrupt, expired, wrong-season or mismatched champion authority withholds publication. Synthetic authority fixtures prove mechanics only and never constitute a real production champion."
new_d036 = "A SHADOW or QUALIFIED candidate is never the production champion merely because its qualification artifact exists or a registry/configuration row names it. Forecast-model champion authority is inherited only from the existing learning-governance chain and must be independently re-derived at replay: exact retained candidate/incumbent production evaluations, common-truth lineage, exact comparison rows and the retained qualified champion learning-policy registry must reproduce the promotion rules and still derive the exact `ModelPromotionCertificate(PROMOTE)` bound into the `ModelRegistryGeneration`. A hand-authored `PROMOTE` label is insufficient. DecisionPolicy, scenario-generator and scenario-policy authority each require exact typed empirical qualification plus a separate immutable reviewed `ChampionAdmissionCertificate` with retained review evidence. Review and generation authorization timestamps are timezone-aware and point-in-time; future review/authorization cannot leak backward. The four authorities are composed into one parent-linked `ProductionChampionGeneration`; stale writers cannot create the next generation without the exact expected parent. Production cutover and answer authority are verifier-only for this chain: they independently replay the generation and exact-match all four identities against the schema-v2 production planning bundle. Runtime publication code cannot issue admissions, create generations or silently fall back to repository configuration. Missing, corrupt, not-yet-valid, expired, wrong-season, forged-promotion or mismatched champion authority withholds publication. Synthetic authority fixtures prove mechanics only and never constitute a real production champion."
replace_once("docs/APEX_DECISIONS.md", old_d036, new_d036)

# Production runbook.
champion_section = """## Replayed champion authority before publication

Qualification proves eligibility, not production selection. Before publication Apex must load one immutable `ProductionChampionGeneration` that already existed at the explicit release time. Forecast-model authority is accepted only when the retained model-registry generation points to promotion evidence whose exact candidate/incumbent evaluation reports, comparison report and qualified champion learning-policy registry independently re-derive `PROMOTE`. DecisionPolicy, scenario-generator and scenario-policy authority each require an exact retained reviewed admission whose typed empirical qualification was valid at the generation authorization time. Parent generations are recursively replayed at the child authorization time. Naive or future review/authorization timestamps fail closed.

The generation must exact-match the forecast model, DecisionPolicy, `ScenarioSet.scenario_generator_id` and `RobustnessReport.scenario_policy_id` in the already replayed schema-v2 planning bundle. `ProductionPublicationAuthorization` schema v2 binds the exact champion-generation artifact. Cutover and answer authority independently replay that artifact; runtime publication code may verify it but cannot issue admissions, promotions or champion generations. See `docs/APEX_CHAMPION_AUTHORITY_V2.md`.

"""
insert_before_once(
    "docs/APEX_PRODUCTION_CUTOVER_V2.md",
    "## Typed empirical admission before publication",
    champion_section,
)
replace_once(
    "docs/APEX_PRODUCTION_CUTOVER_V2.md",
    "4. Load and independently replay the exact schema-v2 `ProductionPlanningBundle`; reconcile season, entry, Gameweek, GlobalWorld and every retained decision-lineage identity; reject tactical schema v1 as production authority.\n",
    "4. Load and independently replay the exact schema-v2 `ProductionPlanningBundle`; reconcile season, entry, Gameweek, GlobalWorld and every retained decision-lineage identity; reject tactical schema v1 as production authority. Then load the exact point-in-time `ProductionChampionGeneration`, independently re-derive forecast promotion authority, replay reviewed non-model admissions, and exact-match all four champion identities against that planning bundle. Missing, future, forged or mismatched champion authority fails closed.\n",
)
replace_once(
    "docs/APEX_PRODUCTION_CUTOVER_V2.md",
    "10. Seal a `ProductionPublicationAuthorization` containing the exact scope, bundle/world/runtime/manifest identities, exact `created_at`/`valid_until`, AssuranceCase snapshot, proof-registry snapshot, ReleaseCertificate result and the content identity of the backend-qualification snapshot.\n",
    "10. Seal a schema-v2 `ProductionPublicationAuthorization` containing the exact scope, bundle/world/runtime/manifest identities, exact champion-generation artifact, exact `created_at`/`valid_until`, AssuranceCase snapshot, proof-registry snapshot, ReleaseCertificate result and the content identity of the backend-qualification snapshot.\n",
)
replace_once(
    "docs/APEX_PRODUCTION_CUTOVER_V2.md",
    "`PUBLISHED` is possible only after a blocker-free ReleaseCertificate, exact schema-v2 planning lineage, replay-valid qualified planning-reference parity, complete typed proof lineage, identity-bound qualified production backend evidence, a valid explicit publication horizon and successful exact CAS.",
    "`PUBLISHED` is possible only after a blocker-free ReleaseCertificate, exact schema-v2 planning lineage, replay-valid point-in-time champion authority, replay-valid qualified planning-reference parity, complete typed proof lineage, identity-bound qualified production backend evidence, a valid explicit publication horizon and successful exact CAS.",
)
insert_before_once(
    "docs/APEX_PRODUCTION_CUTOVER_V2.md",
    "- `src/apex_fpl/core/production.py`",
    "- `src/apex_fpl/core/champion_authority.py`\n",
)
insert_before_once(
    "docs/APEX_PRODUCTION_CUTOVER_V2.md",
    "- `src/apex_fpl/control/production_backend_qualification.py`",
    "- `src/apex_fpl/control/champion_authority.py`\n- `src/apex_fpl/control/learning_promotion_replay.py`\n",
)
insert_before_once(
    "docs/APEX_PRODUCTION_CUTOVER_V2.md",
    "- `docs/APEX_INVARIANTS.md`",
    "- `docs/APEX_CHAMPION_AUTHORITY_V2.md`\n",
)
insert_before_once(
    "docs/APEX_PRODUCTION_CUTOVER_V2.md",
    "- `tests/test_v2_production_cutover.py`",
    "- `tests/test_v2_champion_authority.py`\n",
)

# Master Context and architecture continuity.
replace_once(
    "docs/APEX_MASTER_CONTEXT.md",
    "16. Qualification and champion promotion are separate reviewed operations; no operator command may auto-promote a champion.",
    "16. Qualification and champion promotion are separate reviewed operations; no operator command may auto-promote a champion.\n17. Production champion authority is point-in-time and replay-derived: forecast promotion must be independently re-derived from exact retained learning evidence, non-model champions require reviewed admissions, and cutover/answer authority must exact-match the resulting `ProductionChampionGeneration` to the production planning bundle.",
)
arch_section = """\n## Production champion authority\n\nProduction qualification and production selection authority are distinct. The production control plane accepts only one immutable point-in-time `ProductionChampionGeneration` matching the exact forecast model, DecisionPolicy, scenario generator and scenario policy in the replayed planning bundle. Forecast champion authority re-derives the existing learning promotion chain from retained evaluation/comparison/policy evidence; DecisionPolicy and scenario authorities replay separate reviewed admissions. Cutover and answer resolution are verifier-only and bind the exact generation artifact through schema-v2 publication authorization.\n"""
if "## Production champion authority" not in read("docs/APEX_ARCHITECTURE_V2.md"):
    write("docs/APEX_ARCHITECTURE_V2.md", read("docs/APEX_ARCHITECTURE_V2.md").rstrip() + "\n" + arch_section)

# Human changelog.
entry = """## 2026-08-27 — V2 explicit replayed champion authority chain
- Added immutable reviewed `ChampionAdmissionCertificate` and parent-linked `ProductionChampionGeneration` contracts that keep empirical qualification separate from production selection authority.
- Forecast champion authority now reuses and independently replays the existing learning-governance chain: exact candidate/incumbent production evaluations, common truth, comparison rows, qualified champion learning-policy registry and promotion rules must re-derive `PROMOTE`; a hand-authored PROMOTE certificate is insufficient.
- DecisionPolicy, scenario-generator and scenario-policy champions require exact typed empirical qualification plus separate retained reviewed admissions; review and generation authorization timestamps are timezone-aware and point-in-time replayed.
- Production publication authorization is schema v2 and binds the exact champion-generation artifact. Cutover and answer authority independently replay it against the exact schema-v2 planning bundle; missing or mismatched authority is non-actionable.
- Added adversarial chronology, stale-writer, swapped-candidate, exact-qualification and forged-promotion tests; runtime publication remains verifier-only and cannot create admissions/promotions/generations.
- Added focused Apex CI and V2 Shadow trigger coverage, `APEX_CHAMPION_AUTHORITY_V2.md`, D036, constitutional invariant/requirement traceability and cutover runbook integration.
- This mechanism does not fabricate real production champions, prospective outcomes, deployed Plane-B backend evidence or a PUBLISHED V2 release. Production remains WITHHELD.

"""
insert_before_once(
    "docs/APEX_CHANGELOG.md",
    "## 2026-08-26 — V2 prospective empirical operations plane",
    entry,
)

# Refresh top-level project status without destroying historical detail.
replace_once("PROJECT_STATUS.md", "**Status date:** 7 August 2026", "**Status date:** 27 August 2026")
status_section = """## V2 control-plane status — 27 August 2026

Apex V2 is in a stacked engineering-certification migration, not live production cutover. PRs #75–#86 remain the preceding unmerged V2 stack; #86 is engineering-certified but production is WITHHELD. PR #87 adds explicit champion selection authority so a qualified candidate or mutable registry/configuration row cannot become production authority by implication.

#87 now binds production publication and answer authority to one immutable point-in-time `ProductionChampionGeneration`. Forecast champion authority must be independently re-derived from exact retained learning evaluation/comparison/policy evidence; DecisionPolicy, scenario-generator and scenario-policy champions require separate reviewed admissions with typed empirical qualifications. The exact generation must match the schema-v2 production planning bundle and is retained in schema-v2 `ProductionPublicationAuthorization`. Synthetic fixtures prove mechanism only.

No real 2026/27 forecast champion, DecisionPolicy champion, scenario champion, planning reference-solver champion, deployed production PostgreSQL Plane-B evidence, prospective future qualification outcome or PUBLISHED V2 release is asserted. Until those genuine authorities exist and the full cutover chain passes, `ready_to_act` and `safe_to_act` remain false for V2 production.

"""
insert_before_once("PROJECT_STATUS.md", "## Current state", status_section)

# Sanity checks.
for path in (
    "config/requirements.yaml",
    "docs/APEX_INVARIANTS.md",
    "docs/APEX_CHAMPION_AUTHORITY_V2.md",
    "docs/APEX_DECISIONS.md",
    "docs/APEX_PRODUCTION_CUTOVER_V2.md",
    "docs/APEX_MASTER_CONTEXT.md",
    "docs/APEX_ARCHITECTURE_V2.md",
    "docs/APEX_CHANGELOG.md",
    "PROJECT_STATUS.md",
):
    content = read(path)
    if not content.strip():
        raise SystemExit(f"empty governance file: {path}")

if "INV-PRODUCTION-CHAMPION-AUTHORITY" not in read("config/requirements.yaml"):
    raise SystemExit("production requirement did not acquire champion-authority invariant")
if "learning_promotion_replay.py" not in read("config/requirements.yaml"):
    raise SystemExit("production requirement did not acquire promotion replay implementation")
if "tests/test_v2_champion_authority.py" not in read("config/requirements.yaml"):
    raise SystemExit("production requirement did not acquire champion authority tests")

print("champion authority governance patch complete")
