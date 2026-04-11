from __future__ import annotations

import time
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime
from functools import wraps
from typing import Callable, Optional

from promptlog.config import PromptLogConfig, get_config
from promptlog.schema import FeedbackResult, PromptConfig, Run, _generate_run_id
from promptlog import store


# ---------------------------------------------------------------------------
# Per-call mutable state threaded via ContextVar
# ---------------------------------------------------------------------------


@dataclass
class _RunState:
    prompt: Optional[str] = None
    feedback: Optional[FeedbackResult] = None
    feedback_saved: bool = False


_current_run_state: ContextVar[Optional[_RunState]] = ContextVar(
    "_current_run_state", default=None
)

# Tracks the currently executing run_id for automatic parent_run_id detection
_active_run_id: ContextVar[Optional[str]] = ContextVar("_active_run_id", default=None)

# Collects run_ids created during this Python process — used by atexit smart review
_session_run_ids: list[str] = []


# ---------------------------------------------------------------------------
# Public decorator
# ---------------------------------------------------------------------------


def track(
    name: Optional[str] = None,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    top_p: Optional[float] = None,
    top_k: Optional[int] = None,
    system_prompt: Optional[str] = None,
    prompt_template: Optional[str] = None,
    config: Optional[dict] = None,
    tags: Optional[dict] = None,
    blocking: bool = False,  # noqa: ARG001 — reserved for v2, intentionally unused
) -> Callable:
    """
    Decorator that logs every call to the wrapped function as a Run.

    Usage:
        @pl.track(model="gpt-4o", temperature=0.1)
        def classify(review: str) -> str:
            ...

    Must be called with parentheses: @pl.track(...) — not @pl.track bare.
    pl.init() must be called before the decorated function is invoked.
    """

    def decorator(func: Callable) -> Callable:
        if asyncio_iscoroutinefunction(func):
            raise NotImplementedError(
                f"@pl.track does not support async functions in MVP. "
                f"'{func.__name__}' is an async function. Async support coming in v2."
            )

        @wraps(func)
        def wrapper(*args, **kwargs):
            # Raises RuntimeError if pl.init() was never called
            cfg = get_config()

            # Pass-through if disabled
            if not cfg.enabled:
                return func(*args, **kwargs)

            resolved_name = name or func.__name__
            resolved_config = _resolve_config(
                cfg=cfg,
                func_name=resolved_name,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=top_p,
                top_k=top_k,
                system_prompt=system_prompt,
                prompt_template=prompt_template,
                config_dict=config,
                tags=tags,
            )

            # Ensure DB is ready
            store.init_db(cfg.storage_path)

            # Detect parent run (set if this call is nested inside another @pl.track)
            parent_run_id = _active_run_id.get()

            # Generate run_id upfront so child runs can reference it as their parent
            new_run_id = _generate_run_id()
            active_token = _active_run_id.set(new_run_id)

            # Set up per-call state in ContextVar
            state = _RunState()
            state_token = _current_run_state.set(state)

            start_ms = time.monotonic() * 1000
            error_str: Optional[str] = None
            result = None

            try:
                result = func(*args, **kwargs)
                return result
            except Exception as exc:
                error_str = f"{type(exc).__name__}: {exc}"
                raise
            finally:
                latency = time.monotonic() * 1000 - start_ms

                # Auto-capture prompt from string args if log_prompt was never called
                captured_prompt = state.prompt
                if captured_prompt is None:
                    captured_prompt = _extract_prompt_from_args(args, kwargs)

                run = Run(
                    run_id=new_run_id,
                    name=resolved_name,
                    session_id=cfg.session_id,
                    parent_run_id=parent_run_id,
                    project=cfg.project,
                    prompt=captured_prompt,
                    output=str(result) if result is not None else None,
                    config=resolved_config,
                    latency_ms=latency,
                    feedback=state.feedback if state.feedback_saved else None,
                    timestamp=datetime.utcnow(),
                    error=error_str,
                )
                store.insert_run(cfg.storage_path, run)
                _session_run_ids.append(run.run_id)
                _current_run_state.reset(state_token)
                _active_run_id.reset(active_token)

        return wrapper

    return decorator


