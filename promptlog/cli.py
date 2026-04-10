from __future__ import annotations

import csv
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import click
from rich.console import Console, Group
from rich.table import Table
from rich.panel import Panel
from rich.markdown import Markdown
from rich import box

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
# promptlog ls
# ---------------------------------------------------------------------------


@app.command("ls")
@click.option("--project", required=True, help="Project name")
@click.option("--name", default=None, help="Filter by function/task name")
@click.option("--unscored", is_flag=True, default=False, help="Show only unscored runs")
@click.option("--failed", is_flag=True, default=False, help="Show only failed runs (with errors)")
@click.option("--last", "last_n", type=int, default=None, help="Show last N runs")
def ls_cmd(
    project: str,
    name: Optional[str],
    unscored: bool,
    failed: bool,
    last_n: Optional[int],
) -> None:
    """List logged runs for a project."""
    db_path = _resolve_storage_path(project, None)
    if not db_path.exists():
        console.print(f"[red]No database found for project '{project}'.[/red]")
        raise SystemExit(1)

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
    table.add_column("prompt", max_width=40)
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

        prompt_preview = "-"
        if run.prompt:
            prompt_preview = run.prompt[:40] + ("..." if len(run.prompt) > 40 else "")

        table.add_row(
            run.run_id,
            run.name,
            run.config.model or "-",
            str(run.config.temperature) if run.config.temperature is not None else "-",
            prompt_preview,
            output_preview,
            scored_str,
            passed_str,
            run.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
        )

    console.print(table)


# ---------------------------------------------------------------------------
# promptlog view
# ---------------------------------------------------------------------------


@app.command("view")
@click.argument("run_id")
@click.option("--project", required=True, help="Project name")
def view_cmd(run_id: str, project: str) -> None:
    """View full detail for a specific run."""
    db_path = _resolve_storage_path(project, None)
    if not db_path.exists():
        console.print(f"[red]No database found for project '{project}'.[/red]")
        raise SystemExit(1)
    _show_run_detail(db_path, run_id)


def _show_run_detail(db_path: Path, run_id: str) -> None:
    run = store.get_run(db_path, run_id)
    if run is None:
        console.print(f"[red]Run '{run_id}' not found.[/red]")
        raise SystemExit(1)

    details = f"Task     : {run.name:<21} Project : {run.project}\n"
    details += f"Model    : {run.config.model or '-':<21} Temp    : {run.config.temperature if run.config.temperature is not None else '-':<9}"
    if run.latency_ms is not None:
        details += f" Latency : {run.latency_ms:.1f}ms"
    if run.config.version:
        details += f"\nVersion  : {run.config.version}"

    table = Table(box=box.ROUNDED, show_header=True, header_style="bold", show_lines=True, width=100)
    table.add_column(f"Run Profile: {run.run_id}", no_wrap=False)

    table.add_row(details)

    prompt_str = run.prompt or "[dim](none)[/dim]"
    table.add_row(f"[bold cyan]Prompt[/bold cyan]\n{prompt_str}")

    if run.error:
        table.add_row(f"[bold red]Error[/bold red]\n{run.error}")
    else:
        table.add_row(Group("[bold green]Output[/bold green]", Markdown(run.output or "(none)")))

    if run.feedback:
        fb = run.feedback

        display_label = fb.label
        if not display_label:
            if run.passed is True:
                display_label = "PASS"
            elif run.passed is False:
                display_label = "FAIL"
            else:
                display_label = "-"

        fb_text = f"Status   : {display_label} [{fb.score if fb.score is not None else '-'}]"
        if fb.notes:
            fb_text += f"\nNotes    : {fb.notes}"
        table.add_row(Group("[bold yellow]Feedback[/bold yellow]", fb_text))

    console.print(table)


# ---------------------------------------------------------------------------
# promptlog stats
# ---------------------------------------------------------------------------


@app.command("stats")
@click.option("--project", required=True, help="Project name")
def stats_cmd(project: str) -> None:
    """View aggregated pass rates and average scores per task."""
    db_path = _resolve_storage_path(project, None)
    if not db_path.exists():
        console.print(f"[red]No database found for project '{project}'.[/red]")
        raise SystemExit(1)
    _show_summary(db_path, project)


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
# promptlog rescore
# ---------------------------------------------------------------------------


@app.command("rescore")
@click.argument("run_id")
@click.option("--project", required=True, help="Project name")
@click.option("--pass", "pass_flag", is_flag=True, default=False, help="Mark as PASS (score=1.0)")
@click.option("--fail", "fail_flag", is_flag=True, default=False, help="Mark as FAIL (score=0.0)")
@click.option("--score", type=float, default=None, help="Numeric score 0.0–1.0")
@click.option("--label", default=None, help="Label e.g. PASS FAIL PARTIAL")
@click.option("--notes", default=None, help="Free-text notes")
def rescore_cmd(
    run_id: str,
    project: str,
    pass_flag: bool,
    fail_flag: bool,
    score: Optional[float],
    label: Optional[str],
    notes: Optional[str],
) -> None:
    """Manually score or update feedback for a specific run."""
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
# promptlog export
# ---------------------------------------------------------------------------


