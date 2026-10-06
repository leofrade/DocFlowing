"""OmniMarkdown Router - Fast PDF Complexity Classifier (RF-02).

Performs lightweight, sub-second heuristic inspection on PDFs using PyPDF:
- Scanned detection: low character count + embedded images -> COMPLEX_SCAN (Marker)
- Structural detection: math/LaTeX indicators or multi-column layout -> COMPLEX_LAYOUT (Marker)
- Standard/clean text -> SIMPLE_TEXT (MarkItDown)
Equipped with defensive fallback and asynchronous execution.
"""

import asyncio
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from pypdf import PdfReader

from omni_router.config import RouterConfig, default_config
from omni_router.schemas import ComplexityType, PDFInspectionResult

logger = logging.getLogger(__name__)

# Common LaTeX mathematical keywords and environments
LATEX_MATH_PATTERN = re.compile(
    r"\\(begin\{(?:equation|align|gather|bmatrix|pmatrix|cases|multline)\}|"
    r"frac\{|sqrt\{|sum[\s_]|int[\s_]|prod[\s_]|alpha|beta|gamma|theta|partial|"
    r"infty|nabla|pm|leq|geq|neq|approx|mathbf|mathbb|times)",
    re.IGNORECASE,
)

LATEX_DELIMITERS_PATTERN = re.compile(r"\$\$[\s\S]+?\$\$|\$[^\$\n]{2,}\$")

# Unicode mathematical operators and characters
MATH_UNICODE_CHARS = {
    "∑", "∫", "√", "∂", "≠", "≤", "≥", "±", "∞", "≈", "∏",
    "∇", "∈", "∉", "⊂", "⊆", "∪", "∩", "×", "÷", "∀", "∃",
}


