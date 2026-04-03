# Architecture

**Docman — Document Processing Pipeline**

---

## Overview

Docman is a document processing pipeline built on the Heddle framework. It
evaluates Heddle's actor-based architecture with a real-world pipeline: extract
text from PDF/DOCX documents using Docling, classify and summarize them with
LLMs, then persist everything to DuckDB for search and analysis.

Docman is a **consumer** of Heddle — it provides concrete backends, worker configs,
and pipeline definitions. The Heddle framework itself lives in a separate repo.

---

## Source Tree

```text
src/docman/
├── backends/
│   ├── docling_backend.py    # DoclingBackend — PDF/DOCX extraction via Docling
│   ├── duckdb_ingest.py      # DuckDBIngestBackend — document persistence to DuckDB
│   └── duckdb_query.py       # DocmanQueryBackend — thin subclass with Docman schema defaults
│
└── tools/
    └── vector_search.py      # DuckDBVectorTool — wrapper with document-specific defaults

configs/
├── workers/
│   ├── doc_extractor.yaml          # Docling extraction (processor)
│   ├── doc_extractor_windows.yaml  # Windows-specific extractor config
│   ├── doc_classifier.yaml         # LLM document classification
│   ├── doc_summarizer.yaml         # LLM summarization (standard tier)
│   ├── doc_summarizer_local.yaml   # LLM summarization (local tier)
│   ├── doc_ingest.yaml             # DuckDB persistence (processor)
│   └── doc_query.yaml              # DuckDB query (standalone processor)
│
├── orchestrators/
│   ├── doc_pipeline.yaml           # Full pipeline (mixed tiers)
│   └── doc_pipeline_local.yaml     # Full pipeline (local tier only)
│
└── mcp/
    └── docman.yaml                 # MCP gateway config (exposes pipeline + queries as tools)

docs/
├── ARCHITECTURE.md         # This file
├── CONTRIBUTING.md         # Contribution standards and CLA
├── setup-macos.md          # Full macOS environment setup
├── setup-windows.md        # Full Windows environment setup
└── docling-setup.md        # Docling configuration and tuning

scripts/
├── dev-start.sh            # Development pipeline launcher (macOS/Linux)
└── dev-start.ps1           # Development pipeline launcher (Windows)

tests/                      # 40 unit tests (no infrastructure needed)
```

---

## Pipeline Stages

The pipeline processes documents through four stages. Heddle's `PipelineOrchestrator`
auto-infers dependencies from `input_mapping` paths and runs independent stages
concurrently. In Docman's case, each stage depends on the previous one, so
execution remains sequential:

```text
PDF/DOCX → [Extract] → [Classify] → [Summarize] → [Ingest] → DuckDB
           Level 0      Level 1      Level 2       Level 3
```

To process multiple documents concurrently, run multiple pipeline instances —
NATS queue groups handle load balancing automatically.

### Stage 1: Extract (`doc_extractor`)

- **Type:** ProcessorWorker + DoclingBackend
- **What it does:** Reads PDF/DOCX via Docling, extracts text, tables, and figures
- **Output:** Writes extracted JSON to workspace, returns `file_ref` + metadata
  (page count, table presence, section list, text preview)
- **Key detail:** `text_preview` (first ~500 words) is included inline so the
  classifier doesn't need file access

### Stage 2: Classify (`doc_classifier`)

- **Type:** LLMWorker (local tier)
- **What it does:** LLM classifies document type from text preview and metadata
- **Output:** `document_type` (invoice, report, letter, memo, contract, resume,
  academic_paper, manual, form, other), confidence score, reasoning

### Stage 3: Summarize (`doc_summarizer`)

- **Type:** LLMWorker (standard or local tier)
- **What it does:** LLM produces structured summary adapted to document type
- **Output:** Summary (2-5 paragraphs), key points, word count
- **Config pending:** Heddle's `resolve_file_refs` now supports file-ref resolution; needs wiring in config

### Stage 4: Ingest (`doc_ingest`)

- **Type:** ProcessorWorker + DuckDBIngestBackend
- **What it does:** Persists all pipeline results to DuckDB — metadata,
  classification, summary, full text, and optional vector embeddings
- **Output:** Document UUID and insertion status

---

## Standalone Workers

### doc_query (DocmanQueryBackend)

Not part of the pipeline. Accepts structured query requests against the DuckDB
database with five actions:

| Action | Description |
|--------|-------------|
| `search` | Full-text search via DuckDB FTS extension |
| `filter` | Filter by document_type, has_tables, page range |
| `stats` | Aggregate counts and averages (grouped by type, tables) |
| `get` | Single document by ID (includes full text) |
| `vector_search` | Semantic similarity search via embeddings |

---

## DuckDB Tools

Docman provides thin wrappers around `heddle.contrib.duckdb` with document-specific
defaults:

