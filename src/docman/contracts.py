"""Pydantic I/O contracts for Docman workers.

Each model defines the typed input or output schema for a pipeline stage
or standalone worker.  These are the **source of truth** — worker YAML
configs reference them via ``input_schema_ref`` / ``output_schema_ref``,
and Loom's ``resolve_schema_refs()`` converts them to JSON Schema at load
time.

Models:
    Extraction stage  — ExtractorInput, ExtractorOutput
    Classification    — ClassifierInput, ClassifierOutput
    Summarization     — SummarizerInput, SummarizerOutput
    Ingestion         — IngestInput, IngestOutput
    Query             — QueryInput, QueryOutput
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Extraction (doc_extractor / doc_extractor_smart)
# ---------------------------------------------------------------------------


class ExtractorInput(BaseModel):
    """Input for the extraction stage."""

    file_ref: str = Field(..., description="Filename relative to workspace directory")


class ExtractorOutput(BaseModel):
    """Output from the extraction stage (shared by Docling, MarkItDown, and Smart backends)."""

    file_ref: str = Field(..., description="Filename of extracted JSON in workspace")
    page_count: int = Field(..., description="Number of pages detected")
    has_tables: bool = Field(..., description="Whether tables were found")
    sections: list[str] = Field(
        ..., description="Section headers found in document (max 20)"
    )
    text_preview: str = Field(..., description="First ~500 words of extracted text")


# ---------------------------------------------------------------------------
# Classification (doc_classifier)
# ---------------------------------------------------------------------------

DOCUMENT_TYPES = Literal[
    "invoice",
    "report",
    "letter",
    "memo",
    "contract",
    "resume",
    "academic_paper",
    "manual",
    "form",
    "other",
]


class ClassifierInput(BaseModel):
    """Input for the classification stage."""

    text_preview: str = Field(..., description="First ~500 words of document text")
    page_count: int | None = None
    has_tables: bool | None = None
    sections: list[str] | None = Field(
        default=None, description="Section headers from the document"
    )


class ClassifierOutput(BaseModel):
    """Output from the classification stage."""

    document_type: str = Field(..., description="Classified document type")
    confidence: float = Field(..., ge=0.0, le=1.0)
    reasoning: str = Field(..., description="Brief explanation of classification")


# ---------------------------------------------------------------------------
# Summarization (doc_summarizer)
# ---------------------------------------------------------------------------


class SummarizerInput(BaseModel):
    """Input for the summarization stage."""

    file_ref: str = Field(
        ..., description="Filename of extracted JSON in workspace (contains full text)"
    )
    document_type: str = Field(
        ..., description="Classified document type from previous stage"
    )


class SummarizerOutput(BaseModel):
    """Output from the summarization stage."""

    summary: str
    key_points: list[str]
    word_count: int


# ---------------------------------------------------------------------------
# Ingestion (doc_ingest)
# ---------------------------------------------------------------------------


class IngestInput(BaseModel):
    """Input for the ingestion stage — aggregated from all prior stages."""

    source_file: str = Field(..., description="Original filename of the source document")
    file_ref: str | None = Field(
        default=None, description="Filename of extracted JSON in workspace"
    )
    page_count: int | None = None
    has_tables: bool | None = None
    sections: list[str] | None = Field(
        default=None, description="Section headers found in document"
    )
    text_preview: str | None = Field(
        default=None, description="First ~500 words of extracted text"
    )
    document_type: str | None = Field(
        default=None, description="Classification result"
    )
    classification_confidence: float | None = None
    classification_reasoning: str | None = None
    summary: str | None = Field(
        default=None, description="Document summary from summarizer"
    )
    key_points: list[str] | None = Field(
        default=None, description="Key points extracted by summarizer"
    )
    word_count: int | None = None


class IngestOutput(BaseModel):
    """Output from the ingestion stage."""

    document_id: str = Field(..., description="UUID assigned to the ingested document")
    status: str = Field(..., description="Ingestion status (inserted)")
    source_file: str = Field(..., description="Original filename echoed back")


# ---------------------------------------------------------------------------
# Query (doc_query — standalone, not part of pipeline)
# ---------------------------------------------------------------------------


class QueryInput(BaseModel):
    """Input for the query worker."""

    action: Literal["search", "filter", "stats", "get", "vector_search"] = Field(
        ..., description="Query action"
    )
    query: str | None = Field(
        default=None, description="Search query text (for 'search' action)"
    )
    document_id: str | None = Field(
        default=None, description="Document UUID (for 'get' action)"
    )
    document_type: str | None = Field(
        default=None, description="Filter by document type"
    )
    has_tables: bool | None = Field(
        default=None, description="Filter by table presence"
    )
    min_pages: int | None = Field(default=None, description="Minimum page count filter")
    max_pages: int | None = Field(default=None, description="Maximum page count filter")
    group_by: str | None = Field(
        default=None, description="Column to group by (for 'stats' action)"
    )
    limit: int | None = Field(
        default=None, description="Maximum results to return (default: 20, max: 100)"
    )
    embedding: dict[str, Any] | None = Field(
        default=None, description="Embedding config for vector_search"
    )


class QueryOutput(BaseModel):
    """Output from the query worker."""

    results: list[dict[str, Any]] | None = Field(
        default=None, description="List of matching documents or aggregated stats"
    )
    total: int | None = Field(default=None, description="Total matching count")
    document: dict[str, Any] | None = Field(
        default=None, description="Single document record (for 'get' action)"
    )
