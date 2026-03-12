"""Docman processing backends for Loom pipeline stages."""
from docman.backends.docling_backend import DoclingBackend
from docman.backends.duckdb_ingest import DuckDBIngestBackend
from docman.backends.duckdb_query import DocmanQueryBackend, DuckDBQueryBackend

__all__ = ["DoclingBackend", "DuckDBIngestBackend", "DocmanQueryBackend", "DuckDBQueryBackend"]
