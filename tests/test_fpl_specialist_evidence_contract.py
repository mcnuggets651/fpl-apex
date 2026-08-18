from pathlib import Path

import yaml

from apex_fpl.data.tactical import TRUSTED_SOURCE_TIERS as TACTICAL_OVERRIDE_TIERS


def test_specialist_sources_are_configured_as_corroboration_only():
    config = yaml.safe_load(Path("config/news_sources.yaml").read_text())
    specialist = {
        row["name"]: row
        for row in config["feeds"]
        if row.get("tier") == "fpl_specialist"
    }

    assert "Fantasy Football Scout" in specialist
    assert "AllAboutFPL" in specialist
    assert specialist["Fantasy Football Scout"]["url"].startswith("https://")
    assert specialist["AllAboutFPL"]["url"].startswith("https://")


def test_transfer_specialist_is_configured_as_review_only():
    config = yaml.safe_load(Path("config/news_sources.yaml").read_text())
    transfer_sources = {
        row["name"]: row
        for row in config["feeds"]
        if row.get("tier") == "transfer_specialist"
    }

    assert "Fabrizio Romano" in transfer_sources
    assert transfer_sources["Fabrizio Romano"]["url"].startswith("https://")


def test_specialist_sources_cannot_directly_override_tactical_projection_inputs():
    # Specialist sites are valuable independent corroboration, but their
    # predicted XIs/opinions/transfer reports must never directly become minutes,
    # role or set-piece overrides. Those material inputs retain the stricter
    # trusted-source gate.
    assert "fpl_specialist" not in TACTICAL_OVERRIDE_TIERS
    assert "transfer_specialist" not in TACTICAL_OVERRIDE_TIERS
