# promptlog/config.py

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Literal
from pathlib import Path


# ---------------------------------------------------------------------------
# Feedback mode type
# ---------------------------------------------------------------------------

FeedbackMode = Literal["end", "none"]

# "end"  → after all tracked functions finish, CLI prompts for feedback
# "none" → silent, no feedback prompt, score manually via `promptlog feedback`


# ---------------------------------------------------------------------------
# Global state — one instance lives for the duration of the process
# ---------------------------------------------------------------------------

@dataclass
class PromptLogConfig:
    """
    Global configuration set by pl.init().
    Holds project-level settings that all @pl.track decorators inherit.
    """

    project: str                                    # required — groups all runs together
    storage_path: Path                              # where SQLite DB lives
    feedback_mode: FeedbackMode = "none"            # when to ask for feedback
    default_model: Optional[str] = None             # fallback if not set in @pl.track
    default_temperature: Optional[float] = None     # fallback if not set in @pl.track
    default_tags: dict = field(default_factory=dict)
    enabled: bool = True                            # set False to disable all logging globally


# ---------------------------------------------------------------------------
# Module-level singleton — this is what the rest of promptlog reads
# ---------------------------------------------------------------------------

_config: Optional[PromptLogConfig] = None


def init(
    project: str,
    storage_path: Optional[str] = None,
    feedback_mode: FeedbackMode = "none",
    default_model: Optional[str] = None,
    default_temperature: Optional[float] = None,
    default_tags: Optional[dict] = None,
    enabled: bool = True,
) -> PromptLogConfig:
    """
    Initialize promptlog for a project. Call this once at the top of your script.

    Args:
        project:             Name of the project. All runs are grouped under this.
        storage_path:        Where to store the SQLite DB.
                             Defaults to ~/.promptlog/<project>.db
        feedback_mode:       "end"  → ask for feedback after all runs finish
                             "none" → silent, score manually later via CLI
        default_model:       Fallback model name if not set in @pl.track
        default_temperature: Fallback temperature if not set in @pl.track
        default_tags:        Tags applied to every run in this project
        enabled:             Set False to disable all logging (e.g. in production)

    Returns:
        PromptLogConfig — the active config (rarely needed directly)

    Example:
        import promptlog as pl

        pl.init(project="movie_app")
        pl.init(project="quant_pipeline", feedback_mode="end")
        pl.init(project="my_app", enabled=False)   # production — no logging
    """
    global _config

    # resolve storage path
    resolved_path = _resolve_storage_path(project, storage_path)

    _config = PromptLogConfig(
        project=project,
        storage_path=resolved_path,
        feedback_mode=feedback_mode,
        default_model=default_model,
        default_temperature=default_temperature,
        default_tags=default_tags or {},
        enabled=enabled,
    )

    return _config


def get_config() -> PromptLogConfig:
    """
    Returns the active config.
    Called internally by tracker.py and store.py.
    Raises if pl.init() was never called.
    """
    if _config is None:
        raise RuntimeError(
            "promptlog is not initialized.\n"
            "Add `pl.init(project='your_project')` at the top of your script."
        )
    return _config


def is_initialized() -> bool:
    """Safe check — returns False instead of raising."""
    return _config is not None


def reset() -> None:
    """
    Resets global config to None.
    Used in tests to isolate test cases from each other.
    Not intended for production use.
    """
    global _config
    _config = None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve_storage_path(project: str, storage_path: Optional[str]) -> Path:
    """
    Resolves where the SQLite DB will live.

    Priority:
    1. Explicit path passed to pl.init()
    2. Default: ~/.promptlog/<project>.db
    """
    if storage_path:
        path = Path(storage_path)
    else:
        path = Path.home() / ".promptlog" / f"{project}.db"

    # ensure parent directory exists
    path.parent.mkdir(parents=True, exist_ok=True)

    return path


# ---------------------------------------------------------------------------
# Sanity check
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # 1. before init — should raise
    print(f"initialized: {is_initialized()}")      # False

    # 2. basic init
    cfg = init(project="movie_app")
    print(f"initialized : {is_initialized()}")     # True
    print(f"project     : {cfg.project}")          # movie_app
    print(f"storage     : {cfg.storage_path}")     # ~/.promptlog/movie_app.db
    print(f"feedback    : {cfg.feedback_mode}")    # none
    print(f"enabled     : {cfg.enabled}")          # True

    # 3. init with all options
    reset()
    cfg2 = init(
        project="quant_pipeline",
        feedback_mode="end",
        default_model="gpt-4o",
        default_temperature=0.7,
        default_tags={"env": "dev"},
    )
    print(f"project     : {cfg2.project}")         # quant_pipeline
    print(f"feedback    : {cfg2.feedback_mode}")   # end
    print(f"model       : {cfg2.default_model}")   # gpt-4o
    print(f"tags        : {cfg2.default_tags}")    # {"env": "dev"}

    # 4. disabled mode — production
    reset()
    cfg3 = init(project="my_app", enabled=False)
    print(f"enabled     : {cfg3.enabled}")         # False

    # 5. get_config works after init
    active = get_config()
    print(f"active      : {active.project}")       # my_app

    # 6. reset and get_config raises
    reset()
    try:
        get_config()
    except RuntimeError as e:
        print(f"error       : {e}")