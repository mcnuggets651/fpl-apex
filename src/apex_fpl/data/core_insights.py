from __future__ import annotations

from io import StringIO

import pandas as pd

from apex_fpl.data.http import CachedHttp

RAW_BASE = "https://raw.githubusercontent.com/olbauday/FPL-Core-Insights/{ref}/data/{season}"


class FPLCoreClient:
    def __init__(self, http: CachedHttp, season: str, ref: str = "main"):
        self.http = http
        self.season = season
        self.ref = ref or "main"

    def _csv(self, name: str, force: bool = False) -> pd.DataFrame:
        url = f"{RAW_BASE.format(ref=self.ref, season=self.season)}/{name}"
        key_ref = self.ref[:12].replace("/", "_")
        text = self.http.get_text(
            url,
            f"core_{key_ref}_{self.season}_{name.replace('/', '_')}",
            force,
        )
        return pd.read_csv(StringIO(text))

    def playerstats(self, force: bool = False) -> pd.DataFrame:
        df = self._csv("playerstats.csv", force)
        if "id" in df.columns:
            df["player_id"] = pd.to_numeric(df["id"], errors="coerce").astype("Int64")
        return df

    def players(self, force: bool = False) -> pd.DataFrame:
        return self._csv("players.csv", force)

    @staticmethod
    def _stable_identity_rows(players: pd.DataFrame, label: str) -> pd.DataFrame:
        """Return one unambiguous player_code -> player_id identity row.

        FPL Core occasionally contains repeated identical identity rows. Those are
        harmless, but a true conflicting mapping must never be silently resolved.
        Normalising here keeps the prior-season bridge one-to-one without weakening
        identity validation.
        """
        required = {"player_code", "player_id"}
        if not required.issubset(players.columns):
            raise ValueError(f"{label} FPL Core players.csv lacks stable player_code/player_id mapping")

        identity = players[["player_code", "player_id"]].copy()
        identity["player_id"] = pd.to_numeric(identity["player_id"], errors="coerce")
        identity = identity.dropna(subset=["player_code", "player_id"])
        identity["player_id"] = identity["player_id"].astype(int)

        code_conflicts = identity.groupby("player_code")["player_id"].nunique()
        bad_codes = code_conflicts[code_conflicts > 1]
        if not bad_codes.empty:
            raise ValueError(
                f"{label} FPL Core contains conflicting player_code mappings: "
                + ", ".join(map(str, bad_codes.index[:10]))
            )

        id_conflicts = identity.groupby("player_id")["player_code"].nunique()
        bad_ids = id_conflicts[id_conflicts > 1]
        if not bad_ids.empty:
            raise ValueError(
                f"{label} FPL Core contains conflicting player_id mappings: "
                + ", ".join(map(str, bad_ids.index[:10]))
            )

        return identity.drop_duplicates(["player_code", "player_id"]).reset_index(drop=True)

    def previous_season_playerstats(self, force: bool = False) -> pd.DataFrame:
        """Map prior-season playing time to current official IDs via stable codes."""
        parts = [int(value) for value in str(self.season).replace("/", "-").split("-")]
        if len(parts) != 2:
            raise ValueError(f"unsupported FPL season format: {self.season!r}")
        previous = f"{parts[0] - 1}-{parts[1] - 1}"
        prior_client = FPLCoreClient(self.http, previous, ref=self.ref)
        current_players = self._stable_identity_rows(self.players(force=force), "current-season")
        prior_players = self._stable_identity_rows(prior_client.players(force=force), "prior-season")
        prior_stats = prior_client.playerstats(force=force)

        available = [
            col
            for col in (
                "minutes",
                "starts",
                "expected_goals_per_90",
                "expected_assists_per_90",
                "defensive_contribution_per_90",
            )
            if col in prior_stats.columns
        ]
        # FPL Core playerstats.csv is a longitudinal table: cumulative player
        # snapshots are appended once per Gameweek. Joining it directly to the
        # one-row player identity table creates many matches per established player.
        # Select the latest published snapshot per official prior-season ID and
        # reject genuinely ambiguous duplicate snapshots instead of silently
        # aggregating or double-counting them.
        if prior_stats["player_id"].duplicated().any():
            if "gw" not in prior_stats.columns:
                raise ValueError(
                    "FPL Core longitudinal playerstats.csv lacks a Gameweek column"
                )
            stats = prior_stats[["player_id", "gw", *available]].copy()
            stats["gw"] = pd.to_numeric(stats["gw"], errors="coerce")
            if stats[["player_id", "gw"]].isna().any().any():
                raise ValueError("FPL Core playerstats.csv contains invalid player/GW keys")
            if stats.duplicated(["player_id", "gw"]).any():
                raise ValueError(
                    "FPL Core playerstats.csv contains ambiguous duplicate player/GW snapshots"
                )
            prior_stats = stats.sort_values(["player_id", "gw"]).drop_duplicates(
                "player_id", keep="last"
            )

        previous_rows = prior_players.merge(
            prior_stats[["player_id", *available]],
            on="player_id",
            how="left",
            validate="one_to_one",
        )
        previous_rows = previous_rows.rename(
            columns={col: f"previous_{col}" for col in available}
        ).drop(columns="player_id")
        current = current_players.rename(columns={"player_id": "current_player_id"})
        out = current.merge(
            previous_rows,
            on="player_code",
            how="left",
            validate="one_to_one",
        ).rename(columns={"current_player_id": "player_id"})
        out["previous_start_probability"] = (
            pd.to_numeric(out.get("previous_starts"), errors="coerce") / 38.0
        ).clip(0, 1)
        out["previous_minutes_per_match"] = (
            pd.to_numeric(out.get("previous_minutes"), errors="coerce") / 38.0
        ).clip(0, 90)
        return out.drop(columns="player_code")

    def teams(self, force: bool = False) -> pd.DataFrame:
        return self._csv("teams.csv", force)

    def preseason_friendlies(self, force: bool = False) -> pd.DataFrame:
        """Player-match stats for the season's GW0 friendlies, if published."""
        try:
            return self._csv(
                "By Tournament/Friendlies/GW0/playermatchstats.csv",
                force,
            )
        except Exception:
            return pd.DataFrame(
                columns=[
                    "player_id",
                    "match_id",
                    "minutes_played",
                    "xg",
                    "xa",
                    "defensive_contributions",
                    "start_min",
                ]
            )

    def fixture_elos(
        self,
        gameweeks: list[int],
        force: bool = False,
    ) -> pd.DataFrame:
        """Return FPL-team-ID Elo context for requested Premier League fixtures.

        FPL Core fixture files use the historical team ``code`` column (e.g.
        Arsenal=3, Man City=43), while its current ``teams.csv`` also includes
        the official FPL ``id`` 1..20. The per-Gameweek fixture files can also
        contain cup matches. Only rows explicitly labelled ``prem`` are valid for
        the FPL fixture surface; otherwise cup Elo can masquerade as league
        coverage when future Premier League Elo values are still unpublished.
        """
        teams = self.teams(force=force)
        required_team_cols = {"code", "id"}
        if not required_team_cols.issubset(teams.columns):
            raise ValueError(
                "FPL Core teams.csv is missing code/id mapping needed for Elo reconciliation"
            )
        code_to_id = {
            int(code): int(team_id)
            for code, team_id in zip(
                pd.to_numeric(teams["code"], errors="coerce"),
                pd.to_numeric(teams["id"], errors="coerce"),
            )
            if pd.notna(code) and pd.notna(team_id)
        }

        rows: list[dict] = []
        for gw in gameweeks:
            fixtures = self._csv(f"By Gameweek/GW{int(gw)}/fixtures.csv", force)
            required = {
                "gameweek",
                "home_team",
                "home_team_elo",
                "away_team",
                "away_team_elo",
            }
            if not required.issubset(fixtures.columns):
                raise ValueError(
                    f"FPL Core GW{gw} fixtures missing Elo columns: "
                    f"{sorted(required - set(fixtures.columns))}"
                )
            if "tournament" in fixtures.columns:
                fixtures = fixtures[
                    fixtures["tournament"].astype(str).str.casefold().eq("prem")
                ]
            current = fixtures[
                pd.to_numeric(fixtures["gameweek"], errors="coerce") == int(gw)
            ]
            for _, fixture in current.iterrows():
                home_code = pd.to_numeric(
                    pd.Series([fixture["home_team"]]), errors="coerce"
                ).iloc[0]
                away_code = pd.to_numeric(
                    pd.Series([fixture["away_team"]]), errors="coerce"
                ).iloc[0]
                home_elo = pd.to_numeric(
                    pd.Series([fixture["home_team_elo"]]), errors="coerce"
                ).iloc[0]
                away_elo = pd.to_numeric(
                    pd.Series([fixture["away_team_elo"]]), errors="coerce"
                ).iloc[0]
                if any(pd.isna(value) for value in [home_code, away_code, home_elo, away_elo]):
                    continue
                home_id = code_to_id.get(int(home_code))
                away_id = code_to_id.get(int(away_code))
                if home_id is None or away_id is None:
                    continue
                rows.extend(
                    [
                        {
                            "gw": int(gw),
                            "team": home_id,
                            "opponent": away_id,
                            "is_home": True,
                            "team_elo": float(home_elo),
                            "opponent_elo": float(away_elo),
                        },
                        {
                            "gw": int(gw),
                            "team": away_id,
                            "opponent": home_id,
                            "is_home": False,
                            "team_elo": float(away_elo),
                            "opponent_elo": float(home_elo),
                        },
                    ]
                )
        return pd.DataFrame(
            rows,
            columns=[
                "gw",
                "team",
                "opponent",
                "is_home",
                "team_elo",
                "opponent_elo",
            ],
        ).drop_duplicates(["gw", "team", "opponent", "is_home"])
