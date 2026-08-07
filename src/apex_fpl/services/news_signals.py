from __future__ import annotations

import re

import pandas as pd

from apex_fpl.data.news import NewsItem

# Conservative headline-level rules. These never alter canonical identity and are
# intentionally weaker than official FPL availability. The multiplier can only
# reduce expected minutes; positive headlines improve evidence/confidence, not the
# player's projection above the usage model.
_NEGATIVE = [
    (
        re.compile(r"\b(ruled out|will miss|surgery|long[- ]term|setback|suspended)\b", re.I),
        0.20,
        "strong negative availability",
        "availability",
    ),
    (
        re.compile(r"\b(injur(?:y|ed)|hamstring|ankle|knee|muscle problem)\b", re.I),
        0.55,
        "injury mention",
        "availability",
    ),
    (
        re.compile(r"\b(doubtful|major doubt|fitness doubt)\b", re.I),
        0.65,
        "fitness doubt",
        "availability",
    ),
    (
        re.compile(r"\b(will not start|unlikely to start|not expected to start)\b", re.I),
        0.68,
        "manager/line-up doubt",
        "manager",
    ),
    (
        re.compile(r"\b(knock|minor issue|late fitness test)\b", re.I),
        0.78,
        "minor doubt",
        "availability",
    ),
    (
        re.compile(
            r"\b(completes? (?:a )?move|set to leave|close to joining|agrees? personal terms|"
            r"transfer talks|expected to leave|wants to leave)\b",
            re.I,
        ),
        0.78,
        "transfer uncertainty",
        "transfer",
    ),
]
_POSITIVE = [
    (
        re.compile(
            r"\b(return(?:s|ed)? to training|back in training|fit again|available|cleared to play)\b",
            re.I,
        ),
        1.00,
        "positive return evidence",
        "availability",
    ),
    (
        re.compile(r"\b(will start|set to start|ready to start|expected to start)\b", re.I),
        1.00,
        "positive manager/line-up evidence",
        "manager",
    ),
]


def _aliases(row: pd.Series) -> list[str]:
    vals = [row.get("web_name"), row.get("second_name")]
    aliases = []
    for value in vals:
        if pd.notna(value) and len(str(value).strip()) >= 4:
            aliases.append(str(value).strip())
    return sorted(set(aliases), key=len, reverse=True)


def infer_news_signals(
    players: pd.DataFrame,
    items: list[NewsItem],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Map trusted-feed headlines to players using conservative name matching.

    Returns one row per player with the strongest relevant minutes multiplier and
    a complete audit table. Transfer/manager signals are retained as typed audit
    evidence, but cannot change the player's official club, position or price.
    """
    signal_columns = [
        "player_id",
        "news_multiplier",
        "news_confidence",
        "news_reason",
        "news_event_type",
    ]
    audit_columns = [
        "player_id",
        "web_name",
        "headline",
        "source",
        "published",
        "link",
        "multiplier",
        "reason",
        "event_type",
    ]
    if not items or players.empty:
        return pd.DataFrame(columns=signal_columns), pd.DataFrame(columns=audit_columns)

    audit: list[dict] = []
    for _, player in players.iterrows():
        aliases = _aliases(player)
        if not aliases:
            continue
        for item in items:
            title = item.title or ""
            if not any(
                re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", title, re.I)
                for alias in aliases
            ):
                continue

            multiplier, reason, event_type = 1.0, "name mention", "general"
            for regex, value, label, kind in _NEGATIVE:
                if regex.search(title):
                    multiplier, reason, event_type = value, label, kind
                    break
            if multiplier == 1.0 and event_type == "general":
                for regex, value, label, kind in _POSITIVE:
                    if regex.search(title):
                        multiplier, reason, event_type = value, label, kind
                        break

            audit.append(
                {
                    "player_id": int(player["player_id"]),
                    "web_name": player.get("web_name", ""),
                    "headline": title,
                    "source": item.source,
                    "published": item.published,
                    "link": item.link,
                    "multiplier": multiplier,
                    "reason": reason,
                    "event_type": event_type,
                }
            )

    audit_df = pd.DataFrame(audit, columns=audit_columns)
    if audit_df.empty:
        return pd.DataFrame(columns=signal_columns), audit_df

    # Most pessimistic relevant current headline wins for minutes. This is an
    # intentionally cautious advisory signal; official availability remains a
    # separate, stronger input in the expected-minutes model.
    idx = audit_df.groupby("player_id")["multiplier"].idxmin()
    strongest = audit_df.loc[idx].copy()
    signal = strongest[["player_id", "multiplier", "reason", "event_type"]].rename(
        columns={
            "multiplier": "news_multiplier",
            "reason": "news_reason",
            "event_type": "news_event_type",
        }
    )
    signal["news_confidence"] = signal["news_event_type"].map(
        {"availability": 0.62, "manager": 0.58, "transfer": 0.52, "general": 0.40}
    ).fillna(0.40)
    return signal[signal_columns].reset_index(drop=True), audit_df.reset_index(drop=True)
