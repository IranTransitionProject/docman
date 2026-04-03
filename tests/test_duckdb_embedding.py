"""
Tests for DuckDBIngestBackend._generate_embedding() (unit tests).

Covers the embedding generation logic in isolation:
    1. No embedding config returns None.
    2. Empty full_text returns None.
    3. Text under _EMBED_TEXT_LIMIT sent in full.
    4. Text over _EMBED_TEXT_LIMIT truncated to 8000 chars.
    5. Successful embedding returns float list.
    6. Provider failure returns None (no crash).
    7. Missing model name falls back to default "nomic-embed-text".

OllamaEmbeddingProvider and asyncio.run are mocked -- no Ollama needed.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from docman.backends.duckdb_ingest import _EMBED_TEXT_LIMIT, DuckDBIngestBackend

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def backend(tmp_path):
    """Create a DuckDBIngestBackend (DB path irrelevant for embedding tests)."""
    return DuckDBIngestBackend(db_path=str(tmp_path / "test.duckdb"))


# ---------------------------------------------------------------------------
# No-op / early-return tests
# ---------------------------------------------------------------------------


class TestEmbeddingSkipped:
    """Tests for cases where embedding generation is skipped."""

    def test_no_embedding_config_returns_none(self, backend):
        """Without 'embedding' key in config, _generate_embedding returns None."""
        result = backend._generate_embedding("some text", {})
        assert result is None

    def test_empty_embedding_config_returns_none(self, backend):
        """An empty embedding config dict is falsy, returns None."""
        result = backend._generate_embedding("some text", {"embedding": {}})
        assert result is None

    def test_empty_text_returns_none(self, backend):
        """Empty full_text should return None even with embedding config."""
        config = {"embedding": {"model": "nomic-embed-text"}}
        result = backend._generate_embedding("", config)
        assert result is None


# ---------------------------------------------------------------------------
# Successful embedding tests
# ---------------------------------------------------------------------------


class TestEmbeddingSuccess:
    """Tests for successful embedding generation."""

    @patch("docman.backends.duckdb_ingest.asyncio.run")
    @patch("heddle.worker.embeddings.OllamaEmbeddingProvider")
    def test_successful_embedding_returns_float_list(
        self, mock_provider_cls, mock_asyncio_run, backend
    ):
        """A successful embed() call should return the float list."""
        fake_embedding = [0.1, 0.2, 0.3, 0.4, 0.5]
        mock_asyncio_run.return_value = fake_embedding

        config = {"embedding": {"model": "nomic-embed-text", "ollama_url": "http://test:11434"}}
        result = backend._generate_embedding("Hello world", config)

        assert result == fake_embedding
        mock_provider_cls.assert_called_once_with(
            model="nomic-embed-text",
            base_url="http://test:11434",
        )

    @patch("docman.backends.duckdb_ingest.asyncio.run")
    @patch("heddle.worker.embeddings.OllamaEmbeddingProvider")
    def test_text_under_limit_sent_in_full(self, mock_provider_cls, mock_asyncio_run, backend):
        """Text shorter than _EMBED_TEXT_LIMIT should be sent without truncation."""
        short_text = "A" * 100
        mock_asyncio_run.return_value = [0.1]

        config = {"embedding": {"model": "nomic-embed-text"}}
        backend._generate_embedding(short_text, config)

        # asyncio.run receives the coroutine from provider.embed(text[:8000]).
        # The provider instance's embed method was called with the full short text.
        mock_instance = mock_provider_cls.return_value
        mock_instance.embed.assert_called_once()
        actual_text = mock_instance.embed.call_args[0][0]
        assert actual_text == short_text
        assert len(actual_text) == 100

    @patch("docman.backends.duckdb_ingest.asyncio.run")
    @patch("heddle.worker.embeddings.OllamaEmbeddingProvider")
    def test_text_over_limit_truncated(self, mock_provider_cls, mock_asyncio_run, backend):
        """Text longer than _EMBED_TEXT_LIMIT should be truncated to 8000 chars."""
        long_text = "B" * 12000
        mock_asyncio_run.return_value = [0.2]

        config = {"embedding": {"model": "nomic-embed-text"}}
        backend._generate_embedding(long_text, config)

        mock_instance = mock_provider_cls.return_value
        mock_instance.embed.assert_called_once()
        actual_text = mock_instance.embed.call_args[0][0]
        assert len(actual_text) == _EMBED_TEXT_LIMIT

    @patch("docman.backends.duckdb_ingest.asyncio.run")
    @patch("heddle.worker.embeddings.OllamaEmbeddingProvider")
    def test_default_model_used_when_not_specified(
        self, mock_provider_cls, mock_asyncio_run, backend
    ):
        """If embedding config has no 'model' key, default to 'nomic-embed-text'."""
        mock_asyncio_run.return_value = [0.3]

        config = {"embedding": {"ollama_url": "http://test:11434"}}
        backend._generate_embedding("some text", config)

        mock_provider_cls.assert_called_once_with(
            model="nomic-embed-text",
            base_url="http://test:11434",
        )


# ---------------------------------------------------------------------------
# Error handling tests
# ---------------------------------------------------------------------------


class TestEmbeddingErrors:
    """Tests for embedding failure scenarios."""

    @patch("docman.backends.duckdb_ingest.asyncio.run")
    @patch("heddle.worker.embeddings.OllamaEmbeddingProvider")
    def test_provider_failure_returns_none(self, mock_provider_cls, mock_asyncio_run, backend):
        """If the embedding provider raises, _generate_embedding returns None."""
        mock_asyncio_run.side_effect = ConnectionError("Ollama not running")

        config = {"embedding": {"model": "nomic-embed-text"}}
        result = backend._generate_embedding("some text", config)

        assert result is None
