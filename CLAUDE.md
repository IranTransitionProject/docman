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
docs/
  docling-setup.md  # Docling installation, configuration, and performance tuning guide
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
- Path traversal validation: file_ref must resolve within workspace_dir
- `text_preview` (first ~500 words) is included inline in extractor output so the classifier doesn't need file access
- Workspace directory is shared filesystem, configured per deployment

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
# Terminal 6: loom pipeline --config configs/orchestrators/doc_pipeline.yaml --nats-url nats://localhost:4222
# Submit:     loom submit "Process document" --context file_ref=test.pdf --nats-url nats://localhost:4222
```

## Current state

The following items are **implemented and working**:
- DoclingBackend (`src/docman/backends/docling_backend.py`) — complete with path traversal validation, configurable Docling tuning via backend_config
- Worker configs for all 3 stages with I/O schemas — complete
- Pipeline config (`configs/orchestrators/doc_pipeline.yaml`) — complete
- 2 unit tests pass (path traversal, file not found validation)

## What to implement next

1. **Happy-path test** — Mock DocumentConverter to test the full extraction flow without a real PDF
2. **Summarizer file_ref resolution** — LLMWorker needs to read file_ref from workspace and inject content into the prompt
3. **End-to-end test** — With NATS, Redis, and Ollama running locally
4. **Error handling in DoclingBackend** — Wrap Docling calls in try/except for corrupt PDFs, unsupported formats
5. **Remove unused imports** — `json/Path/MagicMock/patch` in test file

## Known issues

- `asyncio.get_event_loop()` is deprecated — should use `asyncio.get_running_loop()` in docling_backend.py
- `import asyncio` is inside test functions instead of at module level
- The summarizer stage can't actually read extracted text from workspace (see Data flow section)

## Environment

- Apple Silicon Mac
- Python >=3.11 (pyproject.toml), recommend 3.13 for compatibility
- Docling >=2.0.0 for document extraction (pulls torch, torchvision)
- Ollama for local LLM tier (llama3.2:3b recommended)
