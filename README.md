# Docman

Document processing pipeline built on the [Loom](https://github.com/IranTransitionProject/loom) framework.

A test project that evaluates Loom's actor-based architecture with a real-world pipeline: PDF/DOCX extraction (Docling) → classification (LLM) → summarization (LLM).

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/ -v
```

See `CLAUDE.md` for full architecture and run instructions.
