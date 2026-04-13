# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-04-12

### Added
- `@track()` decorator for automatic prompt/response logging with LLM metadata (model, temperature, tokens, latency)
- `log_prompt()` function for explicit prompt capture without a decorator
- `init()` function for project-level configuration (storage path, project name)
- SQLite-backed local storage with per-project databases
- Parent-child run relationships for nested/chained LLM calls
- Session tracking across multiple runs
- CLI commands:
  - `promptlog ls` — list runs with tree hierarchy
  - `promptlog view` — inspect a full run record
  - `promptlog stats` — aggregate metrics grouped by name/version
  - `promptlog review` — interactive scoring loop for human feedback
  - `promptlog rescore` — update feedback on existing runs
  - `promptlog export` — export runs to CSV or JSON
  - `promptlog projects` — list all tracked projects
  - `promptlog delete` — remove specific runs
- Integration examples for OpenAI, Anthropic, Google Gemini, LangChain, and AutoGen
- Rich terminal UI for all CLI output
- Local-first storage: `.promptlog/` in project dir or `~/.promptlog/` globally
