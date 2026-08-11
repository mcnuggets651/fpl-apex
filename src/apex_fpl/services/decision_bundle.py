from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any, TYPE_CHECKING

import pandas as pd

from apex_fpl.config import Settings
from apex_fpl.optimisation.squad import SquadSolution
from apex_fpl.optimisation.transfers import TransferPlan
from apex_fpl.services.data_quality import DataQualityAssessment, QualityCheck
from apex_fpl.services.provenance import SourceStatus
from apex_fpl.services.safety import SafetyAssessment
from apex_fpl.services.team_state import TeamState, TeamStateResolution

if TYPE_CHECKING:
    from apex_fpl.services.pipeline import PipelineOutput


BUNDLE_CONTRACT = "apex-decision-bundle-v1"
FRAME_FILES = {
    "players": "players.json",
    "projections": "projections.json",
    "integrity": "integrity.json",
    "news_audit": "news_audit.json",
}
DECISION_SETTING_FIELDS = (
    "season",
    "horizon",
    "budget",
    "max_per_team",
    "fixture_decay",
    "risk_penalty",
    "weights",
    "bench_weights",
    "fpl_entry_id",
    "required_sources",
    "max_official_age_hours",
    "max_airsenal_age_hours",
    "min_airsenal_player_coverage",
    "understat_enabled",
    "understat_history_seasons",
    "understat_team_model_mode",
)


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "item"):
        return value.item()
    if isinstance(value, (set, frozenset, tuple)):
        return sorted(value)
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"unsupported JSON value: {type(value).__name__}")


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=_json_default,
    ).encode("utf-8")


def canonical_json_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _canonical_frame(frame: pd.DataFrame) -> dict[str, Any]:
    ordered = frame.copy()
    columns = sorted(str(col) for col in ordered.columns)
    ordered = ordered.reindex(columns=columns)
    sort_keys = [
        col
        for col in (
            "player_id",
            "gw",
            "match_id",
            "event",
            "team",
            "opponent",
            "web_name",
        )
        if col in ordered.columns
    ]
    if sort_keys and not ordered.empty:
        ordered = ordered.sort_values(sort_keys, kind="mergesort", na_position="last")
    # Pandas normalises numpy scalars, timestamps and missing values reliably at
    # this boundary. Loading the JSON payload never executes code (unlike pickle).
    payload = json.loads(
        ordered.to_json(
            orient="split",
            index=False,
            date_format="iso",
            date_unit="us",
            double_precision=15,
        )
    )
    return {"columns": payload["columns"], "data": payload["data"]}


def dataframe_bytes(frame: pd.DataFrame) -> bytes:
    return canonical_json_bytes(_canonical_frame(frame))


def dataframe_sha256(frame: pd.DataFrame) -> str:
    return hashlib.sha256(dataframe_bytes(frame)).hexdigest()


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    return json.loads(frame.to_json(orient="records", date_format="iso"))


def _solution_payload(solution: SquadSolution) -> dict[str, Any]:
    return {
        "status": solution.status,
        "objective": solution.objective,
        "squad": _records(solution.squad),
        "xi": _records(solution.xi),
        "captain": _records(solution.captain),
        "vice_captain": _records(solution.vice_captain),
        "bench": _records(solution.bench),
    }


def _solution_from_payload(payload: dict[str, Any]) -> SquadSolution:
    return SquadSolution(
        status=str(payload.get("status", "Infeasible")),
        objective=float(payload.get("objective", float("nan"))),
        squad=pd.DataFrame(payload.get("squad") or []),
        xi=pd.DataFrame(payload.get("xi") or []),
        captain=pd.DataFrame(payload.get("captain") or []),
        vice_captain=pd.DataFrame(payload.get("vice_captain") or []),
        bench=pd.DataFrame(payload.get("bench") or []),
    )


def _team_state_from_payload(payload: dict[str, Any] | None) -> TeamState | None:
    if not payload:
        return None
    row = dict(payload)
    row["squad"] = {int(pid) for pid in row.get("squad") or []}
    row["selling_prices"] = {
        int(pid): float(price)
        for pid, price in (row.get("selling_prices") or {}).items()
    }
    return TeamState(**row)


