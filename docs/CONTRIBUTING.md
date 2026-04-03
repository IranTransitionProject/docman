# Contributing

Thank you for your interest in contributing to Docman.

---

## Before You Contribute

**Read [`GOVERNANCE.md`](../GOVERNANCE.md) first.** This project serves as a
reference implementation and test harness for the Heddle framework. Contributions
must work within Heddle's architecture — using its ABCs, messaging patterns, and
pipeline model.

---

## Contributor License Agreement (CLA)

**All contributors must sign the CLA before any pull request is merged.**

This is not negotiable and is not bureaucratic friction — it exists to preserve
the project's ability to offer alternative licensing to organizations that cannot
accept copyleft terms, while keeping the public license open for everyone else.

**What the CLA does:**

- Grants the project the right to sublicense your contribution
- Does NOT transfer your copyright — you retain full ownership of your work
- Applies to all future contributions once signed

**How to sign:**
The CLA bot will prompt you automatically when you open your first pull request.
Sign electronically in that flow. It takes under a minute.

If you have questions about the CLA before contributing, contact: <admin@irantransitionproject.org>

---

## Technical Standards

Contributions must adhere to the project's architectural rules:

**Use Heddle abstractions:**
Backends must implement `ProcessingBackend` or `SyncProcessingBackend` from Heddle.
Do not bypass Heddle's worker/processor model with direct function calls.

**Path traversal protection:**
All file operations must validate paths via `WorkspaceManager`. File references
must resolve within the configured workspace directory.

**Pipeline discipline:**
Each pipeline stage should have a single responsibility with well-defined I/O
schemas. Do not combine multiple processing steps into one worker.

**Test coverage:**
All new functionality must include unit tests. Tests must pass without
infrastructure (NATS, Valkey, Ollama, DuckDB on disk). Use in-memory DuckDB
and mocked backends for testing.

---

## What We Need Most

- New processing backends (additional document formats, extraction engines)
- Pipeline stage improvements (better classification, multi-language support)
- Integration tests with NATS infrastructure
- Wire `resolve_file_refs` in summarizer config (Heddle support exists, needs config update)
- MCP gateway examples and transport extensions
- Documentation improvements and examples
- Bug reports with reproducible steps

---

## What We Are Not Looking For

- Backends that bypass Heddle's `ProcessingBackend` ABC
- Direct LLM calls that skip worker I/O contract validation
- Provider-specific logic that cannot be abstracted
- Dependencies that only work on a single platform without alternatives

---

## Pull Request Process

1. Fork the repo
2. Make changes in a feature branch
3. Sign the CLA when prompted
4. Ensure all tests pass: `uv run pytest tests/ -v`
5. Submit a pull request with a clear description of what changed and why

Expect review feedback focused on Heddle compatibility and test coverage.

---

## AI-Assisted Development

This project uses Claude (Anthropic) as a development tool. The `CLAUDE.md` file
documents the project's architecture, pipeline design, and current state for
AI-assisted sessions.

AI-generated code is subject to the same standards as human contributions:
Heddle-compatible backends, validated I/O contracts, and test coverage.

---

## Contact

<admin@irantransitionproject.org>
