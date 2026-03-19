"""
Docman DuckDB query backend — thin subclass of loom.contrib.duckdb.

Provides Docman-specific schema defaults (table name, columns, filters,
stats groups) on top of the generic DuckDBQueryBackend from LOOM.

Input:  {"action": "search|filter|stats|get|vector_search", ...action-specific params}
Output: {"results": [...], "total": int} or {"document": {...}}

See Also:
    configs/workers/doc_query.yaml -- worker config with I/O schemas
    src/docman/backends/duckdb_ingest.py -- ingestion backend
"""

from __future__ import annotations

from loom.contrib.duckdb import (
    DuckDBQueryBackend as _BaseDuckDBQueryBackend,
)
from loom.contrib.duckdb import (
    DuckDBQueryError,
)

# Columns returned in search/filter results. Excludes full_text to keep
# NATS messages small — use the "get" action to retrieve full content.
_RESULT_COLUMNS = [
    "id",
    "source_file",
    "file_ref",
    "page_count",
    "has_tables",
    "sections",
    "document_type",
    "classification_confidence",
    "summary",
    "key_points",
    "word_count",
    "text_preview",
    "ingested_at",
]


class DocmanQueryBackend(_BaseDuckDBQueryBackend):
    """DuckDB query backend with Docman document schema defaults."""

    def __init__(self, db_path: str = "/tmp/docman-workspace/docman.duckdb") -> None:
        super().__init__(
            db_path=db_path,
            table_name="documents",
            result_columns=_RESULT_COLUMNS,
            json_columns={"sections", "key_points"},
            id_column="id",
            full_text_column="full_text",
            fts_fields="full_text,summary,text_preview",
            filter_fields={
                "document_type": "document_type = ?",
                "has_tables": "has_tables = ?",
                "min_pages": "page_count >= ?",
                "max_pages": "page_count <= ?",
            },
            stats_groups={"document_type", "has_tables"},
            stats_aggregates=[
                "COUNT(*) AS doc_count",
                "ROUND(AVG(page_count), 1) AS avg_page_count",
                "ROUND(AVG(word_count), 0) AS avg_word_count",
            ],
            default_order_by="ingested_at DESC",
        )


# Backward-compat alias so existing YAML configs continue to work:
#   processing_backend: "docman.backends.duckdb_query.DuckDBQueryBackend"
DuckDBQueryBackend = DocmanQueryBackend

__all__ = ["DocmanQueryBackend", "DuckDBQueryBackend", "DuckDBQueryError"]