@app.command("export")
@click.option("--project", required=True, help="Project name")
@click.option(
    "--format", "fmt",
    type=click.Choice(["csv", "json"]),
    default="csv",
    show_default=True,
    help="Output format",
)
@click.option("--output", "output_path", default=None, help="File path to write (default: stdout)")
def export_cmd(project: str, fmt: str, output_path: Optional[str]) -> None:
    """Export all runs for a project to CSV or JSON."""
    db_path = _resolve_storage_path(project, None)
    if not db_path.exists():
        console.print(f"[red]No database found for project '{project}'.[/red]")
        raise SystemExit(1)

    runs = store.get_runs(db_path, project=project)
    if not runs:
        console.print("[dim]No runs found.[/dim]")
        return

    rows = [r.summary() for r in runs]

    dest = open(output_path, "w", newline="") if output_path else sys.stdout

    try:
        if fmt == "csv":
            writer = csv.DictWriter(dest, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        else:
            json.dump(rows, dest, indent=2, default=str)
            dest.write("\n")
    finally:
        if output_path:
            dest.close()

    if output_path:
        console.print(f"[green]✓ Exported {len(rows)} runs to {output_path}[/green]")


# ---------------------------------------------------------------------------
# promptlog projects
# ---------------------------------------------------------------------------


@app.command("projects")
def projects_cmd() -> None:
    """List all known projects."""
    storage_dir = Path.home() / ".promptlog"
    db_files = sorted(storage_dir.glob("*.db")) if storage_dir.exists() else []

    if not db_files:
        console.print("[dim]No projects found in ~/.promptlog/[/dim]")
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("project", style="cyan")
    table.add_column("runs", justify="right")
    table.add_column("db_path", style="dim")

    for db_file in db_files:
        project_name = db_file.stem
        runs = store.get_runs(db_file, project=project_name)
        table.add_row(project_name, str(len(runs)), str(db_file))

    console.print(table)


# ---------------------------------------------------------------------------
# promptlog delete
# ---------------------------------------------------------------------------


@app.command("delete")
@click.argument("run_id")
@click.option("--project", required=True, help="Project name")
@click.option("--yes", "-y", is_flag=True, default=False, help="Skip confirmation prompt")
def delete_cmd(run_id: str, project: str, yes: bool) -> None:
    """Delete a specific run."""
    db_path = _resolve_storage_path(project, None)
    if not db_path.exists():
        console.print(f"[red]No database found for project '{project}'.[/red]")
        raise SystemExit(1)

    run = store.get_run(db_path, run_id)
    if run is None:
        console.print(f"[red]Run '{run_id}' not found.[/red]")
        raise SystemExit(1)

    if not yes:
        console.print(
            f"[yellow]Delete run '{run_id}' (task: {run.name}, "
            f"{run.timestamp.strftime('%Y-%m-%d %H:%M:%S')})? [y/n][/yellow]",
            end=" ",
        )
        answer = input().strip().lower()
        if answer != "y":
            console.print("[dim]Cancelled.[/dim]")
            return

    store.delete_run(db_path, run_id)
    console.print(f"[green]✓ Deleted {run_id}[/green]")


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
    run_interactive_review(db_path, project)


def run_interactive_review(
    db_path: Path,
    project: str,
    session_run_ids: Optional[list[str]] = None,
    compact: bool = False,
) -> None:
    """Core interactive review loop. Called by review_cmd and the atexit handler.

    session_run_ids: when provided (atexit path), only review runs from this session.
    compact: when True, skip panels and show a single inline prompt line instead.
    """
    unscored = store.get_runs(db_path, project=project, unscored_only=True)

    if session_run_ids is not None:
        session_set = set(session_run_ids)
        unscored = [r for r in unscored if r.run_id in session_set]

    if not unscored:
        console.print("[dim]No unscored runs. Nothing to review.[/dim]")
        return

    total = len(unscored)
    scored_count = 0

    for i, run in enumerate(unscored, 1):
        if compact:
            console.print(
                f"\nRate output task [bold cyan]\"{run.name}\"[/bold cyan]:\n"
                f"> [bold][ (p)ass | (f)ail | (s)core | (n)skip | (q)uit ][/bold]",
                end=" ",
            )
        else:
            console.rule(f"[bold dim]{i} / {total}[/bold dim]")

            prompt_panel = Panel(
                run.prompt or "(none)",
                title="[bold cyan]Prompt[/bold cyan]",
                title_align="left",
                border_style="cyan",
                subtitle=f"[dim]id: {run.run_id} | task: {run.name}[/dim]",
                subtitle_align="right",
            )
            console.print(prompt_panel)

            if run.error:
                console.print(Panel(
                    str(run.error),
                    title="[bold red]Error[/bold red]",
                    title_align="left",
                    border_style="red",
                ))
            else:
                model_str = run.config.model or "unknown"
                temp_str = str(run.config.temperature) if run.config.temperature is not None else "-"
                console.print(Panel(
                    Markdown(run.output or "(none)"),
                    title="[bold green]Output[/bold green]",
                    title_align="left",
                    border_style="green",
                    subtitle=f"[dim]{model_str} | temp: {temp_str}[/dim]",
                    subtitle_align="right",
                ))

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
