"""Tests for store.py — SQLite persistence layer."""
from datetime import datetime
from pathlib import Path

import pytest

from promptlog.schema import FeedbackResult, PromptConfig, Run
from promptlog import store


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_path(tmp_path) -> Path:
    path = tmp_path / "test.db"
    store.init_db(path)
    # Clear the init guard so each test gets a fresh init if needed
    store._initialized_dbs.discard(path)
    store.init_db(path)
    return path


def make_run(
    name: str = "agent",
    project: str = "proj",
    prompt: str = None,
    output: str = None,
    error: str = None,
    feedback: FeedbackResult = None,
    **kwargs,
) -> Run:
    cfg = PromptConfig(name=name, project=project)
    return Run(
        name=name,
        project=project,
        config=cfg,
        prompt=prompt,
        output=output,
        error=error,
        feedback=feedback,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# init_db
# ---------------------------------------------------------------------------


def test_init_db_creates_runs_table(db_path):
    import sqlite3
    with sqlite3.connect(db_path) as conn:
        result = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='runs'"
        ).fetchone()
    assert result is not None


def test_init_db_is_idempotent(db_path):
    # Calling again should not raise
    store.init_db(db_path)


# ---------------------------------------------------------------------------
# insert_run / get_run round-trip
# ---------------------------------------------------------------------------


def test_insert_and_get_run(db_path):
    run = make_run(name="classify", project="movie", prompt="hello", output="POSITIVE")
    store.insert_run(db_path, run)

    retrieved = store.get_run(db_path, run.run_id)
    assert retrieved is not None
    assert retrieved.run_id == run.run_id
    assert retrieved.name == "classify"
    assert retrieved.project == "movie"
    assert retrieved.prompt == "hello"
    assert retrieved.output == "POSITIVE"


def test_get_run_preserves_config(db_path):
    cfg = PromptConfig(name="agent", project="proj", model="gpt-4o", temperature=0.1)
    run2 = Run(name="agent", project="proj", config=cfg)
    store.insert_run(db_path, run2)

    retrieved = store.get_run(db_path, run2.run_id)
    assert retrieved.config.model == "gpt-4o"
    assert retrieved.config.temperature == 0.1


def test_get_run_with_feedback(db_path):
    fb = FeedbackResult(score=1.0, label="PASS", notes="Good")
    run = make_run(feedback=fb)
    store.insert_run(db_path, run)

    retrieved = store.get_run(db_path, run.run_id)
    assert retrieved.feedback is not None
    assert retrieved.feedback.score == 1.0
    assert retrieved.feedback.label == "PASS"
    assert retrieved.feedback.notes == "Good"


def test_get_run_with_error(db_path):
    run = make_run(error="ValueError: something went wrong")
    store.insert_run(db_path, run)

    retrieved = store.get_run(db_path, run.run_id)
    assert retrieved.error == "ValueError: something went wrong"


def test_get_run_nonexistent_returns_none(db_path):
    result = store.get_run(db_path, "doesnotexist")
    assert result is None


def test_run_timestamp_preserved(db_path):
    ts = datetime(2026, 1, 15, 10, 30, 0)
    run = make_run()
    # Override timestamp by creating Run with fixed timestamp
    cfg = PromptConfig(name="agent", project="proj")
    run2 = Run(name="agent", project="proj", config=cfg, timestamp=ts)
    store.insert_run(db_path, run2)

    retrieved = store.get_run(db_path, run2.run_id)
    assert retrieved.timestamp == ts


# ---------------------------------------------------------------------------
# update_feedback
# ---------------------------------------------------------------------------


def test_update_feedback(db_path):
    run = make_run()
    store.insert_run(db_path, run)

    fb = FeedbackResult(score=0.8, label="PARTIAL", notes="Close")
    store.update_feedback(db_path, run.run_id, fb)

    retrieved = store.get_run(db_path, run.run_id)
    assert retrieved.feedback is not None
    assert retrieved.feedback.score == 0.8
    assert retrieved.feedback.label == "PARTIAL"


def test_update_feedback_overwrites_existing(db_path):
    fb1 = FeedbackResult(label="FAIL")
    run = make_run(feedback=fb1)
    store.insert_run(db_path, run)

    fb2 = FeedbackResult(label="PASS", score=1.0)
    store.update_feedback(db_path, run.run_id, fb2)

    retrieved = store.get_run(db_path, run.run_id)
    assert retrieved.feedback.label == "PASS"


