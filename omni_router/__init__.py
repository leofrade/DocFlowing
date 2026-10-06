"""OmniMarkdown Router: Intelligent Orchestrator for MarkItDown and Marker."""

from omni_router.adapters.base import BaseAdapter
from omni_router.adapters.markitdown_adapter import MarkItDownAdapter
from omni_router.adapters.marker_adapter import MarkerAdapter
from omni_router.classifiers.pdf_classifier import PDFClassifier
from omni_router.config import RouterConfig, default_config
from omni_router.router import OmniMarkdownRouter, OmniRouter
from omni_router.schemas import (
    ComplexityType,
    ConversionResult,
    EngineLiteral,
    EngineType,
    PDFInspectionResult,
)

__version__ = "1.0.0"

__all__ = [
    "OmniMarkdownRouter",
    "OmniRouter",
    "ConversionResult",
    "EngineType",
    "EngineLiteral",
    "ComplexityType",
    "PDFInspectionResult",
    "RouterConfig",
    "default_config",
    "BaseAdapter",
    "MarkItDownAdapter",
    "MarkerAdapter",
    "PDFClassifier",
]
