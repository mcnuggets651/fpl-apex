from __future__ import annotations

import re
import pandas as pd

from apex_fpl.data.news import NewsItem

# Conservative title-level rules. These never alter canonical identity and are
# intentionally weaker than an official FPL availability flag.
_NEGATIVE = [
    (re.compile(r"\b(ruled out|will miss|surgery|long[- ]term|setback)\b", re.I), 0.20, "strong negative"),
    (re.compile(r"\b(injur(?:y|ed)|hamstring|ankle|knee|muscle problem)\b", re.I), 0.55, "injury mention"),
    (re.compile(r"\b(doubtful|major doubt|fitness doubt)\b", re.I), 0.65, "doubt"),
    (re.compile(r"\b(knock|minor issue|late fitness test)\b", re.I), 0.78, "minor doubt"),
]
_POSITIVE = [
    (re.compile(r"\b(return(?:s|ed)? to training|back in training|fit again|available|cleared to play)\b", re.I), 0.96, "positive return"),
]


def _aliases(row: pd.Series) -> list[str]:
    vals = [row.get("web_name"), row.get("second_name")]
    aliases = []
    for v in vals:
        if pd.notna(v) and len(str(v).strip()) >= 4:
            aliases.append(str(v).strip())
    return sorted(set(aliases), key=len, reverse=True)


def infer_news_signals(players: pd.DataFrame, items: list[NewsItem]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Map configured feed headlines to players using conservative name matching.

    Returns one row per player with the strongest relevant multiplier and an
    audit table containing every headline match. No match means multiplier 1.0.
    """
    if not items or players.empty:
        return (
            pd.DataFrame(columns=["player_id", "news_multiplier", "news_confidence", "news_reason"]),
            pd.DataFrame(columns=["player_id", "web_name", "headline", "source", "published", "link", "multiplier", "reason"]),
        )

    audit: list[dict] = []
    for _, p in players.iterrows():
        aliases = _aliases(p)
        if not aliases:
            continue
        for item in items:
            title = item.title or ""
            if not any(re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", title, re.I) for alias in aliases):
                continue
            multiplier, reason = 1.0, "name mention"
            for rx, value, label in _NEGATIVE:
                if rx.search(title):
                    multiplier, reason = value, label
                    break
            if multiplier == 1.0:
                for rx, value, label in _POSITIVE:
                    if rx.search(title):
                        multiplier, reason = value, label
                        break
            audit.append({
                "player_id": int(p["player_id"]),
                "web_name": p.get("web_name", ""),
                "headline": title,
                "source": item.source,
                "published": item.published,
                "link": item.link,
                "multiplier": multiplier,
                "reason": reason,
            })

    audit_df = pd.DataFrame(audit)
    if audit_df.empty:
        return (
            pd.DataFrame(columns=["player_id", "news_multiplier", "news_confidence", "news_reason"]),
            audit_df,
        )

    # Most pessimistic relevant headline wins until manual/official context is
    # reviewed. Confidence is deliberately capped: headline parsing is advisory.
    idx = audit_df.groupby("player_id")["multiplier"].idxmin()
    strongest = audit_df.loc[idx].copy()
    signal = strongest[["player_id", "multiplier", "reason"]].rename(
        columns={"multiplier": "news_multiplier", "reason": "news_reason"}
    )
    signal["news_confidence"] = 0.55
    return signal.reset_index(drop=True), audit_df.reset_index(drop=True)
