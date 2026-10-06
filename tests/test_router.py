"""Unit tests for OmniMarkdownRouter (RF-01, RF-03, RF-04, RF-05).

Tests routing decisions:
- Office and text documents (.docx, .xlsx, .csv, .txt) -> MarkItDown (0% GPU)
- Clean textual PDFs -> MarkItDown
- Complex PDFs -> Marker
- Graceful Fallback when Marker encounters errors (CUDA OOM, remote failure)
- Graceful Fallback when Marker is unavailable in CPU-only environments
- User force_engine override
- Asynchronous aconvert execution
- Output standardized Pydantic v2 schema
"""

import io
from pathlib import Path
from unittest.mock import MagicMock
import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from omni_router.adapters.base import BaseAdapter
from omni_router.adapters.markitdown_adapter import MarkItDownAdapter
from omni_router.adapters.marker_adapter import MarkerAdapter
from omni_router.classifiers.pdf_classifier import PDFClassifier
from omni_router.router import OmniMarkdownRouter
from omni_router.schemas import ComplexityType, ConversionResult, PDFInspectionResult


from tests.test_classifier import _build_pdf_page


class MockMarkerAdapter(BaseAdapter):
    """Mock Marker adapter for controllable testing."""

    def __init__(self, available: bool = True, should_fail: bool = False, fail_exception: Exception = None):
        self._available = available
        self._should_fail = should_fail
        self._fail_exception = fail_exception or RuntimeError("Simulated CUDA Out Of Memory (OOM)")

    def is_available(self) -> bool:
        return self._available

    def convert(self, file_path, **kwargs) -> ConversionResult:
        if not self._available:
            raise RuntimeError("Marker is not available.")
        if self._should_fail:
            raise self._fail_exception

        return ConversionResult(
            markdown="# Marker High Fidelity Output\nConverted via Marker.",
            engine_used="marker",
            fallback_triggered=False,
            latency_ms=120.0,
            metadata={"mock": True, "engine": "marker"},
            error_message=None,
        )


@pytest.fixture
def sample_files(tmp_path: Path) -> dict[str, Path]:
    """Fixture providing diverse sample files."""
    # 1. Plain text file
    txt_file = tmp_path / "notes.txt"
    txt_file.write_text("Meeting notes from project discussion.\nItem 1: Complete RAG router.", encoding="utf-8")

    # 2. CSV file
    csv_file = tmp_path / "data.csv"
    csv_file.write_text("id,name,role\n1,Alice,Engineer\n2,Bob,Architect\n", encoding="utf-8")

    # 3. Simple PDF
    simple_pdf = tmp_path / "simple.pdf"
    simple_text = (
        "This is a standard simple textual document with sufficient character length "
        "to satisfy the minimum character count per page threshold cleanly."
    )
    simple_pdf.write_bytes(_build_pdf_page(simple_text))

    # 4. Complex Math PDF
    complex_pdf = tmp_path / "complex_math.pdf"
    math_text = "Formula: \\begin{equation} \\frac{x}{y} = \\sum_{i=1}^n z_i \\int d\\theta \\end{equation}"
    complex_pdf.write_bytes(_build_pdf_page(math_text))

    return {
        "txt": txt_file,
        "csv": csv_file,
        "simple_pdf": simple_pdf,
        "complex_pdf": complex_pdf,
    }


def test_route_text_document_to_markitdown(sample_files: dict[str, Path]) -> None:
    """Text and CSV files must route directly to MarkItDown (0% GPU)."""
    router = OmniMarkdownRouter()
    result = router.convert(sample_files["txt"])

    assert isinstance(result, ConversionResult)
    assert result.engine_used == "markitdown"
    assert result.fallback_triggered is False
    assert "Meeting notes" in result.markdown
    assert result.latency_ms > 0


def test_route_csv_document_to_markitdown(sample_files: dict[str, Path]) -> None:
    """CSV document routes to MarkItDown and produces markdown table."""
    router = OmniMarkdownRouter()
    result = router.convert(sample_files["csv"])

    assert result.engine_used == "markitdown"
    assert result.fallback_triggered is False
    assert "Alice" in result.markdown


def test_route_simple_pdf_to_markitdown(sample_files: dict[str, Path]) -> None:
    """Clean text PDF is classified as SIMPLE_TEXT and routed to MarkItDown."""
    router = OmniMarkdownRouter()
    result = router.convert(sample_files["simple_pdf"])

    assert result.engine_used == "markitdown"
    assert result.fallback_triggered is False
    assert "standard simple textual document" in result.markdown