**DocmanQueryBackend** — subclass of `heddle.contrib.duckdb.DuckDBQueryBackend` with
Docman table schema (columns, filters, FTS fields, stats aggregates).

**DuckDBVectorTool** — wrapper around `heddle.contrib.duckdb.DuckDBVectorTool` with
document table/column defaults, implements `SyncToolProvider` for LLM
function-calling.

**DuckDBViewTool** — used directly from `heddle.contrib.duckdb` (no wrapper needed).

---

## Data Flow

Large data passes via **file references** in a shared workspace directory. Messages
carry only `file_ref` strings, not inline content.

1. Source file placed in workspace directory
2. DoclingBackend reads source, writes extracted JSON to workspace
3. Extractor returns `file_ref` pointing to extracted JSON + inline `text_preview`
4. Classifier uses inline `text_preview` (no file access needed)
5. Summarizer receives `file_ref` (Heddle's `resolve_file_refs` can resolve this; config not yet wired)
6. Ingest backend reads full text from workspace JSON, persists to DuckDB

---

## Design Rules

**DoclingBackend runs synchronously** in a thread pool via `asyncio.run_in_executor`.
Docling is synchronous; the thread pool prevents blocking the async event loop.

**DuckDB backends run synchronously** via `SyncProcessingBackend`. DuckDB is
synchronous by nature.

**Path traversal validation:** All `file_ref` values must resolve within the
configured `workspace_dir`. The `WorkspaceManager` enforces this.

**DuckDB schema auto-creation:** The schema is created on first ingestion. No
migration step needed.

**FTS extension:** DuckDB FTS enables full-text search across `full_text`,
`summary`, and `text_preview` columns.

**Query results exclude `full_text`** by default to keep NATS messages small.
Use the `get` action for full content.

**Vector embeddings are optional.** Controlled by the `embedding` config section
in `doc_ingest.yaml`. When absent, the embedding column stores NULL. Embeddings
use `FLOAT[]` (variable-length) and `list_cosine_similarity`.

---

## Relationship to Heddle

Docman depends on `heddle[duckdb]` as a package and uses these Heddle components:

| Heddle Component | Docman Usage |
|----------------|-------------|
| `ProcessingBackend` ABC | DoclingBackend, DuckDBIngestBackend |
| `SyncProcessingBackend` | DuckDB backends (synchronous) |
| `DuckDBQueryBackend` | DocmanQueryBackend subclass |
| `DuckDBVectorTool` | DuckDBVectorTool wrapper |
| `DuckDBViewTool` | Used directly (no wrapper) |
| `ProcessorWorker` | Runs extraction and ingestion stages |
| `LLMWorker` | Runs classification and summarization stages |
| `PipelineOrchestrator` | Orchestrates 4-stage pipeline (dependency-aware parallelism) |
| `WorkspaceManager` | File-ref resolution with path traversal protection |
| `MCPGateway` | Exposes Docman as MCP server via `configs/mcp/docman.yaml` |

The CLI loads backends by fully qualified class path from worker configs:

```yaml
processing_backend: "docman.backends.docling_backend.DoclingBackend"
```

---

## MCP Gateway

Docman can be exposed as an MCP (Model Context Protocol) server using Heddle's
built-in MCP gateway. A single YAML config maps Docman's pipeline and query
backend to MCP tools — no MCP-specific code needed.

```bash
heddle mcp --config configs/mcp/docman.yaml
```

The gateway auto-discovers tools from the config:

| MCP Tool | Source |
|----------|--------|
| `process_document` | Pipeline: extract → classify → summarize → ingest |
| `docman_search` | DocmanQueryBackend `search` action (FTS) |
| `docman_filter` | DocmanQueryBackend `filter` action |
| `docman_stats` | DocmanQueryBackend `stats` action |
| `docman_get` | DocmanQueryBackend `get` action |

Workspace files (PDFs, extracted JSON) are exposed as MCP resources with
`workspace:///` URIs.

---

## Docling Configuration

DoclingBackend reads tuning options from `backend_config` in `doc_extractor.yaml`.
Key settings for Apple Silicon (M1 Pro 32GB):

| Setting | Value | Purpose |
|---------|-------|---------|
| `device` | `"mps"` | GPU acceleration via Metal Performance Shaders |
| `num_threads` | `8` | Matches M1 Pro performance cores |
| `ocr_engine` | `"ocrmac"` | Native macOS Vision framework OCR |
| `layout_batch_size` | `4` | Balanced for 32GB RAM |
| `ocr_batch_size` | `4` | Balanced for 32GB RAM |

Pre-download detection models: `docling-tools models download`

For comprehensive Docling configuration, see [Docling Setup](docling-setup.md).

---

*For environment setup, see [macOS Setup](setup-macos.md) or
[Windows Setup](setup-windows.md).*
