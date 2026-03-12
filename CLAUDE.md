# CLAUDE.md — Docman project context

## What this project is

Docman is a test project that evaluates the Loom framework architecture. It implements a document processing pipeline using Docling for PDF/DOCX extraction, with LLM-based classification and summarization stages.

This is a **consumer** of the Loom framework — it provides concrete worker configs, processing backends, and pipeline definitions. The Loom framework itself lives in a separate repo.

## Project structure

```
src/docman/
  backends/       # ProcessingBackend implementations (DoclingBackend)
configs/
  workers/        # YAML configs for doc_extractor, doc_classifier, doc_summarizer
  orchestrators/  # Pipeline config (doc_pipeline.yaml)
tests/            # Unit tests (mock backends, no infrastructure)
```

## Relationship to Loom

Docman depends on `loom` as a package. It uses:
- `ProcessingBackend` ABC — DoclingBackend implements this
- `ProcessorWorker` — runs DoclingBackend via `loom processor` CLI
- `LLMWorker` — runs classifier and summarizer via `loom worker` CLI
- `PipelineOrchestrator` — orchestrates the 3-stage pipeline via `loom pipeline` CLI

The CLI loads backends by fully qualified class path from worker configs:
```yaml
processing_backend: "docman.backends.docling_backend.DoclingBackend"
```

## Pipeline stages

1. **doc_extractor** (ProcessorWorker + DoclingBackend) — Docling extracts text, tables, figures from PDF/DOCX. Writes extracted JSON to workspace, returns file_ref + metadata summary.
2. **doc_classifier** (LLMWorker) — LLM classifies document type from text_preview + metadata. Returns document_type, confidence, reasoning.
3. **doc_summarizer** (LLMWorker) — LLM summarizes based on document type and extracted content. Returns summary, key_points, word_count.

## Data flow

- Large data passes via **file references** in a shared workspace directory (`--workspace-dir`)
- Messages carry only file_ref strings, not inline content
- DoclingBackend reads source file from workspace, writes extracted JSON to workspace
- Summarizer worker reads extracted text from workspace via file_ref

## Key design rules

- DoclingBackend runs Docling synchronously in a thread pool (`asyncio.run_in_executor`)
- Path traversal validation: file_ref must resolve within workspace_dir
- `text_preview` (first ~500 words) is included inline in extractor output so the classifier doesn't need file access
- Workspace directory is shared filesystem, configured per deployment

## Build and test commands

```bash
# Create venv and install
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Run unit tests (no infrastructure needed)
pytest tests/ -v

# Run with infrastructure (needs NATS + Loom installed)
# Terminal 1: docker run -p 4222:4222 nats:latest
# Terminal 2: loom router
# Terminal 3: loom processor --config configs/workers/doc_extractor.yaml --workspace-dir /tmp/docman-workspace
# Terminal 4: loom worker --config configs/workers/doc_classifier.yaml --tier local
# Terminal 5: loom worker --config configs/workers/doc_summarizer.yaml --tier standard
# Terminal 6: loom pipeline --config configs/orchestrators/doc_pipeline.yaml --workspace-dir /tmp/docman-workspace
# Submit:     loom submit "Process document" --context file_ref=test.pdf
```

## What to implement next

1. **DoclingBackend** (`src/docman/backends/docling_backend.py`) — ProcessingBackend that wraps Docling
2. **Worker configs** — YAML configs for all 3 stages with I/O schemas
3. **Pipeline config** — `configs/orchestrators/doc_pipeline.yaml` wiring the 3 stages
4. **Tests** — Unit tests with mock Docling, backend path validation tests
5. **End-to-end test** — With NATS running locally on M1 Mac

## Environment

- M1 Mac (modest performance, sufficient for basic testing)
- Python 3.12
- Docling >=2.0.0 for document extraction
- Ollama for local LLM tier
