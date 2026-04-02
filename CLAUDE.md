# CLAUDE.md — Docman project context

## What this project is

Docman (v0.5.0) is a document processing pipeline built on the Loom framework. It extracts content from PDF, DOCX, PPTX, XLSX, and HTML files using an adaptive two-tier extraction strategy (MarkItDown for speed, Docling for depth), with LLM-based classification and summarization stages.

This is a **consumer** of the Loom framework — it provides concrete worker configs, processing backends, and pipeline definitions. The Loom framework itself lives in a separate repo.

## Project structure

```text
src/docman/
  contracts.py           # Pydantic I/O models — source of truth for worker schemas
  backends/
    docling_backend.py   # DoclingBackend — deep PDF/DOCX extraction via IBM Docling (OCR, tables)
    markitdown_backend.py # MarkItDownBackend — fast extraction via Microsoft MarkItDown (no ML)
    smart_extractor.py   # SmartExtractorBackend — MarkItDown-first, Docling fallback
    duckdb_ingest.py     # DuckDBIngestBackend — document persistence (serialize_writes=True)
    duckdb_query.py      # DocmanQueryBackend — thin subclass of loom.contrib.duckdb.DuckDBQueryBackend
  tools/
    vector_search.py     # DuckDBVectorTool — thin wrapper around loom.contrib.duckdb.DuckDBVectorTool
manifest.yaml            # App manifest for Loom Workshop deployment
configs/
  workers/        # YAML configs for doc_extractor, doc_classifier, doc_summarizer, doc_ingest, doc_query
  orchestrators/  # Pipeline configs (doc_pipeline, doc_pipeline_local, doc_pipeline_smart)
  mcp/            # MCP gateway config (docman.yaml)
scripts/
  dev-start.sh    # Local development launcher
  dev-start.ps1   # Windows development launcher
  build-app.sh    # Build deployment ZIP for Loom Workshop
docs/
  ARCHITECTURE.md   # System architecture overview
  CONTRIBUTING.md   # Contribution standards and CLA
  setup-macos.md    # Full macOS environment setup
  setup-windows.md  # Full Windows environment setup
  docling-setup.md  # Docling configuration and performance tuning
tests/            # Unit tests (mock backends, in-memory DuckDB, no infrastructure)
```

## Relationship to Loom

Docman depends on `loom-ai[duckdb]` as a package. It uses:

- `ProcessingBackend` ABC — DoclingBackend, MarkItDownBackend, SmartExtractorBackend, DuckDBIngestBackend implement this
- `resolve_schema_refs()` — worker configs use `input_schema_ref` / `output_schema_ref` pointing to `docman.contracts.*` Pydantic models (Loom resolves to JSON Schema at load time)
- `loom.contrib.duckdb.DuckDBQueryBackend` — DocmanQueryBackend subclasses this with Docman-specific schema defaults
- `loom.contrib.duckdb.DuckDBVectorTool` — DuckDBVectorTool wraps this with Docman-specific column/table defaults
- `loom.contrib.duckdb.DuckDBViewTool` — used directly (no Docman wrapper needed, already generic)
- `ProcessorWorker` — runs extraction and DuckDB backends via `loom processor` CLI
- `LLMWorker` — runs classifier and summarizer via `loom worker` CLI
- `PipelineOrchestrator` — orchestrates the 4-stage pipeline via `loom pipeline` CLI (with dependency-aware parallel stage execution)

The CLI loads backends by fully qualified class path from worker configs:

```yaml
processing_backend: "docman.backends.smart_extractor.SmartExtractorBackend"
```

## Extraction backends

Docman provides three extraction backends, all producing the same output contract (`ExtractorOutput`):

- **MarkItDownBackend** — Uses Microsoft MarkItDown for fast, lightweight document-to-Markdown conversion. No ML models, no torch dependency. Supports PDF, DOCX, PPTX, XLSX, HTML, and more. Cannot OCR scanned PDFs or extract complex table structures. Derives metadata (sections, tables, page count) from the Markdown output.
- **DoclingBackend** — Uses IBM Docling for deep extraction with OCR, table structure recognition, and layout analysis. Requires torch. Best for scanned PDFs and complex layouts.
- **SmartExtractorBackend** (recommended) — Composite backend that tries MarkItDown first and falls back to Docling when needed. Fallback triggers: extracted text shorter than `min_text_length` (default: 50 chars), MarkItDown error, or file extension in `force_docling_extensions` list. Reports `model_used: "markitdown"` or `"docling"` so you can see which path ran.

