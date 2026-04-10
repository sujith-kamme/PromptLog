from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table

from promptlog.config import _resolve_storage_path
from promptlog.schema import FeedbackResult
from promptlog import store

console = Console()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


@click.group()
def app() -> None:
    """promptlog — lightweight prompt experiment tracker."""


# ---------------------------------------------------------------------------
# promptlog runs
# ---------------------------------------------------------------------------


@app.command("runs")
@click.option("--project", required=True, help="Project name")
@click.option("--name", default=None, help="Filter by function/agent name")
@click.option("--unscored", is_flag=True, default=False, help="Show only unscored runs")
@click.option("--failed", is_flag=True, default=False, help="Show only failed runs (with errors)")
@click.option("--last", "last_n", type=int, default=None, help="Show last N runs")
@click.option("--id", "run_id", default=None, help="Show full detail for one run")
@click.option("--summary", is_flag=True, default=False, help="Aggregated stats per agent + version")
def runs_cmd(
    project: str,
    name: Optional[str],
    unscored: bool,
    failed: bool,
    last_n: Optional[int],
    run_id: Optional[str],
    summary: bool,
) -> None:
    """View logged runs for a project."""
    db_path = _resolve_storage_path(project, None)
    if not db_path.exists():
        console.print(f"[red]No database found for project '{project}'.[/red]")
        raise SystemExit(1)

    if run_id:
        _show_run_detail(db_path, run_id)
        return

    if summary:
        _show_summary(db_path, project)
        return

    runs = store.get_runs(
        db_path,
        project=project,
        name=name,
        unscored_only=unscored,
        failed_only=failed,
        last_n=last_n,
    )

    if not runs:
        console.print("[dim]No runs found.[/dim]")
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("run_id", style="cyan", no_wrap=True)
    table.add_column("name")
    table.add_column("model", style="dim")
    table.add_column("temp", style="dim", justify="right")
    table.add_column("output", max_width=60)
    table.add_column("scored", justify="center")
    table.add_column("passed", justify="center")
    table.add_column("timestamp", style="dim")

    for run in runs:
        output_preview = ""
        if run.output:
            output_preview = run.output[:60] + ("..." if len(run.output) > 60 else "")

        scored_str = "[green]yes[/green]" if run.is_scored else "[dim]no[/dim]"
        if run.passed is True:
            passed_str = "[green]PASS[/green]"
        elif run.passed is False:
            passed_str = "[red]FAIL[/red]"
        else:
            passed_str = "[dim]-[/dim]"

        table.add_row(
            run.run_id,
            run.name,
            run.config.model or "-",
            str(run.config.temperature) if run.config.temperature is not None else "-",
            output_preview,
            scored_str,
            passed_str,
            run.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
        )

    console.print(table)


