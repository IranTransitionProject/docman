# Docman

Document processing pipeline built on the [Loom](https://github.com/IranTransitionProject/loom) framework.

A test project that evaluates Loom's actor-based architecture with a real-world pipeline: PDF/DOCX extraction (Docling) → classification (LLM) → summarization (LLM) → persistence (DuckDB). Also provides standalone query and semantic search capabilities.

## Pipeline stages

| Stage | Worker | Backend | What it does |
|-------|--------|---------|-------------|
| 1. Extract | ProcessorWorker | DoclingBackend | Reads PDF/DOCX via Docling, extracts text/tables/figures, writes JSON to workspace |
| 2. Classify | LLMWorker | — | LLM classifies document type from text preview and metadata |
| 3. Summarize | LLMWorker | — | LLM produces structured summary based on document type |
| 4. Ingest | ProcessorWorker | DuckDBIngestBackend | Persists metadata, classification, summary, full text, and optional vector embeddings to DuckDB |

**Standalone:** `doc_query` (DuckDBQueryBackend) — search (FTS), filter, stats, get, and vector_search actions against the DuckDB database.

## LLM tools

Docman also provides Loom `SyncToolProvider` implementations for LLM function-calling:

- **DuckDBViewTool** — exposes DuckDB views (e.g., `document_summaries`) as LLM-callable query tools
- **DuckDBVectorTool** — semantic similarity search using `list_cosine_similarity` over stored embeddings

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/ -v   # 73 tests, no infrastructure needed
```

## Setup guides

- [macOS setup](docs/setup-macos.md) — Full environment setup for Apple Silicon
- [Windows setup](docs/setup-windows.md) — Full environment setup for Windows/WSL2
- [Docling tuning](docs/docling-setup.md) — Docling installation, GPU acceleration, OCR options

See `CLAUDE.md` for full architecture details, design rules, and run instructions.
