from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pandas as pd
import typer
from rich.console import Console
from rich.table import Table

from apex_fpl.config import load_settings
from apex_fpl.data.http import CachedHttp
from apex_fpl.data.official import OfficialFPLClient
from apex_fpl.models.backtest import score_predictions
from apex_fpl.services.pipeline import run_pipeline
from apex_fpl.services.team_state import resolve_team_state, write_team_state_report

app = typer.Typer(no_args_is_help=True)
console = Console()


def _repo_root() -> Path:
    # Editable installs are the supported operational mode for the GitHub decision
    # engine. cli.py lives in <repo>/src/apex_fpl/cli.py.
    return Path(__file__).resolve().parents[2]


def _run(scenario: str, horizon: int, force: bool, plan_transfers: bool = True):
    settings = load_settings()
    out = run_pipeline(
        settings,
        horizon=horizon,
        scenario=scenario,
        force=force,
        plan_transfers=plan_transfers,
    )
    table = Table(title="Apex FPL scenarios")
    table.add_column("Scenario")
    table.add_column("Status")
    table.add_column("Captain")
    table.add_column("Objective", justify="right")
    for name, sol in out.scenarios.items():
        cap = sol.captain.iloc[0]["web_name"] if not sol.captain.empty else "-"
        table.add_row(name, sol.status, str(cap), f"{sol.objective:.2f}")
    console.print(table)

    if out.team_state is not None:
        console.print(f"Team sync: {out.team_state.detail}")
    if out.transfer_plan is not None:
        console.print(
            f"Transfer plan: [bold]{out.transfer_plan.status}[/bold] "
            f"({len(out.transfer_plan.weeks)} GW horizon)"
        )
    console.print(
        f"Decision gate: safe_to_act={out.safety.safe_to_act} | "
        f"full_apex_ready={out.safety.full_apex_ready}"
    )
    if out.safety.blockers:
        for blocker in out.safety.blockers:
            console.print(f"[red]BLOCKER: {blocker}[/red]")
    console.print(f"Reports: {settings.report_dir.resolve()}")
    failed = [s for s in out.sources if not s.ok]
    if failed:
        console.print(
            f"[yellow]{len(failed)} auxiliary source warning(s); "
            "see reports/sources.csv.[/yellow]"
        )
    if not out.integrity.empty:
        console.print(
            f"[yellow]{len(out.integrity)} integrity warning(s); "
            "official FPL identity retained.[/yellow]"
        )


@app.command()
def run(
    scenario: str = typer.Option("both"),
    horizon: int = typer.Option(8),
    force: bool = typer.Option(False),
):
    """Refresh data, project, optimise, optionally plan transfers, and write reports."""
    _run(scenario, horizon, force, True)


@app.command()
def refresh(force: bool = typer.Option(True)):
    """Refresh sources and execute a standard unrestricted run."""
    _run("unrestricted", load_settings().horizon, force, True)


@app.command()
def project(horizon: int = typer.Option(8), force: bool = typer.Option(False)):
    """Run the projection pipeline and write the ranked player table."""
    _run("unrestricted", horizon, force, False)


@app.command("optimise")
def optimise(
    scenario: str = typer.Option("unrestricted"),
    horizon: int = typer.Option(8),
):
    """Run initial-squad optimisation for a named scenario."""
    _run(scenario, horizon, False, False)


@app.command("sync-team")
def sync_team(force: bool = typer.Option(True)):
    """Synchronise the configured public FPL entry into reports/team_state.json."""
    settings = load_settings()
    if not settings.fpl_entry_id and not settings.current_squad_path.exists():
        raise typer.BadParameter("No FPL_ENTRY_ID or manual current squad is configured")
    http = CachedHttp(settings.cache_dir)
    official = OfficialFPLClient(http).snapshot(force=force)
    resolution = resolve_team_state(
        http=http,
        players=official.players,
        events=official.events,
        cache_dir=settings.cache_dir,
        current_squad_path=settings.current_squad_path,
        team_state_path=settings.team_state_path,
        entry_id=settings.fpl_entry_id,
        force=force,
    )
    write_team_state_report(settings.report_dir, resolution)
    console.print(resolution.detail)
    if not resolution.ok:
        raise typer.Exit(1)


