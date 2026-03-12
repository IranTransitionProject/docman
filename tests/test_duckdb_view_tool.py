"""Tests for DuckDBViewTool — LLM-callable DuckDB view query tool."""
import json

import duckdb
import pytest

from docman.tools.duckdb_view import DuckDBViewTool


@pytest.fixture
def db_with_view(tmp_path):
    """Create a DuckDB database with a documents table and view, populated with test data."""
    db_path = str(tmp_path / "test.duckdb")
    conn = duckdb.connect(db_path)
    conn.execute("""
        CREATE TABLE documents (
            id VARCHAR PRIMARY KEY,
            source_file VARCHAR NOT NULL,
            document_type VARCHAR,
            summary TEXT,
            key_points JSON,
            page_count INTEGER,
            has_tables BOOLEAN,
            classification_confidence DOUBLE,
            ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE VIEW document_summaries AS
        SELECT id, source_file, document_type, summary, key_points,
               page_count, has_tables, classification_confidence, ingested_at
        FROM documents
    """)

    # Insert test documents
    conn.execute("""
        INSERT INTO documents (id, source_file, document_type, summary, page_count, has_tables, classification_confidence)
        VALUES
            ('doc-1', 'report.pdf', 'report', 'Annual financial report with revenue data', 10, true, 0.95),
            ('doc-2', 'memo.docx', 'memo', 'Internal memo about project timeline', 2, false, 0.88),
            ('doc-3', 'invoice.pdf', 'invoice', 'Invoice for consulting services', 1, true, 0.92),
            ('doc-4', 'contract.pdf', 'contract', 'Service agreement between parties', 15, false, 0.85)
    """)
    conn.close()
    return db_path


class TestDuckDBViewToolDefinition:
    """Tests for tool definition generation."""

    def test_definition_has_correct_name(self, db_with_view):
        tool = DuckDBViewTool(db_path=db_with_view, view_name="document_summaries")
        defn = tool.get_definition()
        assert defn["name"] == "query_document_summaries"

    def test_definition_has_operations(self, db_with_view):
        tool = DuckDBViewTool(db_path=db_with_view, view_name="document_summaries")
        defn = tool.get_definition()
        ops = defn["parameters"]["properties"]["operation"]
        assert ops["enum"] == ["search", "list"]

    def test_definition_includes_filter_columns(self, db_with_view):
        tool = DuckDBViewTool(db_path=db_with_view, view_name="document_summaries")
        defn = tool.get_definition()
        filters = defn["parameters"]["properties"]["filters"]["properties"]
        assert "document_type" in filters
        assert "page_count" in filters
        assert "has_tables" in filters

    def test_custom_description(self, db_with_view):
        tool = DuckDBViewTool(
            db_path=db_with_view,
            view_name="document_summaries",
            description="Custom tool description",
        )
        defn = tool.get_definition()
        assert defn["description"] == "Custom tool description"

    def test_is_tool_provider_subclass(self, db_with_view):
        from loom.worker.tools import ToolProvider
        tool = DuckDBViewTool(db_path=db_with_view, view_name="document_summaries")
        assert isinstance(tool, ToolProvider)


class TestDuckDBViewToolSearch:
    """Tests for search operation."""

    def test_search_finds_matching_documents(self, db_with_view):
        tool = DuckDBViewTool(db_path=db_with_view, view_name="document_summaries")
        result = json.loads(tool.execute_sync({"operation": "search", "query": "financial"}))
        assert result["total"] >= 1
        assert any("financial" in r.get("summary", "").lower() for r in result["results"])

    def test_search_empty_query_returns_empty(self, db_with_view):
        tool = DuckDBViewTool(db_path=db_with_view, view_name="document_summaries")
        result = json.loads(tool.execute_sync({"operation": "search", "query": ""}))
        assert result["results"] == []
        assert result["total"] == 0

    def test_search_no_matches(self, db_with_view):
        tool = DuckDBViewTool(db_path=db_with_view, view_name="document_summaries")
        result = json.loads(tool.execute_sync({"operation": "search", "query": "xyznonexistent"}))
        assert result["total"] == 0

    def test_search_respects_limit(self, db_with_view):
        tool = DuckDBViewTool(db_path=db_with_view, view_name="document_summaries")
        result = json.loads(tool.execute_sync({"operation": "search", "query": "e", "limit": 2}))
        assert len(result["results"]) <= 2

    def test_search_case_insensitive(self, db_with_view):
        tool = DuckDBViewTool(db_path=db_with_view, view_name="document_summaries")
        result = json.loads(tool.execute_sync({"operation": "search", "query": "FINANCIAL"}))
        assert result["total"] >= 1


