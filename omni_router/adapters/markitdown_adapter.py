"""OmniMarkdown Router - MarkItDown Engine Adapter.

Implements the BaseAdapter interface using Microsoft's MarkItDown library.
Optimized for ultra-fast, sub-second conversion of text, office formats, and simple PDFs.
"""

import time
from pathlib import Path
from typing import Any, Dict, Optional, Union
import logging

from omni_router.adapters.base import BaseAdapter
from omni_router.schemas import ConversionResult

logger = logging.getLogger(__name__)

# Tentativa de import seguro do MarkItDown
try:
    from markitdown import MarkItDown
    MARKITDOWN_AVAILABLE = True
except ImportError:
    MarkItDown = None  # type: ignore
    MARKITDOWN_AVAILABLE = False


class MarkItDownAdapter(BaseAdapter):
    """Adapter for Microsoft's MarkItDown conversion engine."""

    def __init__(self, markitdown_instance: Optional[Any] = None) -> None:
        """Initialize MarkItDown adapter.

        Args:
            markitdown_instance: Optional pre-configured MarkItDown instance.
        """
        self._available = MARKITDOWN_AVAILABLE
        self._md: Optional[Any] = None

        if self._available:
            try:
                self._md = markitdown_instance or MarkItDown()
            except Exception as exc:
                logger.error(f"Failed to initialize MarkItDown: {exc}")
                self._available = False

    def is_available(self) -> bool:
        """Return True if MarkItDown is installed and initialized."""
        return self._available and self._md is not None

    def convert(self, file_path: Union[str, Path], **kwargs: Any) -> ConversionResult:
        """Convert document to Markdown using MarkItDown.

        Args:
            file_path: Path to the target file.
            **kwargs: Additional parameters passed to MarkItDown.convert.

        Returns:
            ConversionResult with converted markdown and performance metrics.
        """
        if not self.is_available():
            raise RuntimeError(
                "MarkItDown engine is not available. Please ensure 'markitdown' is installed."
            )

        path = Path(file_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        start_time = time.perf_counter()
        raw_result = self._md.convert(str(path), **kwargs)  # type: ignore
        latency_ms = (time.perf_counter() - start_time) * 1000.0

        # MarkItDown provides either markdown attribute or text_content
        markdown_text = getattr(raw_result, "markdown", None)
        if markdown_text is None:
            markdown_text = getattr(raw_result, "text_content", "")

        metadata: Dict[str, Any] = {
            "title": getattr(raw_result, "title", None),
            "file_name": path.name,
            "file_size_bytes": path.stat().st_size,
        }

        return ConversionResult(
            markdown=markdown_text or "",
            engine_used="markitdown",
            fallback_triggered=False,
            latency_ms=round(latency_ms, 2),
            metadata=metadata,
            error_message=None,
        )