class PDFClassifier:
    """Lightweight heuristic complexity classifier for PDF documents."""

    def __init__(self, config: Optional[RouterConfig] = None) -> None:
        """Initialize PDF classifier with optional custom configuration."""
        self.config = config or default_config

    def classify(self, file_path: Union[str, Path]) -> PDFInspectionResult:
        """Inspect PDF and return complexity classification.

        Args:
            file_path: Path to target PDF file.

        Returns:
            PDFInspectionResult with classification enum and diagnostic metrics.
        """
        path = Path(file_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"PDF file not found: {path}")

        try:
            return self._inspect_pdf(path)
        except Exception as exc:
            logger.warning(
                f"Error inspecting PDF {path}: {exc}. Triggering defensive fallback to SIMPLE_TEXT."
            )
            return PDFInspectionResult(
                classification=ComplexityType.SIMPLE_TEXT,
                page_count=0,
                total_pages=0,
                avg_chars_per_page=0.0,
                has_images=False,
                has_math_symbols=False,
                math_symbol_count=0,
                is_multi_column=False,
                details={"error": str(exc), "defensive_fallback": True},
            )

    async def aclassify(self, file_path: Union[str, Path]) -> PDFInspectionResult:
        """Asynchronously inspect PDF without blocking the event loop."""
        return await asyncio.to_thread(self.classify, file_path)

    def _inspect_pdf(self, path: Path) -> PDFInspectionResult:
        """Internal lightweight inspection logic."""
        reader = PdfReader(str(path), strict=False)

        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception as dec_err:
                logger.debug(f"Could not decrypt PDF with empty password: {dec_err}")

        total_pages = len(reader.pages)
        if total_pages == 0:
            return PDFInspectionResult(
                classification=ComplexityType.SIMPLE_TEXT,
                page_count=0,
                total_pages=0,
                avg_chars_per_page=0.0,
                details={"empty_document": True},
            )

        sample_count = min(total_pages, self.config.max_pages_sample)
        total_chars = 0
        has_images = False
        math_symbol_count = 0
        is_multi_column = False

        for i in range(sample_count):
            page = reader.pages[i]

            # 1. Image presence check
            page_has_image = self._check_images(page)
            if page_has_image:
                has_images = True

            # 2. Text extraction and column analysis
            page_text, page_is_columnar = self._extract_text_and_check_columns(page)
            char_count = len(page_text.strip())
            total_chars += char_count

            if page_is_columnar:
                is_multi_column = True

            # 3. Math indicators detection
            math_hits = self._detect_math_indicators(page_text)
            math_symbol_count += math_hits

        avg_chars_per_page = total_chars / max(sample_count, 1)
        has_math = math_symbol_count >= self.config.math_symbol_threshold

        # Decision tree following RF-02
        if avg_chars_per_page < self.config.min_chars_per_page and has_images:
            classification = ComplexityType.COMPLEX_SCAN
        elif has_math or is_multi_column:
            classification = ComplexityType.COMPLEX_LAYOUT
        else:
            classification = ComplexityType.SIMPLE_TEXT

        return PDFInspectionResult(
            classification=classification,
            page_count=sample_count,
            total_pages=total_pages,
            avg_chars_per_page=round(avg_chars_per_page, 2),
            has_images=has_images,
            has_math_symbols=has_math,
            math_symbol_count=math_symbol_count,
            is_multi_column=is_multi_column,
            details={
                "min_chars_threshold": self.config.min_chars_per_page,
                "math_threshold": self.config.math_symbol_threshold,
            },
        )

    def _check_images(self, page: Any) -> bool:
        """Check if a PDF page contains embedded raster images."""
        try:
            if hasattr(page, "images") and len(page.images) > 0:
                return True
        except Exception:
            pass

        try:
            # Inspection of resource dictionary as fallback
            resources = page.get("/Resources", {})
            if isinstance(resources, dict) and "/XObject" in resources:
                xobjects = resources["/XObject"]
                if hasattr(xobjects, "get_object"):
                    xobjects = xobjects.get_object()
                if isinstance(xobjects, dict):
                    for obj in xobjects.values():
                        sub = getattr(obj, "get", lambda _: None)("/Subtype")
                        if sub == "/Image":
                            return True
        except Exception:
            pass

        return False

    def _extract_text_and_check_columns(self, page: Any) -> tuple[str, bool]:
        """Extract text and perform spatial analysis for multi-column detection."""
        x_positions: List[float] = []

        def visitor(text: str, cm: Any, tm: Any, font_dict: Any, font_size: Any) -> None:
            if text and text.strip():
                if tm and len(tm) >= 6:
                    try:
                        x_positions.append(float(tm[4]))
                    except (ValueError, TypeError):
                        pass

        try:
            extracted_text = page.extract_text(visitor_text=visitor) or ""
        except Exception as exc:
            logger.debug(f"Visitor text extraction failed, falling back to basic: {exc}")
            try:
                extracted_text = page.extract_text() or ""
            except Exception:
                extracted_text = ""

        is_columnar = False
        try:
            page_width = float(page.mediabox.width)
            if page_width > 0 and len(x_positions) >= 10:
                # Relative horizontal coordinates (0.0 to 1.0)
                norm_x = [x / page_width for x in x_positions if 0 <= x <= page_width]
                if len(norm_x) >= 10:
                    left_col = [x for x in norm_x if 0.05 <= x <= 0.44]
                    right_col = [x for x in norm_x if 0.52 <= x <= 0.95]
                    gutter = [x for x in norm_x if 0.44 < x < 0.52]

                    # Clear two-column pattern: text on left and right with empty or minimal gutter
                    total_samples = len(norm_x)
                    if (
                        len(left_col) / total_samples >= 0.25
                        and len(right_col) / total_samples >= 0.25
                        and len(gutter) / total_samples < 0.10
                    ):
                        is_columnar = True
        except Exception as col_err:
            logger.debug(f"Column detection calculation exception: {col_err}")

        return extracted_text, is_columnar

    def _detect_math_indicators(self, text: str) -> int:
        """Count LaTeX commands, math delimiters, and Unicode math symbols in text."""
        if not text:
            return 0

        hits = 0
        # 1. Regex keywords
        hits += len(LATEX_MATH_PATTERN.findall(text))
        # 2. Math delimiters ($...$ or $$...$$)
        hits += len(LATEX_DELIMITERS_PATTERN.findall(text))
        # 3. Unicode symbols
        for char in text:
            if char in MATH_UNICODE_CHARS:
                hits += 1

        return hits