## Pipeline stages

1. **doc_extractor** (ProcessorWorker + SmartExtractorBackend or DoclingBackend) — Extracts text, tables, structure from documents. Writes extracted JSON to workspace, returns file_ref + metadata summary.
2. **doc_classifier** (LLMWorker) — LLM classifies document type from text_preview + metadata. Returns document_type, confidence, reasoning.
3. **doc_summarizer** (LLMWorker) — LLM summarizes based on document type and extracted content. Returns summary, key_points, word_count.
4. **doc_ingest** (ProcessorWorker + DuckDBIngestBackend) — Persists all pipeline results (metadata, classification, summary, full text) into DuckDB. Reads full extracted text from workspace JSON. Returns document_id.

**Pipeline execution order:** Loom's `PipelineOrchestrator` auto-infers dependencies from `input_mapping` paths and runs independent stages concurrently. Docman's pipeline has genuinely sequential dependencies (classify depends on extract, summarize depends on both, ingest depends on all three), so it produces 4 levels of 1 stage each — sequential execution.

**Pipeline variants:**

- `doc_pipeline.yaml` — Standard (Docling extraction, standard-tier summarizer)
- `doc_pipeline_local.yaml` — All-local (Docling extraction, local-tier summarizer)
- `doc_pipeline_smart.yaml` — Smart extraction (MarkItDown-first, standard-tier summarizer)

**Scaling note:** To process multiple documents concurrently, run multiple pipeline orchestrator instances. NATS queue groups automatically load-balance across replicas:

```bash
# Process 3 documents concurrently — each instance handles one goal
loom pipeline --config configs/orchestrators/doc_pipeline_smart.yaml &
loom pipeline --config configs/orchestrators/doc_pipeline_smart.yaml &
loom pipeline --config configs/orchestrators/doc_pipeline_smart.yaml &
```

## Standalone workers

- **doc_query** (ProcessorWorker + DuckDBQueryBackend) — Not part of the pipeline. Accepts structured query requests against the DuckDB database. Supports 5 actions: `search` (full-text via DuckDB FTS), `filter` (by document_type, has_tables, page range), `stats` (aggregate counts/averages), `get` (single document by ID), `vector_search` (semantic similarity via embeddings).

## I/O contracts

Worker I/O schemas are defined as Pydantic models in `src/docman/contracts.py`. Worker YAML configs reference them via `input_schema_ref` / `output_schema_ref`, and Loom's `resolve_schema_refs()` converts them to JSON Schema at load time.

Models: `ExtractorInput`, `ExtractorOutput`, `ClassifierInput`, `ClassifierOutput`, `SummarizerInput`, `SummarizerOutput`, `IngestInput`, `IngestOutput`, `QueryInput`, `QueryOutput`.

## Data flow

- Large data passes via **file references** in a shared workspace directory (`--workspace-dir`)
- Messages carry only file_ref strings, not inline content
- Extraction backends (MarkItDown, Docling) read source file from workspace, write extracted JSON to workspace
- **Summarizer file resolution:** `resolve_file_refs: ["file_ref"]` and `workspace_dir` are set in the summarizer config — Loom's LLMWorker reads extracted JSON from workspace automatically.

## Docling configuration

DoclingBackend reads tuning options from the `backend_config` section of `doc_extractor.yaml`. Key settings for Apple Silicon (M1 Pro 32GB):

- `device: "mps"` — GPU acceleration via Metal Performance Shaders
- `num_threads: 8` — matches M1 Pro's 8 performance cores
- `ocr_engine: "ocrmac"` — native macOS Vision framework OCR
- `layout_batch_size: 4` / `ocr_batch_size: 4` — balanced for 32GB RAM

Pre-download detection models: `docling-tools models download`

Full guide: `docs/docling-setup.md`

## MCP gateway

Docman can be exposed as an MCP (Model Context Protocol) server using Loom's built-in MCP gateway — zero MCP-specific code needed.

```bash
# Start Docman as an MCP server (requires loom[mcp] and NATS + workers running)
loom mcp --config configs/mcp/docman.yaml

# Or with streamable-http transport
loom mcp --config configs/mcp/docman.yaml --transport streamable-http --port 8000
```

The MCP config (`configs/mcp/docman.yaml`) maps Docman's workers and query backend to MCP tools:

