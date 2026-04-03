"""
Tests for DuckDBIngestBackend (unit tests -- uses in-memory DuckDB).

Covers:
    1. Happy-path ingestion -- insert document, verify data in DB.
    2. Full-text storage -- verify full text is read from workspace JSON.
    3. Idempotent re-insert -- verify INSERT OR REPLACE works.
    4. Error handling -- missing workspace file, DB errors.

DuckDBIngestBackend extends SyncProcessingBackend, so process_sync() is
tested directly (no asyncio needed for unit tests).
"""

import json

import duckdb
import pytest
from heddle.worker.processor import BackendError

from docman.backends.duckdb_ingest import DuckDBError, DuckDBIngestBackend

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def workspace(tmp_path):
    """Provide an isolated temporary workspace directory."""
    return tmp_path


@pytest.fixture
def db_path(tmp_path):
    """Provide a temporary DuckDB database path."""
    return str(tmp_path / "test.duckdb")


@pytest.fixture
def backend(db_path):
    """Create a DuckDBIngestBackend with a temporary database."""
    return DuckDBIngestBackend(db_path=db_path)


@pytest.fixture
def config(db_path, workspace):
    """Standard config dict for tests."""
    return {"db_path": db_path, "workspace_dir": str(workspace)}


@pytest.fixture
def sample_payload():
    """A complete pipeline payload with all fields populated."""
    return {
        "source_file": "report.pdf",
        "file_ref": "report_extracted.json",
        "page_count": 10,
        "has_tables": True,
        "sections": ["Introduction", "Methods", "Results"],
        "text_preview": "This is a research report about climate change.",
        "document_type": "report",
        "classification_confidence": 0.92,
        "classification_reasoning": "Multi-section document with research methodology.",
        "summary": "A comprehensive study on climate change impacts.",
        "key_points": ["Rising temperatures", "Sea level rise", "Policy recommendations"],
        "word_count": 5000,
    }


@pytest.fixture
def extracted_json(workspace):
    """Write a mock extracted JSON file to the workspace."""
    data = {
        "text": "# Introduction\n\nThis is the full extracted text of the document.",
        "sections": ["Introduction", "Methods", "Results"],
        "has_tables": True,
        "page_count": 10,
    }
    path = workspace / "report_extracted.json"
    path.write_text(json.dumps(data))
    return path


# ---------------------------------------------------------------------------
# Basic validation tests
# ---------------------------------------------------------------------------


class TestValidation:
    """Tests for input validation and error hierarchy."""

    def test_duckdb_error_is_backend_error(self):
        """DuckDBError should be a subclass of BackendError."""
        assert issubclass(DuckDBError, BackendError)

    def test_missing_source_file_still_inserts(self, backend, config, workspace):
        """A payload without source_file should still insert (defaults to empty)."""
        (workspace / "empty_extracted.json").write_text(json.dumps({"text": ""}))

        result = backend.process_sync(
            {"file_ref": "empty_extracted.json"},
            config,
        )

        assert result["output"]["status"] == "inserted"
        assert result["output"]["source_file"] == ""


# ---------------------------------------------------------------------------
# Happy-path ingestion tests
# ---------------------------------------------------------------------------


