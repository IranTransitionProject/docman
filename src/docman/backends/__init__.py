"""Docman processing backends for Loom pipeline stages."""

from docman.backends.docling_backend import DoclingBackend
from docman.backends.duckdb_ingest import DuckDBIngestBackend
from docman.backends.duckdb_query import DocmanQueryBackend, DuckDBQueryBackend
from docman.backends.markitdown_backend import MarkItDownBackend
from docman.backends.smart_extractor import SmartExtractorBackend

__all__ = [
    "DoclingBackend",
    "DocmanQueryBackend",
    "DuckDBIngestBackend",
    "DuckDBQueryBackend",
    "MarkItDownBackend",
    "SmartExtractorBackend",
]