def test_route_complex_pdf_to_marker_when_available(sample_files: dict[str, Path]) -> None:
    """Complex PDF routes to Marker when available."""
    mock_marker = MockMarkerAdapter(available=True, should_fail=False)
    router = OmniMarkdownRouter(marker_adapter=mock_marker)

    result = router.convert(sample_files["complex_pdf"])

    assert result.engine_used == "marker"
    assert result.fallback_triggered is False
    assert "Marker High Fidelity Output" in result.markdown


def test_graceful_fallback_when_marker_fails(sample_files: dict[str, Path]) -> None:
    """When Marker fails (e.g. CUDA OOM), router catches error and falls back to MarkItDown."""
    mock_marker = MockMarkerAdapter(
        available=True,
        should_fail=True,
        fail_exception=RuntimeError("CUDA out of memory: tried to allocate 2.00 GiB")
    )
    router = OmniMarkdownRouter(marker_adapter=mock_marker)

    result = router.convert(sample_files["complex_pdf"])

    # Fallback to MarkItDown
    assert result.engine_used == "markitdown"
    assert result.fallback_triggered is True
    assert "CUDA out of memory" in (result.error_message or "")
    assert result.latency_ms > 0


def test_graceful_fallback_when_marker_unavailable(sample_files: dict[str, Path]) -> None:
    """When Marker is unavailable (CPU-only, no API), router falls back to MarkItDown."""
    mock_marker = MockMarkerAdapter(available=False)
    router = OmniMarkdownRouter(marker_adapter=mock_marker)

    result = router.convert(sample_files["complex_pdf"])

    assert result.engine_used == "markitdown"
    assert result.fallback_triggered is True
    assert "Marker engine is unavailable" in (result.error_message or "")


def test_force_engine_override_markitdown(sample_files: dict[str, Path]) -> None:
    """User can force MarkItDown even on complex documents (RF-05)."""
    mock_marker = MockMarkerAdapter(available=True)
    router = OmniMarkdownRouter(marker_adapter=mock_marker)

    result = router.convert(sample_files["complex_pdf"], force_engine="markitdown")

    assert result.engine_used == "markitdown"
    assert result.fallback_triggered is False


def test_force_engine_override_marker(sample_files: dict[str, Path]) -> None:
    """User can force Marker even on simple text documents (RF-05)."""
    mock_marker = MockMarkerAdapter(available=True)
    router = OmniMarkdownRouter(marker_adapter=mock_marker)

    result = router.convert(sample_files["simple_pdf"], force_engine="marker")

    assert result.engine_used == "marker"
    assert result.fallback_triggered is False
    assert "Marker High Fidelity Output" in result.markdown


def test_force_engine_marker_with_failure_triggers_fallback(sample_files: dict[str, Path]) -> None:
    """Forced Marker failure triggers fallback to MarkItDown with fallback_triggered=True."""
    mock_marker = MockMarkerAdapter(
        available=True,
        should_fail=True,
        fail_exception=TimeoutError("Marker service timeout after 30s")
    )
    router = OmniMarkdownRouter(marker_adapter=mock_marker)

    result = router.convert(sample_files["simple_pdf"], force_engine="marker")

    assert result.engine_used == "markitdown"
    assert result.fallback_triggered is True
    assert "timeout" in (result.error_message or "").lower()


def test_invalid_force_engine_raises_error(sample_files: dict[str, Path]) -> None:
    """Invalid engine override name raises ValueError."""
    router = OmniMarkdownRouter()
    with pytest.raises(ValueError, match="Invalid engine 'tesseract'"):
        router.convert(sample_files["simple_pdf"], force_engine="tesseract")


def test_nonexistent_file_raises_error() -> None:
    """Non-existent file raises FileNotFoundError."""
    router = OmniMarkdownRouter()
    with pytest.raises(FileNotFoundError):
        router.convert("file_that_does_not_exist.pdf")


@pytest.mark.asyncio
async def test_aconvert_asynchronous(sample_files: dict[str, Path]) -> None:
    """aconvert executes asynchronously and returns identical ConversionResult."""
    router = OmniMarkdownRouter()
    result = await router.aconvert(sample_files["txt"])

    assert isinstance(result, ConversionResult)
    assert result.engine_used == "markitdown"
    assert "Meeting notes" in result.markdown


def test_inspect_file(sample_files: dict[str, Path]) -> None:
    """inspect_file returns diagnostic information without converting."""
    router = OmniMarkdownRouter()
    info = router.inspect_file(sample_files["complex_pdf"])

    assert info["is_pdf"] is True
    assert info["recommended_engine"] == "marker"
    assert "pdf_inspection" in info
