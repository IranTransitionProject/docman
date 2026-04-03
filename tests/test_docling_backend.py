"""
Tests for DoclingBackend (unit tests -- no Docling installation required).

Covers three areas:
    1. Input validation -- path traversal rejection, missing file detection.
    2. Happy-path extraction -- mocks Docling's DocumentConverter to verify
       the full extraction flow (text, metadata, JSON output) without a
       real PDF.
    3. Error handling -- verifies that Docling failures and I/O errors are
       wrapped in DoclingConversionError with the original cause preserved.

DoclingBackend extends SyncProcessingBackend, so process_sync() is tested
directly (no asyncio needed for unit tests). The thread-pool offloading
is tested via SyncProcessingBackend's own tests in Heddle.
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from heddle.worker.processor import BackendError

from docman.backends.docling_backend import DoclingBackend, DoclingConversionError

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def workspace(tmp_path):
    """Provide an isolated temporary workspace directory for each test."""
    return tmp_path


@pytest.fixture
def backend(workspace):
    """Create a DoclingBackend pointing at the temporary workspace."""
    return DoclingBackend(workspace_dir=str(workspace))


# ---------------------------------------------------------------------------
# Input validation tests
# ---------------------------------------------------------------------------


class TestInputValidation:
    """Tests for pre-extraction input validation (no Docling interaction)."""

    def test_path_traversal_rejected(self, backend, workspace):
        """file_ref containing '../' that escapes workspace must raise ValueError."""
        with pytest.raises(ValueError, match="Path traversal"):
            backend.process_sync(
                {"file_ref": "../../etc/passwd"},
                {"workspace_dir": str(workspace)},
            )

    def test_file_not_found(self, backend, workspace):
        """file_ref pointing to a non-existent file must raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            backend.process_sync(
                {"file_ref": "nonexistent.pdf"},
                {"workspace_dir": str(workspace)},
            )

    def test_docling_conversion_error_is_backend_error(self):
        """DoclingConversionError should be a subclass of BackendError."""
        assert issubclass(DoclingConversionError, BackendError)


# ---------------------------------------------------------------------------
# Happy-path extraction test
# ---------------------------------------------------------------------------


