# PromptLog

**A lightweight, framework-agnostic prompt tracking library for LLM projects — automatic logging, versioning, and run comparison.**

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![PyPI version](https://img.shields.io/badge/pypi-0.1.0-orange.svg)](https://pypi.org/project/promptlog/)
[![Status: Alpha](https://img.shields.io/badge/status-alpha-yellow.svg)]()

---

## Table of Contents

- [What is PromptLog?](#what-is-promptlog)
- [Key Features](#key-features)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Core Concepts](#core-concepts)
- [API Reference](#api-reference)
- [CLI Reference](#cli-reference)
- [Integrations](#integrations)
- [Contributing](#contributing)
- [License](#license)

---

## What is PromptLog?

> **A lightweight, framework-agnostic LLM prompt tracker — log runs, version prompts, and store feedback for your Python LLM application.**

Building LLM apps means constantly tweaking prompts, swapping models, and eyeballing outputs — but with no record of what changed or why. You ship a prompt update and have no idea if it actually improved things.

PromptLog fixes that. Add one decorator to any function that calls an LLM and every execution is automatically logged — prompt, output, latency, model config — to a local SQLite database. No cloud, no infra, no SDK changes. Then use the CLI to review outputs, score them, track prompt versions by content hash, and compare pass rates across iterations. It works with OpenAI, Anthropic, Gemini, LangChain, AutoGen, or anything else that returns a string.

---

## Key Features

- **One decorator, full capture** — wrap any sync function with `@pl.track()` and get prompt, output, latency, and errors logged automatically
- **Prompt versioning** — `prompt_template` is auto-hashed (MD5, 8 chars) so you can group and compare runs by prompt version
- **Human feedback loop** — score runs interactively with `promptlog review` or non-interactively with `promptlog rescore`
- **Hierarchical run tracking** — nested `@pl.track` calls automatically form parent-child trees, visualized in the CLI
- **Session-aware review** — `feedback_mode="end"` only prompts for feedback on runs from the current script execution
- **Framework-agnostic** — works with OpenAI, Anthropic, Google Gemini, LangChain, AutoGen, or any Python function
- **Local-first SQLite** — no external service, data lives in `~/.promptlog/` or a local `.promptlog/` folder
- **Rich CLI** — list, inspect, score, compare, and export runs from the terminal

---

## Installation

```bash
pip install promptlog
```

To run the bundled examples (requires API keys):

```bash
pip install "promptlog[examples]"
```

---

## Quick Start

```python
import promptlog as pl
from openai import OpenAI

# 1. Initialize once — sets the project name and storage
pl.init(project="my_app", feedback_mode="end")

client = OpenAI()

# 2. Decorate any function that calls an LLM
@pl.track(model="gpt-4o-mini", temperature=0.0)
def classify(review: str) -> str:
    pl.log_prompt(f"Classify sentiment: {review}")   # optional — auto-captured if omitted
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": f"Classify sentiment: {review}"}],
    )
    return response.choices[0].message.content

# 3. Call normally — tracking is transparent
result = classify("The product was excellent!")
print(result)

# With feedback_mode="end", an interactive review prompt appears when the script exits.
```

Then inspect via the CLI:

```bash
promptlog ls --project my_app
promptlog view <run_id> --project my_app
promptlog stats --project my_app
```

---

## Core Concepts

### Projects & Sessions

A **project** groups all runs under a named experiment (e.g., `"sentiment_classifier"`). All CLI commands require `--project`.

A **session** is a unique identifier generated each time `pl.init()` is called. It lets `feedback_mode="end"` scope the review to only the runs from the current script execution.

### Runs

A **run** is one execution of a `@pl.track`-decorated function. Each run records:

| Field | Description |
|---|---|
| `run_id` | Unique 8-char identifier |
| `session_id` | Groups runs from the same `pl.init()` call |
| `parent_run_id` | Set when this run is called inside another tracked function |
| `name` | Function or task name |
| `project` | Project grouping |
| `prompt` | Rendered prompt (explicit via `pl.log_prompt()` or auto-captured from string args) |
| `output` | Return value of the function as a string |
| `error` | Exception message if the function raised |
| `latency_ms` | Execution time in milliseconds |
| `timestamp` | UTC datetime of execution |
| `config` | Full `PromptConfig` snapshot (model, temperature, version, tags, …) |
| `feedback` | `FeedbackResult` once a human has scored the run |

### Prompt Versioning

When you set `prompt_template` in `@pl.track`, PromptLog automatically hashes it with MD5 (first 8 hex characters) and stores it as `version`. The same template always produces the same version hash, so you can group and compare runs across multiple executions.

```python
@pl.track(
    model="gpt-4o",
    prompt_template="Classify the sentiment of this review: {review}"
)
def classify(review: str) -> str:
    ...
```

Use `promptlog stats --project <name>` to see per-version pass rates and average scores.

### Human Feedback

Feedback is always given by a human (LLM-based scoring is planned for v2). A `FeedbackResult` has:

| Field | Type | Description |
|---|---|---|
| `score` | `float` (0.0–1.0) | Numeric quality score |
| `label` | `str` | Categorical label: `PASS`, `FAIL`, `PARTIAL`, `CORRECT`, etc. |
| `notes` | `str` | Free-text comments |
| `feedback_given_at` | `datetime` | When feedback was recorded |
| `feedback_by` | `str` | Always `"human"` in v0.1 |

A run `passed` if its label is `PASS`, `CORRECT`, or `PROCEED`, or if `score >= 0.5`.

### Hierarchical Runs

When a `@pl.track`-decorated function is called **inside** another tracked function, the inner run automatically gets `parent_run_id` set. The CLI renders this as an indented tree:

```
run_id    name               model         ms    scored  passed
────────  ─────────────────  ────────────  ────  ──────  ──────
a1b2c3d4  run_pipeline       -             843   yes     PASS
  e5f6g7  ├─ summarize       gpt-4o-mini   412   yes     PASS
  h8i9j0  └─ critique        gpt-4o-mini   431   yes     PASS
```

---

## API Reference

### `pl.init()`

Initialize PromptLog for a project. Call this **once** at the top of your script.

```python
pl.init(
    project="my_project",
    storage_path=None,
    feedback_mode="none",
    default_model=None,
    default_temperature=None,
    default_tags=None,
    enabled=True,
)
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `project` | `str` | **required** | Project name — all runs are grouped under this |
| `storage_path` | `str \| None` | `None` | Explicit path to the SQLite `.db` file |
| `feedback_mode` | `"end" \| "none"` | `"none"` | `"end"` triggers an interactive review when the script exits; `"none"` is silent |
| `default_model` | `str \| None` | `None` | Fallback model for all `@pl.track` calls in this project |
| `default_temperature` | `float \| None` | `None` | Fallback temperature for all `@pl.track` calls |
| `default_tags` | `dict \| None` | `{}` | Tags applied to every run |
| `enabled` | `bool` | `True` | Set `False` to disable all tracking (e.g., in production) |

**Returns:** `PromptLogConfig` — the active config object (rarely needed directly).

---

### `@pl.track()`

Decorator that logs every call to the wrapped function as a `Run`. Must be called with parentheses.

```python
@pl.track(
    name=None,
    model=None,
    temperature=None,
    max_tokens=None,
    top_p=None,
    top_k=None,
    system_prompt=None,
    prompt_template=None,
    config=None,
    tags=None,
)
def my_function(input: str) -> str:
    ...
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `name` | `str \| None` | function name | Override the run name shown in the CLI |
| `model` | `str \| None` | `None` | LLM model identifier (e.g., `"gpt-4o"`) |
| `temperature` | `float \| None` | `None` | Sampling temperature |
| `max_tokens` | `int \| None` | `None` | Maximum tokens to generate |
| `top_p` | `float \| None` | `None` | Top-p nucleus sampling |
| `top_k` | `int \| None` | `None` | Top-k sampling |
| `system_prompt` | `str \| None` | `None` | Static system message |
| `prompt_template` | `str \| None` | `None` | Raw template before variable substitution — auto-hashed for versioning |
| `config` | `dict \| None` | `None` | Dict fallback for any of the above (lower priority than explicit args) |
| `tags` | `dict \| None` | `{}` | Arbitrary key-value metadata merged with global default tags |

> **Note:** `@pl.track` does not support `async` functions. Wrap async code in a sync function using `asyncio.run()` — see the [AutoGen example](#autogen).

---

### `pl.log_prompt()`

Explicitly record the rendered prompt for the current tracked run. Call this **inside** a `@pl.track`-decorated function.

```python
@pl.track(model="gpt-4o")
def classify(review: str) -> str:
    pl.log_prompt(f"Classify sentiment: {review}")   # capture the final rendered prompt
    ...
```

If `pl.log_prompt()` is never called, PromptLog falls back to joining all `str` arguments passed to the function. For multi-argument or template-based prompts, always call `pl.log_prompt()` explicitly for accuracy.

**Raises** `RuntimeError` if called outside a `@pl.track`-decorated function.

---

### Schema Classes

#### `PromptConfig`

Snapshot of the configuration at the time of a run. Stored as JSON inside the database.

```python
from promptlog.schema import PromptConfig
```

| Field | Type | Description |
|---|---|---|
| `name` | `str` | Function/task name |
| `project` | `str` | Project name |
| `model` | `str \| None` | LLM model name |
| `temperature` | `float \| None` | Sampling temperature |
| `max_tokens` | `int \| None` | Max tokens |
| `top_p` | `float \| None` | Top-p |
| `top_k` | `int \| None` | Top-k |
| `system_prompt` | `str \| None` | System message |
| `prompt_template` | `str \| None` | Raw template |
| `version` | `str \| None` | Auto-generated MD5 hash of `prompt_template` (8 chars) |
| `tags` | `dict` | Merged tags |

#### `FeedbackResult`

Human feedback attached to a run.

```python
from promptlog.schema import FeedbackResult
```

| Field | Type | Description |
|---|---|---|
| `score` | `float \| None` | 0.0–1.0 numeric score |
| `label` | `str \| None` | Categorical label (`PASS`, `FAIL`, `PARTIAL`, …) |
| `notes` | `str \| None` | Free-text comments |
| `feedback_given_at` | `datetime \| None` | Timestamp of feedback |
| `feedback_by` | `str` | `"human"` (always in v0.1) |

#### `Run`

Represents a single tracked execution. Created automatically — never instantiated manually.

```python
from promptlog.schema import Run
```

Key properties:

| Property | Type | Description |
|---|---|---|
| `is_scored` | `bool` | `True` if feedback has been given |
| `passed` | `bool \| None` | `True` if label is PASS/CORRECT/PROCEED or score ≥ 0.5 |

Key method:

```python
run.summary() -> dict   # flat dict used for CSV/JSON export and CLI display
```

---

## CLI Reference

All commands use the `promptlog` entry point installed with the package.

```bash
promptlog --help
```

---

### `promptlog ls`

List logged runs for a project, rendered as a hierarchical tree.

```bash
promptlog ls --project <name> [--name <task>] [--unscored] [--failed] [--last N]
```

| Option | Description |
|---|---|
| `--project` | **Required.** Project name |
| `--name` | Filter by function/task name |
| `--unscored` | Show only runs without feedback |
| `--failed` | Show only runs that raised an exception |
| `--last N` | Show the last N runs |

**Example output:**

```
 run_id    name             model         ms    scored  passed
─────────────────────────────────────────────────────────────
 a1b2c3d4  run_pipeline     -             843   yes     PASS
   e5f6g7  ├─ summarize     gpt-4o-mini   412   yes     PASS
   h8i9j0  └─ critique      gpt-4o-mini   431   yes     PASS
```

---

### `promptlog view`

Show full detail for a specific run.

```bash
promptlog view <run_id> --project <name>
```

Displays a rich table with:
- Run profile: task name, project, model, temperature, latency, prompt version
- Full prompt text
- Full output (Markdown-rendered) or error
- Feedback (if present): label, score, notes

---

### `promptlog stats`

Show aggregated metrics grouped by `(name, version)`.

```bash
promptlog stats --project <name>
```

**Example output:**

```
 name        version   total  scored  passed  failed  avg_score
────────────────────────────────────────────────────────────────
 classify    a1b2c3d4     10       8       7       1       0.88
 classify    f9e8d7c6      5       5       3       2       0.60
```

Use this to compare the performance of different prompt versions side-by-side.

---

### `promptlog review`

Interactively score all unscored runs for a project.

```bash
promptlog review --project <name>
```

For each unscored run, you see the prompt and output in panels, then choose:

```
[p] pass    → PASS, score=1.0
[f] fail    → FAIL, score=0.0
[s] score   → enter a custom score (0.0–1.0), label, and notes
[n] skip    → skip this run
[q] quit    → stop and save progress
```

---

### `promptlog rescore`

Manually set or update feedback for a specific run without entering the interactive loop.

```bash
promptlog rescore <run_id> --project <name> [--pass | --fail | --score <val>] [--label <str>] [--notes <str>]
```

| Option | Description |
|---|---|
| `--pass` | Mark as PASS (score=1.0) |
| `--fail` | Mark as FAIL (score=0.0) |
| `--score` | Numeric score 0.0–1.0 |
| `--label` | Custom label string |
| `--notes` | Free-text notes |

If the run is already scored, you will be asked to confirm before overwriting.

**Examples:**

```bash
promptlog rescore a1b2c3d4 --project my_app --pass
promptlog rescore a1b2c3d4 --project my_app --score 0.75 --label PARTIAL --notes "Missing citation"
```

---

### `promptlog export`

Export all runs for a project to CSV or JSON.

```bash
promptlog export --project <name> [--format csv|json] [--output <file>]
```

| Option | Default | Description |
|---|---|---|
| `--format` | `csv` | Output format: `csv` or `json` |
| `--output` | stdout | File path to write output to |

**Examples:**

```bash
# Print CSV to stdout
promptlog export --project my_app

# Write JSON to a file
promptlog export --project my_app --format json --output runs.json
```

Exported fields match `Run.summary()`: run_id, session_id, parent_run_id, name, project, model, temperature, version, prompt (truncated to 80 chars), output (truncated), latency_ms, is_scored, feedback_score, feedback_label, feedback_notes, passed, timestamp, error.

---

### `promptlog projects`

List all known projects by scanning `~/.promptlog/` and `./.promptlog/`.

```bash
promptlog projects
```

**Example output:**

```
 project         runs  db_path
──────────────────────────────────────────────────────
 my_app            42  /Users/you/.promptlog/my_app.db
 langchain          8  /Users/you/.promptlog/langchain.db
```

---

### `promptlog delete`

Delete a specific run from the database.

```bash
promptlog delete <run_id> --project <name> [--yes]
```

| Option | Description |
|---|---|
| `--yes` / `-y` | Skip the confirmation prompt |

---

## Integrations

PromptLog works by wrapping any Python function, so it integrates with any LLM SDK or framework without modifications to your SDK calls.

### OpenAI SDK

```python
import promptlog as pl
from openai import OpenAI

pl.init(project="openai_app", feedback_mode="end")

client = OpenAI()
MODEL = "gpt-4o-mini"
TEMPERATURE = 0.0
PROMPT = "In one sentence, what is the capital of France?"


@pl.track(model=MODEL, temperature=TEMPERATURE)
def chat(prompt: str) -> str:
    pl.log_prompt(prompt)
    response = client.chat.completions.create(
        model=MODEL,
        temperature=TEMPERATURE,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content


chat(PROMPT)
```

---

### Anthropic SDK

```python
import anthropic
import promptlog as pl

pl.init(project="anthropic_app", feedback_mode="end")

client = anthropic.Anthropic()
MODEL = "claude-haiku-4-5-20251001"
TEMPERATURE = 0.0
PROMPT = "In one sentence, what is the capital of France?"


@pl.track(model=MODEL, temperature=TEMPERATURE)
def chat(prompt: str) -> str:
    pl.log_prompt(prompt)
    response = client.messages.create(
        model=MODEL,
        temperature=TEMPERATURE,
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


chat(PROMPT)
```

---

### Google Gemini SDK

```python
import promptlog as pl
from google import genai

pl.init(project="gemini_app", feedback_mode="end")

client = genai.Client()
MODEL = "gemini-2.0-flash"
TEMPERATURE = 0.0
PROMPT = "In one sentence, what is the capital of France?"


@pl.track(model=MODEL, temperature=TEMPERATURE)
def chat(prompt: str) -> str:
    pl.log_prompt(prompt)
    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config={"temperature": TEMPERATURE},
    )
    return response.text


chat(PROMPT)
```

---

### LangChain

PromptLog works naturally with LCEL chains. Wrap your chain invocations in tracked functions:

```python
import promptlog as pl
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI

pl.init(project="langchain_app", feedback_mode="end")

MODEL = "gpt-4o-mini"
SUMMARIZE_TEMPERATURE = 0.3
CRITIQUE_TEMPERATURE = 0.7

summarize_template = PromptTemplate.from_template("In two sentences, explain what {topic} is.")
critique_template = PromptTemplate.from_template("Critique this explanation in one sentence: {explanation}")

summarize_chain = summarize_template | ChatOpenAI(model=MODEL, temperature=SUMMARIZE_TEMPERATURE) | StrOutputParser()
critique_chain = critique_template | ChatOpenAI(model=MODEL, temperature=CRITIQUE_TEMPERATURE) | StrOutputParser()


@pl.track()
def run_pipeline(topic: str) -> dict:
    @pl.track(model=MODEL, temperature=SUMMARIZE_TEMPERATURE)
    def summarize(topic: str) -> str:
        pl.log_prompt(summarize_template.format(topic=topic))
        return summarize_chain.invoke({"topic": topic})

    @pl.track(model=MODEL, temperature=CRITIQUE_TEMPERATURE)
    def critique(explanation: str) -> str:
        pl.log_prompt(critique_template.format(explanation=explanation))
        return critique_chain.invoke({"explanation": explanation})

    summary = summarize(topic)
    comment = critique(summary)
    return {"summary": summary, "critique": comment}


result = run_pipeline("the French Revolution")
```

This produces three linked runs: `run_pipeline` as the parent, with `summarize` and `critique` as children.

---

### AutoGen

Since `@pl.track` does not support async functions, wrap your AutoGen team's async loop inside a sync function using `asyncio.run()`:

```python
import asyncio
import promptlog as pl
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_agentchat.conditions import MaxMessageTermination
from autogen_ext.models.openai import OpenAIChatCompletionClient

pl.init(project="autogen_app", feedback_mode="end")

MODEL = "gpt-4o-mini"
TEMPERATURE = 0.5
TASK = "What is the capital of France and why is it significant?"

model_client = OpenAIChatCompletionClient(model=MODEL, temperature=TEMPERATURE)

writer = AssistantAgent("writer", model_client=model_client,
    system_message="You are a writer. Answer the question clearly in one sentence.")
critic = AssistantAgent("critic", model_client=model_client,
    system_message="You are a critic. Review the writer's answer and suggest one improvement.")
user_proxy = AssistantAgent("user_proxy", model_client=model_client,
    system_message="Observe the writer and critic and let them finish their work.")


@pl.track(model=MODEL, temperature=TEMPERATURE)
def run_conversation(task: str) -> str:
    pl.log_prompt(task)

    async def _run() -> str:
        team = RoundRobinGroupChat(
            [writer, critic, user_proxy],
            termination_condition=MaxMessageTermination(max_messages=4),
        )
        result = await team.run(task=task)
        for msg in reversed(result.messages):
            if msg.source in ("writer", "critic"):
                return msg.content
        return ""

    return asyncio.run(_run())


run_conversation(TASK)
```
---

### Feedback Modes

| Mode | Behavior |
|---|---|
| `"none"` (default) | Silent. Score runs manually later with `promptlog review` or `promptlog rescore`. |
| `"end"` | Registers an `atexit` handler. When the script exits normally, launches an interactive review prompt scoped to runs from the **current session** only. |

```python
pl.init(project="my_app", feedback_mode="end")    # review at exit
pl.init(project="my_app", feedback_mode="none")   # silent, manual review later
```

---

## Contributing

```bash
git clone https://github.com/sujith-kamme/PromptLog.git
cd PromptLog

# Install in editable mode with dev dependencies
pip install -e ".[examples]"
```

Please open issues at [github.com/sujith-kamme/PromptLog/issues](https://github.com/sujith-kamme/PromptLog/issues).

---

## License

MIT — see [LICENSE](LICENSE).
