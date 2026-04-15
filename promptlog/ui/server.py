"""PromptLog Web Dashboard - FastAPI Backend"""

import json
import csv
import io
from pathlib import Path
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from promptlog.config import _resolve_storage_path
from promptlog.schema import FeedbackResult
from promptlog import store


# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------


app = FastAPI(title="PromptLog Dashboard")

# Mount static files - path relative to where server is run from
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


# ---------------------------------------------------------------------------
# Pydantic Models for Request/Response
# ---------------------------------------------------------------------------


class FeedbackRequest(BaseModel):
    score: Optional[float] = None
    label: Optional[str] = None
    notes: Optional[str] = None


class ProjectInfo(BaseModel):
    name: str
    run_count: int
    db_path: str


class RunsResponse(BaseModel):
    runs: list[dict]
    total: int
    filtered: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_all_projects() -> list[ProjectInfo]:
    """Scan ~/.promptlog/ and ./.promptlog/ for all projects."""
    global_dir = Path.home() / ".promptlog"
    local_dir = Path.cwd() / ".promptlog"

    db_paths = []
    if global_dir.exists():
        db_paths.extend(global_dir.glob("*.db"))
    if local_dir.exists() and local_dir.resolve() != global_dir.resolve():
        db_paths.extend(local_dir.glob("*.db"))

    projects = []
    for db_file in db_paths:
        project_name = db_file.stem
        try:
            runs = store.get_runs(db_file, project=project_name)
            projects.append(ProjectInfo(
                name=project_name,
                run_count=len(runs),
                db_path=str(db_file),
            ))
        except Exception:
            continue  # Skip corrupted DBs

    return sorted(projects, key=lambda p: p.name)


def _run_to_dict(run) -> dict:
    """Convert Run object to dict for JSON response."""
    return {
        "run_id": run.run_id,
        "session_id": run.session_id,
        "parent_run_id": run.parent_run_id,
        "name": run.name,
        "project": run.project,
        "model": run.config.model,
        "temperature": run.config.temperature,
        "version": run.config.version,
        "prompt": run.prompt,
        "output": run.output,
        "latency_ms": run.latency_ms,
        "is_scored": run.is_scored,
        "feedback_score": run.feedback.score if run.feedback else None,
        "feedback_label": run.feedback.label if run.feedback else None,
        "feedback_notes": run.feedback.notes if run.feedback else None,
        "passed": run.passed,
        "timestamp": run.timestamp.isoformat(),
        "error": run.error,
    }


# ---------------------------------------------------------------------------
# HTML Routes
# ---------------------------------------------------------------------------


@app.get("/")
async def index():
    """Serve the main HTML page."""
    index_path = static_dir / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="index.html not found")
    return FileResponse(index_path)


# ---------------------------------------------------------------------------
# API Routes - Projects
# ---------------------------------------------------------------------------


@app.get("/api/projects")
async def list_projects():
    """List all known projects."""
    projects = _get_all_projects()
    return [p.model_dump() for p in projects]


@app.get("/api/projects/{project_name}")
async def get_project(project_name: str):
    """Get project metadata and summary stats."""
    db_path = _resolve_storage_path(project_name, None)
    if not db_path.exists():
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found")

    runs = store.get_runs(db_path, project=project_name)

    total_runs = len(runs)
    scored_runs = sum(1 for r in runs if r.is_scored)
    passed_runs = sum(1 for r in runs if r.passed is True)
    failed_runs = sum(1 for r in runs if r.passed is False)

    return {
        "name": project_name,
        "db_path": str(db_path),
        "total_runs": total_runs,
        "scored_runs": scored_runs,
        "passed_runs": passed_runs,
        "failed_runs": failed_runs,
        "pass_rate": passed_runs / scored_runs if scored_runs > 0 else None,
        "versions": list(set(r.config.version for r in runs if r.config.version)),
        "models": list(set(r.config.model for r in runs if r.config.model)),
    }


# ---------------------------------------------------------------------------
# API Routes - Runs
# ---------------------------------------------------------------------------


