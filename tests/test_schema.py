"""Tests for schema.py — pure Pydantic, no DB, no fixtures."""
from datetime import datetime

from promptlog.schema import FeedbackResult, PromptConfig, Run


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_config(**kwargs) -> PromptConfig:
    defaults = dict(name="agent", project="proj")
    return PromptConfig(**{**defaults, **kwargs})


def make_run(**kwargs) -> Run:
    defaults = dict(name="agent", project="proj", config=make_config())
    return Run(**{**defaults, **kwargs})


def make_feedback(**kwargs) -> FeedbackResult:
    return FeedbackResult(**kwargs)


# ---------------------------------------------------------------------------
# PromptConfig
# ---------------------------------------------------------------------------


def test_prompt_config_version_auto_hash():
    cfg = make_config(prompt_template="Say hello to {name}")
    assert cfg.version is not None
    assert len(cfg.version) == 8


def test_prompt_config_version_is_deterministic():
    template = "Say hello to {name}"
    cfg1 = make_config(prompt_template=template)
    cfg2 = make_config(prompt_template=template)
    assert cfg1.version == cfg2.version


def test_prompt_config_different_templates_different_versions():
    cfg1 = make_config(prompt_template="template A")
    cfg2 = make_config(prompt_template="template B")
    assert cfg1.version != cfg2.version


def test_prompt_config_explicit_version_not_overwritten():
    cfg = make_config(prompt_template="hello {name}", version="myversion")
    assert cfg.version == "myversion"


def test_prompt_config_no_template_version_is_none():
    cfg = make_config()
    assert cfg.version is None


def test_prompt_config_optional_fields_default_none():
    cfg = make_config()
    assert cfg.model is None
    assert cfg.temperature is None
    assert cfg.max_tokens is None
    assert cfg.top_p is None
    assert cfg.top_k is None
    assert cfg.system_prompt is None
    assert cfg.prompt_template is None


def test_prompt_config_tags_default_empty():
    cfg = make_config()
    assert cfg.tags == {}


# ---------------------------------------------------------------------------
# FeedbackResult
# ---------------------------------------------------------------------------


def test_feedback_result_defaults():
    fb = FeedbackResult()
    assert fb.score is None
    assert fb.label is None
    assert fb.notes is None
    assert fb.feedback_given_at is None
    assert fb.feedback_by == "human"


def test_feedback_result_full():
    now = datetime.utcnow()
    fb = FeedbackResult(score=0.8, label="PASS", notes="Great", feedback_given_at=now)
    assert fb.score == 0.8
    assert fb.label == "PASS"
    assert fb.notes == "Great"
    assert fb.feedback_given_at == now
    assert fb.feedback_by == "human"


# ---------------------------------------------------------------------------
# Run.is_scored
# ---------------------------------------------------------------------------


def test_run_is_scored_false_when_no_feedback():
    run = make_run()
    assert run.is_scored is False


def test_run_is_scored_true_when_feedback_present():
    run = make_run(feedback=FeedbackResult(label="PASS"))
    assert run.is_scored is True


# ---------------------------------------------------------------------------
# Run.passed
# ---------------------------------------------------------------------------


def test_run_passed_none_when_no_feedback():
    run = make_run()
    assert run.passed is None


def test_run_passed_true_for_pass_label():
    run = make_run(feedback=FeedbackResult(label="PASS"))
    assert run.passed is True


def test_run_passed_true_for_correct_label():
    run = make_run(feedback=FeedbackResult(label="CORRECT"))
    assert run.passed is True


def test_run_passed_true_for_proceed_label():
    run = make_run(feedback=FeedbackResult(label="PROCEED"))
    assert run.passed is True


def test_run_passed_false_for_fail_label():
    run = make_run(feedback=FeedbackResult(label="FAIL"))
    assert run.passed is False


def test_run_passed_false_for_unknown_label():
    run = make_run(feedback=FeedbackResult(label="GARBAGE"))
    assert run.passed is False


def test_run_passed_true_for_score_above_threshold():
    run = make_run(feedback=FeedbackResult(score=0.7))
    assert run.passed is True


def test_run_passed_true_for_score_at_threshold():
    run = make_run(feedback=FeedbackResult(score=0.5))
    assert run.passed is True


def test_run_passed_false_for_score_below_threshold():
    run = make_run(feedback=FeedbackResult(score=0.3))
    assert run.passed is False


def test_run_passed_none_when_feedback_has_no_label_or_score():
    run = make_run(feedback=FeedbackResult(notes="just a note"))
    assert run.passed is None


# ---------------------------------------------------------------------------
# Run.summary()
# ---------------------------------------------------------------------------


def test_run_summary_contains_expected_keys():
    run = make_run()
    s = run.summary()
    for key in [
        "run_id", "name", "project", "model", "temperature", "version",
        "prompt", "output", "latency_ms", "is_scored",
        "feedback_score", "feedback_label", "feedback_notes",
        "feedback_given_at", "passed", "timestamp", "error",
    ]:
        assert key in s, f"Missing key: {key}"


def test_run_summary_no_feedback():
    run = make_run()
    s = run.summary()
    assert s["is_scored"] is False
    assert s["feedback_score"] is None
    assert s["feedback_label"] is None
    assert s["passed"] is None


def test_run_summary_with_feedback():
    fb = FeedbackResult(score=1.0, label="PASS", notes="Good")
    run = make_run(feedback=fb)
    s = run.summary()
    assert s["is_scored"] is True
    assert s["feedback_score"] == 1.0
    assert s["feedback_label"] == "PASS"
    assert s["feedback_notes"] == "Good"
    assert s["passed"] is True


def test_run_summary_prompt_truncated():
    long_prompt = "x" * 200
    run = make_run(prompt=long_prompt)
    s = run.summary()
    assert s["prompt"] is not None
    assert len(s["prompt"]) <= 84  # 80 chars + "..."


def test_run_summary_short_prompt_not_truncated():
    run = make_run(prompt="short")
    s = run.summary()
    assert s["prompt"] == "short"


def test_run_summary_auto_generated_run_id():
    run = make_run()
    assert len(run.run_id) == 8
