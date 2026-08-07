from __future__ import annotations

import numpy as np
import pandas as pd


def blend_projection(base: pd.DataFrame, weights: dict[str, float], risk_penalty: float) -> pd.DataFrame:
    """Blend experts row-by-row and renormalise when an expert is absent for a GW."""
    cols = {
        "official_ep": "official_xp",
        "apex_model": "apex_xp",
        "airsenal": "airsenal_xp",
        "market": "market_xp",
    }
    out = base.copy()
    numerator = np.zeros(len(out), dtype=float)
    denominator = np.zeros(len(out), dtype=float)
    for key, col in cols.items():
        if col not in out.columns:
            continue
        v = pd.to_numeric(out[col], errors="coerce").to_numpy(float)
        mask = np.isfinite(v)
        w = float(weights.get(key, 0))
        numerator[mask] += v[mask] * w
        denominator[mask] += w
    fallback = pd.to_numeric(out.get("apex_xp", 0), errors="coerce").fillna(0).to_numpy(float)
    out["xp"] = np.where(denominator > 0, numerator / np.maximum(denominator, 1e-12), fallback)
    sd = pd.to_numeric(out.get("apex_sd", 0), errors="coerce").fillna(0)
    out["risk_adjusted_xp"] = np.maximum(out["xp"] - risk_penalty * sd, 0)
    return out