# ---------------------------------------------------------------------------
# get_runs filters
# ---------------------------------------------------------------------------


def test_get_runs_filter_by_project(db_path):
    r1 = make_run(project="proj_a")
    r2 = make_run(project="proj_b")
    store.insert_run(db_path, r1)
    store.insert_run(db_path, r2)

    results = store.get_runs(db_path, project="proj_a")
    assert len(results) == 1
    assert results[0].project == "proj_a"


def test_get_runs_filter_by_name(db_path):
    r1 = make_run(name="classify", project="proj")
    r2 = make_run(name="summarize", project="proj")
    store.insert_run(db_path, r1)
    store.insert_run(db_path, r2)

    results = store.get_runs(db_path, project="proj", name="classify")
    assert len(results) == 1
    assert results[0].name == "classify"


def test_get_runs_unscored_only(db_path):
    r1 = make_run(project="proj")
    r2 = make_run(project="proj", feedback=FeedbackResult(label="PASS"))
    store.insert_run(db_path, r1)
    store.insert_run(db_path, r2)

    results = store.get_runs(db_path, project="proj", unscored_only=True)
    assert len(results) == 1
    assert results[0].run_id == r1.run_id


def test_get_runs_failed_only(db_path):
    r1 = make_run(project="proj")
    r2 = make_run(project="proj", error="SomeError: boom")
    store.insert_run(db_path, r1)
    store.insert_run(db_path, r2)

    results = store.get_runs(db_path, project="proj", failed_only=True)
    assert len(results) == 1
    assert results[0].error is not None


def test_get_runs_last_n(db_path):
    for i in range(5):
        store.insert_run(db_path, make_run(project="proj", output=str(i)))

    results = store.get_runs(db_path, project="proj", last_n=2)
    assert len(results) == 2


def test_get_runs_returns_empty_list_for_no_matches(db_path):
    results = store.get_runs(db_path, project="nonexistent")
    assert results == []


# ---------------------------------------------------------------------------
# get_summary
# ---------------------------------------------------------------------------


def test_get_summary_basic(db_path):
    cfg = PromptConfig(name="classify", project="proj")
    for _ in range(3):
        store.insert_run(db_path, Run(name="classify", project="proj", config=cfg))

    summary = store.get_summary(db_path, "proj")
    assert len(summary) == 1
    row = summary[0]
    assert row["name"] == "classify"
    assert row["total"] == 3
    assert row["scored"] == 0
    assert row["passed"] == 0
    assert row["failed"] == 0
    assert row["avg_score"] is None


def test_get_summary_with_scored_runs(db_path):
    cfg = PromptConfig(name="agent", project="proj")

    r1 = Run(name="agent", project="proj", config=cfg, feedback=FeedbackResult(label="PASS", score=1.0))
    r2 = Run(name="agent", project="proj", config=cfg, feedback=FeedbackResult(label="FAIL", score=0.0))
    r3 = Run(name="agent", project="proj", config=cfg)

    store.insert_run(db_path, r1)
    store.insert_run(db_path, r2)
    store.insert_run(db_path, r3)

    summary = store.get_summary(db_path, "proj")
    row = summary[0]
    assert row["total"] == 3
    assert row["scored"] == 2
    assert row["passed"] == 1
    assert row["failed"] == 1
    assert row["avg_score"] == pytest.approx(0.5)


def test_get_summary_groups_by_name_and_version(db_path):
    cfg_a = PromptConfig(name="agent", project="proj", prompt_template="template A")
    cfg_b = PromptConfig(name="agent", project="proj", prompt_template="template B")

    store.insert_run(db_path, Run(name="agent", project="proj", config=cfg_a))
    store.insert_run(db_path, Run(name="agent", project="proj", config=cfg_b))
    store.insert_run(db_path, Run(name="agent", project="proj", config=cfg_a))

    summary = store.get_summary(db_path, "proj")
    assert len(summary) == 2
    totals = {row["version"]: row["total"] for row in summary}
    assert totals[cfg_a.version] == 2
    assert totals[cfg_b.version] == 1
