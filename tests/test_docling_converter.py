"""
Tests for DoclingBackend._build_converter() (unit tests -- no Docling needed).

Covers the converter construction logic:
    1. Default OCR engine selection by platform (ocrmac on macOS).
    2. Explicit OCR engine branches (easyocr, tesseract).
    3. OCR disabled via do_ocr=false.
    4. Table structure options (enabled/disabled).
    5. Device and threading configuration.
    6. Batch size pass-through.
    7. Empty/missing config uses sensible defaults.

All Docling imports are mocked -- tests verify that _build_converter calls
the right constructors with the right arguments, without importing torch.
"""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import MagicMock

import pytest

from docman.backends.docling_backend import DoclingBackend

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_modules():
    """Create mock Docling modules so _build_converter's lazy imports succeed.

    Returns a dict suitable for patching sys.modules and individual mock
    objects for assertion checks.
    """
    # docling.document_converter
    mock_converter_mod = ModuleType("docling.document_converter")
    mock_DocumentConverter = MagicMock(name="DocumentConverter")
    mock_PdfFormatOption = MagicMock(name="PdfFormatOption")
    mock_converter_mod.DocumentConverter = mock_DocumentConverter
    mock_converter_mod.PdfFormatOption = mock_PdfFormatOption

    # docling.datamodel.pipeline_options
    mock_pipeline_mod = ModuleType("docling.datamodel.pipeline_options")
    mock_PdfPipelineOptions = MagicMock(name="PdfPipelineOptions")
    mock_AcceleratorOptions = MagicMock(name="AcceleratorOptions")
    mock_TableStructureOptions = MagicMock(name="TableStructureOptions")
    mock_OcrMacOptions = MagicMock(name="OcrMacOptions")
    mock_EasyOcrOptions = MagicMock(name="EasyOcrOptions")
    mock_TesseractOcrOptions = MagicMock(name="TesseractOcrOptions")

    mock_pipeline_mod.PdfPipelineOptions = mock_PdfPipelineOptions
    mock_pipeline_mod.AcceleratorOptions = mock_AcceleratorOptions
    mock_pipeline_mod.TableStructureOptions = mock_TableStructureOptions
    mock_pipeline_mod.OcrMacOptions = mock_OcrMacOptions
    mock_pipeline_mod.EasyOcrOptions = mock_EasyOcrOptions
    mock_pipeline_mod.TesseractOcrOptions = mock_TesseractOcrOptions

    # docling.datamodel.base_models
    mock_base_mod = ModuleType("docling.datamodel.base_models")
    mock_InputFormat = MagicMock(name="InputFormat")
    mock_InputFormat.PDF = "PDF"
    mock_InputFormat.DOCX = "DOCX"
    mock_base_mod.InputFormat = mock_InputFormat

    modules = {
        "docling": ModuleType("docling"),
        "docling.document_converter": mock_converter_mod,
        "docling.datamodel": ModuleType("docling.datamodel"),
        "docling.datamodel.pipeline_options": mock_pipeline_mod,
        "docling.datamodel.base_models": mock_base_mod,
    }

    mocks = {
        "DocumentConverter": mock_DocumentConverter,
        "PdfFormatOption": mock_PdfFormatOption,
        "PdfPipelineOptions": mock_PdfPipelineOptions,
        "AcceleratorOptions": mock_AcceleratorOptions,
        "TableStructureOptions": mock_TableStructureOptions,
        "OcrMacOptions": mock_OcrMacOptions,
        "EasyOcrOptions": mock_EasyOcrOptions,
        "TesseractOcrOptions": mock_TesseractOcrOptions,
        "InputFormat": mock_InputFormat,
    }

    return modules, mocks


@pytest.fixture
def backend():
    """Create a DoclingBackend (workspace_dir is irrelevant for converter tests)."""
    return DoclingBackend(workspace_dir="/tmp/test-ws")


@pytest.fixture
def docling_mocks(monkeypatch):
    """Patch all Docling modules with mocks and return the mock dict."""
    modules, mocks = _make_mock_modules()
    for mod_name, mod_obj in modules.items():
        monkeypatch.setitem(sys.modules, mod_name, mod_obj)
    return mocks


# ---------------------------------------------------------------------------
# Default configuration tests
# ---------------------------------------------------------------------------


