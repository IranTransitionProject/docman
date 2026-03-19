"""
Tests for Docman's DuckDBQueryBackend wrapper — verifies Docman-specific defaults.

Core query backend logic (search, filter, stats, get, vector_search) is tested
in LOOM (tests/test_contrib_duckdb_query.py). This file tests that the Docman
subclass configures the correct schema-specific defaults and that the
backward-compat alias works.

Uses DuckDBIngestBackend to populate the database with the real Docman schema.
"""

import json

import pytest
from loom.worker.processor import BackendError

from docman.backends.duckdb_ingest import DuckDBIngestBackend
from docman.backends.duckdb_query import DocmanQueryBackend, DuckDBQueryBackend, DuckDBQueryError


@pytest.fixture
def workspace(tmp_path):
    return tmp_path


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test.duckdb")


@pytest.fixture
def config(db_path):
    return {"db_path": db_path}


@pytest.fixture
def ingest_config(db_path, workspace):
    return {"db_path": db_path, "workspace_dir": str(workspace)}


@pytest.fixture
def populated_db(db_path, workspace, ingest_config):
    """Populate database with sample documents via DuckDBIngestBackend."""
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
            "summary": "A study on climate change impacts.",
            "key_points": ["Rising temperatures", "Policy recommendations"],
            "word_count": 5000,
        },
        {
            "source_file": "invoice.pdf",
            "file_ref": "invoice_extracted.json",
            "page_count": 1,
            "has_tables": True,
            "sections": [],
            "text_preview": "Invoice number 12345.",
            "document_type": "invoice",
            "classification_confidence": 0.98,
            "classification_reasoning": "Financial document.",
            "summary": "An invoice for consulting services.",
            "key_points": ["Amount: $500"],
            "word_count": 200,
        },
    ]

    for doc in documents:
        extracted = {
            "text": f"Full text content of {doc['source_file']}.",
            "sections": doc["sections"],
            "has_tables": doc["has_tables"],
            "page_count": doc["page_count"],
        }
        (workspace / doc["file_ref"]).write_text(json.dumps(extracted))
        result = ingest.process_sync(doc, ingest_config)
        doc_ids.append(result["output"]["document_id"])

    return doc_ids


@pytest.fixture
def backend(db_path):
    return DuckDBQueryBackend(db_path=db_path)


class TestBackwardCompat:
    """Tests for backward-compatibility alias and error hierarchy."""

    def test_alias_is_docman_backend(self):
        assert DuckDBQueryBackend is DocmanQueryBackend

    def test_error_hierarchy(self):
        assert issubclass(DuckDBQueryError, BackendError)

    def test_is_subclass_of_loom_backend(self):
        from loom.contrib.duckdb import DuckDBQueryBackend as LoomBackend

        assert issubclass(DocmanQueryBackend, LoomBackend)


class TestDocmanDefaults:
    """Tests that Docman wrapper sets correct schema defaults."""

    def test_filter_by_document_type(self, backend, config, populated_db):
        result = backend.process_sync({"action": "filter", "document_type": "invoice"}, config)
        output = result["output"]
        assert output["total"] == 1
        assert output["results"][0]["source_file"] == "invoice.pdf"

    def test_filter_by_has_tables(self, backend, config, populated_db):
        result = backend.process_sync({"action": "filter", "has_tables": True}, config)
        assert result["output"]["total"] == 2

    def test_filter_by_page_range(self, backend, config, populated_db):
        result = backend.process_sync({"action": "filter", "min_pages": 5, "max_pages": 20}, config)
        assert result["output"]["total"] == 1
        assert result["output"]["results"][0]["source_file"] == "report.pdf"

    def test_stats_by_document_type(self, backend, config, populated_db):
        result = backend.process_sync({"action": "stats", "group_by": "document_type"}, config)
        output = result["output"]
        assert output["total"] == 2
        type_counts = {r["document_type"]: r["doc_count"] for r in output["results"]}
        assert type_counts["report"] == 1
        assert type_counts["invoice"] == 1

    def test_stats_includes_docman_aggregates(self, backend, config, populated_db):
        result = backend.process_sync({"action": "stats"}, config)
        for r in result["output"]["results"]:
            assert "doc_count" in r
            assert "avg_page_count" in r
            assert "avg_word_count" in r

    def test_get_parses_json_columns(self, backend, config, populated_db):
        doc_id = populated_db[0]
        result = backend.process_sync({"action": "get", "document_id": doc_id}, config)
        doc = result["output"]["document"]
        assert isinstance(doc["sections"], list)
        assert isinstance(doc["key_points"], list)

    def test_search_excludes_full_text(self, backend, config, populated_db):
        result = backend.process_sync({"action": "search", "query": "climate"}, config)
        for doc in result["output"]["results"]:
            assert "full_text" not in doc

    def test_get_includes_full_text(self, backend, config, populated_db):
        doc_id = populated_db[0]
        result = backend.process_sync({"action": "get", "document_id": doc_id}, config)
        assert "full_text" in result["output"]["document"]