class TestIngestion:
    """Tests for the full ingestion flow."""

    def test_ingest_produces_expected_output(self, backend, config, sample_payload, extracted_json):
        """Ingestion should return document_id, status, and source_file."""
        result = backend.process_sync(sample_payload, config)

        assert result["model_used"] == "duckdb"
        output = result["output"]
        assert output["status"] == "inserted"
        assert output["source_file"] == "report.pdf"
        assert len(output["document_id"]) == 36  # UUID format

    def test_data_persisted_in_database(
        self, backend, config, sample_payload, extracted_json, db_path
    ):
        """Verify the document is actually stored in DuckDB with correct values."""
        result = backend.process_sync(sample_payload, config)
        doc_id = result["output"]["document_id"]

        conn = duckdb.connect(db_path, read_only=True)
        try:
            row = conn.execute(
                "SELECT source_file, document_type, page_count, has_tables, summary "
                "FROM documents WHERE id = ?",
                [doc_id],
            ).fetchone()
        finally:
            conn.close()

        assert row is not None
        assert row[0] == "report.pdf"
        assert row[1] == "report"
        assert row[2] == 10
        assert row[3] is True
        assert row[4] == "A comprehensive study on climate change impacts."

    def test_sections_stored_as_json(
        self, backend, config, sample_payload, extracted_json, db_path
    ):
        """Sections and key_points should be stored as JSON arrays."""
        result = backend.process_sync(sample_payload, config)
        doc_id = result["output"]["document_id"]

        conn = duckdb.connect(db_path, read_only=True)
        try:
            row = conn.execute(
                "SELECT sections, key_points FROM documents WHERE id = ?",
                [doc_id],
            ).fetchone()
        finally:
            conn.close()

        sections = json.loads(row[0])
        key_points = json.loads(row[1])
        assert sections == ["Introduction", "Methods", "Results"]
        assert "Rising temperatures" in key_points

    def test_schema_created_automatically(
        self, backend, config, sample_payload, extracted_json, db_path
    ):
        """The documents table should be created on first use."""
        # DB file doesn't exist yet -- process_sync should create it.
        backend.process_sync(sample_payload, config)

        conn = duckdb.connect(db_path, read_only=True)
        try:
            tables = conn.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_name = 'documents'"
            ).fetchall()
        finally:
            conn.close()

        assert len(tables) == 1


# ---------------------------------------------------------------------------
# Full-text storage tests
# ---------------------------------------------------------------------------


class TestFullTextStorage:
    """Tests for reading and storing full extracted text from workspace."""

    def test_full_text_read_from_workspace(
        self, backend, config, sample_payload, extracted_json, db_path
    ):
        """Full text should be read from the workspace JSON and stored in DB."""
        result = backend.process_sync(sample_payload, config)
        doc_id = result["output"]["document_id"]

        conn = duckdb.connect(db_path, read_only=True)
        try:
            row = conn.execute(
                "SELECT full_text FROM documents WHERE id = ?",
                [doc_id],
            ).fetchone()
        finally:
            conn.close()

        assert "full extracted text" in row[0]

    def test_missing_workspace_file_stores_empty_text(self, backend, config, db_path):
        """If the workspace JSON doesn't exist, full_text should be empty."""
        payload = {
            "source_file": "missing.pdf",
            "file_ref": "nonexistent_extracted.json",
        }

        result = backend.process_sync(payload, config)
        doc_id = result["output"]["document_id"]

        conn = duckdb.connect(db_path, read_only=True)
        try:
            row = conn.execute(
                "SELECT full_text FROM documents WHERE id = ?",
                [doc_id],
            ).fetchone()
        finally:
            conn.close()

        assert row[0] == ""

    def test_no_file_ref_stores_empty_text(self, backend, config, db_path):
        """If file_ref is not provided, full_text should be empty."""
        payload = {"source_file": "doc.pdf"}

        result = backend.process_sync(payload, config)
        doc_id = result["output"]["document_id"]

        conn = duckdb.connect(db_path, read_only=True)
        try:
            row = conn.execute(
                "SELECT full_text FROM documents WHERE id = ?",
                [doc_id],
            ).fetchone()
        finally:
            conn.close()

        assert row[0] == ""


# ---------------------------------------------------------------------------
# Idempotent re-insert test
# ---------------------------------------------------------------------------


class TestIdempotency:
    """Tests for idempotent document re-processing."""

    def test_multiple_inserts_create_separate_records(
        self, backend, config, sample_payload, extracted_json, db_path
    ):
        """Each ingestion creates a new UUID, so multiple runs create separate records."""
        result1 = backend.process_sync(sample_payload, config)
        result2 = backend.process_sync(sample_payload, config)

        assert result1["output"]["document_id"] != result2["output"]["document_id"]

        conn = duckdb.connect(db_path, read_only=True)
        try:
            count = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        finally:
            conn.close()

        assert count == 2


