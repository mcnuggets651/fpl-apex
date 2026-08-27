from pathlib import Path

path = Path("src/apex_fpl/control/champion_authority.py")
text = path.read_text(encoding="utf-8")
old_import = "from apex_fpl.control.learning_promotion_replay import verify_model_promotion_replay\nfrom apex_fpl.control.learning_store import load_learning_object\n"
new_import = "from apex_fpl.control.learning_promotion_replay import verify_forecast_registry_champion\n"
if text.count(old_import) != 1:
    raise SystemExit("champion authority learning replay import target mismatch")
text = text.replace(old_import, new_import, 1)
start = text.find("def _forecast_champion(\n")
end = text.find("\n\ndef _load_generation_contract(\n", start)
if start < 0 or end < 0:
    raise SystemExit("champion authority forecast function markers missing")
replacement = '''def _forecast_champion(\n    registry_generation_artifact_id: str,\n    *,\n    season: str,\n    as_of: str,\n    store: ArtifactStore,\n) -> str:\n    evidence = verify_forecast_registry_champion(\n        registry_generation_artifact_id,\n        season=season,\n        as_of=as_of,\n        store=store,\n    )\n    return evidence.champion_model_id\n'''
text = text[:start] + replacement + text[end:]
path.write_text(text, encoding="utf-8")
print("champion registry replay integration patched")
