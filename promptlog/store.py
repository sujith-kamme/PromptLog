from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from promptlog.schema import FeedbackResult, PromptConfig, Run


# ---------------------------------------------------------------------------
# Internal guard — avoid re-running DDL on every decorated call
# ---------------------------------------------------------------------------

_initialized_dbs: set[Path] = set()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def init_db(db_path: Path) -> None:
    """Create the runs table if it doesn't exist. Idempotent."""
    if db_path in _initialized_dbs:
        return
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                run_id        TEXT PRIMARY KEY,
                name          TEXT NOT NULL,
                project       TEXT NOT NULL,
                prompt        TEXT,
                output        TEXT,
                config_json   TEXT NOT NULL,
                latency_ms    REAL,
                feedback_json TEXT,
                timestamp     TEXT NOT NULL,
                error         TEXT
            )
            """
        )
    _initialized_dbs.add(db_path)


def insert_run(db_path: Path, run: Run) -> None:
    """Persist a Run to the database."""
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO runs
                (run_id, name, project, prompt, output, config_json,
                 latency_ms, feedback_json, timestamp, error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run.run_id,
                run.name,
                run.project,
                run.prompt,
                run.output,
                run.config.model_dump_json(),
                run.latency_ms,
                run.feedback.model_dump_json() if run.feedback else None,
                run.timestamp.isoformat(),
                run.error,
            ),
        )


def update_feedback(db_path: Path, run_id: str, feedback: FeedbackResult) -> None:
    """Attach or overwrite feedback on an existing run."""
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE runs SET feedback_json = ? WHERE run_id = ?",
            (feedback.model_dump_json(), run_id),
        )


def get_run(db_path: Path, run_id: str) -> Optional[Run]:
    """Fetch a single run by run_id. Returns None if not found."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM runs WHERE run_id = ?", (run_id,)
        ).fetchone()
    return _row_to_run(row) if row else None


def get_runs(
    db_path: Path,
    project: str,
    name: Optional[str] = None,
    unscored_only: bool = False,
    failed_only: bool = False,
    last_n: Optional[int] = None,
) -> list[Run]:
    """Query runs with optional filters."""
    conditions = ["project = ?"]
    params: list = [project]

    if name:
        conditions.append("name = ?")
        params.append(name)
    if unscored_only:
        conditions.append("feedback_json IS NULL")
    if failed_only:
        conditions.append("error IS NOT NULL")

    where = " AND ".join(conditions)
    query = f"SELECT * FROM runs WHERE {where} ORDER BY timestamp DESC"

    if last_n is not None:
        query += " LIMIT ?"
        params.append(last_n)

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, params).fetchall()

    return [_row_to_run(r) for r in rows]


def delete_run(db_path: Path, run_id: str) -> None:
    """Delete a single run by run_id."""
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM runs WHERE run_id = ?", (run_id,))


def get_summary(db_path: Path, project: str) -> list[dict]:
    """
    Aggregate stats per (name, version) group.
    Returns a list of dicts with: name, version, total, scored, passed, failed, avg_score.
    """
    runs = get_runs(db_path, project=project)

    groups: dict[tuple[str, Optional[str]], list[Run]] = {}
    for run in runs:
        key = (run.name, run.config.version)
        groups.setdefault(key, []).append(run)

    result = []
    for (name, version), group_runs in groups.items():
        scored = [r for r in group_runs if r.is_scored]
        passed = [r for r in scored if r.passed is True]
        failed = [r for r in scored if r.passed is False]
        scores = [
            r.feedback.score
            for r in scored
            if r.feedback and r.feedback.score is not None
        ]
        result.append(
            {
                "name": name,
                "version": version,
                "total": len(group_runs),
                "scored": len(scored),
                "passed": len(passed),
                "failed": len(failed),
                "avg_score": sum(scores) / len(scores) if scores else None,
            }
        )

    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _row_to_run(row: sqlite3.Row) -> Run:
    return Run(
        run_id=row["run_id"],
        name=row["name"],
        project=row["project"],
        prompt=row["prompt"],
        output=row["output"],
        config=PromptConfig.model_validate_json(row["config_json"]),
        latency_ms=row["latency_ms"],
        feedback=(
            FeedbackResult.model_validate_json(row["feedback_json"])
            if row["feedback_json"]
            else None
        ),
        timestamp=datetime.fromisoformat(row["timestamp"]),
        error=row["error"],
    )