class TestDefaultConfig:
    """Tests for _build_converter with default/empty config."""

    def test_default_ocr_on_macos(self, backend, docling_mocks, monkeypatch):
        """On macOS (Darwin), default OCR engine should be ocrmac."""
        monkeypatch.setattr("platform.system", lambda: "Darwin")
        monkeypatch.setattr("platform.machine", lambda: "arm64")

        backend._build_converter({})

        docling_mocks["OcrMacOptions"].assert_called_once_with(recognition="accurate")
        docling_mocks["EasyOcrOptions"].assert_not_called()
        docling_mocks["TesseractOcrOptions"].assert_not_called()

    def test_default_ocr_on_linux(self, backend, docling_mocks, monkeypatch):
        """On non-macOS (Linux), default OCR engine should be easyocr."""
        monkeypatch.setattr("platform.system", lambda: "Linux")
        monkeypatch.setattr("platform.machine", lambda: "x86_64")

        backend._build_converter({})

        docling_mocks["EasyOcrOptions"].assert_called_once()
        docling_mocks["OcrMacOptions"].assert_not_called()

    def test_default_threads_arm64(self, backend, docling_mocks, monkeypatch):
        """On arm64 (Apple Silicon), default num_threads should be 8."""
        monkeypatch.setattr("platform.system", lambda: "Darwin")
        monkeypatch.setattr("platform.machine", lambda: "arm64")

        backend._build_converter({})

        docling_mocks["AcceleratorOptions"].assert_called_once_with(device="auto", num_threads=8)

    def test_default_threads_x86(self, backend, docling_mocks, monkeypatch):
        """On x86_64, default num_threads should be 4."""
        monkeypatch.setattr("platform.system", lambda: "Linux")
        monkeypatch.setattr("platform.machine", lambda: "x86_64")

        backend._build_converter({})

        docling_mocks["AcceleratorOptions"].assert_called_once_with(device="auto", num_threads=4)

    def test_empty_config_uses_defaults(self, backend, docling_mocks, monkeypatch):
        """An empty config dict should produce a valid converter with defaults."""
        monkeypatch.setattr("platform.system", lambda: "Darwin")
        monkeypatch.setattr("platform.machine", lambda: "arm64")

        backend._build_converter({})

        # DocumentConverter should be called once with allowed_formats and format_options.
        docling_mocks["DocumentConverter"].assert_called_once()
        call_kwargs = docling_mocks["DocumentConverter"].call_args
        assert "PDF" in call_kwargs.kwargs.get(
            "allowed_formats", call_kwargs[1].get("allowed_formats", [])
        )


# ---------------------------------------------------------------------------
# Explicit OCR engine tests
# ---------------------------------------------------------------------------


class TestOcrEngineSelection:
    """Tests for explicit ocr_engine configuration."""

    def test_easyocr_engine(self, backend, docling_mocks, monkeypatch):
        """ocr_engine='easyocr' should use EasyOcrOptions."""
        monkeypatch.setattr("platform.system", lambda: "Darwin")
        monkeypatch.setattr("platform.machine", lambda: "arm64")

        backend._build_converter({"ocr_engine": "easyocr"})

        docling_mocks["EasyOcrOptions"].assert_called_once()
        docling_mocks["OcrMacOptions"].assert_not_called()
        docling_mocks["TesseractOcrOptions"].assert_not_called()

    def test_tesseract_engine(self, backend, docling_mocks, monkeypatch):
        """ocr_engine='tesseract' should use TesseractOcrOptions."""
        monkeypatch.setattr("platform.system", lambda: "Darwin")
        monkeypatch.setattr("platform.machine", lambda: "arm64")

        backend._build_converter({"ocr_engine": "tesseract"})

        docling_mocks["TesseractOcrOptions"].assert_called_once()
        docling_mocks["OcrMacOptions"].assert_not_called()
        docling_mocks["EasyOcrOptions"].assert_not_called()

    def test_do_ocr_false_skips_ocr(self, backend, docling_mocks, monkeypatch):
        """do_ocr=False should skip all OCR configuration."""
        monkeypatch.setattr("platform.system", lambda: "Darwin")
        monkeypatch.setattr("platform.machine", lambda: "arm64")

        backend._build_converter({"do_ocr": False})

        docling_mocks["OcrMacOptions"].assert_not_called()
        docling_mocks["EasyOcrOptions"].assert_not_called()
        docling_mocks["TesseractOcrOptions"].assert_not_called()

        # Pipeline should be created with do_ocr=False and no ocr_options.
        call_kwargs = docling_mocks["PdfPipelineOptions"].call_args.kwargs
        assert call_kwargs["do_ocr"] is False
        assert "ocr_options" not in call_kwargs


