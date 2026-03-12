"""
Docling-based document extraction backend.

Wraps IBM Docling to extract text, tables, and structure from PDF/DOCX files.
Runs synchronously in a thread pool to keep the event loop responsive.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

from loom.worker.processor import ProcessingBackend


class DoclingBackend(ProcessingBackend):
    """
    ProcessingBackend that uses Docling for document extraction.

    Expects payload: {"file_ref": "filename.pdf"}
    Config must include: workspace_dir

    Reads source file from workspace_dir, writes extracted JSON to workspace_dir,
    returns file_ref to extracted output + inline metadata summary.
    """

    def __init__(self, workspace_dir: str = "/tmp/docman-workspace"):
        self.workspace_dir = Path(workspace_dir)

    async def process(self, payload: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        file_ref = payload["file_ref"]
        workspace = Path(config.get("workspace_dir", str(self.workspace_dir)))

        # Validate path traversal
        source_path = (workspace / file_ref).resolve()
        if not str(source_path).startswith(str(workspace.resolve())):
            raise ValueError(f"Path traversal detected: {file_ref}")

        if not source_path.exists():
            raise FileNotFoundError(f"Source file not found: {source_path}")

        # Run Docling in thread pool (it's synchronous)
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, self._extract, source_path, workspace)

        return {"output": result, "model_used": "docling"}

    def _extract(self, source_path: Path, workspace: Path) -> dict[str, Any]:
        """Synchronous Docling extraction."""
        from docling.document_converter import DocumentConverter

        converter = DocumentConverter()
        doc_result = converter.convert(str(source_path))
        doc = doc_result.document

        # Extract text content
        text = doc.export_to_markdown()

        # Build output
        output_name = f"{source_path.stem}_extracted.json"
        output_path = workspace / output_name

        # Extract metadata
        sections = []
        for item in doc.iterate_items():
            if hasattr(item, "label") and item.label in ("section_header", "title"):
                sections.append(item.text if hasattr(item, "text") else str(item))

        has_tables = any(
            hasattr(item, "label") and item.label == "table"
            for item in doc.iterate_items()
        )

        # Estimate page count from document
        page_count = len(doc.pages) if hasattr(doc, "pages") else 1

        # Text preview (first ~500 words)
        words = text.split()
        text_preview = " ".join(words[:500])

        # Write extracted content to workspace
        extracted = {
            "text": text,
            "sections": sections,
            "has_tables": has_tables,
            "page_count": page_count,
        }
        output_path.write_text(json.dumps(extracted, indent=2))

        return {
            "file_ref": output_name,
            "page_count": page_count,
            "has_tables": has_tables,
            "sections": sections[:20],  # Cap at 20 section headers
            "text_preview": text_preview,
        }
