"""Unit tests for PDFClassifier (RF-02).

Tests complexity detection:
- Simple text PDFs -> SIMPLE_TEXT
- Scanned PDFs (low char count + images) -> COMPLEX_SCAN
- Technical PDFs (LaTeX formulas, math symbols) -> COMPLEX_LAYOUT
- Multi-column layouts -> COMPLEX_LAYOUT
- Defensive fallback on corrupted files
- Async execution
"""

import io
from pathlib import Path
import pytest
from pypdf import PdfWriter
from pypdf.generic import (
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
    NumberObject,
)

from omni_router.classifiers.pdf_classifier import PDFClassifier
from omni_router.config import RouterConfig
from omni_router.schemas import ComplexityType


def _build_pdf_page(text: str = "", add_image: bool = False, x_offset: int = 50) -> bytes:
    """Helper to build an in-memory PDF with specified text and optional image."""
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)

    font = DictionaryObject()
    font[NameObject("/Type")] = NameObject("/Font")
    font[NameObject("/Subtype")] = NameObject("/Type1")
    font[NameObject("/BaseFont")] = NameObject("/Helvetica")
    font_ref = writer._add_object(font)

    if "/Resources" not in page:
        page[NameObject("/Resources")] = DictionaryObject()
    if "/Font" not in page["/Resources"]:
        page["/Resources"][NameObject("/Font")] = DictionaryObject()
    page["/Resources"]["/Font"][NameObject("/F1")] = font_ref

    if add_image:
        img_stream = DecodedStreamObject()
        img_stream.set_data(b"\x00" * 100)
        img_stream[NameObject("/Type")] = NameObject("/XObject")
        img_stream[NameObject("/Subtype")] = NameObject("/Image")
        img_stream[NameObject("/Width")] = NumberObject(10)
        img_stream[NameObject("/Height")] = NumberObject(10)
        img_stream[NameObject("/ColorSpace")] = NameObject("/DeviceGray")
        img_stream[NameObject("/BitsPerComponent")] = NumberObject(8)
        if "/XObject" not in page["/Resources"]:
            page["/Resources"][NameObject("/XObject")] = DictionaryObject()
        page["/Resources"]["/XObject"][NameObject("/Im0")] = writer._add_object(img_stream)

    if text:
        safe_text = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        content_bytes = f"BT /F1 12 Tf {x_offset} 700 Td ({safe_text}) Tj ET".encode("latin-1")
        content = DecodedStreamObject()
        content.set_data(content_bytes)
        page[NameObject("/Contents")] = writer._add_object(content)

    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _build_multi_column_pdf() -> bytes:
    """Helper to build a PDF with two distinct text columns."""
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)

    font = DictionaryObject()
    font[NameObject("/Type")] = NameObject("/Font")
    font[NameObject("/Subtype")] = NameObject("/Type1")
    font[NameObject("/BaseFont")] = NameObject("/Helvetica")
    font_ref = writer._add_object(font)

    if "/Resources" not in page:
        page[NameObject("/Resources")] = DictionaryObject()
    if "/Font" not in page["/Resources"]:
        page["/Resources"][NameObject("/Font")] = DictionaryObject()
    page["/Resources"]["/Font"][NameObject("/F1")] = font_ref

    # Generate streams with left column (x=60) and right column (x=360)
    lines = []
    # Left column: x ~ 60 (60/612 = 0.098)
    for i in range(15):
        y = 700 - (i * 20)
        lines.append(f"BT /F1 10 Tf 60 {y} Td (Left column line number {i}) Tj ET")
    # Right column: x ~ 360 (360/612 = 0.588)
    for i in range(15):
        y = 700 - (i * 20)
        lines.append(f"BT /F1 10 Tf 360 {y} Td (Right column line number {i}) Tj ET")

    content_data = "\n".join(lines).encode("latin-1")
    content = DecodedStreamObject()
    content.set_data(content_data)
    page[NameObject("/Contents")] = writer._add_object(content)

    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


@pytest.fixture
def classifier() -> PDFClassifier:
    """Default classifier instance."""
    return PDFClassifier()


