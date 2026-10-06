"""OmniMarkdown Router - Intelligent Decision Orchestrator.

Routes documents dynamically between Microsoft's MarkItDown and Marker
based on file format, MIME inspection, and PDF complexity heuristics.
Includes automatic fallback and user override support (RF-01, RF-05).
"""

import logging
import mimetypes
import time
from pathlib import Path
from typing import Any, Dict, Optional, Union

from omni_router.adapters.base import BaseAdapter
from omni_router.adapters.markitdown_adapter import MarkItDownAdapter
from omni_router.adapters.marker_adapter import MarkerAdapter
from omni_router.classifiers.pdf_classifier import PDFClassifier
from omni_router.config import RouterConfig, default_config
from omni_router.schemas import (
    ComplexityType,
    ConversionResult,
    EngineLiteral,
    EngineType,
)

logger = logging.getLogger(__name__)

# Try optional python-magic for binary buffer inspection if available
try:
    import magic  # type: ignore
    MAGIC_AVAILABLE = True
except ImportError:
    magic = None  # type: ignore
    MAGIC_AVAILABLE = False


class OmniMarkdownRouter:
    """Smart Document-to-Markdown Orchestrator."""

    def __init__(
        self,
        config: Optional[RouterConfig] = None,
        markitdown_adapter: Optional[BaseAdapter] = None,
        marker_adapter: Optional[BaseAdapter] = None,
        classifier: Optional[PDFClassifier] = None,
    ) -> None:
        """Initialize OmniMarkdownRouter with components and configuration.

        Args:
            config: Optional configuration settings.
            markitdown_adapter: Optional custom MarkItDown adapter.
            marker_adapter: Optional custom Marker adapter.
            classifier: Optional custom PDFClassifier instance.
        """
        self.config = config or default_config
        self.markitdown_adapter = markitdown_adapter or MarkItDownAdapter()
        self.marker_adapter = marker_adapter or MarkerAdapter(config=self.config)
        self.classifier = classifier or PDFClassifier(config=self.config)

    def inspect_file(self, file_path: Union[str, Path]) -> Dict[str, Any]:
        """Inspect file MIME type, extension, and PDF complexity without converting.

        Args:
            file_path: Path to target file.

        Returns:
            Dictionary with detection and classification details.
        """
        path = Path(file_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        mime_type = self._detect_mime_type(path)
        is_pdf = path.suffix.lower() == ".pdf" or mime_type == "application/pdf"

        info: Dict[str, Any] = {
            "file_name": path.name,
            "extension": path.suffix.lower(),
            "mime_type": mime_type,
            "is_pdf": is_pdf,
            "is_office_format": path.suffix.lower() in self.config.office_extensions,
        }

        if is_pdf:
            inspection = self.classifier.classify(path)
            info["pdf_inspection"] = inspection.model_dump()
            info["recommended_engine"] = (
                "markitdown"
                if inspection.classification == ComplexityType.SIMPLE_TEXT
                else "marker"
            )
        else:
            info["recommended_engine"] = "markitdown"

        return info

    def convert(
        self,
        file_path: Union[str, Path],
        force_engine: Optional[Union[EngineLiteral, EngineType, str]] = None,
        **kwargs: Any,
    ) -> ConversionResult:
        """Convert a document to Markdown with smart routing and graceful fallback.

        Args:
            file_path: Path to document file (.pdf, .docx, .xlsx, .csv, etc.).
            force_engine: Optional override ("markitdown" or "marker").
            **kwargs: Extra parameters passed down to the underlying adapter.

        Returns:
            ConversionResult with standardized schema and metadata.
        """
        path = Path(file_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        start_time = time.perf_counter()
        normalized_force = str(force_engine).lower() if force_engine else None

        if normalized_force:
            result = self._convert_with_force_engine(path, normalized_force, **kwargs)
        else:
            result = self._convert_with_auto_routing(path, **kwargs)

        total_latency_ms = (time.perf_counter() - start_time) * 1000.0
        result.latency_ms = round(total_latency_ms, 2)
        return result

    async def aconvert(
        self,
        file_path: Union[str, Path],
        force_engine: Optional[Union[EngineLiteral, EngineType, str]] = None,
        **kwargs: Any,
    ) -> ConversionResult:
        """Asynchronously convert a document to Markdown with smart routing."""
        path = Path(file_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        start_time = time.perf_counter()
        normalized_force = str(force_engine).lower() if force_engine else None

        if normalized_force:
            result = await self._aconvert_with_force_engine(path, normalized_force, **kwargs)
        else:
            result = await self._aconvert_with_auto_routing(path, **kwargs)

        total_latency_ms = (time.perf_counter() - start_time) * 1000.0
        result.latency_ms = round(total_latency_ms, 2)
        return result

    def _convert_with_force_engine(
        self,
        path: Path,
        engine: str,
        **kwargs: Any,
    ) -> ConversionResult:
        """Execute conversion when engine is forced by caller (RF-05)."""
        if engine == "markitdown":
            return self.markitdown_adapter.convert(path, **kwargs)

        if engine == "marker":
            try:
                return self.marker_adapter.convert(path, **kwargs)
            except Exception as exc:
                logger.warning(
                    f"Forced engine 'marker' failed for {path.name}: {exc}. "
                    f"Triggering graceful fallback to 'markitdown'."
                )
                res = self.markitdown_adapter.convert(path, **kwargs)
                res.fallback_triggered = True
                res.error_message = f"Marker error: {exc}"
                return res

        raise ValueError(
            f"Invalid engine '{engine}'. Supported engines: 'markitdown', 'marker'."
        )

    async def _aconvert_with_force_engine(
        self,
        path: Path,
        engine: str,
        **kwargs: Any,
    ) -> ConversionResult:
        """Execute asynchronous conversion when engine is forced."""
        if engine == "markitdown":
            return await self.markitdown_adapter.aconvert(path, **kwargs)

        if engine == "marker":
            try:
                return await self.marker_adapter.aconvert(path, **kwargs)
            except Exception as exc:
                logger.warning(
                    f"Forced engine 'marker' failed for {path.name}: {exc}. "
                    f"Triggering graceful fallback to 'markitdown'."
                )
                res = await self.markitdown_adapter.aconvert(path, **kwargs)
                res.fallback_triggered = True
                res.error_message = f"Marker error: {exc}"
                return res

        raise ValueError(
            f"Invalid engine '{engine}'. Supported engines: 'markitdown', 'marker'."
        )

    def _convert_with_auto_routing(self, path: Path, **kwargs: Any) -> ConversionResult:
        """Automatically route file based on MIME type and PDF complexity analysis."""
        mime_type = self._detect_mime_type(path)
        is_pdf = path.suffix.lower() == ".pdf" or mime_type == "application/pdf"

        if is_pdf:
            inspection = self.classifier.classify(path)

            if inspection.classification == ComplexityType.SIMPLE_TEXT:
                logger.info(
                    f"Routing PDF {path.name} to MarkItDown (SIMPLE_TEXT, clean text layer)."
                )
                result = self.markitdown_adapter.convert(path, **kwargs)
                result.metadata["pdf_inspection"] = inspection.model_dump()
                return result

            # COMPLEX_SCAN or COMPLEX_LAYOUT
            logger.info(
                f"Routing PDF {path.name} to Marker ({inspection.classification.value})."
            )
            if self.marker_adapter.is_available():
                try:
                    result = self.marker_adapter.convert(path, **kwargs)
                    result.metadata["pdf_inspection"] = inspection.model_dump()
                    return result
                except Exception as exc:
                    logger.warning(
                        f"Marker failed for {path.name} ({exc}). "
                        f"Gracefully falling back to MarkItDown."
                    )
                    result = self.markitdown_adapter.convert(path, **kwargs)
                    result.fallback_triggered = True
                    result.error_message = f"Marker failed: {exc}"
                    result.metadata["pdf_inspection"] = inspection.model_dump()
                    return result
            else:
                logger.warning(
                    f"Marker required for {path.name} ({inspection.classification.value}) "
                    f"but is unavailable. Degrading gracefully to MarkItDown."
                )
                result = self.markitdown_adapter.convert(path, **kwargs)
                result.fallback_triggered = True
                result.error_message = (
                    "Marker engine is unavailable in this environment (no GPU/models "
                    "or unconfigured remote API). Fallback to MarkItDown executed."
                )
                result.metadata["pdf_inspection"] = inspection.model_dump()
                return result

        # Office or other standard documents: direct to MarkItDown (0% GPU)
        logger.info(
            f"Routing file {path.name} ({path.suffix}) to MarkItDown (0% GPU Office/Web parser)."
        )
        result = self.markitdown_adapter.convert(path, **kwargs)
        result.metadata["mime_type"] = mime_type
        return result

    async def _aconvert_with_auto_routing(self, path: Path, **kwargs: Any) -> ConversionResult:
        """Asynchronously route file based on MIME type and PDF complexity analysis."""
        mime_type = self._detect_mime_type(path)
        is_pdf = path.suffix.lower() == ".pdf" or mime_type == "application/pdf"

        if is_pdf:
            inspection = await self.classifier.aclassify(path)

            if inspection.classification == ComplexityType.SIMPLE_TEXT:
                logger.info(
                    f"Routing PDF {path.name} to MarkItDown (SIMPLE_TEXT, clean text layer)."
                )
                result = await self.markitdown_adapter.aconvert(path, **kwargs)
                result.metadata["pdf_inspection"] = inspection.model_dump()
                return result

            # COMPLEX_SCAN or COMPLEX_LAYOUT
            logger.info(
                f"Routing PDF {path.name} to Marker ({inspection.classification.value})."
            )
            if self.marker_adapter.is_available():
                try:
                    result = await self.marker_adapter.aconvert(path, **kwargs)
                    result.metadata["pdf_inspection"] = inspection.model_dump()
                    return result
                except Exception as exc:
                    logger.warning(
                        f"Marker failed for {path.name} ({exc}). "
                        f"Gracefully falling back to MarkItDown."
                    )
                    result = await self.markitdown_adapter.aconvert(path, **kwargs)
                    result.fallback_triggered = True
                    result.error_message = f"Marker failed: {exc}"
                    result.metadata["pdf_inspection"] = inspection.model_dump()
                    return result
            else:
                logger.warning(
                    f"Marker required for {path.name} ({inspection.classification.value}) "
                    f"but is unavailable. Degrading gracefully to MarkItDown."
                )
                result = await self.markitdown_adapter.aconvert(path, **kwargs)
                result.fallback_triggered = True
                result.error_message = (
                    "Marker engine is unavailable in this environment (no GPU/models "
                    "or unconfigured remote API). Fallback to MarkItDown executed."
                )
                result.metadata["pdf_inspection"] = inspection.model_dump()
                return result

        # Office or other standard documents: direct to MarkItDown (0% GPU)
        logger.info(
            f"Routing file {path.name} ({path.suffix}) to MarkItDown (0% GPU Office/Web parser)."
        )
        result = await self.markitdown_adapter.aconvert(path, **kwargs)
        result.metadata["mime_type"] = mime_type
        return result

    def _detect_mime_type(self, path: Path) -> str:
        """Detect MIME type using python-magic or mimetypes with defensive fallback."""
        if MAGIC_AVAILABLE:
            try:
                mime = magic.from_file(str(path), mime=True)
                if mime:
                    return str(mime)
            except Exception:
                pass

        mime_type, _ = mimetypes.guess_type(str(path))
        return mime_type or "application/octet-stream"


# Convenient alias
OmniRouter = OmniMarkdownRouter
