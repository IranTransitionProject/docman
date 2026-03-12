"""Tests for DuckDBVectorTool — semantic similarity search."""
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

    # Insert docs with 4-dimensional embeddings.
    # Vectors chosen so that "climate" docs cluster together.
    conn.execute("""
        INSERT INTO documents VALUES
        ('d1', 'climate.pdf', 'report', 'Climate change analysis', 10, false,
         [0.9, 0.1, 0.0, 0.0], CURRENT_TIMESTAMP),
        ('d2', 'weather.pdf', 'report', 'Weather patterns study', 5, false,
         [0.8, 0.2, 0.1, 0.0], CURRENT_TIMESTAMP),
        ('d3', 'budget.pdf', 'financial', 'Annual budget report', 20, true,
         [0.0, 0.0, 0.9, 0.1], CURRENT_TIMESTAMP),
        ('d4', 'noembedding.pdf', 'memo', 'No embedding doc', 1, false,
         NULL, CURRENT_TIMESTAMP)
    """)

    conn.close()
    return db_path


class TestDuckDBVectorToolDefinition:
    """Tests for tool definition generation."""

    def test_tool_name(self, db_with_embeddings):
        tool = DuckDBVectorTool(db_path=db_with_embeddings)
        defn = tool.get_definition()
        assert defn["name"] == "find_similar_documents"

    def test_has_query_parameter(self, db_with_embeddings):
        tool = DuckDBVectorTool(db_path=db_with_embeddings)
        defn = tool.get_definition()
        assert "query" in defn["parameters"]["properties"]
        assert "query" in defn["parameters"]["required"]

    def test_has_limit_parameter(self, db_with_embeddings):
        tool = DuckDBVectorTool(db_path=db_with_embeddings)
        defn = tool.get_definition()
        assert "limit" in defn["parameters"]["properties"]

    def test_custom_description(self, db_with_embeddings):
        tool = DuckDBVectorTool(
            db_path=db_with_embeddings,
            description="Custom search desc",
        )
        defn = tool.get_definition()
        assert defn["description"] == "Custom search desc"


class TestDuckDBVectorToolSearch:
    """Tests for similarity search execution."""

    def test_search_returns_results(self, db_with_embeddings, monkeypatch):
        """Search returns similar documents ranked by cosine similarity."""
        tool = DuckDBVectorTool(db_path=db_with_embeddings)

        # Mock the embedding call to return a climate-like vector
        def fake_embed_query(self_tool, text):
            return [0.85, 0.15, 0.0, 0.0]

        monkeypatch.setattr(DuckDBVectorTool, "_embed_query", fake_embed_query)

        result = json.loads(tool.execute_sync({"query": "climate data"}))
        assert "results" in result
        assert len(result["results"]) > 0
        # Climate doc should be most similar
        assert result["results"][0]["source_file"] == "climate.pdf"

    def test_excludes_null_embeddings(self, db_with_embeddings, monkeypatch):
        """Documents without embeddings are excluded from results."""
        tool = DuckDBVectorTool(db_path=db_with_embeddings)

        def fake_embed_query(self_tool, text):
            return [0.5, 0.5, 0.5, 0.5]

        monkeypatch.setattr(DuckDBVectorTool, "_embed_query", fake_embed_query)

        result = json.loads(tool.execute_sync({"query": "anything"}))
        source_files = [r["source_file"] for r in result["results"]]
        assert "noembedding.pdf" not in source_files

    def test_respects_limit(self, db_with_embeddings, monkeypatch):
        """Limit parameter caps the number of results."""
        tool = DuckDBVectorTool(db_path=db_with_embeddings)

        def fake_embed_query(self_tool, text):
            return [0.5, 0.5, 0.5, 0.5]

        monkeypatch.setattr(DuckDBVectorTool, "_embed_query", fake_embed_query)

        result = json.loads(tool.execute_sync({"query": "test", "limit": 1}))
        assert len(result["results"]) == 1

    def test_max_results_enforcement(self, db_with_embeddings, monkeypatch):
        """Limit is capped at max_results."""
        tool = DuckDBVectorTool(db_path=db_with_embeddings, max_results=2)

        def fake_embed_query(self_tool, text):
            return [0.5, 0.5, 0.5, 0.5]

        monkeypatch.setattr(DuckDBVectorTool, "_embed_query", fake_embed_query)

        result = json.loads(tool.execute_sync({"query": "test", "limit": 100}))
        assert len(result["results"]) <= 2

    def test_empty_query(self, db_with_embeddings):
        """Empty query returns empty results without calling Ollama."""
        tool = DuckDBVectorTool(db_path=db_with_embeddings)
        result = json.loads(tool.execute_sync({"query": ""}))
        assert result["results"] == []
        assert result["total"] == 0

    def test_similarity_scores_included(self, db_with_embeddings, monkeypatch):
        """Results include similarity scores."""
        tool = DuckDBVectorTool(db_path=db_with_embeddings)

        def fake_embed_query(self_tool, text):
            return [0.9, 0.1, 0.0, 0.0]

        monkeypatch.setattr(DuckDBVectorTool, "_embed_query", fake_embed_query)

        result = json.loads(tool.execute_sync({"query": "climate"}))
        for r in result["results"]:
            assert "similarity" in r
            assert isinstance(r["similarity"], (int, float))

    def test_embed_failure_returns_error(self, db_with_embeddings, monkeypatch):
        """Failed embedding returns an error dict."""
        tool = DuckDBVectorTool(db_path=db_with_embeddings)

        def fail_embed(self_tool, text):
            return None

        monkeypatch.setattr(DuckDBVectorTool, "_embed_query", fail_embed)

        result = json.loads(tool.execute_sync({"query": "anything"}))
        assert "error" in result


class TestDuckDBVectorToolQueryBackend:
    """Tests for vector_search action in DuckDBQueryBackend."""

    def test_vector_search_action_registered(self):
        """vector_search is a valid action in the query backend."""
        from docman.backends.duckdb_query import DuckDBQueryBackend

        backend = DuckDBQueryBackend()
        # The handlers dict is built in process_sync, so check indirectly
        # by verifying the method exists
        assert hasattr(backend, "_vector_search")
