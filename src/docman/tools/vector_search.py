"""
DuckDB vector similarity search tool for LLM function-calling.

Uses embedding vectors stored in DuckDB to find semantically similar
documents. Query text is embedded via Ollama at search time, then
compared against stored vectors using DuckDB's ``list_cosine_similarity``.

Example knowledge_silos config::

    knowledge_silos:
      - name: "similar_docs"
        type: "tool"
        provider: "docman.tools.vector_search.DuckDBVectorTool"
        config:
          db_path: "/tmp/docman-workspace/docman.duckdb"
          description: "Find documents semantically similar to a query"
          embedding_model: "nomic-embed-text"
          ollama_url: "http://localhost:11434"

See also:
    src/docman/backends/duckdb_ingest.py -- generates and stores embeddings
    src/loom/worker/embeddings.py -- OllamaEmbeddingProvider
    src/loom/worker/tools.py -- SyncToolProvider base class
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import duckdb

from loom.worker.tools import SyncToolProvider

logger = logging.getLogger(__name__)

# Columns returned in vector search results (excludes full_text and embedding).
_RESULT_COLUMNS = [
    "id", "source_file", "document_type", "summary",
    "page_count", "has_tables", "ingested_at",
]


class DuckDBVectorTool(SyncToolProvider):
    """Semantic similarity search over DuckDB document embeddings.

    Generates a query embedding via Ollama, then uses DuckDB's
    ``list_cosine_similarity`` function to find the most similar
    documents by their stored embedding vectors.

    Only documents with non-null embeddings are searched.
    """

    def __init__(
        self,
        db_path: str,
        description: str = "Find semantically similar documents",
        embedding_model: str = "nomic-embed-text",
        ollama_url: str | None = None,
        max_results: int = 10,
    ) -> None:
        self.db_path = db_path
        self.description = description
        self.embedding_model = embedding_model
        self.ollama_url = ollama_url
        self.max_results = max_results

    def get_definition(self) -> dict[str, Any]:
        """Return tool definition for LLM function-calling."""
        return {
            "name": "find_similar_documents",
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language query to find similar documents",
                    },
                    "limit": {
                        "type": "integer",
                        "description": f"Max results (default: 5, max: {self.max_results})",
                    },
                },
                "required": ["query"],
            },
        }

    def execute_sync(self, arguments: dict[str, Any]) -> str:
        """Embed the query and search for similar documents."""
        query = arguments.get("query", "")
        limit = min(arguments.get("limit", 5), self.max_results)

        if not query.strip():
            return json.dumps({"results": [], "total": 0})

        # Generate query embedding via Ollama.
        query_embedding = self._embed_query(query)
        if query_embedding is None:
            return json.dumps({"error": "Failed to generate query embedding"})

        try:
            conn = duckdb.connect(self.db_path, read_only=True)
            try:
                result = self._similarity_search(conn, query_embedding, limit)
            finally:
                conn.close()
        except Exception as e:
            return json.dumps({"error": str(e)})

        return json.dumps(result, default=str)

    def _embed_query(self, text: str) -> list[float] | None:
        """Generate embedding for the query text."""
        from loom.worker.embeddings import OllamaEmbeddingProvider

        provider = OllamaEmbeddingProvider(
            model=self.embedding_model,
            base_url=self.ollama_url,
        )
        try:
            return asyncio.run(provider.embed(text))
        except Exception as exc:
            logger.warning(
                "vector_search.embed_query_failed",
                extra={"error": str(exc)},
            )
            return None

    def _similarity_search(
        self,
        conn: duckdb.DuckDBPyConnection,
        query_embedding: list[float],
        limit: int,
    ) -> dict[str, Any]:
        """Run cosine similarity search against stored embeddings."""
        cols = ", ".join(_RESULT_COLUMNS)

        rows = conn.execute(
            f"""
            SELECT {cols},
                   list_cosine_similarity(embedding, ?) AS similarity
            FROM documents
            WHERE embedding IS NOT NULL
            ORDER BY similarity DESC
            LIMIT ?
            """,
            [query_embedding, limit],
        ).fetchall()

        result_cols = _RESULT_COLUMNS + ["similarity"]
        results = [
            {col: val for col, val in zip(result_cols, row)}
            for row in rows
        ]

        return {"results": results, "total": len(results)}