# ---------------------------------------------------------------------------
# Embedding tests
# ---------------------------------------------------------------------------


class TestEmbeddingGeneration:
    """Tests for optional vector embedding generation during ingestion."""

    def test_no_embedding_config_stores_null(
        self, backend, config, sample_payload, extracted_json, db_path
    ):
        """Without embedding config, embedding column is null."""
        result = backend.process_sync(sample_payload, config)
        doc_id = result["output"]["document_id"]

        conn = duckdb.connect(db_path, read_only=True)
        try:
            row = conn.execute("SELECT embedding FROM documents WHERE id = ?", [doc_id]).fetchone()
        finally:
            conn.close()

        assert row[0] is None

    def test_embedding_stored_when_configured(
        self, backend, config, sample_payload, extracted_json, db_path, monkeypatch
    ):
        """With embedding config and mocked Ollama, embedding is stored."""
        config["embedding"] = {"model": "nomic-embed-text", "ollama_url": "http://test:11434"}

        # Mock _generate_embedding to return a fake vector
        fake_embedding = [0.1, 0.2, 0.3, 0.4]
        monkeypatch.setattr(
            DuckDBIngestBackend,
            "_generate_embedding",
            lambda self, text, cfg: fake_embedding,
        )

        result = backend.process_sync(sample_payload, config)
        doc_id = result["output"]["document_id"]

        conn = duckdb.connect(db_path, read_only=True)
        try:
            row = conn.execute("SELECT embedding FROM documents WHERE id = ?", [doc_id]).fetchone()
        finally:
            conn.close()

        assert row[0] is not None
        assert list(row[0]) == pytest.approx(fake_embedding, rel=1e-5)

    def test_embedding_failure_stores_null(
        self, backend, config, sample_payload, extracted_json, db_path, monkeypatch
    ):
        """If embedding generation fails, null is stored (no crash)."""
        config["embedding"] = {"model": "nomic-embed-text"}

        monkeypatch.setattr(
            DuckDBIngestBackend,
            "_generate_embedding",
            lambda self, text, cfg: None,
        )

        result = backend.process_sync(sample_payload, config)
        doc_id = result["output"]["document_id"]

        conn = duckdb.connect(db_path, read_only=True)
        try:
            row = conn.execute("SELECT embedding FROM documents WHERE id = ?", [doc_id]).fetchone()
        finally:
            conn.close()

        assert row[0] is None

    def test_no_full_text_skips_embedding(self, backend, config, db_path):
        """If there's no full text, embedding is not generated."""
        payload = {"source_file": "empty.pdf"}

        result = backend.process_sync(payload, config)
        doc_id = result["output"]["document_id"]

        conn = duckdb.connect(db_path, read_only=True)
        try:
            row = conn.execute("SELECT embedding FROM documents WHERE id = ?", [doc_id]).fetchone()
        finally:
            conn.close()

        assert row[0] is None

    def test_schema_includes_embedding_column(self, backend, config, db_path):
        """The documents table should include an embedding FLOAT[] column."""
        backend.process_sync({"source_file": "test.pdf"}, config)

        conn = duckdb.connect(db_path, read_only=True)
        try:
            rows = conn.execute("DESCRIBE documents").fetchall()
        finally:
            conn.close()

        col_names = [row[0] for row in rows]
        assert "embedding" in col_names


# ---------------------------------------------------------------------------
# View creation test
# ---------------------------------------------------------------------------


class TestViewCreation:
    """Tests for the document_summaries view."""

    def test_summary_view_created(self, backend, config, sample_payload, extracted_json, db_path):
        """document_summaries view should be created during schema setup."""
        backend.process_sync(sample_payload, config)

        conn = duckdb.connect(db_path, read_only=True)
        try:
            rows = conn.execute("SELECT * FROM document_summaries").fetchall()
        finally:
            conn.close()

        assert len(rows) == 1
