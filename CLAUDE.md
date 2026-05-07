# CLAUDE.md — Docman

## What this is

Docman (v0.5.0) is a document processing pipeline built on the Heddle framework. It extracts content from PDF, DOCX, PPTX, XLSX, and HTML files using a two-tier extraction strategy (MarkItDown for speed, Docling for depth), with LLM classification and summarization stages.

Docman is a **Heddle consumer** — it implements `ProcessingBackend` and `ToolProvider`. The framework lives in `../heddle`.

## Pipeline stages

1. **doc_extractor** (ProcessorWorker + SmartExtractorBackend) — extract text, tables, structure → `file_ref` + metadata
2. **doc_classifier** (LLMWorker) — classify document type from `text_preview` → `document_type` + confidence
3. **doc_summarizer** (LLMWorker) — summarize based on type + content → summary + key_points
4. **doc_ingest** (ProcessorWorker + DuckDBIngestBackend) — persist all results → `document_id`

Heddle auto-infers stage dependencies from `input_mapping`; this pipeline is genuinely sequential (4 levels × 1 stage each).

## Extraction backends

- **MarkItDownBackend** — fast, no ML, no torch. Cannot OCR scanned PDFs.
- **DoclingBackend** — deep extraction (OCR, tables, layout). Requires torch.
- **SmartExtractorBackend** (recommended) — MarkItDown-first; falls back to Docling when extracted text < 50 chars or on MarkItDown error. Reports `model_used: "markitdown"` or `"docling"`.

## Key design rules

- All extraction backends extend `SyncProcessingBackend` — synchronous work runs in `asyncio.run_in_executor`
- SmartExtractorBackend creates inner backends lazily — importing docman does not pull in torch or markitdown
- `text_preview` (first ~500 words) is inlined in extractor output so the classifier doesn't need file access
- Vector embeddings use `FLOAT[]` (variable-length) in DuckDB — use `list_cosine_similarity`, NOT `array_cosine_similarity`
- Backends are loaded by fully qualified class path: `processing_backend: "docman.backends.smart_extractor.SmartExtractorBackend"`

## Build and test

```bash
uv sync --extra dev                      # Python 3.11+; Heddle resolved from ../heddle
uv run docling-tools models download     # one-time: pre-download Docling detection models
uv run pytest tests/ -v                  # no infrastructure needed
uv run ruff check src/ tests/            # lint
```

To test with live infrastructure:

```bash
docker run -p 4222:4222 nats:latest
uv run heddle router --nats-url nats://localhost:4222
uv run heddle processor --config configs/workers/doc_extractor.yaml --nats-url nats://localhost:4222
uv run heddle pipeline --config configs/orchestrators/doc_pipeline_smart.yaml --nats-url nats://localhost:4222
```

Docling GPU/OCR tuning (MPS, OCR engine, batch sizes): `docs/docling-setup.md`
MCP gateway setup: `../heddle/docs/building-workflows.md` Part 11
