from __future__ import annotations

from datetime import datetime, timezone
import re

import pandas as pd

from apex_fpl.data.news import NewsItem, TRUSTED_SOURCE_TIERS


# Verified positive starting-role evidence is allowed to move a statistical role
# prior, but only within these deliberately small one-Gameweek bounds. It never
# bypasses official injury/suspension availability, which remains a hard ceiling.
START_EVIDENCE_MINUTES_DELTA = {
    "official_club": 8.0,
    "official_league": 7.0,
    "trusted_media": 5.0,
}
START_EVIDENCE_PROBABILITY_DELTA = {
    "official_club": 0.10,
    "official_league": 0.09,
    "trusted_media": 0.07,
}
SOURCE_CONFIDENCE = {
    "official_club": 0.92,
    "official_league": 0.85,
    "trusted_media": 0.72,
}

# Conservative headline-level rules. These never alter canonical identity and are
# intentionally weaker than official FPL availability. The multiplier can only
# reduce expected minutes; positive headlines improve evidence/confidence, not the
# player's projection above the usage model.
_NEGATIVE = [
    (
        re.compile(
            r"\b(ruled out|will miss|surgery|setback|suspended|"
            r"long[- ]term (?:injury|absence)|out (?:for the )?long[- ]term)\b",
            re.I,
        ),
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

_DECISION_CONTEXT = [
    (
        re.compile(r"\b(?:on|take|takes|taker|taking|first[- ]choice for) (?:the )?penalt(?:y|ies)\b", re.I),
        "set_piece",
        "penalty responsibility evidence",
    ),
    (
        re.compile(r"\b(?:take|takes|taker|taking|on) (?:the )?(?:corners|free[- ]kicks|set pieces)\b", re.I),
        "set_piece",
        "set-piece responsibility evidence",
    ),
    (
        re.compile(r"\b(?:play(?:s|ed|ing)?|used) (?:as|at) (?:a |the )?(?:number )?(?:9|10|winger|striker|forward)\b", re.I),
        "role",
        "tactical role evidence",
    ),
]

EVIDENCE_MAX_AGE_HOURS = {
    "manager": 72.0,
    "role": 168.0,
    "set_piece": 336.0,
    "availability": 168.0,
    "transfer": 168.0,
}


def _aliases(row: pd.Series) -> list[str]:
    full_name = " ".join(
        str(row.get(col, "")).strip()
        for col in ("first_name", "second_name")
        if pd.notna(row.get(col))
    ).strip()
    vals = [full_name, row.get("web_name"), row.get("second_name")]
    aliases = []
    for value in vals:
        if pd.notna(value) and len(str(value).strip()) >= 4:
            aliases.append(str(value).strip())
    return sorted(set(aliases), key=len, reverse=True)


def _age_hours(published: str, now: datetime) -> float | None:
    try:
        dt = datetime.fromisoformat(str(published).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max((now - dt.astimezone(timezone.utc)).total_seconds() / 3600.0, 0.0)
    except Exception:
        return None


def _is_negated(text: str, match: re.Match) -> bool:
    """Reject simple local negation before a risk phrase.

    This is deliberately narrow; unclear prose is retained as audit-only rather
    than using broad sentiment inference to alter minutes.
    """
    prefix = text[max(0, match.start() - 24) : match.start()]
    return bool(re.search(r"\b(?:not|isn't|wasn't|no longer)\s+$", prefix, re.I))


def infer_news_signals(
    players: pd.DataFrame,
    items: list[NewsItem],
    *,
    max_age_hours: float | None = None,
    now: datetime | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Map fresh trusted/official headlines to players conservatively.

    Headlines older than ``max_age_hours`` are removed before they can alter
    expected minutes. Long-lived injury state belongs to the official FPL status
    fields; news is the short-lived layer for press conferences, transfers and
    late rotation information.

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
        "news_minutes_delta",
        "news_start_probability_delta",
        "news_source_name",
        "news_source_tier",
        "news_published_at",
        "news_retrieved_at",
        "news_source_url",
    ]
    audit_columns = [
        "player_id",
        "web_name",
        "headline",
        "summary",
        "source_name",
        "source_tier",
        "published_at",
        "retrieved_at",
        "age_hours",
        "source_url",
        "multiplier",
        "minutes_delta",
        "start_probability_delta",
        "reason",
        "evidence_type",
        "eligible_for_projection",
        "ineligibility_reason",
    ]
    if not items or players.empty:
        return pd.DataFrame(columns=signal_columns), pd.DataFrame(columns=audit_columns)

    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    alias_owners: dict[str, set[int]] = {}
    for _, player in players.iterrows():
        for alias in _aliases(player):
            alias_owners.setdefault(alias.casefold(), set()).add(int(player["player_id"]))
    audit: list[dict] = []
    for _, player in players.iterrows():
        aliases = _aliases(player)
        if not aliases:
            continue
        for item in items:
            age = _age_hours(item.published or "", now)
            title = item.title or ""
            summary = re.sub(r"<[^>]+>", " ", item.summary or "")
            evidence_text = " ".join((title, summary))
            matched_aliases = [
                alias for alias in aliases
                if re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", evidence_text, re.I)
            ]
            if not matched_aliases:
                continue

            unambiguous = any(len(alias_owners[alias.casefold()]) == 1 for alias in matched_aliases)
            if not unambiguous:
                team_name = str(player.get("team_name") or "").strip()
                unambiguous = bool(
                    team_name
                    and re.search(rf"(?<!\w){re.escape(team_name)}(?!\w)", evidence_text, re.I)
                )

            multiplier, reason, event_type = 1.0, "name mention", "general"
            for regex, value, label, kind in _NEGATIVE:
                match = regex.search(evidence_text)
                if match and not _is_negated(evidence_text, match):
                    multiplier, reason, event_type = value, label, kind
                    break
            if multiplier == 1.0 and event_type == "general":
                for regex, value, label, kind in _POSITIVE:
                    if regex.search(evidence_text):
                        multiplier, reason, event_type = value, label, kind
                        break
            if multiplier == 1.0 and event_type == "general":
                for regex, kind, label in _DECISION_CONTEXT:
                    if regex.search(evidence_text):
                        event_type, reason = kind, label
                        break

            tier = str(item.source_tier or "unknown")
            ineligible = ""
            if tier not in TRUSTED_SOURCE_TIERS:
                ineligible = "untrusted_or_unclassified_source_tier"
            elif not unambiguous:
                ineligible = "ambiguous_player_identity"
            elif age is None:
                ineligible = "unknown_publication_time"
            elif age > (
                min(max_age_hours, EVIDENCE_MAX_AGE_HOURS.get(event_type, max_age_hours))
                if max_age_hours is not None
                else EVIDENCE_MAX_AGE_HOURS.get(event_type, 120.0)
            ):
                ineligible = "expired_publication"
            elif not str(item.link or "").startswith(("https://", "http://")):
                ineligible = "missing_verifiable_source_url"
            elif event_type == "general":
                ineligible = "no_decision_relevant_evidence"

            minutes_delta = 0.0
            start_delta = 0.0
            if event_type == "manager" and reason == "positive manager/line-up evidence":
                minutes_delta = START_EVIDENCE_MINUTES_DELTA.get(tier, 0.0)
                start_delta = START_EVIDENCE_PROBABILITY_DELTA.get(tier, 0.0)

            audit.append(
                {
                    "player_id": int(player["player_id"]),
                    "web_name": player.get("web_name", ""),
                    "headline": title,
                    "summary": summary.strip(),
                    "source_name": item.source,
                    "source_tier": tier,
                    "published_at": item.published,
                    "retrieved_at": item.retrieved_at,
                    "age_hours": round(age, 2) if age is not None else None,
                    "source_url": item.link,
                    "multiplier": multiplier,
                    "minutes_delta": minutes_delta,
                    "start_probability_delta": start_delta,
                    "reason": reason,
                    "evidence_type": event_type,
                    "eligible_for_projection": not ineligible,
                    "ineligibility_reason": ineligible or None,
                }
            )

    audit_df = pd.DataFrame(audit, columns=audit_columns)
    if audit_df.empty:
        return pd.DataFrame(columns=signal_columns), audit_df

    eligible = audit_df[audit_df["eligible_for_projection"]].copy()
    if eligible.empty:
        return pd.DataFrame(columns=signal_columns), audit_df.reset_index(drop=True)

    # Strong negative availability dominates. Otherwise prefer the verified
    # source with the largest bounded positive starting-role update.
    eligible["source_confidence"] = eligible["source_tier"].map(SOURCE_CONFIDENCE).fillna(0)
    eligible["adjustment_priority"] = (
        (1.0 - eligible["multiplier"]) * 100.0
        + eligible["minutes_delta"]
        + eligible["source_confidence"] / 100.0
    )
    strongest = (
        eligible.sort_values(
            ["player_id", "adjustment_priority", "published_at", "source_url"],
            ascending=[True, False, False, True],
            kind="mergesort",
        )
        .drop_duplicates("player_id", keep="first")
        .copy()
    )
    signal = strongest[
        [
            "player_id",
            "multiplier",
            "reason",
            "evidence_type",
            "minutes_delta",
            "start_probability_delta",
            "source_name",
            "source_tier",
            "published_at",
            "retrieved_at",
            "source_url",
            "source_confidence",
        ]
    ].rename(
        columns={
            "multiplier": "news_multiplier",
            "reason": "news_reason",
            "evidence_type": "news_event_type",
            "minutes_delta": "news_minutes_delta",
            "start_probability_delta": "news_start_probability_delta",
            "source_name": "news_source_name",
            "source_tier": "news_source_tier",
            "published_at": "news_published_at",
            "retrieved_at": "news_retrieved_at",
            "source_url": "news_source_url",
            "source_confidence": "news_confidence",
        }
    )
    return signal[signal_columns].reset_index(drop=True), audit_df.reset_index(drop=True)
