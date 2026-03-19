"""
DuckDB ingestion backend for document persistence.

Stores document metadata, classification, summaries, and full extracted text
into a DuckDB database. Runs as stage 4 of the doc_pipeline, receiving
aggregated results from the extract, classify, and summarize stages.

This backend also reads the full extracted text from the workspace JSON
file (written by DoclingBackend) and stores it in DuckDB, enabling
full-text search via the DuckDB FTS extension.

Pipeline position:
    doc_extractor -> doc_classifier -> doc_summarizer -> doc_ingest (this)

Input:  Aggregated pipeline results (source_file, extraction metadata,
        classification, summary).
Output: {"document_id": str, "status": "inserted", "source_file": str}

See Also:
    configs/workers/doc_ingest.yaml -- worker config with I/O schemas
    src/docman/backends/duckdb_query.py -- query/analytics backend
    loom.worker.processor.SyncProcessingBackend -- base class for sync backends
    loom.core.workspace.WorkspaceManager -- file-ref resolution with path safety
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import uuid
from pathlib import Path
from typing import Any

import duckdb
from loom.core.workspace import WorkspaceManager
from loom.worker.processor import BackendError, SyncProcessingBackend

logger = logging.getLogger(__name__)

# Max characters of text sent to the embedding model (nomic-embed-text context: ~8192 tokens).
_EMBED_TEXT_LIMIT = 8000


class DuckDBError(BackendError):
    """Raised when a DuckDB operation fails.

    Wraps underlying DuckDB or I/O exceptions with a descriptive message
    and the original cause attached via ``__cause__``.
    """


class DuckDBIngestBackend(SyncProcessingBackend):
    """SyncProcessingBackend that ingests document data into DuckDB.

    Receives aggregated pipeline results (extraction metadata, classification,
    summary) and persists them as a row in the ``documents`` table. Also reads
    the full extracted text from the workspace JSON file to enable full-text
    search.

    The database schema is created automatically on first use -- no separate
    migration step is required.

    Attributes:
        db_path: Default path to the DuckDB database file.
    """

    def __init__(self, db_path: str = "/tmp/docman-workspace/docman.duckdb") -> None:
        self.db_path = Path(db_path)

    def process_sync(self, payload: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        """Ingest document data into DuckDB.

        Reads the full extracted text from the workspace (via file_ref),
        then inserts a complete document record into the database.

        Args:
            payload: Aggregated pipeline results containing source_file,
                file_ref, extraction metadata, classification, and summary.
            config: Worker config dict. May include ``db_path`` and
                ``workspace_dir`` to override constructor defaults.

        Returns:
            A dict with ``"output"`` (document_id, status, source_file)
            and ``"model_used"`` (always ``"duckdb"``).

        Raises:
            DuckDBError: If database operations or workspace file reads fail.
        """
        db_path = config.get("db_path", str(self.db_path))
        document_id = str(uuid.uuid4())

        # Read full extracted text from workspace.
        full_text = self._read_full_text(payload.get("file_ref"), config)

        # Generate embedding if configured.
        embedding = self._generate_embedding(full_text, config)

        try:
            conn = duckdb.connect(db_path)
            try:
                self._ensure_schema(conn)
                self._insert_document(conn, document_id, payload, full_text, embedding)
            finally:
                conn.close()
        except DuckDBError:
            raise
        except Exception as exc:
            raise DuckDBError(
                f"Failed to ingest document '{payload.get('source_file', 'unknown')}': {exc}"
            ) from exc

        logger.info(
            "duckdb.ingestion_complete",
            extra={
                "document_id": document_id,
                "source_file": payload.get("source_file"),
                "document_type": payload.get("document_type"),
            },
        )

        return {
            "output": {
                "document_id": document_id,
                "status": "inserted",
                "source_file": payload.get("source_file", ""),
            },
            "model_used": "duckdb",
        }

    def _read_full_text(self, file_ref: str | None, config: dict[str, Any]) -> str:
        """Read the full extracted text from the workspace JSON file.

        The extracted JSON is written by DoclingBackend and contains
        a ``"text"`` field with the full markdown content.

        Args:
            file_ref: Filename of the extracted JSON in the workspace.
                If None or empty, returns an empty string.
            config: Worker config dict with ``workspace_dir``.

        Returns:
            The full extracted text, or empty string if unavailable.
        """
        if not file_ref:
            return ""

        ws_dir = config.get("workspace_dir", str(self.db_path.parent))
        ws = WorkspaceManager(ws_dir)
        try:
            extracted = ws.read_json(file_ref)
            return extracted.get("text", "")
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            logger.warning(
                "duckdb.full_text_read_failed",
                extra={"file_ref": file_ref, "error": str(exc)},
            )
            return ""

    def _generate_embedding(self, full_text: str, config: dict[str, Any]) -> list[float] | None:
        """Generate a vector embedding for the document text.

        Uses the Ollama embedding provider when ``embedding`` config is
        present. Returns ``None`` when embedding is not configured or
        the text is empty.

        Args:
            full_text: Full extracted text to embed (truncated to
                ``_EMBED_TEXT_LIMIT`` characters).
            config: Worker config dict with optional ``embedding`` section
                containing ``model`` and ``ollama_url``.

        Returns:
            Embedding vector as a list of floats, or None.
        """
        embedding_config = config.get("embedding")
        if not embedding_config or not full_text:
            return None

        # Import here to avoid hard dependency when embeddings aren't used.
        from loom.worker.embeddings import OllamaEmbeddingProvider

        provider = OllamaEmbeddingProvider(
            model=embedding_config.get("model", "nomic-embed-text"),
            base_url=embedding_config.get("ollama_url"),
        )

        try:
            embedding = asyncio.run(provider.embed(full_text[:_EMBED_TEXT_LIMIT]))
            logger.info(
                "duckdb.embedding_generated",
                extra={"dimensions": len(embedding)},
            )
            return embedding
        except Exception as exc:
            logger.warning(
                "duckdb.embedding_failed",
                extra={"error": str(exc)},
            )
            return None

    def _ensure_schema(self, conn: duckdb.DuckDBPyConnection) -> None:
        """Create the documents table and FTS index if they don't exist.

        Uses DuckDB's ``fts`` extension for full-text search on the
        ``full_text`` and ``summary`` columns.

        Args:
            conn: Open DuckDB connection.
        """
        conn.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id                        VARCHAR PRIMARY KEY,
                source_file               VARCHAR NOT NULL,
                file_ref                  VARCHAR,
                page_count                INTEGER,
                has_tables                BOOLEAN,
                sections                  JSON,
                document_type             VARCHAR,
                classification_confidence DOUBLE,
                classification_reasoning  VARCHAR,
                summary                   TEXT,
                key_points                JSON,
                word_count                INTEGER,
                full_text                 TEXT,
                text_preview              TEXT,
                embedding                 FLOAT[],
                ingested_at               TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Install and load the FTS extension, then create the index.
        # PRAGMA create_fts_index is idempotent-safe with IF NOT EXISTS
        # only in newer DuckDB versions, so we catch and ignore if it
        # already exists.
        conn.execute("INSTALL fts")
        conn.execute("LOAD fts")
        with contextlib.suppress(duckdb.Error):
            # Index may already exist or table may be empty; both are fine.
            conn.execute("""
                PRAGMA create_fts_index(
                    'documents', 'id', 'full_text', 'summary', 'text_preview',
                    overwrite=1
                )
            """)

        # Create summary view for LLM tool access (excludes full_text).
        conn.execute("""
            CREATE VIEW IF NOT EXISTS document_summaries AS
            SELECT id, source_file, document_type, summary, key_points,
                   page_count, has_tables, classification_confidence, ingested_at
            FROM documents
        """)

    def _insert_document(
        self,
        conn: duckdb.DuckDBPyConnection,
        document_id: str,
        payload: dict[str, Any],
        full_text: str,
        embedding: list[float] | None = None,
    ) -> None:
        """Insert or replace a document record in the database.

        Uses INSERT OR REPLACE for idempotent re-processing of the
        same document.

        Args:
            conn: Open DuckDB connection.
            document_id: Generated UUID for this document.
            payload: Aggregated pipeline results.
            full_text: Full extracted markdown text from workspace.
            embedding: Optional vector embedding for similarity search.
        """
        conn.execute(
            """
            INSERT OR REPLACE INTO documents (
                id, source_file, file_ref, page_count, has_tables, sections,
                document_type, classification_confidence, classification_reasoning,
                summary, key_points, word_count, full_text, text_preview, embedding
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                document_id,
                payload.get("source_file", ""),
                payload.get("file_ref"),
                payload.get("page_count"),
                payload.get("has_tables"),
                json.dumps(payload.get("sections", [])),
                payload.get("document_type"),
                payload.get("classification_confidence"),
                payload.get("classification_reasoning"),
                payload.get("summary"),
                json.dumps(payload.get("key_points", [])),
                payload.get("word_count"),
                full_text,
                payload.get("text_preview", ""),
                embedding,
            ],
        )
