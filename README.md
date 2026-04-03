# Docman — Document Processing Pipeline

[![CI](https://github.com/IranTransitionProject/docman/actions/workflows/ci.yml/badge.svg)](https://github.com/IranTransitionProject/docman/actions/workflows/ci.yml)
[![codecov](https://codecov.io/github/IranTransitionProject/docman/graph/badge.svg?token=HIFLM6NGSF)](https://codecov.io/github/IranTransitionProject/docman)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![License: MPL 2.0](https://img.shields.io/badge/License-MPL_2.0-brightgreen.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
<!-- Keep in sync with heddle pyproject.toml version -->
[![Built on Heddle](https://img.shields.io/badge/built_on-Heddle_v0.8.0-blueviolet.svg)](https://github.com/getheddle/heddle)
[![Status: Active Development](https://img.shields.io/badge/status-active_development-brightgreen.svg)]()

**PDF/DOCX extraction, LLM classification and summarization, DuckDB persistence — built on the [Heddle](https://github.com/getheddle/heddle) framework.**

---

## What This Project Does

Docman is a document processing pipeline that evaluates Heddle's actor-based
architecture with a real-world workload. It takes PDF and DOCX files through
four stages:

| Stage | Worker | What it does |
|-------|--------|-------------|
| **Extract** | ProcessorWorker + DoclingBackend | Reads PDF/DOCX via Docling, extracts text/tables/figures, writes JSON to workspace |
| **Classify** | LLMWorker | LLM classifies document type from text preview and metadata |
| **Summarize** | LLMWorker | LLM produces structured summary adapted to document type |
| **Ingest** | ProcessorWorker + DuckDBIngestBackend | Persists metadata, classification, summary, full text, and optional embeddings to DuckDB |

A standalone `doc_query` worker provides full-text search, filtering, statistics,
and semantic vector search against the DuckDB database.

The entire system can be exposed as an **MCP (Model Context Protocol) server**
using Heddle's built-in MCP gateway — a single YAML config, zero MCP-specific code.

---

## Who This Is For

**Developers evaluating Heddle** who want to see how the framework handles a
multi-stage pipeline with mixed worker types (LLM and processor).

**Document processing engineers** who need a pipeline for extracting, classifying,
and searching document collections.

**Anyone** building on the Heddle framework who wants a reference implementation
to study or fork.

---

## Current State

| Component | Status |
|-----------|--------|
| DoclingBackend (PDF/DOCX extraction) | Complete |
| DuckDBIngestBackend (persistence + FTS + embeddings) | Complete |
| DocmanQueryBackend (search, filter, stats, get) | Complete |
| DuckDBVectorTool (semantic similarity search) | Complete |
| Worker configs (5 workers) | Complete |
| Pipeline configs (standard + local tier) | Complete |
| MCP gateway config | Complete |
| Unit tests | 124 passing |
| Summarizer file-ref resolution | Config pending (Heddle support exists) |

---

## Quick Start

```bash
# Requires Python 3.11+ and uv (https://docs.astral.sh/uv/)
uv sync --extra dev
uv run pytest tests/ -v   # 124 tests, no infrastructure needed
```

For full environment setup with Docling, Ollama, NATS, and the complete
pipeline, see the platform-specific guides below.

---

## Documentation

- **[Architecture](docs/ARCHITECTURE.md)** — Pipeline stages, data flow, DuckDB
  tools, design rules, Heddle integration details
- **[macOS Setup](docs/setup-macos.md)** — Full environment setup for Apple Silicon
- **[Windows Setup](docs/setup-windows.md)** — Full environment setup for
  Windows 11 / WSL2
- **[Docling Configuration](docs/docling-setup.md)** — Layout models, GPU
  acceleration, OCR engines, performance tuning
- **[Contributing](docs/CONTRIBUTING.md)** — CLA, technical standards, PR process

---

## Get Involved

**Extend the pipeline.** Add new backends for additional document formats,
improve classification categories, or implement multi-language support.

**Contribute.** New processing backends, pipeline improvements, integration
tests, and documentation improvements are all welcome.
See [Contributing](docs/CONTRIBUTING.md).

**Report issues.** Bug reports with reproducible steps help the most.

---

## License

[MPL 2.0](LICENSE) — Mozilla Public License 2.0. Modified source files must
remain open; unmodified files can be combined with proprietary code in a
Larger Work.

Alternative licensing available for organizations with copyleft constraints.
Contact: <admin@irantransitionproject.org>

---

*For governance, succession, and contributor rights, see [GOVERNANCE.md](GOVERNANCE.md).*
