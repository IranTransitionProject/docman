# Docman — Document Processing Pipeline

**PDF/DOCX extraction, LLM classification and summarization, DuckDB persistence — built on the [Loom](https://github.com/IranTransitionProject/loom) framework.**

---

## What This Project Does

Docman is a document processing pipeline that evaluates Loom's actor-based
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

---

## Who This Is For

**Developers evaluating Loom** who want to see how the framework handles a
multi-stage pipeline with mixed worker types (LLM and processor).

**Document processing engineers** who need a pipeline for extracting, classifying,
and searching document collections.

**Anyone** building on the Loom framework who wants a reference implementation
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
| Unit tests | 40 passing |
| Summarizer file-ref resolution | Known gap |

---

## Quick Start

```bash
# Requires Python 3.11+
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/ -v   # 40 tests, no infrastructure needed
```

For full environment setup with Docling, Ollama, NATS, and the complete
pipeline, see the platform-specific guides below.

---

## Documentation

- **[Architecture](docs/ARCHITECTURE.md)** — Pipeline stages, data flow, DuckDB
  tools, design rules, Loom integration details
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
Contact: hooman@mac.com

---

*For governance, succession, and contributor rights, see [GOVERNANCE.md](GOVERNANCE.md).*