def test_classify_simple_text_pdf(tmp_path: Path, classifier: PDFClassifier) -> None:
    """PDF with clean text and no complex structures should be SIMPLE_TEXT."""
    text = (
        "This is a standard textual corporate report containing simple paragraphs "
        "and clean sentences. It does not contain any complex mathematical equations, "
        "nor does it have any raster images or multi-column newspaper layouts."
    )
    pdf_bytes = _build_pdf_page(text=text, add_image=False)
    file_path = tmp_path / "simple_doc.pdf"
    file_path.write_bytes(pdf_bytes)

    result = classifier.classify(file_path)

    assert result.classification == ComplexityType.SIMPLE_TEXT
    assert result.has_images is False
    assert result.has_math_symbols is False
    assert result.avg_chars_per_page >= 100


def test_classify_scanned_pdf(tmp_path: Path, classifier: PDFClassifier) -> None:
    """PDF with low character count and embedded image should be COMPLEX_SCAN."""
    # Under default min_chars_per_page (100) + embedded image
    text = "Short scan label"
    pdf_bytes = _build_pdf_page(text=text, add_image=True)
    file_path = tmp_path / "scanned_invoice.pdf"
    file_path.write_bytes(pdf_bytes)

    result = classifier.classify(file_path)

    assert result.classification == ComplexityType.COMPLEX_SCAN
    assert result.has_images is True
    assert result.avg_chars_per_page < 100


def test_classify_math_technical_pdf(tmp_path: Path, classifier: PDFClassifier) -> None:
    """PDF with LaTeX expressions and math formulas should be COMPLEX_LAYOUT."""
    text = (
        "Let us consider \\begin{equation} \\frac{a}{b} = \\sum_{i=1}^n x_i "
        "\\int f(x)dx \\sqrt{y} \\alpha \\beta \\end{equation}"
    )
    pdf_bytes = _build_pdf_page(text=text, add_image=False)
    file_path = tmp_path / "math_paper.pdf"
    file_path.write_bytes(pdf_bytes)

    result = classifier.classify(file_path)

    assert result.classification == ComplexityType.COMPLEX_LAYOUT
    assert result.has_math_symbols is True
    assert result.math_symbol_count >= 3


def test_classify_multi_column_pdf(tmp_path: Path, classifier: PDFClassifier) -> None:
    """PDF with distinct two-column layout should be COMPLEX_LAYOUT."""
    pdf_bytes = _build_multi_column_pdf()
    file_path = tmp_path / "two_column.pdf"
    file_path.write_bytes(pdf_bytes)

    result = classifier.classify(file_path)

    assert result.classification == ComplexityType.COMPLEX_LAYOUT
    assert result.is_multi_column is True


def test_defensive_fallback_on_corrupted_pdf(tmp_path: Path, classifier: PDFClassifier) -> None:
    """Corrupted file triggers defensive fallback to SIMPLE_TEXT without raising."""
    corrupted_file = tmp_path / "corrupted.pdf"
    corrupted_file.write_bytes(b"%PDF-1.4\nGARBAGE_CONTENT_CORRUPTED\x00\xff\xfe")

    result = classifier.classify(corrupted_file)

    # Fallback to SIMPLE_TEXT
    assert result.classification == ComplexityType.SIMPLE_TEXT
    assert result.details.get("defensive_fallback") is True


def test_nonexistent_file_raises_not_found(classifier: PDFClassifier) -> None:
    """Non-existent file should raise FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        classifier.classify("non_existent_file_xyz.pdf")


@pytest.mark.asyncio
async def test_aclassify_async(tmp_path: Path, classifier: PDFClassifier) -> None:
    """Asynchronous classification produces equivalent result."""
    text = "A simple sentence that tests async capability." * 5
    pdf_bytes = _build_pdf_page(text=text, add_image=False)
    file_path = tmp_path / "async_doc.pdf"
    file_path.write_bytes(pdf_bytes)

    result = await classifier.aclassify(file_path)

    assert result.classification == ComplexityType.SIMPLE_TEXT
    assert result.page_count == 1


def test_custom_config_thresholds(tmp_path: Path) -> None:
    """Classifier respects custom config thresholds."""
    custom_cfg = RouterConfig(min_chars_per_page=500, math_symbol_threshold=1)
    custom_clf = PDFClassifier(config=custom_cfg)

    # 150 chars with image: under standard threshold (100) it would be SIMPLE_TEXT,
    # but under custom 500 it becomes COMPLEX_SCAN!
    text = "Short text under 500 characters." * 3
    pdf_bytes = _build_pdf_page(text=text, add_image=True)
    file_path = tmp_path / "custom_threshold.pdf"
    file_path.write_bytes(pdf_bytes)

    result = custom_clf.classify(file_path)
    assert result.classification == ComplexityType.COMPLEX_SCAN
