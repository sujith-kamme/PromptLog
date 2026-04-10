"""Tests for tracker.py — @pl.track decorator and context helpers."""
from pathlib import Path

import pytest

from promptlog import config, store
import promptlog as pl


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_config():
    """Isolate each test from global config state."""
    config.reset()
    yield
    config.reset()


@pytest.fixture
def db_path(tmp_path) -> Path:
    return tmp_path / "test.db"


@pytest.fixture
def initialized(tmp_path) -> config.PromptLogConfig:
    return pl.init(project="test_proj", storage_path=str(tmp_path / "test.db"))


# ---------------------------------------------------------------------------
# Guard: pl.init() required
# ---------------------------------------------------------------------------


def test_track_raises_if_not_initialized():
    @pl.track(model="gpt-4o")
    def my_func(x: str) -> str:
        return x

    with pytest.raises(RuntimeError, match="not initialized"):
        my_func("hello")


# ---------------------------------------------------------------------------
# enabled=False no-op
# ---------------------------------------------------------------------------


def test_track_noop_when_disabled(tmp_path):
    cfg = pl.init(project="p", storage_path=str(tmp_path / "t.db"), enabled=False)

    @pl.track(model="gpt-4o")
    def my_func() -> str:
        return "result"

    result = my_func()
    assert result == "result"

    # Nothing should be written to DB
    assert not cfg.storage_path.exists() or store.get_runs(cfg.storage_path, project="p") == []


# ---------------------------------------------------------------------------
# Basic tracking
# ---------------------------------------------------------------------------


def test_track_saves_run(initialized):
    @pl.track(model="gpt-4o")
    def my_func() -> str:
        return "hello"

    my_func()

    runs = store.get_runs(initialized.storage_path, project="test_proj")
    assert len(runs) == 1
    assert runs[0].output == "hello"
    assert runs[0].name == "my_func"


def test_track_captures_return_value(initialized):
    @pl.track()
    def greet(name: str) -> str:
        return f"Hello, {name}!"

    greet("world")

    runs = store.get_runs(initialized.storage_path, project="test_proj")
    assert runs[0].output == "Hello, world!"


def test_track_captures_latency(initialized):
    @pl.track()
    def my_func() -> str:
        return "done"

    my_func()

    runs = store.get_runs(initialized.storage_path, project="test_proj")
    assert runs[0].latency_ms is not None
    assert runs[0].latency_ms >= 0


def test_track_captures_timestamp(initialized):
    from datetime import datetime

    @pl.track()
    def my_func() -> str:
        return "done"

    before = datetime.utcnow()
    my_func()
    after = datetime.utcnow()

    runs = store.get_runs(initialized.storage_path, project="test_proj")
    assert before <= runs[0].timestamp <= after


# ---------------------------------------------------------------------------
# Custom name
# ---------------------------------------------------------------------------


def test_track_custom_name(initialized):
    @pl.track(name="my_custom_agent")
    def func() -> str:
        return "ok"

    func()

    runs = store.get_runs(initialized.storage_path, project="test_proj")
    assert runs[0].name == "my_custom_agent"


# ---------------------------------------------------------------------------
# Config propagation
# ---------------------------------------------------------------------------


def test_track_model_propagated(initialized):
    @pl.track(model="claude-sonnet-4-6")
    def func() -> str:
        return "ok"

    func()

    runs = store.get_runs(initialized.storage_path, project="test_proj")
    assert runs[0].config.model == "claude-sonnet-4-6"


def test_track_temperature_propagated(initialized):
    @pl.track(temperature=0.3)
    def func() -> str:
        return "ok"

    func()

    runs = store.get_runs(initialized.storage_path, project="test_proj")
    assert runs[0].config.temperature == 0.3


def test_track_temperature_zero_preserved(initialized):
    """temperature=0.0 is valid and must not be treated as falsy."""
    @pl.track(temperature=0.0)
    def func() -> str:
        return "ok"

    func()

    runs = store.get_runs(initialized.storage_path, project="test_proj")
    assert runs[0].config.temperature == 0.0


# ---------------------------------------------------------------------------
# Config resolution order
# ---------------------------------------------------------------------------


def test_track_explicit_param_beats_config_dict(tmp_path):
    pl.init(project="p", storage_path=str(tmp_path / "t.db"))

    @pl.track(model="explicit-model", config={"model": "dict-model"})
    def func() -> str:
        return "ok"

    func()

    runs = store.get_runs(tmp_path / "t.db", project="p")
    assert runs[0].config.model == "explicit-model"


def test_track_config_dict_beats_defaults(tmp_path):
    pl.init(project="p", storage_path=str(tmp_path / "t.db"), default_model="default-model")

    @pl.track(config={"model": "dict-model"})
    def func() -> str:
        return "ok"

    func()

    runs = store.get_runs(tmp_path / "t.db", project="p")
    assert runs[0].config.model == "dict-model"


def test_track_defaults_from_init(tmp_path):
    pl.init(project="p", storage_path=str(tmp_path / "t.db"), default_model="default-model")

    @pl.track()
    def func() -> str:
        return "ok"

    func()

    runs = store.get_runs(tmp_path / "t.db", project="p")
    assert runs[0].config.model == "default-model"


# ---------------------------------------------------------------------------
# Tags merging
# ---------------------------------------------------------------------------


