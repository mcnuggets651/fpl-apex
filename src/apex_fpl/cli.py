from __future__ import annotations

from pathlib import Path

import pandas as pd
import typer
from rich.console import Console
from rich.table import Table

from apex_fpl.config import load_settings
from apex_fpl.models.backtest import score_predictions
from apex_fpl.services.pipeline import run_pipeline

app = typer.Typer(no_args_is_help=True)
console = Console()


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

    if out.transfer_plan is not None:
        console.print(
            f"Transfer plan: [bold]{out.transfer_plan.status}[/bold] "
            f"({len(out.transfer_plan.weeks)} GW horizon)"
        )
    console.print(f"Decision gate: safe_to_act={out.safety.safe_to_act} | full_apex_ready={out.safety.full_apex_ready}")
    if out.safety.blockers:
        for blocker in out.safety.blockers:
            console.print(f"[red]BLOCKER: {blocker}[/red]")
    console.print(f"Reports: {settings.report_dir.resolve()}")
    failed = [s for s in out.sources if not s.ok]
    if failed:
        console.print(f"[yellow]{len(failed)} auxiliary source warning(s); see reports/sources.csv.[/yellow]")
    if not out.integrity.empty:
        console.print(
            f"[yellow]{len(out.integrity)} integrity warning(s); official FPL identity retained.[/yellow]"
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
def optimise(scenario: str = typer.Option("unrestricted"), horizon: int = typer.Option(8)):
    """Run initial-squad optimisation for a named scenario."""
    _run(scenario, horizon, False, False)


@app.command("plan-transfers")
def plan_transfers(horizon: int = typer.Option(8), force: bool = typer.Option(False)):
    """Run the multi-GW transfer planner using data/manual/current_squad.csv."""
    settings = load_settings()
    if not settings.current_squad_path.exists():
        raise typer.BadParameter(
            f"Missing {settings.current_squad_path}. Copy the example and add your 15 player IDs."
        )
    _run("unrestricted", horizon, force, True)


@app.command()
def backtest(
    file: Path = typer.Argument(..., exists=True, readable=True),
    prediction_col: str = typer.Option("xp"),
    actual_col: str = typer.Option("event_points"),
):
    """Score a historical prediction CSV with MAE/RMSE/bias/rank correlation."""
    df = pd.read_csv(file)
    metrics = score_predictions(df, prediction_col=prediction_col, actual_col=actual_col)
    table = Table(title="Apex backtest")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    for key, value in metrics.__dict__.items():
        table.add_row(key, f"{value:.4f}")
    console.print(table)


if __name__ == "__main__":
    app()
