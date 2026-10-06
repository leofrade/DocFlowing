"""OmniMarkdown Router - Pydantic v2 Data Contracts and Schemas.

Defines unified output models and classification enums as specified
in Section 4 (RF-04) of the Product Requirements Document.
"""

from enum import Enum
from typing import Any, Dict, Literal, Optional
from pydantic import BaseModel, Field


class EngineType(str, Enum):
    """Supported conversion engines."""

    MARKITDOWN = "markitdown"
    MARKER = "marker"


EngineLiteral = Literal["markitdown", "marker"]


class ComplexityType(str, Enum):
    """PDF classification types based on complexity heuristics."""

    SIMPLE_TEXT = "SIMPLE_TEXT"
    COMPLEX_SCAN = "COMPLEX_SCAN"
    COMPLEX_LAYOUT = "COMPLEX_LAYOUT"


class PDFInspectionResult(BaseModel):
    """Detailed result of PDF lightweight inspection."""

    classification: ComplexityType = Field(
        ...,
        description="Classificação atribuída ao PDF com base na heurística de complexidade"
    )
    page_count: int = Field(
        default=0,
        description="Número de páginas inspecionadas"
    )
    total_pages: int = Field(
        default=0,
        description="Número total de páginas do documento"
    )
    avg_chars_per_page: float = Field(
        default=0.0,
        description="Média de caracteres extraídos por página"
    )
    has_images: bool = Field(
        default=False,
        description="Indica se há imagens embutidas no documento"
    )
    has_math_symbols: bool = Field(
        default=False,
        description="Indica se foram detectadas fórmulas ou notações matemáticas"
    )
    math_symbol_count: int = Field(
        default=0,
        description="Quantidade de indicadores matemáticos detectados"
    )
    is_multi_column: bool = Field(
        default=False,
        description="Indica se foi detectado layout com múltiplas colunas"
    )
    details: Dict[str, Any] = Field(
        default_factory=dict,
        description="Metadados adicionais da inspeção (ex: fallback, avisos, coordenadas)"
    )


class ConversionResult(BaseModel):
    """Standardized conversion output contract (RF-04)."""

    markdown: str = Field(
        ...,
        description="Conteúdo convertido em Markdown"
    )
    engine_used: Literal["markitdown", "marker"] = Field(
        ...,
        description="Motor efetivamente utilizado"
    )
    fallback_triggered: bool = Field(
        default=False,
        description="Indica se houve fallback após falha do motor principal"
    )
    latency_ms: float = Field(
        ...,
        description="Tempo total de processamento em milissegundos"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Metadados do arquivo e do parser"
    )
    error_message: Optional[str] = Field(
        default=None,
        description="Mensagem de erro em caso de resiliência parcial"
    )