# ---------------------------------------------------------------------------
# Context helpers — callable inside a @pl.track decorated function
# ---------------------------------------------------------------------------


def log_prompt(prompt: str) -> None:
    """
    Explicitly record the rendered prompt for the current tracked run.
    Call this inside a @pl.track decorated function.
    """
    state = _current_run_state.get()
    if state is None:
        raise RuntimeError(
            "log_prompt() called outside a @pl.track decorated function."
        )
    state.prompt = prompt


def log_feedback(
    score: Optional[float] = None,
    label: Optional[str] = None,
    notes: Optional[str] = None,
    expected: Optional[str] = None,
    got: Optional[str] = None,
) -> None:
    """
    Record programmatic feedback for the current tracked run.
    Call this inside a @pl.track decorated function.

    Feedback is embedded in the Run when it is saved after the function returns.
    """
    state = _current_run_state.get()
    if state is None:
        raise RuntimeError(
            "log_feedback() called outside a @pl.track decorated function."
        )

    # Build notes from expected/got if passed
    final_notes = notes
    if expected is not None or got is not None:
        parts = []
        if expected is not None:
            parts.append(f"expected: {expected}")
        if got is not None:
            parts.append(f"got: {got}")
        if notes:
            parts.append(notes)
        final_notes = " | ".join(parts)

    state.feedback = FeedbackResult(
        score=score,
        label=label,
        notes=final_notes,
        feedback_given_at=datetime.utcnow(),
    )
    state.feedback_saved = True


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_config(
    cfg: PromptLogConfig,
    func_name: str,
    model: Optional[str],
    temperature: Optional[float],
    max_tokens: Optional[int],
    top_p: Optional[float],
    top_k: Optional[int],
    system_prompt: Optional[str],
    prompt_template: Optional[str],
    config_dict: Optional[dict],
    tags: Optional[dict],
) -> PromptConfig:
    """
    Resolve final config values using priority order:
    1. Explicit params on @pl.track(model=..., temperature=...)
    2. config dict passed to @pl.track(config={...})
    3. Defaults from pl.init(default_model=..., default_temperature=...)
    4. None
    """
    base = config_dict or {}

    def _pick(explicit, from_dict_key, default):
        """Return first non-None value in priority order."""
        if explicit is not None:
            return explicit
        dict_val = base.get(from_dict_key)
        if dict_val is not None:
            return dict_val
        return default

    resolved_model = _pick(model, "model", cfg.default_model)
    resolved_temperature = _pick(temperature, "temperature", cfg.default_temperature)
    resolved_max_tokens = _pick(max_tokens, "max_tokens", None)
    resolved_top_p = _pick(top_p, "top_p", None)
    resolved_top_k = _pick(top_k, "top_k", None)
    resolved_system_prompt = _pick(system_prompt, "system_prompt", None)
    resolved_template = _pick(prompt_template, "prompt_template", None)

    # Tags: global defaults + decorator-level tags (decorator wins on conflict)
    resolved_tags = {**cfg.default_tags, **(tags or base.get("tags", {}))}

    return PromptConfig(
        name=func_name,
        project=cfg.project,
        model=resolved_model,
        temperature=resolved_temperature,
        max_tokens=resolved_max_tokens,
        top_p=resolved_top_p,
        top_k=resolved_top_k,
        system_prompt=resolved_system_prompt,
        prompt_template=resolved_template,
        tags=resolved_tags,
    )


def _extract_prompt_from_args(args: tuple, kwargs: dict) -> Optional[str]:
    """Join all string arguments as a fallback prompt capture."""
    parts = []
    for arg in args:
        if isinstance(arg, str):
            parts.append(arg)
    for val in kwargs.values():
        if isinstance(val, str):
            parts.append(val)
    return "\n".join(parts) if parts else None


def asyncio_iscoroutinefunction(func: Callable) -> bool:
    """Detect async functions without importing asyncio at module load time."""
    import asyncio
    return asyncio.iscoroutinefunction(func)