- Pipeline → `process_document` tool (full extract → classify → summarize → ingest)
- Query backend → `docman_search`, `docman_filter`, `docman_stats`, `docman_get` tools
- Workspace files exposed as MCP resources

See Loom's [Building Workflows](https://github.com/IranTransitionProject/loom/blob/main/docs/building-workflows.md) Part 11 for full MCP gateway documentation.

## Key design rules

- All extraction backends extend `SyncProcessingBackend` — synchronous work runs in a thread pool (`asyncio.run_in_executor`)
- SmartExtractorBackend creates inner backends lazily — importing docman does not pull in torch or markitdown
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
# Install all dependencies (requires Python 3.11+, uses uv)
# Loom is resolved from ../loom via [tool.uv.sources] in pyproject.toml
uv sync --extra dev

# Pre-download Docling detection models (avoids delay on first run)
uv run docling-tools models download

# Run unit tests (no infrastructure needed)
uv run pytest tests/ -v

# Run with infrastructure (needs NATS + Loom installed)
# Terminal 1: docker run -p 4222:4222 nats:latest
# Terminal 2: uv run loom router --nats-url nats://localhost:4222
# Terminal 3: uv run loom processor --config configs/workers/doc_extractor.yaml --nats-url nats://localhost:4222
# Terminal 4: OLLAMA_URL=http://localhost:11434 uv run loom worker --config configs/workers/doc_classifier.yaml --tier local --nats-url nats://localhost:4222
# Terminal 5: ANTHROPIC_API_KEY=sk-... uv run loom worker --config configs/workers/doc_summarizer.yaml --tier standard --nats-url nats://localhost:4222
# Terminal 6: uv run loom processor --config configs/workers/doc_ingest.yaml --nats-url nats://localhost:4222
# Terminal 7: uv run loom processor --config configs/workers/doc_query.yaml --nats-url nats://localhost:4222
# Terminal 8: uv run loom pipeline --config configs/orchestrators/doc_pipeline.yaml --nats-url nats://localhost:4222
# Submit:     uv run loom submit "Process document" --context file_ref=test.pdf --nats-url nats://localhost:4222
```

## Current state

The following items are **implemented and working**:

- Pydantic I/O contracts (`src/docman/contracts.py`) — source of truth for all worker schemas, resolved at load time via Loom's `resolve_schema_refs()`
- MarkItDownBackend (`src/docman/backends/markitdown_backend.py`) — fast extraction via Microsoft MarkItDown, derives metadata from Markdown output
- SmartExtractorBackend (`src/docman/backends/smart_extractor.py`) — composite MarkItDown-first with Docling fallback, configurable thresholds
- DoclingBackend (`src/docman/backends/docling_backend.py`) — deep extraction with OCR, table structure, layout analysis
- DuckDBIngestBackend (`src/docman/backends/duckdb_ingest.py`) — persists pipeline results to DuckDB with auto-schema creation, FTS index, optional vector embeddings
- DocmanQueryBackend (`src/docman/backends/duckdb_query.py`) — thin subclass with Docman document schema defaults
- DuckDBVectorTool (`src/docman/tools/vector_search.py`) — thin wrapper with Docman-specific defaults
- Worker configs for all pipeline stages + standalone query worker — using `input_schema_ref`/`output_schema_ref`
- Pipeline configs: `doc_pipeline.yaml` (Docling), `doc_pipeline_local.yaml` (all local), `doc_pipeline_smart.yaml` (MarkItDown-first)
- App manifest (`manifest.yaml`) — declares all configs, Python package, and required Loom extras
- Build script (`scripts/build-app.sh`) — generates deployment ZIP for Loom Workshop

## What to implement next

1. **End-to-end test** — With NATS, Valkey, and Ollama running locally
2. **Design a parallel pipeline variant** — Current pipeline is inherently sequential, but a variant could run classify and summarize concurrently if the summarizer doesn't need `document_type` (Loom's pipeline parallelism would auto-detect this from input_mapping)
3. **MCP progress notifications** — When Loom's MCP bridge wires progress callbacks to MCP progress tokens, Docman's pipeline would automatically report per-stage progress to MCP clients

## Environment

- Apple Silicon Mac
- Python >=3.11 (pyproject.toml), recommend 3.13 for compatibility
- MarkItDown >=0.1.0 for fast document extraction (lightweight, no ML)
- Docling >=2.0.0 for deep document extraction (pulls torch, torchvision)
- DuckDB >=1.0.0 for embedded analytics database
- Ollama for local LLM tier (llama3.2:3b recommended)
