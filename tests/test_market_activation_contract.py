from pathlib import Path

import pytest

from apex_fpl.config import load_settings


def _write_config(path: Path, market_weight: float) -> Path:
    config = path / "apex.yaml"
    config.write_text(
        "\n".join(
            [
                'season: "2026-2027"',
                "weights:",
                f"  official_ep: {0.2666666667 - market_weight}",
                "  apex_model: 0.5111111111",
                "  airsenal: 0.2222222222",
                f"  market: {market_weight}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return config


def test_positive_market_weight_fails_closed_even_with_endpoint(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ODDS_API_URL", "https://example.invalid/market")
    monkeypatch.setenv("ODDS_API_KEY", "configured")
    config = _write_config(tmp_path, 0.1)

    with pytest.raises(
        ValueError,
        match="decision-grade player/Gameweek/freshness provenance",
    ):
        load_settings(config)


def test_zero_market_weight_remains_supported(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ODDS_API_URL", "https://example.invalid/market")
    config = _write_config(tmp_path, 0.0)

    settings = load_settings(config)

    assert settings.weights["market"] == pytest.approx(0.0)
