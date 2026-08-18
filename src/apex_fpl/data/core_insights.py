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
        """Return one unambiguous stable identity row per player code.

        ``player_code`` is the cross-season identity key. When FPL Core publishes
        ``team_code`` we retain it as decision context so the minutes model can tell
        whether prior-season starts belong to the player's current club or to a club
        they have since left. Team membership is not an identity authority: current
        Official FPL identity still wins in production.

        Minimal synthetic/legacy identity frames may omit ``team_code``; that is a
        supported schema and means club-change state is unknown, not false evidence.
        """
        required = {"player_code", "player_id"}
        if not required.issubset(players.columns):
            raise ValueError(
                f"{label} FPL Core players.csv lacks stable player_code/player_id mapping"
            )

        columns = ["player_code", "player_id"]
        if "team_code" in players.columns:
            columns.append("team_code")
        identity = players[columns].copy()
        identity["player_id"] = pd.to_numeric(identity["player_id"], errors="coerce")
        if "team_code" in identity.columns:
            identity["team_code"] = pd.to_numeric(identity["team_code"], errors="coerce")
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

        if "team_code" in identity.columns:
            team_conflicts = (
                identity.dropna(subset=["team_code"])
                .groupby("player_code")["team_code"]
                .nunique()
            )
            bad_teams = team_conflicts[team_conflicts > 1]
            if not bad_teams.empty:
                raise ValueError(
                    f"{label} FPL Core contains conflicting team_code mappings: "
                    + ", ".join(map(str, bad_teams.index[:10]))
                )

        return identity.drop_duplicates(columns).reset_index(drop=True)

    @staticmethod
    def _longitudinal_role_counts(prior_stats: pd.DataFrame) -> pd.DataFrame:
        """Recover factual appearances and available-role games from cumulative GW rows.

        FPL Core stores cumulative player snapshots. Dividing last-season starts or
        minutes by 38 confounds tactical role with injuries, suspensions and other
        absences. Current availability is modelled separately by Apex, so the prior
        role bridge must be conditional on games where the player was actually in the
        selectable/participating population.

        ``previous_appearances`` is reconstructed from positive cumulative minute
        deltas. ``previous_role_games`` counts snapshots where FPL status was available
        or doubtful, but is never allowed below factual appearances or starts. This
        retains healthy unused-bench games as rotation evidence while excluding old
        injury/suspension absences from the starter prior.
        """
        required = {"player_id", "gw", "minutes", "starts"}
        if not required.issubset(prior_stats.columns):
            return pd.DataFrame(columns=["player_id", "appearances", "role_games"])

        stats = prior_stats[
            [
                "player_id",
                "gw",
                "minutes",
                "starts",
                *(["status"] if "status" in prior_stats.columns else []),
            ]
        ].copy()
        stats["player_id"] = pd.to_numeric(stats["player_id"], errors="coerce")
        stats["gw"] = pd.to_numeric(stats["gw"], errors="coerce")
        stats["minutes"] = pd.to_numeric(stats["minutes"], errors="coerce")
        stats["starts"] = pd.to_numeric(stats["starts"], errors="coerce")
        stats = stats.dropna(subset=["player_id", "gw", "minutes", "starts"])
        stats = stats.sort_values(["player_id", "gw"])

        minute_delta = stats.groupby("player_id", sort=False)["minutes"].diff()
        first = stats.groupby("player_id", sort=False).cumcount().eq(0)
        minute_delta = minute_delta.where(~first, stats["minutes"])
        appeared = minute_delta.fillna(0.0).gt(0.0)

        if "status" in stats.columns:
            status = stats["status"].fillna("a").astype(str).str.casefold()
            available = status.isin({"a", "d"})
        else:
            available = appeared.copy()

        work = stats[["player_id"]].copy()
        work["appeared"] = appeared.astype(int)
        work["available"] = available.astype(int)
        counts = work.groupby("player_id", as_index=False).agg(
            appearances=("appeared", "sum"),
            available_games=("available", "sum"),
        )
        latest = stats.groupby("player_id", as_index=False).tail(1)[
            ["player_id", "starts"]
        ]
        counts = counts.merge(latest, on="player_id", how="left", validate="one_to_one")
        counts["role_games"] = pd.concat(
            [
                counts["available_games"],
                counts["appearances"],
                counts["starts"],
            ],
            axis=1,
        ).max(axis=1)
        return counts[["player_id", "appearances", "role_games"]]

    def previous_season_playerstats(self, force: bool = False) -> pd.DataFrame:
        """Map prior-season playing time and club context to current official IDs."""
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
        role_counts = self._longitudinal_role_counts(prior_stats)
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
        if not role_counts.empty:
            prior_stats = prior_stats.merge(
                role_counts,
                on="player_id",
                how="left",
                validate="one_to_one",
            )
            available.extend(["appearances", "role_games"])

        prior_identity = prior_players.reindex(
            columns=["player_code", "player_id", "team_code"]
        )
        previous_rows = prior_identity.merge(
            prior_stats[["player_id", *available]],
            on="player_id",
            how="left",
            validate="one_to_one",
        )
        rename = {col: f"previous_{col}" for col in available}
        rename["team_code"] = "previous_team_code"
        previous_rows = previous_rows.rename(columns=rename).drop(columns="player_id")

        current = current_players.reindex(
            columns=["player_code", "player_id", "team_code"]
        ).rename(
            columns={"player_id": "current_player_id", "team_code": "current_team_code"}
        )
        out = current.merge(
            previous_rows,
            on="player_code",
            how="left",
            validate="one_to_one",
        ).rename(columns={"current_player_id": "player_id"})

        def optional_numeric(column: str) -> pd.Series:
            source = (
                out[column]
                if column in out.columns
                else pd.Series(float("nan"), index=out.index, dtype=float)
            )
            return pd.to_numeric(source, errors="coerce")

        previous_starts = optional_numeric("previous_starts")
        previous_minutes = optional_numeric("previous_minutes")
        role_games = optional_numeric("previous_role_games")
        appearances = optional_numeric("previous_appearances")
        denominator = role_games.where(role_games.gt(0), appearances)
        out["previous_start_probability"] = (
            previous_starts / denominator
        ).where(denominator.gt(0), previous_starts / 38.0).clip(0, 1)
        out["previous_minutes_per_match"] = (
            previous_minutes / denominator
        ).where(denominator.gt(0), previous_minutes / 38.0).clip(0, 90)

        current_team = pd.to_numeric(out["current_team_code"], errors="coerce")
        previous_team = pd.to_numeric(out["previous_team_code"], errors="coerce")
        known = current_team.notna() & previous_team.notna()
        club_changed = pd.Series(pd.NA, index=out.index, dtype="boolean")
        club_changed.loc[known] = current_team.loc[known].ne(previous_team.loc[known])
        out["club_changed"] = club_changed
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
                    "goals",
                    "assists",
                    "total_shots",
                    "shots_on_target",
                    "chances_created",
                    "touches_opposition_box",
                    "start_min",
                ]
            )

    def fixture_elos(
        self,
        gameweeks: list[int],
        force: bool = False,
    ) -> pd.DataFrame:
        """Return FPL-team-ID Elo context for requested Premier League fixtures."""
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
