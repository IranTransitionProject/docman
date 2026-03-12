"""
Tests for DuckDBQueryBackend (unit tests -- uses in-memory DuckDB).

Covers:
    1. Search -- full-text search with FTS fallback to LIKE.
    2. Filter -- attribute-based filtering.
    3. Stats -- aggregate statistics by grouping column.
    4. Get -- single document retrieval by ID.
    5. Error handling -- invalid action, document not found.

The test database is populated with sample documents via a fixture
that uses DuckDBIngestBackend directly to ensure consistent schema.
"""
import json

import duckdb
import pytest

from docman.backends.duckdb_query import DuckDBQueryBackend, DuckDBQueryError
from docman.backends.duckdb_ingest import DuckDBIngestBackend
from loom.worker.processor import BackendError


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
def config(db_path):
    """Standard config dict for the query backend."""
    return {"db_path": db_path}


@pytest.fixture
def ingest_config(db_path, workspace):
    """Config dict for the ingest backend (includes workspace_dir)."""
    return {"db_path": db_path, "workspace_dir": str(workspace)}


@pytest.fixture
def populated_db(db_path, workspace, ingest_config):
    """Populate the database with 3 sample documents and return their IDs.

    Creates workspace JSON files and ingests documents via
    DuckDBIngestBackend to ensure the schema is consistent.
    """
    ingest = DuckDBIngestBackend(db_path=db_path)
    doc_ids = []

    documents = [
        {
            "source_file": "report.pdf",
            "file_ref": "report_extracted.json",
            "page_count": 10,
            "has_tables": True,
            "sections": ["Introduction", "Methods"],
            "text_preview": "Climate change research findings.",
            "document_type": "report",
            "classification_confidence": 0.92,
            "classification_reasoning": "Research document.",
            "summary": "A study on climate change impacts and mitigation strategies.",
            "key_points": ["Rising temperatures", "Policy recommendations"],
            "word_count": 5000,
        },
        {
            "source_file": "invoice.pdf",
            "file_ref": "invoice_extracted.json",
            "page_count": 1,
            "has_tables": True,
            "sections": [],
            "text_preview": "Invoice number 12345. Amount due: $500.",
            "document_type": "invoice",
            "classification_confidence": 0.98,
            "classification_reasoning": "Financial document.",
            "summary": "An invoice for consulting services rendered in Q1.",
            "key_points": ["Amount: $500", "Due date: March 2026"],
            "word_count": 200,
        },
        {
            "source_file": "manual.pdf",
            "file_ref": "manual_extracted.json",
            "page_count": 50,
            "has_tables": False,
            "sections": ["Getting Started", "Installation", "Configuration"],
            "text_preview": "User manual for the software product.",
            "document_type": "manual",
            "classification_confidence": 0.85,
            "classification_reasoning": "Technical documentation.",
            "summary": "Comprehensive user guide covering installation and configuration.",
            "key_points": ["Installation steps", "Configuration options"],
            "word_count": 15000,
        },
    ]

    for doc in documents:
        # Write workspace JSON file with full text.
        extracted = {
            "text": f"Full text content of {doc['source_file']}. {doc['text_preview']}",
            "sections": doc["sections"],
            "has_tables": doc["has_tables"],
            "page_count": doc["page_count"],
        }
        json_name = doc["file_ref"]
        (workspace / json_name).write_text(json.dumps(extracted))

        result = ingest.process_sync(doc, ingest_config)
        doc_ids.append(result["output"]["document_id"])

    return doc_ids


@pytest.fixture
def backend(db_path):
    """Create a DuckDBQueryBackend with the test database."""
    return DuckDBQueryBackend(db_path=db_path)


# ---------------------------------------------------------------------------
# Validation tests
# ---------------------------------------------------------------------------

class TestValidation:
    """Tests for input validation and error hierarchy."""

    def test_duckdb_query_error_is_backend_error(self):
        """DuckDBQueryError should be a subclass of BackendError."""
        assert issubclass(DuckDBQueryError, BackendError)

    def test_unknown_action_raises_value_error(self, backend, config, populated_db):
        """An unknown action should raise ValueError."""
        with pytest.raises(ValueError, match="Unknown action"):
            backend.process_sync({"action": "destroy"}, config)


# ---------------------------------------------------------------------------
# Search tests
# ---------------------------------------------------------------------------

class TestSearch:
    """Tests for full-text search functionality."""

    def test_search_returns_results(self, backend, config, populated_db):
        """Searching for 'climate' should return the report document."""
        result = backend.process_sync(
            {"action": "search", "query": "climate"},
            config,
        )

        output = result["output"]
        assert len(output["results"]) >= 1

        source_files = [r["source_file"] for r in output["results"]]
        assert "report.pdf" in source_files

    def test_search_empty_query_returns_empty(self, backend, config, populated_db):
        """An empty search query should return no results."""
        result = backend.process_sync(
            {"action": "search", "query": ""},
            config,
        )

        assert result["output"]["results"] == []
        assert result["output"]["total"] == 0

    def test_search_respects_limit(self, backend, config, populated_db):
        """Search results should be capped at the specified limit."""
        result = backend.process_sync(
            {"action": "search", "query": "pdf", "limit": 1},
            config,
        )

        assert len(result["output"]["results"]) <= 1

    def test_search_excludes_full_text(self, backend, config, populated_db):
        """Search results should not include full_text (too large for NATS)."""
        result = backend.process_sync(
            {"action": "search", "query": "climate"},
            config,
        )

        for doc in result["output"]["results"]:
            assert "full_text" not in doc