class TestExtraction:
    """Tests that verify the full extraction flow with mocked Docling."""

    @patch("docman.backends.docling_backend.DoclingBackend._build_converter")
    def test_extraction_produces_expected_output(self, mock_build, backend, workspace):
        """Mocked Docling conversion should produce correct output dict and JSON file.

        Verifies:
            - The result contains the expected file_ref, page_count, has_tables,
              sections, and text_preview fields.
            - The extracted JSON file is written to the workspace directory.
            - The JSON file contents match the mock document data.
        """
        # Create a fake source file (content doesn't matter -- Docling is mocked).
        (workspace / "report.pdf").write_bytes(b"%PDF-1.4 fake content")

        # Build a mock Docling document with realistic structure.
        mock_doc = MagicMock()
        mock_doc.export_to_markdown.return_value = "# Introduction\n\nThis is the body text."
        mock_doc.pages = [MagicMock(), MagicMock()]  # 2 pages

        # Simulate iterate_items returning a section header and a table.
        mock_section = MagicMock()
        mock_section.label = "section_header"
        mock_section.text = "Introduction"

        mock_table = MagicMock()
        mock_table.label = "table"

        mock_paragraph = MagicMock()
        mock_paragraph.label = "paragraph"

        # iterate_items is called twice: once for sections, once for has_tables.
        mock_doc.iterate_items.return_value = [mock_section, mock_table, mock_paragraph]

        # Wire the mock converter.
        mock_converter = MagicMock()
        mock_converter.convert.return_value.document = mock_doc
        mock_build.return_value = mock_converter

        # --- Execute ---
        result = backend.process_sync(
            {"file_ref": "report.pdf"},
            {"workspace_dir": str(workspace)},
        )

        # --- Verify result structure ---
        assert result["model_used"] == "docling"

        output = result["output"]
        assert output["file_ref"] == "report_extracted.json"
        assert output["page_count"] == 2
        assert output["has_tables"] is True
        assert "Introduction" in output["sections"]
        assert "This is the body text." in output["text_preview"]

        # --- Verify the extracted JSON was written to workspace ---
        extracted_path = workspace / "report_extracted.json"
        assert extracted_path.exists(), "Extracted JSON file was not created"

        extracted = json.loads(extracted_path.read_text())
        assert extracted["page_count"] == 2
        assert extracted["has_tables"] is True
        assert "Introduction" in extracted["sections"]
        assert "# Introduction" in extracted["text"]

    @patch("docman.backends.docling_backend.DoclingBackend._build_converter")
    def test_extraction_with_empty_document(self, mock_build, backend, workspace):
        """A document with no text, no sections, and no tables should still succeed.

        Verifies that the backend handles empty/minimal documents gracefully
        rather than crashing on missing attributes.
        """
        (workspace / "empty.pdf").write_bytes(b"%PDF-1.4 empty")

        mock_doc = MagicMock()
        mock_doc.export_to_markdown.return_value = ""
        mock_doc.pages = [MagicMock()]  # 1 page
        mock_doc.iterate_items.return_value = []  # No items at all

        mock_converter = MagicMock()
        mock_converter.convert.return_value.document = mock_doc
        mock_build.return_value = mock_converter

        result = backend.process_sync(
            {"file_ref": "empty.pdf"},
            {"workspace_dir": str(workspace)},
        )

        output = result["output"]
        assert output["file_ref"] == "empty_extracted.json"
        assert output["page_count"] == 1
        assert output["has_tables"] is False
        assert output["sections"] == []
        assert output["text_preview"] == ""

    @patch("docman.backends.docling_backend.DoclingBackend._build_converter")
    def test_sections_capped_at_twenty(self, mock_build, backend, workspace):
        """Output sections list should be capped at 20 entries even if the
        document has more, to keep NATS messages small."""
        (workspace / "long.pdf").write_bytes(b"%PDF-1.4 long doc")

        mock_doc = MagicMock()
        mock_doc.export_to_markdown.return_value = "text"
        mock_doc.pages = [MagicMock()]

        # Generate 30 section headers.
        mock_items = []
        for i in range(30):
            item = MagicMock()
            item.label = "section_header"
            item.text = f"Section {i}"
            mock_items.append(item)
        mock_doc.iterate_items.return_value = mock_items

        mock_converter = MagicMock()
        mock_converter.convert.return_value.document = mock_doc
        mock_build.return_value = mock_converter

        result = backend.process_sync(
            {"file_ref": "long.pdf"},
            {"workspace_dir": str(workspace)},
        )

        # Output should cap at 20 sections.
        assert len(result["output"]["sections"]) == 20

        # But the full JSON file should contain all 30.
        extracted = json.loads((workspace / "long_extracted.json").read_text())
        assert len(extracted["sections"]) == 30


# ---------------------------------------------------------------------------
# Error handling tests
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Tests that verify Docling and I/O failures produce DoclingConversionError."""

    @patch("docman.backends.docling_backend.DoclingBackend._build_converter")
    def test_docling_conversion_failure_raises_conversion_error(
        self, mock_build, backend, workspace
    ):
        """When Docling's converter.convert() raises, the backend should wrap
        it in DoclingConversionError with the original exception as __cause__."""
        (workspace / "corrupt.pdf").write_bytes(b"not a real pdf")

        mock_converter = MagicMock()
        mock_converter.convert.side_effect = RuntimeError("Corrupt PDF structure")
        mock_build.return_value = mock_converter

        with pytest.raises(DoclingConversionError, match="Docling conversion failed"):
            backend.process_sync(
                {"file_ref": "corrupt.pdf"},
                {"workspace_dir": str(workspace)},
            )

    @patch("docman.backends.docling_backend.DoclingBackend._build_converter")
    def test_write_failure_raises_conversion_error(self, mock_build, backend, workspace):
        """When writing the extracted JSON fails (disk full, permissions),
        the backend should wrap the OSError in DoclingConversionError."""
        (workspace / "good.pdf").write_bytes(b"%PDF-1.4 content")

        mock_doc = MagicMock()
        mock_doc.export_to_markdown.return_value = "text"
        mock_doc.pages = [MagicMock()]
        mock_doc.iterate_items.return_value = []

        mock_converter = MagicMock()
        mock_converter.convert.return_value.document = mock_doc
        mock_build.return_value = mock_converter

        # Make the workspace read-only so the JSON write fails.
        workspace.chmod(0o555)
        try:
            with pytest.raises(DoclingConversionError, match="Failed to write"):
                backend.process_sync(
                    {"file_ref": "good.pdf"},
                    {"workspace_dir": str(workspace)},
                )
        finally:
            # Restore permissions so pytest can clean up tmp_path.
            workspace.chmod(0o755)