@app.command("plan-transfers")
def plan_transfers(
    horizon: int = typer.Option(8),
    force: bool = typer.Option(False),
):
    """Run a personalised multi-GW transfer plan from FPL ID or manual override."""
    settings = load_settings()
    if not settings.fpl_entry_id and not settings.current_squad_path.exists():
        raise typer.BadParameter(
            "No team state configured. Set FPL_ENTRY_ID or provide current_squad.csv."
        )
    _run("unrestricted", horizon, force, True)


@app.command("pinnacle")
def pinnacle(
    horizon: int = typer.Option(8, help="Gameweeks in the decision horizon."),
    force: bool = typer.Option(True, help="Refresh live source data."),
    scenarios: int = typer.Option(256, help="Correlated projection scenarios."),
    cvar_alpha: float = typer.Option(0.10, help="Lower-tail CVaR quantile."),
    cvar_weight: float = typer.Option(0.20, help="Weight of lower-tail robustness."),
):
    """Run the complete maximum-EV + CVaR Apex Pinnacle decision engine."""
    script = _repo_root() / "scripts" / "run_pinnacle.py"
    if not script.exists():
        raise typer.BadParameter(f"Pinnacle runner not found at {script}")
    command = [
        sys.executable,
        str(script),
        "--horizon",
        str(horizon),
        "--stochastic-scenarios",
        str(scenarios),
        "--cvar-alpha",
        str(cvar_alpha),
        "--cvar-weight",
        str(cvar_weight),
    ]
    if force:
        command.append("--force")
    completed = subprocess.run(command, cwd=_repo_root(), check=False)
    if completed.returncode != 0:
        raise typer.Exit(completed.returncode)
    console.print(
        "[bold green]Apex Pinnacle complete.[/bold green] "
        "Read data/generated/pinnacle_latest.md or run apex-fpl pinnacle-status."
    )


@app.command("pinnacle-status")
def pinnacle_status():
    """Show the latest repository-local Pinnacle gate and headline decisions."""
    path = _repo_root() / "data" / "generated" / "pinnacle_latest.json"
    if not path.exists():
        console.print("[red]No Pinnacle snapshot exists yet.[/red]")
        raise typer.Exit(1)
    payload = json.loads(path.read_text(encoding="utf-8"))
    table = Table(title="Apex Pinnacle status")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("generated_at", str(payload.get("generated_at", "-")))
    table.add_row("FPL entry", str(payload.get("fpl_entry_id", "-")))
    table.add_row("safe_to_act", str(payload.get("safe_to_act", False)))
    table.add_row("full_apex_ready", str(payload.get("full_apex_ready", False)))
    table.add_row("pinnacle_ready", str(payload.get("pinnacle_ready", False)))
    strategy = payload.get("weekly_strategy") or {}
    if strategy:
        table.add_row("weekly action", str(strategy.get("recommended_action", "-")))
        table.add_row("roll regret", str(strategy.get("roll_regret", "-")))
    console.print(table)
    gate = payload.get("pinnacle_gate") or {}
    for blocker in gate.get("blockers", []):
        console.print(f"[red]BLOCKER: {blocker}[/red]")
    for warning in gate.get("warnings", []):
        console.print(f"[yellow]WARNING: {warning}[/yellow]")
    if payload.get("pinnacle_ready") is not True:
        raise typer.Exit(1)


@app.command()
def backtest(
    file: Path = typer.Argument(..., exists=True, readable=True),
    prediction_col: str = typer.Option("xp"),
    actual_col: str = typer.Option("event_points"),
):
    """Score a historical prediction CSV with MAE/RMSE/bias/rank correlation."""
    df = pd.read_csv(file)
    metrics = score_predictions(
        df, prediction_col=prediction_col, actual_col=actual_col
    )
    table = Table(title="Apex backtest")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    for key, value in metrics.__dict__.items():
        table.add_row(key, f"{value:.4f}")
    console.print(table)


if __name__ == "__main__":
    app()