def _settings_payload(settings: Settings, horizon: int) -> dict[str, Any]:
    payload = {
        field: getattr(settings, field)
        for field in DECISION_SETTING_FIELDS
    }
    payload["horizon"] = int(horizon)
    # Record configured external surfaces without persisting credentials or URLs.
    payload["source_configuration"] = {
        "news_feeds_count": len(settings.news_feeds),
        "news_feeds_sha256": canonical_json_sha256(sorted(settings.news_feeds)),
        "odds_endpoint_sha256": (
            hashlib.sha256(settings.odds_api_url.encode("utf-8")).hexdigest()
            if settings.odds_api_url
            else None
        ),
        "odds_credentials_configured": bool(settings.odds_api_key),
        "airsenal_configured": bool(settings.airsenal_csv),
    }
    return payload


def _redact_payload(value: Any, secrets: list[str]) -> Any:
    if isinstance(value, dict):
        return {key: _redact_payload(item, secrets) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_payload(item, secrets) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_payload(item, secrets) for item in value)
    if isinstance(value, str):
        redacted = value
        for secret in secrets:
            if secret:
                redacted = redacted.replace(secret, "[REDACTED]")
        return redacted
    return value


def _hash_files(root: Path, patterns: tuple[str, ...]) -> str:
    rows: list[dict[str, str]] = []
    for pattern in patterns:
        for path in sorted(root.glob(pattern)):
            if not path.is_file():
                continue
            rows.append(
                {
                    "path": path.relative_to(root).as_posix(),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
            )
    return canonical_json_sha256(rows)


def _git_commit(root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return result.stdout.strip() or "unknown"


def _git_material_dirty(root: Path) -> bool | None:
    try:
        result = subprocess.run(
            [
                "git",
                "status",
                "--porcelain",
                "--untracked-files=all",
                "--",
                "src",
                "scripts",
                "config",
                "upstreams.lock.json",
            ],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return bool(result.stdout.strip())


class DecisionBundle:
    """Replayable, content-addressed input surface for every decision layer."""

    def __init__(
        self,
        root: Path,
        manifest: dict[str, Any],
        frames: dict[str, pd.DataFrame],
    ) -> None:
        self.root = root
        self.manifest = manifest
        self.frames = frames

    @property
    def bundle_id(self) -> str:
        return str(self.manifest["bundle_id"])

    @property
    def created_at(self) -> str:
        return str(self.manifest["created_at"])

    @property
    def settings(self) -> dict[str, Any]:
        return dict(self.manifest["settings"])

    @property
    def players(self) -> pd.DataFrame:
        return self.frames["players"].copy()

    @property
    def projections(self) -> pd.DataFrame:
        return self.frames["projections"].copy()

    @classmethod
    def capture(
        cls,
        output: PipelineOutput,
        settings: Settings,
        root: str | Path,
        *,
        repo_root: str | Path = ".",
    ) -> DecisionBundle:
        target = Path(root)
        repository = Path(repo_root).resolve()
        frames = {
            "players": output.players,
            "projections": output.projections,
            "integrity": output.integrity,
            "news_audit": output.news_audit,
        }
        frame_hashes = {name: dataframe_sha256(frame) for name, frame in frames.items()}
        settings_payload = _settings_payload(settings, len(output.gameweeks))
        code = {
            "git_commit": _git_commit(repository),
            "material_code_dirty": _git_material_dirty(repository),
            "source_tree_sha256": _hash_files(
                repository, ("src/**/*.py", "scripts/*.py")
            ),
            "configuration_sha256": _hash_files(
                repository, ("config/**/*", "upstreams.lock.json")
            ),
        }
        team_resolution = output.team_state
        redactions = [
            str(value)
            for value in (
                settings.odds_api_key,
                settings.odds_api_url,
                *settings.news_feeds,
            )
            if value
        ]
        team_payload = (
            {
                "configured": team_resolution.configured,
                "ok": team_resolution.ok,
                "detail": team_resolution.detail,
                "metadata": team_resolution.metadata,
                "state": (
                    team_resolution.state.to_dict()
                    if team_resolution.state is not None
                    else None
                ),
            }
            if team_resolution is not None
            else None
        )
        source_payload = _redact_payload(
            [source.to_dict() for source in output.sources], redactions
        )
        safety_payload = output.safety.to_dict()
        quality_payload = output.data_quality.to_dict()
        transfer_payload = (
            asdict(output.transfer_plan) if output.transfer_plan is not None else None
        )
        legacy_payload = {
            name: _solution_payload(solution)
            for name, solution in output.scenarios.items()
        }
        metadata_hashes = {
            "sources": canonical_json_sha256(source_payload),
            "safety": canonical_json_sha256(safety_payload),
            "data_quality": canonical_json_sha256(quality_payload),
            "team_state": canonical_json_sha256(team_payload),
            "transfer_plan": canonical_json_sha256(transfer_payload),
            "legacy_scenarios": canonical_json_sha256(legacy_payload),
        }
        identity = {
            "contract": BUNDLE_CONTRACT,
            # The commit is provenance, while the content hashes are identity.
            # A documentation-only commit must not invalidate an otherwise
            # byte-identical decision surface.
            "code": {
                "source_tree_sha256": code["source_tree_sha256"],
                "configuration_sha256": code["configuration_sha256"],
            },
            "settings_sha256": canonical_json_sha256(settings_payload),
            "official": {
                key: output.snapshot.get(key)
                for key in ("bootstrap_sha256", "fixtures_sha256")
            },
            "upstreams": output.upstreams,
            "material_inputs": output.material_inputs,
            "frame_hashes": frame_hashes,
            "metadata_hashes": metadata_hashes,
            "gameweeks": [int(gw) for gw in output.gameweeks],
            "team_state_sha256": canonical_json_sha256(
                {
                    "state": team_payload.get("state") if team_payload else None,
                    "metadata": team_payload.get("metadata") if team_payload else None,
                    "configured": (
                        team_payload.get("configured") if team_payload else False
                    ),
                }
            ),
        }
        bundle_id = canonical_json_sha256(identity)
        created_at = datetime.now(timezone.utc).isoformat()
        manifest = {
            "contract": BUNDLE_CONTRACT,
            "bundle_id": bundle_id,
            "created_at": created_at,
            "identity": identity,
            "code": code,
            "settings": settings_payload,
            "official_snapshot": output.snapshot,
            "upstreams": output.upstreams,
            "material_inputs": output.material_inputs,
            "gameweeks": [int(gw) for gw in output.gameweeks],
            "sources": source_payload,
            "safety": safety_payload,
            "data_quality": quality_payload,
            "team_state": team_payload,
            "transfer_plan": transfer_payload,
            "legacy_scenarios": legacy_payload,
            "artifacts": {
                name: {"file": FRAME_FILES[name], "sha256": digest}
                for name, digest in frame_hashes.items()
            },
        }
        bundle = cls(target, manifest, {name: frame.copy() for name, frame in frames.items()})
        bundle.write()
        return bundle

    @classmethod
    def load(cls, root: str | Path) -> DecisionBundle:
        target = Path(root)
        manifest_path = target / "manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"decision bundle manifest missing: {manifest_path}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        frames: dict[str, pd.DataFrame] = {}
        for name, default_file in FRAME_FILES.items():
            artifact = (manifest.get("artifacts") or {}).get(name) or {}
            path = target / str(artifact.get("file") or default_file)
            if not path.exists():
                raise ValueError(f"decision bundle artifact missing: {path}")
            raw = path.read_bytes()
            actual = hashlib.sha256(raw).hexdigest()
            expected = artifact.get("sha256")
            if actual != expected:
                raise ValueError(
                    f"decision bundle artifact hash mismatch: {name} "
                    f"expected={expected} actual={actual}"
                )
            payload = json.loads(raw)
            frames[name] = pd.DataFrame(payload["data"], columns=payload["columns"])
        bundle = cls(target, manifest, frames)
        bundle.validate()
        return bundle

    def write(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        for name, frame in self.frames.items():
            raw = dataframe_bytes(frame)
            artifact = self.manifest["artifacts"][name]
            if hashlib.sha256(raw).hexdigest() != artifact["sha256"]:
                raise ValueError(f"decision bundle frame changed before write: {name}")
            (self.root / artifact["file"]).write_bytes(raw)
        # The manifest is written last so an interrupted capture cannot look valid.
        (self.root / "manifest.json").write_text(
            json.dumps(self.manifest, indent=2, default=_json_default) + "\n",
            encoding="utf-8",
        )

    def validate(self) -> None:
        if self.manifest.get("contract") != BUNDLE_CONTRACT:
            raise ValueError(
                f"unsupported decision bundle contract: {self.manifest.get('contract')}"
            )
        expected_id = canonical_json_sha256(self.manifest.get("identity") or {})
        if expected_id != self.bundle_id:
            raise ValueError(
                "decision bundle identity mismatch: "
                f"expected={self.bundle_id} actual={expected_id}"
            )
        identity = self.manifest.get("identity") or {}
        expected_metadata = identity.get("metadata_hashes") or {}
        metadata = {
            "sources": self.manifest.get("sources") or [],
            "safety": self.manifest.get("safety") or {},
            "data_quality": self.manifest.get("data_quality") or {},
            "team_state": self.manifest.get("team_state"),
            "transfer_plan": self.manifest.get("transfer_plan"),
            "legacy_scenarios": self.manifest.get("legacy_scenarios") or {},
        }
        for name, value in metadata.items():
            if canonical_json_sha256(value) != expected_metadata.get(name):
                raise ValueError(f"decision bundle metadata hash mismatch: {name}")
        if canonical_json_sha256(self.manifest.get("settings") or {}) != identity.get(
            "settings_sha256"
        ):
            raise ValueError("decision bundle settings hash mismatch")
        for name in ("upstreams", "material_inputs", "gameweeks"):
            if self.manifest.get(name) != identity.get(name):
                raise ValueError(f"decision bundle identity field mismatch: {name}")
        for name in ("source_tree_sha256", "configuration_sha256"):
            if (self.manifest.get("code") or {}).get(name) != (
                identity.get("code") or {}
            ).get(name):
                raise ValueError(f"decision bundle code hash mismatch: {name}")
        official_identity = identity.get("official") or {}
        official_manifest = self.manifest.get("official_snapshot") or {}
        for name in ("bootstrap_sha256", "fixtures_sha256"):
            if official_manifest.get(name) != official_identity.get(name):
                raise ValueError(f"decision bundle official hash mismatch: {name}")
        identity_hashes = (self.manifest.get("identity") or {}).get("frame_hashes") or {}
        for name, frame in self.frames.items():
            expected = identity_hashes.get(name)
            actual = dataframe_sha256(frame)
            # Integer columns containing missing values can be inferred as float on
            # load. The raw file hash above remains the authoritative byte check;
            # only enforce the semantic re-hash where pandas preserved the schema.
            if actual != expected:
                raw = (self.root / self.manifest["artifacts"][name]["file"]).read_bytes()
                if hashlib.sha256(raw).hexdigest() != expected:
                    raise ValueError(f"decision bundle semantic hash mismatch: {name}")

    def lineage_summary(self) -> dict[str, Any]:
        return {
            "contract": self.manifest["contract"],
            "bundle_id": self.bundle_id,
            "created_at": self.created_at,
            "git_commit": self.manifest["code"]["git_commit"],
            "material_code_dirty": self.manifest["code"].get("material_code_dirty"),
            "source_tree_sha256": self.manifest["code"]["source_tree_sha256"],
            "configuration_sha256": self.manifest["code"]["configuration_sha256"],
            "settings_sha256": self.manifest["identity"]["settings_sha256"],
            "gameweeks": self.manifest["gameweeks"],
            "official_snapshot": self.manifest["official_snapshot"],
            "upstreams": self.manifest["upstreams"],
            "material_inputs": self.manifest["material_inputs"],
            "artifacts": self.manifest["artifacts"],
        }

    def to_pipeline_output(self) -> PipelineOutput:
        from apex_fpl.services.pipeline import PipelineOutput

        safety = SafetyAssessment(**self.manifest["safety"])
        quality_payload = self.manifest["data_quality"]
        data_quality = DataQualityAssessment(
            ready=bool(quality_payload["ready"]),
            blockers=tuple(quality_payload.get("blockers") or []),
            warnings=tuple(quality_payload.get("warnings") or []),
            checks=tuple(QualityCheck(**row) for row in quality_payload.get("checks") or []),
        )
        sources = [SourceStatus(**row) for row in self.manifest.get("sources") or []]
        team_payload = self.manifest.get("team_state")
        team_resolution = None
        if team_payload is not None:
            team_resolution = TeamStateResolution(
                state=_team_state_from_payload(team_payload.get("state")),
                configured=bool(team_payload.get("configured")),
                ok=bool(team_payload.get("ok")),
                detail=str(team_payload.get("detail") or ""),
                metadata=dict(team_payload.get("metadata") or {}),
            )
        transfer_payload = self.manifest.get("transfer_plan")
        transfer_plan = TransferPlan(**transfer_payload) if transfer_payload else None
        scenarios = {
            name: _solution_from_payload(payload)
            for name, payload in (self.manifest.get("legacy_scenarios") or {}).items()
        }
        return PipelineOutput(
            players=self.players,
            projections=self.projections,
            integrity=self.frames["integrity"].copy(),
            news_audit=self.frames["news_audit"].copy(),
            scenarios=scenarios,
            transfer_plan=transfer_plan,
            sources=sources,
            gameweeks=[int(gw) for gw in self.manifest["gameweeks"]],
            safety=safety,
            snapshot=dict(self.manifest["official_snapshot"]),
            data_quality=data_quality,
            team_state=team_resolution,
            upstreams=dict(self.manifest.get("upstreams") or {}),
            material_inputs=dict(self.manifest.get("material_inputs") or {}),
        )
