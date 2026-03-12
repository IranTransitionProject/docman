# CLAUDE.md — Docman project context

## What this project is

Docman is a test project that evaluates the Loom framework architecture. It implements a document processing pipeline using Docling for PDF/DOCX extraction, with LLM-based classification and summarization stages.

This is a **consumer** of the Loom framework — it provides concrete worker configs, processing backends, and pipeline definitions. The Loom framework itself lives in a separate repo.

## Project structure

```
src/docman/
  backends/
    docling_backend.py   # DoclingBackend — PDF/DOCX extraction via Docling
    duckdb_ingest.py     # DuckDBIngestBackend — document persistence to DuckDB (with optional embeddings)
    duckdb_query.py      # DuckDBQueryBackend — search, filter, stats, retrieval, vector_search
  tools/
    duckdb_view.py       # DuckDBViewTool — expose DuckDB views as LLM-callable tools
    vector_search.py     # DuckDBVectorTool — semantic similarity search tool
configs/
  workers/        # YAML configs for doc_extractor, doc_classifier, doc_summarizer, doc_ingest, doc_query
  orchestrators/  # Pipeline config (doc_pipeline.yaml)
docs/
  docling-setup.md  # Docling installation, configuration, and performance tuning guide
tests/            # Unit tests (mock backends, in-memory DuckDB, no infrastructure)
```

## Relationship to Loom

Docman depends on `loom` as a package. It uses:
- `ProcessingBackend` ABC — DoclingBackend, DuckDBIngestBackend, DuckDBQueryBackend implement this
- `ProcessorWorker` — runs DoclingBackend and DuckDB backends via `loom processor` CLI
- `LLMWorker` — runs classifier and summarizer via `loom worker` CLI
- `PipelineOrchestrator` — orchestrates the 4-stage pipeline via `loom pipeline` CLI

The CLI loads backends by fully qualified class path from worker configs:
```yaml
processing_backend: "docman.backends.docling_backend.DoclingBackend"
```

## Pipeline stages

1. **doc_extractor** (ProcessorWorker + DoclingBackend) — Docling extracts text, tables, figures from PDF/DOCX. Writes extracted JSON to workspace, returns file_ref + metadata summary.
2. **doc_classifier** (LLMWorker) — LLM classifies document type from text_preview + metadata. Returns document_type, confidence, reasoning.
3. **doc_summarizer** (LLMWorker) — LLM summarizes based on document type and extracted content. Returns summary, key_points, word_count.
4. **doc_ingest** (ProcessorWorker + DuckDBIngestBackend) — Persists all pipeline results (metadata, classification, summary, full text) into DuckDB. Reads full extracted text from workspace JSON. Returns document_id.

## Standalone workers

- **doc_query** (ProcessorWorker + DuckDBQueryBackend) — Not part of the pipeline. Accepts structured query requests against the DuckDB database. Supports 5 actions: `search` (full-text via DuckDB FTS), `filter` (by document_type, has_tables, page range), `stats` (aggregate counts/averages), `get` (single document by ID), `vector_search` (semantic similarity via embeddings).

## Data flow

- Large data passes via **file references** in a shared workspace directory (`--workspace-dir`)
- Messages carry only file_ref strings, not inline content
- DoclingBackend reads source file from workspace, writes extracted JSON to workspace
- **Known gap:** The doc_summarizer receives a file_ref but LLMWorker doesn't currently resolve file_refs from workspace. The summarizer would need custom logic to read the extracted JSON and inject it into the LLM prompt. This is documented as a TODO in the summarizer config.

## Docling configuration

DoclingBackend reads tuning options from the `backend_config` section of `doc_extractor.yaml`. Key settings for Apple Silicon (M1 Pro 32GB):

- `device: "mps"` — GPU acceleration via Metal Performance Shaders
- `num_threads: 8` — matches M1 Pro's 8 performance cores
- `ocr_engine: "ocrmac"` — native macOS Vision framework OCR
- `layout_batch_size: 4` / `ocr_batch_size: 4` — balanced for 32GB RAM

Pre-download detection models: `docling-tools models download`

Full guide: `docs/docling-setup.md`

## Key design rules

