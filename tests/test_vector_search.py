"""Tests for Docman's DuckDBVectorTool wrapper — verifies Docman-specific defaults.

Core search/similarity logic is tested in Heddle (tests/test_contrib_duckdb_vector.py).
This file only tests that the Docman wrapper sets the correct defaults.
"""

import json

import duckdb
import pytest

from docman.tools.vector_search import DuckDBVectorTool


@pytest.fixture
def db_with_embeddings(tmp_path):
    """DuckDB database with documents table and pre-computed embeddings."""
    db_path = str(tmp_path / "test.duckdb")
    conn = duckdb.connect(db_path)

    conn.execute("""
        CREATE TABLE documents (
            id VARCHAR PRIMARY KEY,
            source_file VARCHAR,
            document_type VARCHAR,
            summary TEXT,
            page_count INTEGER,
            has_tables BOOLEAN,
            embedding FLOAT[],
            ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("""
        INSERT INTO documents VALUES
        ('d1', 'climate.pdf', 'report', 'Climate change analysis', 10, false,
         [0.9, 0.1, 0.0, 0.0], CURRENT_TIMESTAMP),
        ('d2', 'budget.pdf', 'financial', 'Annual budget report', 20, true,
         [0.0, 0.0, 0.9, 0.1], CURRENT_TIMESTAMP)
    """)

    conn.close()
    return db_path


class TestDocmanDefaults:
    """Tests that Docman wrapper provides correct defaults."""

    def test_tool_name_is_find_similar_documents(self, db_with_embeddings):
        tool = DuckDBVectorTool(db_path=db_with_embeddings)
        defn = tool.get_definition()
        assert defn["name"] == "find_similar_documents"

    def test_default_description(self, db_with_embeddings):
        tool = DuckDBVectorTool(db_path=db_with_embeddings)
        defn = tool.get_definition()
        assert defn["description"] == "Find semantically similar documents"

    def test_uses_documents_table(self, db_with_embeddings, monkeypatch):
        """Verify the tool queries the 'documents' table."""
        tool = DuckDBVectorTool(db_path=db_with_embeddings)

        def fake_embed_query(self_tool, text):
            return [0.85, 0.15, 0.0, 0.0]

        monkeypatch.setattr(DuckDBVectorTool, "_embed_query", fake_embed_query)

        result = json.loads(tool.execute_sync({"query": "climate"}))
        assert len(result["results"]) > 0
        assert result["results"][0]["source_file"] == "climate.pdf"

    def test_returns_docman_columns(self, db_with_embeddings, monkeypatch):
        """Verify result columns match the Docman schema."""
        tool = DuckDBVectorTool(db_path=db_with_embeddings)

        def fake_embed_query(self_tool, text):
            return [0.5, 0.5, 0.5, 0.5]

        monkeypatch.setattr(DuckDBVectorTool, "_embed_query", fake_embed_query)

        result = json.loads(tool.execute_sync({"query": "test"}))
        for r in result["results"]:
            assert "source_file" in r
            assert "document_type" in r
            assert "summary" in r
            assert "similarity" in r

    def test_is_subclass_of_heddle_vector_tool(self):
        from heddle.contrib.duckdb import DuckDBVectorTool as HeddleVectorTool

        assert issubclass(DuckDBVectorTool, HeddleVectorTool)