@app.get("/api/projects/{project_name}/runs")
async def list_runs(
    project_name: str,
    unscored: bool = False,
    failed: bool = False,
    version: Optional[str] = None,
    model: Optional[str] = None,
    name: Optional[str] = None,
    last: Optional[int] = None,
    search: Optional[str] = None,
):
    """List runs with optional filters."""
    db_path = _resolve_storage_path(project_name, None)
    if not db_path.exists():
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found")

    # Get filtered runs from store
    runs = store.get_runs(
        db_path,
        project=project_name,
        name=name,
        unscored_only=unscored,
        failed_only=failed,
        last_n=last,
    )

    # Additional client-side filters
    if version:
        runs = [r for r in runs if r.config.version == version]
    if model:
        runs = [r for r in runs if r.config.model == model]
    if search:
        search_lower = search.lower()
        runs = [
            r for r in runs
            if (r.prompt and search_lower in r.prompt.lower())
            or (r.output and search_lower in r.output.lower())
        ]

    # Sort by timestamp descending for API response
    runs.sort(key=lambda r: r.timestamp, reverse=True)

    return {
        "runs": [_run_to_dict(r) for r in runs],
        "total": len(runs),
        "filtered": len(runs),
    }


@app.get("/api/projects/{project_name}/runs/{run_id}")
async def get_run(project_name: str, run_id: str):
    """Get a single run by ID."""
    db_path = _resolve_storage_path(project_name, None)
    if not db_path.exists():
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found")

    run = store.get_run(db_path, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    # Fetch children for this run
    all_runs = store.get_runs(db_path, project=project_name)
    children = [r for r in all_runs if r.parent_run_id == run_id]

    # Fetch parent if exists
    parent = None
    if run.parent_run_id:
        parent = store.get_run(db_path, run.parent_run_id)

    return {
        "run": _run_to_dict(run),
        "parent": _run_to_dict(parent) if parent else None,
        "children": [_run_to_dict(c) for c in children],
    }


@app.delete("/api/runs/{run_id}")
async def delete_run(run_id: str, project: str):
    """Delete a run by ID."""
    db_path = _resolve_storage_path(project, None)
    if not db_path.exists():
        raise HTTPException(status_code=404, detail=f"Project '{project}' not found")

    run = store.get_run(db_path, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    store.delete_run(db_path, run_id)
    return {"status": "ok", "deleted": run_id}


# ---------------------------------------------------------------------------
# API Routes - Feedback
# ---------------------------------------------------------------------------


@app.put("/api/runs/{run_id}/feedback")
async def update_feedback(run_id: str, feedback: FeedbackRequest):
    """Update feedback for a run."""
    # Find the project for this run - scan all projects
    projects = _get_all_projects()
    db_path = None

    for proj in projects:
        proj_db = Path(proj.db_path)
        run = store.get_run(proj_db, run_id)
        if run:
            db_path = proj_db
            break

    if db_path is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found in any project")

    feedback_result = FeedbackResult(
        score=feedback.score,
        label=feedback.label,
        notes=feedback.notes,
        feedback_given_at=datetime.utcnow(),
        feedback_by="human",
    )

    store.update_feedback(db_path, run_id, feedback_result)

    # Return updated run
    run = store.get_run(db_path, run_id)
    return _run_to_dict(run)


# ---------------------------------------------------------------------------
# API Routes - Stats
# ---------------------------------------------------------------------------


@app.get("/api/projects/{project_name}/stats")
async def get_stats(project_name: str):
    """Get aggregated stats per (name, version) group."""
    db_path = _resolve_storage_path(project_name, None)
    if not db_path.exists():
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found")

    summary = store.get_summary(db_path, project=project_name)
    return {"stats": summary}


# ---------------------------------------------------------------------------
# API Routes - Export
# ---------------------------------------------------------------------------


@app.get("/api/projects/{project_name}/export/csv")
async def export_csv(project_name: str):
    """Export all runs as CSV."""
    db_path = _resolve_storage_path(project_name, None)
    if not db_path.exists():
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found")

    runs = store.get_runs(db_path, project=project_name)
    rows = [r.summary() for r in runs]

    output = io.StringIO()
    if rows:
        writer = csv.DictWriter(output, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={project_name}_runs.csv"},
    )


@app.get("/api/projects/{project_name}/export/json")
async def export_json(project_name: str):
    """Export all runs as JSON."""
    db_path = _resolve_storage_path(project_name, None)
    if not db_path.exists():
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found")

    runs = store.get_runs(db_path, project=project_name)
    rows = [_run_to_dict(r) for r in runs]

    return Response(
        content=json.dumps(rows, indent=2, default=str),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename={project_name}_runs.json"},
    )


# ---------------------------------------------------------------------------
# Main entry point for uvicorn
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
