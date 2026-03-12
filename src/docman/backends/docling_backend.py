"""
Docling-based document extraction backend.

Wraps IBM Docling to extract text, tables, and structure from PDF/DOCX files.
Runs synchronously in a thread pool to keep the event loop responsive.

This is the first stage in DocMan's pipeline:
    doc_extractor (this) → doc_classifier → doc_summarizer

Input:  {"file_ref": "filename.pdf"}  (relative to workspace_dir)
Output: {"file_ref": "filename_extracted.json", "page_count": N,
         "has_tables": bool, "sections": [...], "text_preview": "..."}

The extracted JSON is written to workspace_dir and contains the full
document text. Subsequent stages reference it via file_ref to avoid
passing large text through NATS messages.

Docling tuning options can be passed via backend_config in the worker YAML:
    device:            "mps" | "cpu" | "cuda" | "auto" (default: "auto")
    num_threads:       int (default: system default)
    ocr_engine:        "ocrmac" | "easyocr" | "tesseract" (default: "ocrmac" on macOS)
    layout_batch_size: int (default: 4)
    ocr_batch_size:    int (default: 4)
    do_ocr:            bool (default: true)
    do_table_structure: bool (default: true)

See also:
    configs/workers/doc_extractor.yaml — worker config with I/O schemas
    docs/docling-setup.md — full Docling configuration and tuning guide
    loom.worker.processor.ProcessorWorker — the worker that runs this backend
"""
from __future__ import annotations

import asyncio
import json
import platform
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
        """Extract text and structure from a document using Docling.

        The config dict comes from the worker's YAML config (backend_config section).
        It may override workspace_dir from the constructor default, and it supplies
        Docling tuning options (device, ocr_engine, batch sizes, etc.).

        Returns a dict with "output" (the extraction result) and "model_used" ("docling").
        The ProcessorWorker unpacks this and publishes the TaskResult.
        """
        file_ref = payload["file_ref"]
        workspace = Path(config.get("workspace_dir", str(self.workspace_dir)))

        # Validate path traversal
        source_path = (workspace / file_ref).resolve()
        if not str(source_path).startswith(str(workspace.resolve())):
            raise ValueError(f"Path traversal detected: {file_ref}")

        if not source_path.exists():
            raise FileNotFoundError(f"Source file not found: {source_path}")

        # Run Docling in thread pool (it's synchronous and CPU-intensive).
        # FIXME: asyncio.get_event_loop() is deprecated in Python 3.10+.
        # Use asyncio.get_running_loop() instead.
        loop = asyncio.get_event_loop()
        # TODO: Consider wrapping _extract() in try/except to handle Docling errors
        # (corrupt PDFs, unsupported formats, OOM on large files) and return a
        # structured error instead of letting the exception propagate as a raw traceback.
        result = await loop.run_in_executor(
            None, self._extract, source_path, workspace, config
        )

        return {"output": result, "model_used": "docling"}

    def _build_converter(self, config: dict[str, Any]):
        """Build a DocumentConverter with settings from backend_config.

        Reads tuning options from the config dict (sourced from the worker YAML's
        backend_config section). Falls back to sensible defaults for Apple Silicon.

        See docs/docling-setup.md for full configuration reference.
        """
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling.datamodel.pipeline_options import (
            PdfPipelineOptions,
            AcceleratorOptions,
            TableStructureOptions,
        )
        from docling.datamodel.base_models import InputFormat

        # --- Accelerator options ---
        device = config.get("device", "auto")
        num_threads = config.get("num_threads", 8 if platform.machine() == "arm64" else 4)

        accel = AcceleratorOptions(
            device=device,
            num_threads=num_threads,
        )

        # --- OCR options ---
        do_ocr = config.get("do_ocr", True)
        ocr_options = None
        if do_ocr:
            ocr_engine = config.get("ocr_engine", "ocrmac" if platform.system() == "Darwin" else "easyocr")
            if ocr_engine == "ocrmac":
                from docling.datamodel.pipeline_options import OcrMacOptions
                ocr_options = OcrMacOptions(recognition="accurate")
            elif ocr_engine == "easyocr":
                from docling.datamodel.pipeline_options import EasyOcrOptions
                ocr_options = EasyOcrOptions()
            elif ocr_engine == "tesseract":
                from docling.datamodel.pipeline_options import TesseractOcrOptions
                ocr_options = TesseractOcrOptions()

        # --- Table structure ---
        do_table_structure = config.get("do_table_structure", True)
        table_options = TableStructureOptions(do_cell_matching=True) if do_table_structure else None

        # --- Pipeline options ---
        pipeline_kwargs = {
            "accelerator_options": accel,
            "do_ocr": do_ocr,
            "do_table_structure": do_table_structure,
            "layout_batch_size": config.get("layout_batch_size", 4),
            "ocr_batch_size": config.get("ocr_batch_size", 4),
        }
        if ocr_options:
            pipeline_kwargs["ocr_options"] = ocr_options
        if table_options:
            pipeline_kwargs["table_structure_options"] = table_options

        pipeline_options = PdfPipelineOptions(**pipeline_kwargs)

        return DocumentConverter(
            allowed_formats=[InputFormat.PDF, InputFormat.DOCX],
            format_options={
                InputFormat.PDF: PdfFormatOption(
                    pipeline_options=pipeline_options,
                ),
            },
        )

    def _extract(self, source_path: Path, workspace: Path, config: dict[str, Any]) -> dict[str, Any]:
        """Synchronous Docling extraction (runs in thread pool).

        Imports DocumentConverter lazily to avoid loading Docling (and its
        heavy torch dependency) at module import time.

        Args:
            source_path: Absolute path to the source document.
            workspace: Workspace directory for writing extracted output.
            config: backend_config from the worker YAML (Docling tuning options).
        """
        converter = self._build_converter(config)
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

        # Write extracted content to workspace.
        # TODO: Handle write errors (disk full, permissions) gracefully.
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
