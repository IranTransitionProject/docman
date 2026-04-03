"""
Tests for MarkItDownBackend (unit tests -- no MarkItDown installation required).

Covers:
    1. Input validation -- path traversal rejection, missing file detection.
    2. Happy-path extraction -- mocks MarkItDown to verify the full flow.
    3. Metadata derivation -- sections, tables, page_count from Markdown.
    4. Error handling -- conversion failures wrapped in MarkItDownConversionError.
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from heddle.worker.processor import BackendError

from docman.backends.markitdown_backend import MarkItDownBackend, MarkItDownConversionError

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def workspace(tmp_path):
    return tmp_path


@pytest.fixture
def backend(workspace):
    return MarkItDownBackend(workspace_dir=str(workspace))


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


class TestInputValidation:
    def test_path_traversal_rejected(self, backend, workspace):
        with pytest.raises(ValueError, match="Path traversal"):
            backend.process_sync(
                {"file_ref": "../../etc/passwd"},
                {"workspace_dir": str(workspace)},
            )

    def test_file_not_found(self, backend, workspace):
        with pytest.raises(FileNotFoundError):
            backend.process_sync(
                {"file_ref": "nonexistent.pdf"},
                {"workspace_dir": str(workspace)},
            )

    def test_error_is_backend_error(self):
        assert issubclass(MarkItDownConversionError, BackendError)


# ---------------------------------------------------------------------------
# Happy-path extraction
# ---------------------------------------------------------------------------


class TestExtraction:
    @patch("markitdown.MarkItDown")
    def test_basic_extraction(self, mock_md_cls, backend, workspace):
        """Mocked MarkItDown should produce correct output and JSON file."""
        (workspace / "report.pdf").write_bytes(b"%PDF-1.4 fake")

        mock_result = MagicMock()
        mock_result.text_content = "# Introduction\n\nThis is the body text."
        mock_md_cls.return_value.convert.return_value = mock_result

        result = backend.process_sync(
            {"file_ref": "report.pdf"},
            {"workspace_dir": str(workspace)},
        )

        assert result["model_used"] == "markitdown"
        output = result["output"]
        assert output["file_ref"] == "report_extracted.json"
        assert output["page_count"] == 1
        assert output["has_tables"] is False
        assert "Introduction" in output["sections"]
        assert "This is the body text." in output["text_preview"]

        # Verify JSON was written.
        extracted = json.loads((workspace / "report_extracted.json").read_text())
        assert "# Introduction" in extracted["text"]

    @patch("markitdown.MarkItDown")
    def test_empty_document(self, mock_md_cls, backend, workspace):
        (workspace / "empty.pdf").write_bytes(b"%PDF-1.4 empty")

        mock_result = MagicMock()
        mock_result.text_content = ""
        mock_md_cls.return_value.convert.return_value = mock_result

        result = backend.process_sync(
            {"file_ref": "empty.pdf"},
            {"workspace_dir": str(workspace)},
        )

        output = result["output"]
        assert output["page_count"] == 1
        assert output["has_tables"] is False
        assert output["sections"] == []
        assert output["text_preview"] == ""

    @patch("markitdown.MarkItDown")
    def test_none_text_content(self, mock_md_cls, backend, workspace):
        """MarkItDown may return None for text_content."""
        (workspace / "null.pdf").write_bytes(b"%PDF-1.4")

        mock_result = MagicMock()
        mock_result.text_content = None
        mock_md_cls.return_value.convert.return_value = mock_result

        result = backend.process_sync(
            {"file_ref": "null.pdf"},
            {"workspace_dir": str(workspace)},
        )

        output = result["output"]
        assert output["text_preview"] == ""
        assert output["sections"] == []


# ---------------------------------------------------------------------------
# Metadata derivation from Markdown
# ---------------------------------------------------------------------------


class TestMetadataDerivation:
    @patch("markitdown.MarkItDown")
    def test_sections_from_headings(self, mock_md_cls, backend, workspace):
        (workspace / "doc.pdf").write_bytes(b"%PDF")

        mock_result = MagicMock()
        mock_result.text_content = (
            "# Title\n\nParagraph.\n\n## Methods\n\nText.\n\n### Sub-section\n\nMore."
        )
        mock_md_cls.return_value.convert.return_value = mock_result

        result = backend.process_sync(
            {"file_ref": "doc.pdf"},
            {"workspace_dir": str(workspace)},
        )

        sections = result["output"]["sections"]
        assert "Title" in sections
        assert "Methods" in sections
        assert "Sub-section" in sections

    @patch("markitdown.MarkItDown")
    def test_table_detection(self, mock_md_cls, backend, workspace):
        (workspace / "doc.pdf").write_bytes(b"%PDF")

        mock_result = MagicMock()
        mock_result.text_content = "# Data\n\n| Name | Value |\n| --- | --- |\n| A | 1 |\n"
        mock_md_cls.return_value.convert.return_value = mock_result

        result = backend.process_sync(
            {"file_ref": "doc.pdf"},
            {"workspace_dir": str(workspace)},
        )

        assert result["output"]["has_tables"] is True

    @patch("markitdown.MarkItDown")
    def test_page_count_from_form_feeds(self, mock_md_cls, backend, workspace):
        (workspace / "doc.pdf").write_bytes(b"%PDF")

        mock_result = MagicMock()
        mock_result.text_content = "Page 1\fPage 2\fPage 3"
        mock_md_cls.return_value.convert.return_value = mock_result

        result = backend.process_sync(
            {"file_ref": "doc.pdf"},
            {"workspace_dir": str(workspace)},
        )

        assert result["output"]["page_count"] == 2  # 2 form-feeds

    @patch("markitdown.MarkItDown")
    def test_sections_capped_at_twenty(self, mock_md_cls, backend, workspace):
        (workspace / "long.pdf").write_bytes(b"%PDF")

        headings = "\n\n".join(f"# Section {i}" for i in range(30))
        mock_result = MagicMock()
        mock_result.text_content = headings
        mock_md_cls.return_value.convert.return_value = mock_result

        result = backend.process_sync(
            {"file_ref": "long.pdf"},
            {"workspace_dir": str(workspace)},
        )

        assert len(result["output"]["sections"]) == 20

        # Full JSON should have all 30.
        extracted = json.loads((workspace / "long_extracted.json").read_text())
        assert len(extracted["sections"]) == 30


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    @patch("markitdown.MarkItDown")
    def test_conversion_failure(self, mock_md_cls, backend, workspace):
        (workspace / "corrupt.pdf").write_bytes(b"not a pdf")

        mock_md_cls.return_value.convert.side_effect = RuntimeError("Parse error")

        with pytest.raises(MarkItDownConversionError, match="MarkItDown conversion failed"):
            backend.process_sync(
                {"file_ref": "corrupt.pdf"},
                {"workspace_dir": str(workspace)},
            )

    @patch("markitdown.MarkItDown")
    def test_write_failure(self, mock_md_cls, backend, workspace):
        (workspace / "good.pdf").write_bytes(b"%PDF")

        mock_result = MagicMock()
        mock_result.text_content = "text"
        mock_md_cls.return_value.convert.return_value = mock_result

        workspace.chmod(0o555)
        try:
            with pytest.raises(MarkItDownConversionError, match="Failed to write"):
                backend.process_sync(
                    {"file_ref": "good.pdf"},
                    {"workspace_dir": str(workspace)},
                )
        finally:
            workspace.chmod(0o755)

    def test_conversion_error_preserves_cause(self):
        original = RuntimeError("original")
        err = MarkItDownConversionError("wrapped")
        err.__cause__ = original
        assert err.__cause__ is original