# ---------------------------------------------------------------------------
# Filter tests
# ---------------------------------------------------------------------------

class TestFilter:
    """Tests for attribute-based document filtering."""

    def test_filter_by_document_type(self, backend, config, populated_db):
        """Filtering by document_type should return only matching documents."""
        result = backend.process_sync(
            {"action": "filter", "document_type": "invoice"},
            config,
        )

        output = result["output"]
        assert output["total"] == 1
        assert output["results"][0]["source_file"] == "invoice.pdf"

    def test_filter_by_has_tables(self, backend, config, populated_db):
        """Filtering by has_tables=True should return documents with tables."""
        result = backend.process_sync(
            {"action": "filter", "has_tables": True},
            config,
        )

        output = result["output"]
        assert output["total"] == 2
        source_files = {r["source_file"] for r in output["results"]}
        assert source_files == {"report.pdf", "invoice.pdf"}

    def test_filter_by_page_range(self, backend, config, populated_db):
        """Filtering by min/max pages should return documents in range."""
        result = backend.process_sync(
            {"action": "filter", "min_pages": 5, "max_pages": 20},
            config,
        )

        output = result["output"]
        assert output["total"] == 1
        assert output["results"][0]["source_file"] == "report.pdf"

    def test_filter_no_criteria_returns_all(self, backend, config, populated_db):
        """Filtering with no criteria should return all documents."""
        result = backend.process_sync(
            {"action": "filter"},
            config,
        )

        assert result["output"]["total"] == 3

    def test_filter_combined_criteria(self, backend, config, populated_db):
        """Combining multiple filters should intersect criteria."""
        result = backend.process_sync(
            {"action": "filter", "document_type": "report", "has_tables": True},
            config,
        )

        output = result["output"]
        assert output["total"] == 1
        assert output["results"][0]["document_type"] == "report"


# ---------------------------------------------------------------------------
# Stats tests
# ---------------------------------------------------------------------------

class TestStats:
    """Tests for aggregate statistics."""

    def test_stats_by_document_type(self, backend, config, populated_db):
        """Stats grouped by document_type should show counts per type."""
        result = backend.process_sync(
            {"action": "stats"},
            config,
        )

        output = result["output"]
        assert output["total"] == 3

        type_counts = {r["document_type"]: r["doc_count"] for r in output["results"]}
        assert type_counts["report"] == 1
        assert type_counts["invoice"] == 1
        assert type_counts["manual"] == 1

    def test_stats_by_has_tables(self, backend, config, populated_db):
        """Stats grouped by has_tables should show True/False counts."""
        result = backend.process_sync(
            {"action": "stats", "group_by": "has_tables"},
            config,
        )

        output = result["output"]
        table_counts = {r["has_tables"]: r["doc_count"] for r in output["results"]}
        assert table_counts[True] == 2
        assert table_counts[False] == 1

    def test_stats_invalid_group_by_raises(self, backend, config, populated_db):
        """An invalid group_by column should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid group_by"):
            backend.process_sync(
                {"action": "stats", "group_by": "nonexistent_column"},
                config,
            )


# ---------------------------------------------------------------------------
# Get tests
# ---------------------------------------------------------------------------

class TestGet:
    """Tests for single-document retrieval."""

    def test_get_returns_full_document(self, backend, config, populated_db):
        """Getting a document by ID should return all fields including full_text."""
        doc_id = populated_db[0]  # report

        result = backend.process_sync(
            {"action": "get", "document_id": doc_id},
            config,
        )

        doc = result["output"]["document"]
        assert doc["id"] == doc_id
        assert doc["source_file"] == "report.pdf"
        assert doc["document_type"] == "report"
        assert "full_text" in doc
        assert "Full text content" in doc["full_text"]

    def test_get_nonexistent_raises(self, backend, config, populated_db):
        """Getting a non-existent document should raise DuckDBQueryError."""
        with pytest.raises(DuckDBQueryError, match="Document not found"):
            backend.process_sync(
                {"action": "get", "document_id": "nonexistent-id"},
                config,
            )

    def test_get_missing_id_raises(self, backend, config, populated_db):
        """Getting without document_id should raise ValueError."""
        with pytest.raises(ValueError, match="document_id is required"):
            backend.process_sync(
                {"action": "get"},
                config,
            )

    def test_get_parses_json_columns(self, backend, config, populated_db):
        """JSON columns (sections, key_points) should be parsed back to lists."""
        doc_id = populated_db[0]  # report

        result = backend.process_sync(
            {"action": "get", "document_id": doc_id},
            config,
        )

        doc = result["output"]["document"]
        assert isinstance(doc["sections"], list)
        assert "Introduction" in doc["sections"]
        assert isinstance(doc["key_points"], list)
        assert "Rising temperatures" in doc["key_points"]
