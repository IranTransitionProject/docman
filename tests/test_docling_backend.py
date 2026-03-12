"""Tests for DoclingBackend (unit tests, no Docling required)."""
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
