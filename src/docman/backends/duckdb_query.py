"""
DuckDB query and analytics backend for document retrieval.

Provides structured query operations against the documents table populated
by DuckDBIngestBackend. Supports full-text search (via DuckDB FTS),
attribute filtering, aggregate statistics, and single-document retrieval.

This is a standalone worker — not part of the ingestion pipeline. It
receives query requests and returns results from the DuckDB database.

Input:  {"action": "search|filter|stats|get|vector_search", ...action-specific params}
Output: {"results": [...], "total": int} or {"document": {...}}

Actions:
    search         — Full-text search across document content and summaries.
    filter         — Filter documents by type, table presence, page range.
    stats          — Aggregate statistics (counts, averages) grouped by column.
    get            — Retrieve a single document by ID.
    vector_search  — Semantic similarity search using vector embeddings.

See also:
    configs/workers/doc_query.yaml -- worker config with I/O schemas
    src/docman/backends/duckdb_ingest.py -- ingestion backend
    loom.worker.processor.SyncProcessingBackend -- base class for sync backends
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

import duckdb

from loom.worker.processor import BackendError, SyncProcessingBackend

logger = logging.getLogger(__name__)

# Columns returned in search/filter results. Excludes full_text to keep
# NATS messages small — use the "get" action to retrieve full content.
_RESULT_COLUMNS = [
    "id", "source_file", "file_ref", "page_count", "has_tables",
    "sections", "document_type", "classification_confidence",
    "summary", "key_points", "word_count", "text_preview", "ingested_at",
]


class DuckDBQueryError(BackendError):
    """Raised when a DuckDB query operation fails.

    Wraps underlying DuckDB exceptions with a descriptive message
    and the original cause attached via ``__cause__``.
    """


class DuckDBQueryBackend(SyncProcessingBackend):
    """SyncProcessingBackend that queries the DuckDB document database.

    Opens a read-only connection to the DuckDB database and dispatches
    to the appropriate query handler based on the ``action`` field in
    the payload.

    All queries use parameterized statements to prevent SQL injection.
    Results from search/filter actions exclude the ``full_text`` column
    to keep NATS messages small.

    Attributes:
        db_path: Default path to the DuckDB database file.
    """

    def __init__(self, db_path: str = "/tmp/docman-workspace/docman.duckdb") -> None:
        self.db_path = Path(db_path)

    def process_sync(self, payload: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        """Dispatch a query action against the DuckDB database.

        Args:
            payload: Must contain ``action`` (str). Additional fields
                depend on the action type.
            config: Worker config dict. May include ``db_path`` to
                override the constructor default.

        Returns:
            A dict with ``"output"`` (query results) and
            ``"model_used"`` (always ``"duckdb"``).

        Raises:
            ValueError: If the action is unknown.
            DuckDBQueryError: If the database query fails.
        """
        db_path = config.get("db_path", str(self.db_path))
        action = payload.get("action", "")

        handlers = {
            "search": self._search,
            "filter": self._filter,
            "stats": self._stats,
            "get": self._get,
            "vector_search": self._vector_search,
        }

        handler = handlers.get(action)
        if not handler:
            raise ValueError(
                f"Unknown action '{action}'. "
                f"Supported: {', '.join(handlers.keys())}"
            )

        try:
            conn = duckdb.connect(db_path, read_only=True)
            try:
                # Load FTS extension for search queries.
                conn.execute("LOAD fts")
                result = handler(conn, payload)
            finally:
                conn.close()
        except (ValueError, DuckDBQueryError):
            raise
        except Exception as exc:
            raise DuckDBQueryError(
                f"Query failed (action={action}): {exc}"
            ) from exc

        return {"output": result, "model_used": "duckdb"}

    def _search(self, conn: duckdb.DuckDBPyConnection, payload: dict[str, Any]) -> dict[str, Any]:
        """Full-text search using DuckDB FTS extension.

        Uses BM25 scoring to rank documents by relevance to the query.

        Args:
            conn: Open DuckDB connection.
            payload: Must contain ``query`` (str). Optional ``limit`` (int, default 20).

        Returns:
            ``{"results": [...], "total": int}`` with ranked documents.
        """
        query = payload.get("query", "")
        limit = min(payload.get("limit", 20), 100)

        if not query.strip():
            return {"results": [], "total": 0}

        cols = ", ".join(f"d.{c}" for c in _RESULT_COLUMNS)
        try:
            rows = conn.execute(
                f"""
                SELECT {cols}, fts.score
                FROM documents d
                JOIN (
                    SELECT *, fts_main_documents.match_bm25(id, ?, fields := 'full_text,summary,text_preview') AS score
                    FROM documents
                ) fts ON d.id = fts.id
                WHERE fts.score IS NOT NULL
                ORDER BY fts.score DESC
                LIMIT ?
                """,
                [query, limit],
            ).fetchall()
        except duckdb.Error:
            # FTS index may not exist yet (empty DB). Fall back to LIKE search.
            rows = conn.execute(
                f"""
                SELECT {cols}, 0.0 AS score
                FROM documents d
                WHERE d.full_text ILIKE ? OR d.summary ILIKE ? OR d.text_preview ILIKE ?
                ORDER BY d.ingested_at DESC
                LIMIT ?
                """,
                [f"%{query}%", f"%{query}%", f"%{query}%", limit],
            ).fetchall()

        columns = _RESULT_COLUMNS + ["score"]
        results = [self._row_to_dict(row, columns) for row in rows]

        total = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]

        return {"results": results, "total": len(results)}

    def _filter(self, conn: duckdb.DuckDBPyConnection, payload: dict[str, Any]) -> dict[str, Any]:
        """Filter documents by attribute criteria.

        Supports filtering by document_type, has_tables, and page
        count range. All filters are optional — omitted filters
        match all documents.

        Args:
            conn: Open DuckDB connection.
            payload: Optional fields: ``document_type`` (str),
                ``has_tables`` (bool), ``min_pages`` (int),
                ``max_pages`` (int), ``limit`` (int, default 20).

        Returns:
            ``{"results": [...], "total": int}`` with matching documents.
        """
        conditions = []
        params = []

        if "document_type" in payload:
            conditions.append("document_type = ?")
            params.append(payload["document_type"])

        if "has_tables" in payload:
            conditions.append("has_tables = ?")
            params.append(payload["has_tables"])

        if "min_pages" in payload:
            conditions.append("page_count >= ?")
            params.append(payload["min_pages"])

        if "max_pages" in payload:
            conditions.append("page_count <= ?")
            params.append(payload["max_pages"])

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        limit = min(payload.get("limit", 20), 100)

        cols = ", ".join(_RESULT_COLUMNS)
        rows = conn.execute(
            f"SELECT {cols} FROM documents {where} ORDER BY ingested_at DESC LIMIT ?",
            params + [limit],
        ).fetchall()

        results = [self._row_to_dict(row, _RESULT_COLUMNS) for row in rows]

        count_row = conn.execute(
            f"SELECT COUNT(*) FROM documents {where}",
            params,
        ).fetchone()
        total = count_row[0]

        return {"results": results, "total": total}

    def _stats(self, conn: duckdb.DuckDBPyConnection, payload: dict[str, Any]) -> dict[str, Any]:
        """Compute aggregate statistics grouped by a column.

        Args:
            conn: Open DuckDB connection.
            payload: Optional ``group_by`` (str, default "document_type").
                Must be one of the allowed grouping columns.

        Returns:
            ``{"results": [...], "total": int}`` where each result has
            the group key, count, and avg_page_count.
        """
        allowed_groups = {"document_type", "has_tables"}
        group_by = payload.get("group_by", "document_type")

        if group_by not in allowed_groups:
            raise ValueError(
                f"Invalid group_by '{group_by}'. Allowed: {', '.join(allowed_groups)}"
            )

        rows = conn.execute(
            f"""
            SELECT
                {group_by},
                COUNT(*) AS doc_count,
                ROUND(AVG(page_count), 1) AS avg_page_count,
                ROUND(AVG(word_count), 0) AS avg_word_count
            FROM documents
            GROUP BY {group_by}
            ORDER BY doc_count DESC
            """,
        ).fetchall()

        results = [
            {
                group_by: row[0],
                "doc_count": row[1],
                "avg_page_count": row[2],
                "avg_word_count": row[3],
            }
            for row in rows
        ]

        total_row = conn.execute("SELECT COUNT(*) FROM documents").fetchone()

        return {"results": results, "total": total_row[0]}

    def _get(self, conn: duckdb.DuckDBPyConnection, payload: dict[str, Any]) -> dict[str, Any]:
        """Retrieve a single document by ID, including full text.

        Args:
            conn: Open DuckDB connection.
            payload: Must contain ``document_id`` (str).

        Returns:
            ``{"document": {...}}`` with all fields including full_text.

        Raises:
            ValueError: If document_id is not provided.
            DuckDBQueryError: If the document is not found.
        """
        document_id = payload.get("document_id")
        if not document_id:
            raise ValueError("document_id is required for 'get' action")

        all_columns = _RESULT_COLUMNS + ["full_text"]
        cols = ", ".join(all_columns)
        row = conn.execute(
            f"SELECT {cols} FROM documents WHERE id = ?",
            [document_id],
        ).fetchone()

        if not row:
            raise DuckDBQueryError(f"Document not found: {document_id}")

        return {"document": self._row_to_dict(row, all_columns)}

    def _vector_search(
        self, conn: duckdb.DuckDBPyConnection, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Semantic similarity search using vector embeddings.

        Generates a query embedding via Ollama, then compares it against
        stored document embeddings using cosine similarity.

        Args:
            conn: Open DuckDB connection.
            payload: Must contain ``query`` (str). Optional ``limit``
                (int, default 5). Requires ``embedding`` config in worker
                config for the Ollama model/url.

        Returns:
            ``{"results": [...], "total": int}`` with similar documents.
        """
        query_text = payload.get("query", "")
        limit = min(payload.get("limit", 5), 100)

        if not query_text.strip():
            return {"results": [], "total": 0}

        # Generate query embedding via Ollama
        embedding_config = payload.get("embedding", {})
        from loom.worker.embeddings import OllamaEmbeddingProvider

        provider = OllamaEmbeddingProvider(
            model=embedding_config.get("model", "nomic-embed-text"),
            base_url=embedding_config.get("ollama_url"),
        )
        try:
            query_embedding = asyncio.run(provider.embed(query_text))
        except Exception as exc:
            raise DuckDBQueryError(
                f"Failed to generate query embedding: {exc}"
            ) from exc

        cols = ", ".join(f"d.{c}" for c in _RESULT_COLUMNS)

        rows = conn.execute(
            f"""
            SELECT {cols},
                   list_cosine_similarity(d.embedding, ?) AS similarity
            FROM documents d
            WHERE d.embedding IS NOT NULL
            ORDER BY similarity DESC
            LIMIT ?
            """,
            [query_embedding, limit],
        ).fetchall()

        columns = _RESULT_COLUMNS + ["similarity"]
        results = [self._row_to_dict(row, columns) for row in rows]

        return {"results": results, "total": len(results)}

    @staticmethod
    def _row_to_dict(row: tuple, columns: list[str]) -> dict[str, Any]:
        """Convert a DuckDB result row to a dict, parsing JSON columns.

        Args:
            row: Tuple of values from a DuckDB query.
            columns: Column names corresponding to the row values.

        Returns:
            A dict mapping column names to values, with JSON columns
            parsed back into Python objects.
        """
        result = {}
        json_columns = {"sections", "key_points"}

        for col, val in zip(columns, row):
            if col in json_columns and isinstance(val, str):
                try:
                    val = json.loads(val)
                except json.JSONDecodeError:
                    pass
            # Convert datetime to ISO string for JSON serialization.
            if col == "ingested_at" and val is not None:
                val = str(val)
            result[col] = val

        return result