def test_track_tags_merged_with_global_defaults(tmp_path):
    pl.init(project="p", storage_path=str(tmp_path / "t.db"), default_tags={"env": "dev"})

    @pl.track(tags={"experiment": "v2"})
    def func() -> str:
        return "ok"

    func()

    runs = store.get_runs(tmp_path / "t.db", project="p")
    assert runs[0].config.tags == {"env": "dev", "experiment": "v2"}


def test_track_decorator_tags_override_global(tmp_path):
    pl.init(project="p", storage_path=str(tmp_path / "t.db"), default_tags={"env": "dev"})

    @pl.track(tags={"env": "prod"})
    def func() -> str:
        return "ok"

    func()

    runs = store.get_runs(tmp_path / "t.db", project="p")
    assert runs[0].config.tags["env"] == "prod"


# ---------------------------------------------------------------------------
# log_prompt
# ---------------------------------------------------------------------------


def test_log_prompt_captured(initialized):
    @pl.track()
    def func(text: str) -> str:
        pl.log_prompt(f"Classify: {text}")
        return "POSITIVE"

    func("Her is a masterpiece.")

    runs = store.get_runs(initialized.storage_path, project="test_proj")
    assert runs[0].prompt == "Classify: Her is a masterpiece."


def test_log_prompt_outside_track_raises():
    with pytest.raises(RuntimeError, match="outside a @pl.track"):
        pl.log_prompt("hello")


# ---------------------------------------------------------------------------
# Auto-capture prompt from string args
# ---------------------------------------------------------------------------


def test_auto_capture_prompt_from_positional_args(initialized):
    @pl.track()
    def func(_review: str) -> str:
        return "POSITIVE"

    func("Her is a masterpiece.")

    runs = store.get_runs(initialized.storage_path, project="test_proj")
    assert runs[0].prompt == "Her is a masterpiece."


def test_auto_capture_prompt_from_kwargs(initialized):
    @pl.track()
    def func(_review: str) -> str:
        return "POSITIVE"

    func(_review="Her is a masterpiece.")

    runs = store.get_runs(initialized.storage_path, project="test_proj")
    assert runs[0].prompt == "Her is a masterpiece."


def test_auto_capture_skips_non_string_args(initialized):
    @pl.track()
    def func(_count: int) -> str:
        return "done"

    func(42)

    runs = store.get_runs(initialized.storage_path, project="test_proj")
    assert runs[0].prompt is None


def test_log_prompt_overrides_auto_capture(initialized):
    @pl.track()
    def func(_raw: str) -> str:
        pl.log_prompt("explicit prompt")
        return "ok"

    func("should be ignored")

    runs = store.get_runs(initialized.storage_path, project="test_proj")
    assert runs[0].prompt == "explicit prompt"


# ---------------------------------------------------------------------------
# log_feedback
# ---------------------------------------------------------------------------


def test_log_feedback_captured(initialized):
    @pl.track()
    def func(expected: str) -> str:
        result = "POSITIVE"
        pl.log_feedback(
            score=1.0 if result == expected else 0.0,
            label="PASS" if result == expected else "FAIL",
        )
        return result

    func("POSITIVE")

    runs = store.get_runs(initialized.storage_path, project="test_proj")
    assert runs[0].feedback is not None
    assert runs[0].feedback.score == 1.0
    assert runs[0].feedback.label == "PASS"


def test_log_feedback_outside_track_raises():
    with pytest.raises(RuntimeError, match="outside a @pl.track"):
        pl.log_feedback(score=1.0, label="PASS")


def test_log_feedback_with_expected_got(initialized):
    @pl.track()
    def func() -> str:
        pl.log_feedback(score=0.0, label="FAIL", expected="POSITIVE", got="NEGATIVE")
        return "NEGATIVE"

    func()

    runs = store.get_runs(initialized.storage_path, project="test_proj")
    fb = runs[0].feedback
    assert fb is not None
    assert "expected: POSITIVE" in fb.notes
    assert "got: NEGATIVE" in fb.notes


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_track_captures_exception(initialized):
    @pl.track()
    def func() -> str:
        raise ValueError("something went wrong")

    with pytest.raises(ValueError, match="something went wrong"):
        func()

    runs = store.get_runs(initialized.storage_path, project="test_proj")
    assert len(runs) == 1
    assert "ValueError" in runs[0].error
    assert runs[0].output is None


def test_track_reraises_exception(tmp_path):
    pl.init(project="test_proj", storage_path=str(tmp_path / "test.db"))

    @pl.track()
    def func():
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        func()


# ---------------------------------------------------------------------------
# Nested tracked functions (ContextVar isolation)
# ---------------------------------------------------------------------------


def test_nested_tracked_functions_dont_bleed(initialized):
    @pl.track(name="inner")
    def inner(text: str) -> str:
        pl.log_prompt(f"inner: {text}")
        return "inner_result"

    @pl.track(name="outer")
    def outer(text: str) -> str:
        pl.log_prompt(f"outer: {text}")
        inner_out = inner(text)
        return f"outer_{inner_out}"

    outer("hello")

    runs = store.get_runs(initialized.storage_path, project="test_proj")
    by_name = {r.name: r for r in runs}

    assert by_name["inner"].prompt == "inner: hello"
    assert by_name["outer"].prompt == "outer: hello"
    assert by_name["outer"].output == "outer_inner_result"
