"""
Tests for SmartExtractorBackend (unit tests -- no MarkItDown or Docling needed).

Covers:
    1. Happy path — MarkItDown succeeds with sufficient text → no Docling.
    2. Fallback — MarkItDown produces insufficient text → Docling runs.
    3. Error fallback — MarkItDown raises → Docling runs.
    4. Force Docling — file extension in force list → Docling runs directly.
    5. Configuration — min_text_length and force_docling_extensions.
"""

from unittest.mock import MagicMock

import pytest

from docman.backends.smart_extractor import SmartExtractorBackend

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def workspace(tmp_path):
    return tmp_path


@pytest.fixture
def backend(workspace):
    return SmartExtractorBackend(workspace_dir=str(workspace))


_DEFAULT_PREVIEW = "Sufficient text extracted by MarkItDown for downstream processing stages"


def _markitdown_result(text_preview=_DEFAULT_PREVIEW, **kwargs):
    """Build a fake MarkItDownBackend.process_sync result."""
    output = {
        "file_ref": "doc_extracted.json",
        "page_count": 1,
        "has_tables": False,
        "sections": [],
        "text_preview": text_preview,
        **kwargs,
    }
    return {"output": output, "model_used": "markitdown"}


def _docling_result(text_preview="Docling extracted text with OCR", **kwargs):
    """Build a fake DoclingBackend.process_sync result."""
    output = {
        "file_ref": "doc_extracted.json",
        "page_count": 3,
        "has_tables": True,
        "sections": ["Introduction"],
        "text_preview": text_preview,
        **kwargs,
    }
    return {"output": output, "model_used": "docling"}


# ---------------------------------------------------------------------------
# Happy path — MarkItDown succeeds
# ---------------------------------------------------------------------------


class TestMarkItDownAccepted:
    def test_markitdown_sufficient_text(self, backend):
        mock_md = MagicMock()
        mock_md.process_sync.return_value = _markitdown_result()
        backend._markitdown = mock_md

        mock_docling = MagicMock()
        backend._docling = mock_docling

        result = backend.process_sync(
            {"file_ref": "report.pdf"},
            {"workspace_dir": "/tmp"},
        )

        assert result["model_used"] == "markitdown"
        mock_md.process_sync.assert_called_once()
        mock_docling.process_sync.assert_not_called()

    def test_markitdown_exactly_at_threshold(self, backend):
        mock_md = MagicMock()
        mock_md.process_sync.return_value = _markitdown_result(
            text_preview="x" * 50
        )
        backend._markitdown = mock_md

        mock_docling = MagicMock()
        backend._docling = mock_docling

        result = backend.process_sync(
            {"file_ref": "report.pdf"},
            {"workspace_dir": "/tmp", "min_text_length": 50},
        )

        assert result["model_used"] == "markitdown"
        mock_docling.process_sync.assert_not_called()


# ---------------------------------------------------------------------------
# Fallback — insufficient text
# ---------------------------------------------------------------------------


class TestFallbackInsufficientText:
    def test_empty_text_triggers_fallback(self, backend):
        mock_md = MagicMock()
        mock_md.process_sync.return_value = _markitdown_result(text_preview="")
        backend._markitdown = mock_md

        mock_docling = MagicMock()
        mock_docling.process_sync.return_value = _docling_result()
        backend._docling = mock_docling

        result = backend.process_sync(
            {"file_ref": "scanned.pdf"},
            {"workspace_dir": "/tmp"},
        )

        assert result["model_used"] == "docling"
        mock_docling.process_sync.assert_called_once()

    def test_short_text_triggers_fallback(self, backend):
        mock_md = MagicMock()
        mock_md.process_sync.return_value = _markitdown_result(text_preview="Hi")
        backend._markitdown = mock_md

        mock_docling = MagicMock()
        mock_docling.process_sync.return_value = _docling_result()
        backend._docling = mock_docling

        result = backend.process_sync(
            {"file_ref": "sparse.pdf"},
            {"workspace_dir": "/tmp", "min_text_length": 50},
        )

        assert result["model_used"] == "docling"

    def test_whitespace_only_triggers_fallback(self, backend):
        mock_md = MagicMock()
        mock_md.process_sync.return_value = _markitdown_result(
            text_preview="   \n\t  "
        )
        backend._markitdown = mock_md

        mock_docling = MagicMock()
        mock_docling.process_sync.return_value = _docling_result()
        backend._docling = mock_docling

        result = backend.process_sync(
            {"file_ref": "blank.pdf"},
            {"workspace_dir": "/tmp"},
        )

        assert result["model_used"] == "docling"


