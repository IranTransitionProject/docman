# Docman

**Document processing pipeline built on the Loom framework.**

Docman extracts content from PDF, DOCX, PPTX, XLSX, and HTML files using an adaptive two-tier extraction strategy (MarkItDown for speed, Docling for depth), with LLM-based classification and summarization.

## Quick start

```bash
# Install dependencies (requires Python 3.11+)
uv sync --extra dev

# Run unit tests
uv run pytest tests/ -v

# Build docs locally
uv sync --extra docs
uv run mkdocs serve
```

## Pipeline

| Stage | Worker | Backend | Description |
|-------|--------|---------|-------------|
| 1 | `doc_extractor` | SmartExtractorBackend | Extract text, tables, structure |
| 2 | `doc_classifier` | LLM | Classify document type |
| 3 | `doc_summarizer` | LLM | Summarize based on type |
| 4 | `doc_ingest` | DuckDBIngestBackend | Persist to DuckDB |

## Extraction backends

- **MarkItDown** — Fast, lightweight, no ML dependencies
- **Docling** — Deep extraction with OCR and table structure recognition
- **SmartExtractor** (recommended) — MarkItDown first, Docling fallback

## Project links

- [Loom framework](https://irantransitionproject.github.io/loom/)
- [GitHub repository](https://github.com/IranTransitionProject/docman)
