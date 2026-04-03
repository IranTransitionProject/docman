"""
Tests for Pydantic I/O contracts.

Validates that every contract model:
    - Accepts valid data and rejects invalid data.
    - Generates a JSON Schema (used by Heddle's resolve_schema_refs).
    - Has required/optional fields as expected by the worker configs.
"""

import pytest
from pydantic import ValidationError

from docman.contracts import (
    ClassifierInput,
    ClassifierOutput,
    ExtractorInput,
    ExtractorOutput,
    IngestInput,
    IngestOutput,
    QueryInput,
    QueryOutput,
    SummarizerInput,
    SummarizerOutput,
)

# ---------------------------------------------------------------------------
# ExtractorInput / ExtractorOutput
# ---------------------------------------------------------------------------


class TestExtractorContracts:
    def test_extractor_input_valid(self):
        m = ExtractorInput(file_ref="report.pdf")
        assert m.file_ref == "report.pdf"

    def test_extractor_input_missing_file_ref(self):
        with pytest.raises(ValidationError):
            ExtractorInput()

    def test_extractor_output_valid(self):
        m = ExtractorOutput(
            file_ref="report_extracted.json",
            page_count=3,
            has_tables=True,
            sections=["Intro", "Methods"],
            text_preview="Some text here",
        )
        assert m.page_count == 3
        assert m.has_tables is True

    def test_extractor_output_missing_fields(self):
        with pytest.raises(ValidationError):
            ExtractorOutput(file_ref="x.json")

    def test_extractor_output_schema_generation(self):
        schema = ExtractorOutput.model_json_schema()
        assert schema["type"] == "object"
        assert "file_ref" in schema["properties"]
        assert "page_count" in schema["properties"]


# ---------------------------------------------------------------------------
# ClassifierInput / ClassifierOutput
# ---------------------------------------------------------------------------


class TestClassifierContracts:
    def test_classifier_input_minimal(self):
        m = ClassifierInput(text_preview="Hello world")
        assert m.page_count is None
        assert m.has_tables is None

    def test_classifier_input_full(self):
        m = ClassifierInput(
            text_preview="Hello",
            page_count=5,
            has_tables=True,
            sections=["A", "B"],
        )
        assert m.page_count == 5

    def test_classifier_output_valid(self):
        m = ClassifierOutput(
            document_type="report",
            confidence=0.95,
            reasoning="Contains methodology section",
        )
        assert m.document_type == "report"

    def test_classifier_output_confidence_bounds(self):
        with pytest.raises(ValidationError):
            ClassifierOutput(document_type="report", confidence=1.5, reasoning="x")

    def test_classifier_output_schema_generation(self):
        schema = ClassifierOutput.model_json_schema()
        assert "document_type" in schema["properties"]
        assert "confidence" in schema["properties"]


# ---------------------------------------------------------------------------
# SummarizerInput / SummarizerOutput
# ---------------------------------------------------------------------------


class TestSummarizerContracts:
    def test_summarizer_input_valid(self):
        m = SummarizerInput(file_ref="doc_extracted.json", document_type="report")
        assert m.document_type == "report"

    def test_summarizer_input_missing_fields(self):
        with pytest.raises(ValidationError):
            SummarizerInput(file_ref="x.json")

    def test_summarizer_output_valid(self):
        m = SummarizerOutput(
            summary="A summary.",
            key_points=["point 1"],
            word_count=2,
        )
        assert m.word_count == 2

    def test_summarizer_output_schema_generation(self):
        schema = SummarizerOutput.model_json_schema()
        assert "summary" in schema["properties"]
        assert "key_points" in schema["properties"]


# ---------------------------------------------------------------------------
# IngestInput / IngestOutput
# ---------------------------------------------------------------------------


class TestIngestContracts:
    def test_ingest_input_minimal(self):
        m = IngestInput(source_file="report.pdf")
        assert m.file_ref is None
        assert m.document_type is None

    def test_ingest_input_full(self):
        m = IngestInput(
            source_file="report.pdf",
            file_ref="report_extracted.json",
            page_count=5,
            has_tables=True,
            sections=["A"],
            text_preview="text",
            document_type="report",
            classification_confidence=0.9,
            classification_reasoning="reason",
            summary="A summary.",
            key_points=["p1"],
            word_count=100,
        )
        assert m.classification_confidence == 0.9

    def test_ingest_output_valid(self):
        m = IngestOutput(
            document_id="abc-123",
            status="inserted",
            source_file="report.pdf",
        )
        assert m.status == "inserted"

    def test_ingest_output_schema_generation(self):
        schema = IngestOutput.model_json_schema()
        assert "document_id" in schema["required"]


# ---------------------------------------------------------------------------
# QueryInput / QueryOutput
# ---------------------------------------------------------------------------


class TestQueryContracts:
    def test_query_input_search(self):
        m = QueryInput(action="search", query="machine learning")
        assert m.action == "search"

    def test_query_input_invalid_action(self):
        with pytest.raises(ValidationError):
            QueryInput(action="invalid_action")

    def test_query_input_filter(self):
        m = QueryInput(
            action="filter",
            document_type="invoice",
            has_tables=True,
            min_pages=2,
            max_pages=10,
        )
        assert m.min_pages == 2

    def test_query_output_results(self):
        m = QueryOutput(
            results=[{"id": "1", "summary": "text"}],
            total=1,
        )
        assert m.total == 1

    def test_query_output_get(self):
        m = QueryOutput(document={"id": "1", "full_text": "..."})
        assert m.results is None

    def test_query_output_schema_generation(self):
        schema = QueryOutput.model_json_schema()
        assert "results" in schema["properties"]


# ---------------------------------------------------------------------------
# Cross-cutting: all models generate valid JSON Schema
# ---------------------------------------------------------------------------

ALL_MODELS = [
    ExtractorInput,
    ExtractorOutput,
    ClassifierInput,
    ClassifierOutput,
    SummarizerInput,
    SummarizerOutput,
    IngestInput,
    IngestOutput,
    QueryInput,
    QueryOutput,
]


@pytest.mark.parametrize("model", ALL_MODELS, ids=lambda m: m.__name__)
def test_all_models_produce_json_schema(model):
    """Every contract model must produce a valid JSON Schema dict."""
    schema = model.model_json_schema()
    assert isinstance(schema, dict)
    assert "properties" in schema