# ---------------------------------------------------------------------------
# Fallback — MarkItDown error
# ---------------------------------------------------------------------------


class TestFallbackOnError:
    def test_markitdown_exception_triggers_fallback(self, backend):
        mock_md = MagicMock()
        mock_md.process_sync.side_effect = RuntimeError("MarkItDown failed")
        backend._markitdown = mock_md

        mock_docling = MagicMock()
        mock_docling.process_sync.return_value = _docling_result()
        backend._docling = mock_docling

        result = backend.process_sync(
            {"file_ref": "problem.pdf"},
            {"workspace_dir": "/tmp"},
        )

        assert result["model_used"] == "docling"
        mock_md.process_sync.assert_called_once()
        mock_docling.process_sync.assert_called_once()


# ---------------------------------------------------------------------------
# Force Docling for specific extensions
# ---------------------------------------------------------------------------


class TestForceDocling:
    def test_forced_extension_skips_markitdown(self, backend):
        mock_md = MagicMock()
        backend._markitdown = mock_md

        mock_docling = MagicMock()
        mock_docling.process_sync.return_value = _docling_result()
        backend._docling = mock_docling

        result = backend.process_sync(
            {"file_ref": "scan.tiff"},
            {"workspace_dir": "/tmp", "force_docling_extensions": [".tiff", ".bmp"]},
        )

        assert result["model_used"] == "docling"
        mock_md.process_sync.assert_not_called()

    def test_non_forced_extension_tries_markitdown(self, backend):
        mock_md = MagicMock()
        mock_md.process_sync.return_value = _markitdown_result()
        backend._markitdown = mock_md

        mock_docling = MagicMock()
        backend._docling = mock_docling

        result = backend.process_sync(
            {"file_ref": "report.pdf"},
            {"workspace_dir": "/tmp", "force_docling_extensions": [".tiff"]},
        )

        assert result["model_used"] == "markitdown"
        mock_docling.process_sync.assert_not_called()


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class TestConfiguration:
    def test_custom_min_text_length(self, backend):
        mock_md = MagicMock()
        # 20 chars of real text — below 100 threshold but above default 50
        mock_md.process_sync.return_value = _markitdown_result(
            text_preview="Short but present text"
        )
        backend._markitdown = mock_md

        mock_docling = MagicMock()
        mock_docling.process_sync.return_value = _docling_result()
        backend._docling = mock_docling

        # With high threshold → fallback
        result = backend.process_sync(
            {"file_ref": "doc.pdf"},
            {"workspace_dir": "/tmp", "min_text_length": 100},
        )
        assert result["model_used"] == "docling"

    def test_default_min_text_length_is_50(self, backend):
        mock_md = MagicMock()
        mock_md.process_sync.return_value = _markitdown_result(
            text_preview="x" * 60
        )
        backend._markitdown = mock_md

        mock_docling = MagicMock()
        backend._docling = mock_docling

        # Default threshold (50) — 60 chars should pass
        result = backend.process_sync(
            {"file_ref": "doc.pdf"},
            {"workspace_dir": "/tmp"},
        )
        assert result["model_used"] == "markitdown"
        mock_docling.process_sync.assert_not_called()

    def test_empty_force_list_by_default(self, backend):
        mock_md = MagicMock()
        mock_md.process_sync.return_value = _markitdown_result()
        backend._markitdown = mock_md

        mock_docling = MagicMock()
        backend._docling = mock_docling

        # No force_docling_extensions in config → MarkItDown tried first
        result = backend.process_sync(
            {"file_ref": "doc.tiff"},
            {"workspace_dir": "/tmp"},
        )
        assert result["model_used"] == "markitdown"
        mock_docling.process_sync.assert_not_called()


# ---------------------------------------------------------------------------
# Lazy initialization
# ---------------------------------------------------------------------------


class TestLazyInit:
    def test_backends_not_created_at_init(self):
        backend = SmartExtractorBackend()
        assert backend._markitdown is None
        assert backend._docling is None

    def test_markitdown_property_creates_on_access(self):
        backend = SmartExtractorBackend(workspace_dir="/tmp/ws")
        md = backend.markitdown
        assert md is not None
        assert backend._markitdown is md
        # Second access returns same instance.
        assert backend.markitdown is md

    def test_docling_property_creates_on_access(self):
        backend = SmartExtractorBackend(workspace_dir="/tmp/ws")
        dl = backend.docling
        assert dl is not None
        assert backend._docling is dl
        assert backend.docling is dl
