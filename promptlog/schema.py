from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
import hashlib
import uuid
 
 
def _generate_run_id() -> str:
    return str(uuid.uuid4())[:8]
 
 
def _hash_template(template: str) -> str:
    """Auto-version a prompt by hashing its template content."""
    return hashlib.md5(template.encode()).hexdigest()[:8]
 
 
# ---------------------------------------------------------------------------
# Config — everything you define before the run
# ---------------------------------------------------------------------------
 
class PromptConfig(BaseModel):
    """
    Represents the static configuration of a prompt.
    Captured from @pl.track(...) arguments or a YAML file.
    """
 
    name: str                               # e.g. "market_agent"
    project: str                            # e.g. "quant_pipeline"
    model: Optional[str] = None             # e.g. "gpt-4o"
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    top_p: Optional[float] = None
    top_k: Optional[int] = None
    system_prompt: Optional[str] = None     # static system prompt if any
    prompt_template: Optional[str] = None   # raw template before variable substitution
    version: Optional[str] = None           # auto-generated hash of prompt_template
    tags: dict = Field(default_factory=dict)
 
    def model_post_init(self, __context) -> None:
        """Auto-generate version hash from prompt_template if not set."""
        if self.prompt_template and not self.version:
            self.version = _hash_template(self.prompt_template)
 
 
# ---------------------------------------------------------------------------
# FeedbackResult — human gives this after reviewing the output
# ---------------------------------------------------------------------------
 
class FeedbackResult(BaseModel):
    """
    Human feedback attached to a run after reviewing the output.
    Nothing here is automatic — a human always sets this explicitly
    via CLI (promptlog feedback) or programmatically (pl.log_feedback()).
    """
 
    score: Optional[float] = None           # 0.0 to 1.0
    label: Optional[str] = None             # "PASS", "FAIL", "PARTIAL" etc.
    notes: Optional[str] = None             # free text, what was good/bad
    feedback_given_at: Optional[datetime] = None
    feedback_by: str = "human"              # always human for MVP, "llm" in v2
 
 
# ---------------------------------------------------------------------------
# Run — one execution of a @pl.track decorated function
# ---------------------------------------------------------------------------
 
class Run(BaseModel):
    """
    Represents a single execution of a @pl.track decorated function.
    Created automatically by the decorator — you never instantiate this manually.
    """
 
    run_id: str = Field(default_factory=_generate_run_id)
    name: str                               # agent / function name
    project: str
 
    # prompt content
    prompt: Optional[str] = None            # rendered prompt sent to the LLM
    output: Optional[str] = None            # raw output returned by the LLM
 
    # full config snapshot at time of run
    # stored as a snapshot so changing config later
    # doesn't affect how old runs are displayed
    config: PromptConfig
 
    # performance
    latency_ms: Optional[float] = None
 
    # human feedback — empty until someone gives it
    feedback: Optional[FeedbackResult] = None
 
    # metadata
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    error: Optional[str] = None             # captured if function raised an exception
 
    @property
    def is_scored(self) -> bool:
        """True if a human has given feedback on this run."""
        return self.feedback is not None
 
    @property
    def passed(self) -> Optional[bool]:
        """
        Convenience for CLI display.
        True  → label is PASS / CORRECT / PROCEED, or score >= 0.5
        False → label is FAIL, or score < 0.5
        None  → no feedback given yet
        """
        if self.feedback is None:
            return None
        if self.feedback.label:
            return self.feedback.label.upper() in {"PASS", "CORRECT", "PROCEED"}
        if self.feedback.score is not None:
            return self.feedback.score >= 0.5
        return None
 
    def summary(self) -> dict:
        """
        Clean flat dict used by:
        - CLI table display (promptlog runs)
        - CSV export
        - future dashboard API
        """
        return {
            "run_id":             self.run_id,
            "name":               self.name,
            "project":            self.project,
            "model":              self.config.model,
            "temperature":        self.config.temperature,
            "version":            self.config.version,
            "prompt":             (self.prompt or "")[:80] + "..." if self.prompt else None,
            "output":             (self.output or "")[:80] + "..." if self.output else None,
            "latency_ms":         self.latency_ms,
            "is_scored":          self.is_scored,
            "feedback_score":     self.feedback.score if self.feedback else None,
            "feedback_label":     self.feedback.label if self.feedback else None,
            "feedback_notes":     self.feedback.notes if self.feedback else None,
            "feedback_given_at":  self.feedback.feedback_given_at.isoformat() if self.feedback and self.feedback.feedback_given_at else None,
            "passed":             self.passed,
            "timestamp":          self.timestamp.isoformat(),
            "error":              self.error,
        }