- DoclingBackend runs Docling synchronously in a thread pool (`asyncio.run_in_executor`)
- DuckDB backends also run synchronously via `SyncProcessingBackend` (DuckDB is synchronous)
- Path traversal validation: file_ref must resolve within workspace_dir
- `text_preview` (first ~500 words) is included inline in extractor output so the classifier doesn't need file access
- Workspace directory is shared filesystem, configured per deployment
- DuckDB database file path is configurable via `backend_config.db_path` (defaults to workspace)
- DuckDB schema is auto-created on first ingestion (no migration step needed)
- DuckDB FTS extension enables full-text search across document content and summaries
- Query results exclude `full_text` column by default to keep NATS messages small; use `get` action for full content
- Vector embeddings use `FLOAT[]` (variable-length) column in DuckDB — use `list_cosine_similarity` (NOT `array_cosine_similarity` which requires fixed-size `FLOAT[N]`)
- Embedding generation is optional — controlled by `embedding` config section in `doc_ingest.yaml`. When absent, embedding column stores NULL
- DuckDBViewTool and DuckDBVectorTool implement Loom's `SyncToolProvider` for LLM function-calling via `knowledge_silos` config

## Build and test commands

```bash
# Create venv and install (requires Python 3.11+, recommend 3.13)
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
# Also install Loom in editable mode (from sibling directory):
pip install -e "../loom[dev,local]"

# Pre-download Docling detection models (avoids delay on first run)
docling-tools models download

# Run unit tests (no infrastructure needed)
pytest tests/ -v

# Run with infrastructure (needs NATS + Loom installed)
# Terminal 1: docker run -p 4222:4222 nats:latest
# Terminal 2: NATS_URL=nats://localhost:4222 loom router --nats-url nats://localhost:4222
# Terminal 3: loom processor --config configs/workers/doc_extractor.yaml --nats-url nats://localhost:4222
# Terminal 4: OLLAMA_URL=http://localhost:11434 loom worker --config configs/workers/doc_classifier.yaml --tier local --nats-url nats://localhost:4222
# Terminal 5: ANTHROPIC_API_KEY=sk-... loom worker --config configs/workers/doc_summarizer.yaml --tier standard --nats-url nats://localhost:4222
# Terminal 6: loom processor --config configs/workers/doc_ingest.yaml --nats-url nats://localhost:4222
# Terminal 7: loom processor --config configs/workers/doc_query.yaml --nats-url nats://localhost:4222
# Terminal 8: loom pipeline --config configs/orchestrators/doc_pipeline.yaml --nats-url nats://localhost:4222
# Submit:     loom submit "Process document" --context file_ref=test.pdf --nats-url nats://localhost:4222
```

## Current state

The following items are **implemented and working**:
- DoclingBackend (`src/docman/backends/docling_backend.py`) — complete with path traversal validation, configurable Docling tuning via backend_config, proper error handling (DoclingConversionError), production-quality docstrings
- DuckDBIngestBackend (`src/docman/backends/duckdb_ingest.py`) — persists pipeline results to DuckDB with auto-schema creation, full-text storage from workspace, FTS index, optional vector embedding generation via Ollama
- DuckDBQueryBackend (`src/docman/backends/duckdb_query.py`) — structured query interface with search (FTS), filter, stats, get, and vector_search actions
- DuckDBViewTool (`src/docman/tools/duckdb_view.py`) — Loom ToolProvider that exposes DuckDB views as LLM-callable tools
- DuckDBVectorTool (`src/docman/tools/vector_search.py`) — Loom ToolProvider for semantic similarity search using `list_cosine_similarity`
- Worker configs for all 4 pipeline stages + standalone query worker with I/O schemas — complete
- Pipeline configs (`configs/orchestrators/doc_pipeline.yaml`, `doc_pipeline_local.yaml`) — 4-stage pipeline complete
- Unit tests: 73 tests pass (DoclingBackend, DuckDB ingest/query, view tool, vector search, embeddings)

## What to implement next

1. **Summarizer file_ref resolution** — LLMWorker needs to read file_ref from workspace and inject content into the prompt
2. **End-to-end test** — With NATS, Redis, and Ollama running locally

## Known issues

- The summarizer stage can't actually read extracted text from workspace (see Data flow section)

## Environment

- Apple Silicon Mac
- Python >=3.11 (pyproject.toml), recommend 3.13 for compatibility
- Docling >=2.0.0 for document extraction (pulls torch, torchvision)
- DuckDB >=1.0.0 for embedded analytics database
- Ollama for local LLM tier (llama3.2:3b recommended)