def _show_run_detail(db_path: Path, run_id: str) -> None:
    run = store.get_run(db_path, run_id)
    if run is None:
        console.print(f"[red]Run '{run_id}' not found.[/red]")
        raise SystemExit(1)

    console.rule()
    console.print(f"[bold]run_id[/bold]      : {run.run_id}")
    console.print(f"[bold]name[/bold]        : {run.name}")
    console.print(f"[bold]project[/bold]     : {run.project}")
    console.rule()
    console.print("[bold]config:[/bold]")
    console.print(f"  model       : {run.config.model or '-'}")
    console.print(f"  temperature : {run.config.temperature if run.config.temperature is not None else '-'}")
    console.print(f"  version     : {run.config.version or '-'}")
    if run.config.tags:
        console.print(f"  tags        : {run.config.tags}")
    console.rule()
    console.print("[bold]prompt:[/bold]")
    console.print(f"  {run.prompt or '[dim](none)[/dim]'}")
    console.rule()
    console.print("[bold]output:[/bold]")
    console.print(f"  {run.output or '[dim](none)[/dim]'}")
    console.rule()
    console.print("[bold]meta:[/bold]")
    console.print(f"  latency_ms  : {run.latency_ms:.1f}" if run.latency_ms is not None else "  latency_ms  : -")
    console.print(f"  timestamp   : {run.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
    console.print(f"  error       : {run.error or 'None'}")
    if run.feedback:
        console.rule()
        console.print("[bold]feedback:[/bold]")
        console.print(f"  score       : {run.feedback.score if run.feedback.score is not None else '-'}")
        console.print(f"  label       : {run.feedback.label or '-'}")
        console.print(f"  notes       : {run.feedback.notes or '-'}")
        given_at = run.feedback.feedback_given_at
        console.print(f"  given_at    : {given_at.strftime('%Y-%m-%d %H:%M:%S') if given_at else '-'}")
    console.rule()


def _show_summary(db_path: Path, project: str) -> None:
    rows = store.get_summary(db_path, project)
    if not rows:
        console.print("[dim]No runs found.[/dim]")
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("name")
    table.add_column("version", style="dim")
    table.add_column("total", justify="right")
    table.add_column("scored", justify="right")
    table.add_column("passed", justify="right", style="green")
    table.add_column("failed", justify="right", style="red")
    table.add_column("avg_score", justify="right")

    for row in rows:
        avg = row["avg_score"]
        table.add_row(
            row["name"],
            row["version"] or "-",
            str(row["total"]),
            str(row["scored"]),
            str(row["passed"]),
            str(row["failed"]),
            f"{avg:.2f}" if avg is not None else "-",
        )

    console.print(table)


# ---------------------------------------------------------------------------
# promptlog feedback
# ---------------------------------------------------------------------------


@app.command("feedback")
@click.argument("run_id")
@click.option("--project", required=True, help="Project name")
@click.option("--pass", "pass_flag", is_flag=True, default=False, help="Mark as PASS (score=1.0)")
@click.option("--fail", "fail_flag", is_flag=True, default=False, help="Mark as FAIL (score=0.0)")
@click.option("--score", type=float, default=None, help="Numeric score 0.0–1.0")
@click.option("--label", default=None, help="Label e.g. PASS FAIL PARTIAL")
@click.option("--notes", default=None, help="Free-text notes")
def feedback_cmd(
    run_id: str,
    project: str,
    pass_flag: bool,
    fail_flag: bool,
    score: Optional[float],
    label: Optional[str],
    notes: Optional[str],
) -> None:
    """Give feedback on a specific run."""
    db_path = _resolve_storage_path(project, None)
    if not db_path.exists():
        console.print(f"[red]No database found for project '{project}'.[/red]")
        raise SystemExit(1)

    run = store.get_run(db_path, run_id)
    if run is None:
        console.print(f"[red]Run '{run_id}' not found.[/red]")
        raise SystemExit(1)

    if run.is_scored:
        existing = run.feedback
        existing_label = existing.label or "-"
        existing_score = existing.score if existing.score is not None else "-"
        console.print(
            f"[yellow]Run '{run_id}' is already scored: "
            f"{existing_label} ({existing_score}). Overwrite? [y/n][/yellow]",
            end=" ",
        )
        answer = input().strip().lower()
        if answer != "y":
            console.print("[dim]Skipped.[/dim]")
            return

    # Resolve label from shorthand flags
    resolved_label = label
    resolved_score = score
    if pass_flag:
        resolved_label = "PASS"
        if resolved_score is None:
            resolved_score = 1.0
    elif fail_flag:
        resolved_label = "FAIL"
        if resolved_score is None:
            resolved_score = 0.0

    if resolved_score is None and resolved_label is None:
        console.print("[red]Provide at least one of: --pass, --fail, --score, --label.[/red]")
        raise SystemExit(1)

    feedback = FeedbackResult(
        score=resolved_score,
        label=resolved_label,
        notes=notes,
        feedback_given_at=datetime.utcnow(),
    )
    store.update_feedback(db_path, run_id, feedback)

    label_display = resolved_label or f"score={resolved_score}"
    console.print(f"[green]✓ {run_id} — marked {label_display}[/green]")


# ---------------------------------------------------------------------------
# promptlog review
# ---------------------------------------------------------------------------


@app.command("review")
@click.option("--project", required=True, help="Project name")
def review_cmd(project: str) -> None:
    """Interactively score all unscored runs."""
    db_path = _resolve_storage_path(project, None)
    if not db_path.exists():
        console.print(f"[red]No database found for project '{project}'.[/red]")
        raise SystemExit(1)

    unscored = store.get_runs(db_path, project=project, unscored_only=True)

    if not unscored:
        console.print("[dim]No unscored runs. Nothing to review.[/dim]")
        return

    total = len(unscored)
    scored_count = 0

    for i, run in enumerate(unscored, 1):
        console.rule(f"[bold]{i} / {total}[/bold]")
        console.print(f"[cyan]run_id[/cyan]  : {run.run_id}")
        console.print(f"[cyan]agent[/cyan]   : {run.name}")
        model_str = run.config.model or "-"
        temp_str = str(run.config.temperature) if run.config.temperature is not None else "-"
        version_str = run.config.version or "-"
        console.print(f"[cyan]model[/cyan]   : {model_str}  temp: {temp_str}  version: {version_str}")
        console.print()
        console.print(f"[cyan]prompt[/cyan]  : {run.prompt or '[dim](none)[/dim]'}")
        console.print()
        console.print(f"[cyan]output[/cyan]  : {run.output or '[dim](none)[/dim]'}")
        if run.error:
            console.print(f"[red]error[/red]   : {run.error}")
        console.print()
        console.print("[bold][[p] pass  [f] fail  [s] score  [n] skip  [q] quit][/bold]")

        while True:
            choice = click.prompt(">", default="n", prompt_suffix=" ").strip().lower()

            if choice == "q":
                console.print(f"\n[dim]Review stopped. {scored_count} runs scored.[/dim]")
                return

            elif choice == "n":
                break

            elif choice in ("p", "f"):
                label = "PASS" if choice == "p" else "FAIL"
                score_val = 1.0 if choice == "p" else 0.0
                fb = FeedbackResult(
                    score=score_val,
                    label=label,
                    feedback_given_at=datetime.utcnow(),
                )
                store.update_feedback(db_path, run.run_id, fb)
                console.print(f"[green]✓ Saved: {label}[/green]")
                scored_count += 1
                break

            elif choice == "s":
                score_val = click.prompt("  Score (0.0–1.0)", type=float)
                label_val = click.prompt("  Label (optional)", default="")
                notes_val = click.prompt("  Notes (optional)", default="")
                fb = FeedbackResult(
                    score=score_val,
                    label=label_val or None,
                    notes=notes_val or None,
                    feedback_given_at=datetime.utcnow(),
                )
                store.update_feedback(db_path, run.run_id, fb)
                console.print(f"[green]✓ Saved: score={score_val}[/green]")
                scored_count += 1
                break

            else:
                console.print("[red]Invalid choice. Use p, f, s, n, or q.[/red]")

    console.rule()
    console.print(f"[green]✓ Review complete. {scored_count} / {total} runs scored.[/green]")