# ---------------------------------------------------------------------------
# Table structure tests
# ---------------------------------------------------------------------------


class TestTableStructure:
    """Tests for do_table_structure configuration."""

    def test_table_structure_enabled_by_default(self, backend, docling_mocks, monkeypatch):
        """Default config should enable table structure with do_cell_matching."""
        monkeypatch.setattr("platform.system", lambda: "Darwin")
        monkeypatch.setattr("platform.machine", lambda: "arm64")

        backend._build_converter({})

        docling_mocks["TableStructureOptions"].assert_called_once_with(do_cell_matching=True)
        call_kwargs = docling_mocks["PdfPipelineOptions"].call_args.kwargs
        assert call_kwargs["do_table_structure"] is True
        assert "table_structure_options" in call_kwargs

    def test_table_structure_disabled(self, backend, docling_mocks, monkeypatch):
        """do_table_structure=False should skip table options."""
        monkeypatch.setattr("platform.system", lambda: "Darwin")
        monkeypatch.setattr("platform.machine", lambda: "arm64")

        backend._build_converter({"do_table_structure": False})

        docling_mocks["TableStructureOptions"].assert_not_called()
        call_kwargs = docling_mocks["PdfPipelineOptions"].call_args.kwargs
        assert call_kwargs["do_table_structure"] is False
        assert "table_structure_options" not in call_kwargs


# ---------------------------------------------------------------------------
# Device and batch size tests
# ---------------------------------------------------------------------------


class TestDeviceAndBatchConfig:
    """Tests for device, num_threads, and batch size pass-through."""

    def test_device_mps(self, backend, docling_mocks, monkeypatch):
        """device='mps' should be passed through to AcceleratorOptions."""
        monkeypatch.setattr("platform.system", lambda: "Darwin")
        monkeypatch.setattr("platform.machine", lambda: "arm64")

        backend._build_converter({"device": "mps"})

        docling_mocks["AcceleratorOptions"].assert_called_once_with(device="mps", num_threads=8)

    def test_device_cpu(self, backend, docling_mocks, monkeypatch):
        """device='cpu' should be passed through to AcceleratorOptions."""
        monkeypatch.setattr("platform.system", lambda: "Linux")
        monkeypatch.setattr("platform.machine", lambda: "x86_64")

        backend._build_converter({"device": "cpu"})

        docling_mocks["AcceleratorOptions"].assert_called_once_with(device="cpu", num_threads=4)

    def test_custom_num_threads(self, backend, docling_mocks, monkeypatch):
        """Explicit num_threads overrides the platform default."""
        monkeypatch.setattr("platform.system", lambda: "Darwin")
        monkeypatch.setattr("platform.machine", lambda: "arm64")

        backend._build_converter({"num_threads": 16})

        docling_mocks["AcceleratorOptions"].assert_called_once_with(device="auto", num_threads=16)

    def test_batch_sizes_passed_through(self, backend, docling_mocks, monkeypatch):
        """layout_batch_size and ocr_batch_size should be passed to pipeline options."""
        monkeypatch.setattr("platform.system", lambda: "Darwin")
        monkeypatch.setattr("platform.machine", lambda: "arm64")

        backend._build_converter({"layout_batch_size": 8, "ocr_batch_size": 16})

        call_kwargs = docling_mocks["PdfPipelineOptions"].call_args.kwargs
        assert call_kwargs["layout_batch_size"] == 8
        assert call_kwargs["ocr_batch_size"] == 16

    def test_default_batch_sizes(self, backend, docling_mocks, monkeypatch):
        """Default batch sizes should both be 4."""
        monkeypatch.setattr("platform.system", lambda: "Darwin")
        monkeypatch.setattr("platform.machine", lambda: "arm64")

        backend._build_converter({})

        call_kwargs = docling_mocks["PdfPipelineOptions"].call_args.kwargs
        assert call_kwargs["layout_batch_size"] == 4
        assert call_kwargs["ocr_batch_size"] == 4
