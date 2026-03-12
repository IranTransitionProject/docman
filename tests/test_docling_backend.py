"""
Tests for DoclingBackend (unit tests, no Docling required).

These tests validate input validation (path traversal, file existence)
without invoking Docling itself. Docling is NOT mocked because the
existing tests only exercise the pre-extraction validation logic.

FIXME: `json`, `Path`, `MagicMock`, and `patch` are imported but never used.
       Remove unused imports.

FIXME: `asyncio` is imported inside each test function rather than at the top.
       Move `import asyncio` to the module level.

TODO: Add a happy-path test that mocks DocumentConverter to verify the full
      extraction flow without needing a real PDF:

      @patch("docman.backends.docling_backend.DocumentConverter")
      def test_extraction_success(mock_converter_cls, backend, workspace):
          # Create a fake source file
          (workspace / "test.pdf").write_bytes(b"fake pdf content")

          # Mock Docling's conversion result
          mock_doc = MagicMock()
          mock_doc.export_to_markdown.return_value = "Extracted text here"
          mock_doc.iterate_items.return_value = []
          mock_doc.pages = [MagicMock()]
          mock_converter_cls.return_value.convert.return_value.document = mock_doc

          result = asyncio.run(backend.process(
              {"file_ref": "test.pdf"},
              {"workspace_dir": str(workspace)},
          ))
          assert result["output"]["file_ref"] == "test_extracted.json"
          assert (workspace / "test_extracted.json").exists()

TODO: Add tests for edge cases:
      - Very large files (memory limits)
      - Non-PDF/DOCX files (Docling error handling)
      - Workspace dir doesn't exist
      - File with no text content
"""
# FIXME: These imports are unused — remove them.
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from docman.backends.docling_backend import DoclingBackend


@pytest.fixture
def workspace(tmp_path):
    return tmp_path


@pytest.fixture
def backend(workspace):
    return DoclingBackend(workspace_dir=str(workspace))


def test_path_traversal_rejected(backend, workspace):
    """Backend rejects file_ref that escapes workspace."""
    with pytest.raises(ValueError, match="Path traversal"):
        import asyncio
        asyncio.run(backend.process(
            {"file_ref": "../../etc/passwd"},
            {"workspace_dir": str(workspace)},
        ))


def test_file_not_found(backend, workspace):
    """Backend raises when source file doesn't exist."""
    with pytest.raises(FileNotFoundError):
        import asyncio
        asyncio.run(backend.process(
            {"file_ref": "nonexistent.pdf"},
            {"workspace_dir": str(workspace)},
        ))