class TestDuckDBViewToolList:
    """Tests for list operation."""

    def test_list_all_documents(self, db_with_view):
        tool = DuckDBViewTool(db_path=db_with_view, view_name="document_summaries")
        result = json.loads(tool.execute_sync({"operation": "list", "limit": 100}))
        assert result["total"] == 4

    def test_list_with_filter(self, db_with_view):
        tool = DuckDBViewTool(db_path=db_with_view, view_name="document_summaries")
        result = json.loads(tool.execute_sync({
            "operation": "list",
            "filters": {"document_type": "report"},
        }))
        assert result["total"] >= 1
        assert all(r["document_type"] == "report" for r in result["results"])

    def test_list_with_boolean_filter(self, db_with_view):
        tool = DuckDBViewTool(db_path=db_with_view, view_name="document_summaries")
        result = json.loads(tool.execute_sync({
            "operation": "list",
            "filters": {"has_tables": True},
        }))
        assert result["total"] >= 1
        assert all(r["has_tables"] is True for r in result["results"])

    def test_list_respects_limit(self, db_with_view):
        tool = DuckDBViewTool(db_path=db_with_view, view_name="document_summaries")
        result = json.loads(tool.execute_sync({"operation": "list", "limit": 2}))
        assert len(result["results"]) == 2

    def test_list_ignores_invalid_filter_columns(self, db_with_view):
        """Filters on columns not in the view are silently ignored."""
        tool = DuckDBViewTool(db_path=db_with_view, view_name="document_summaries")
        result = json.loads(tool.execute_sync({
            "operation": "list",
            "filters": {"nonexistent_col": "value"},
        }))
        # Should return all docs since the invalid filter is ignored
        assert result["total"] == 4


class TestDuckDBViewToolLimits:
    """Tests for max_results enforcement."""

    def test_max_results_caps_limit(self, db_with_view):
        tool = DuckDBViewTool(
            db_path=db_with_view,
            view_name="document_summaries",
            max_results=2,
        )
        result = json.loads(tool.execute_sync({"operation": "list", "limit": 100}))
        assert len(result["results"]) <= 2

    def test_error_on_bad_db(self, tmp_path):
        """Graceful error when database doesn't exist."""
        tool = DuckDBViewTool(
            db_path=str(tmp_path / "nonexistent.duckdb"),
            view_name="document_summaries",
        )
        # Introspection would have failed, so columns are empty
        result = json.loads(tool.execute_sync({"operation": "list"}))
        # Should return error or empty results, not crash
        assert "error" in result or result.get("total", 0) == 0


class TestDuckDBViewToolSQLInjection:
    """Verify parameterized queries prevent SQL injection."""

    def test_search_injection_attempt(self, db_with_view):
        """SQL injection in search query is safely escaped."""
        tool = DuckDBViewTool(db_path=db_with_view, view_name="document_summaries")
        result = json.loads(tool.execute_sync({
            "operation": "search",
            "query": "'; DROP TABLE documents; --",
        }))
        # Should not crash and table should still exist
        assert isinstance(result, dict)

        # Verify table still exists
        conn = duckdb.connect(db_with_view, read_only=True)
        count = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        conn.close()
        assert count == 4

    def test_filter_injection_attempt(self, db_with_view):
        """SQL injection in filter values is safely escaped."""
        tool = DuckDBViewTool(db_path=db_with_view, view_name="document_summaries")
        result = json.loads(tool.execute_sync({
            "operation": "list",
            "filters": {"document_type": "'; DROP TABLE documents; --"},
        }))
        assert isinstance(result, dict)
