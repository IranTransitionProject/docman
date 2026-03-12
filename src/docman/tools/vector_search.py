"""
Docman vector similarity search — thin wrapper around loom.contrib.duckdb.

Provides Docman-specific defaults (table, columns, tool name) on top of the
generic DuckDBVectorTool from LOOM.

Example knowledge_silos config::

    knowledge_silos:
      - name: "similar_docs"
        type: "tool"
        provider: "docman.tools.vector_search.DuckDBVectorTool"
        config:
          db_path: "/tmp/docman-workspace/docman.duckdb"
          description: "Find documents semantically similar to a query"
"""
from __future__ import annotations

from loom.contrib.duckdb import DuckDBVectorTool as _BaseDuckDBVectorTool

# Docman-specific columns returned in search results.
_DOCMAN_RESULT_COLUMNS = [
    "id", "source_file", "document_type", "summary",
    "page_count", "has_tables", "ingested_at",
]


class DuckDBVectorTool(_BaseDuckDBVectorTool):
    """Docman vector search tool with document-specific defaults."""

    def __init__(
        self,
        db_path: str,
        description: str = "Find semantically similar documents",
        embedding_model: str = "nomic-embed-text",
        ollama_url: str | None = None,
        max_results: int = 10,
    ) -> None:
        super().__init__(
            db_path=db_path,
            table_name="documents",
            result_columns=_DOCMAN_RESULT_COLUMNS,
            tool_name="find_similar_documents",
            description=description,
            embedding_model=embedding_model,
            ollama_url=ollama_url,
            max_results=max_results,
        )
