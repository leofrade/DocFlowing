"""OmniMarkdown Router - Configuration and Decision Thresholds.

Manages environment variables, default heuristics thresholds,
and parser options for both MarkItDown and Marker engines.
"""

import os
from typing import Optional, Set
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Carrega variáveis do arquivo .env se existir
load_dotenv()


class RouterConfig(BaseModel):
    """Configuration settings for OmniMarkdown Router."""

    min_chars_per_page: int = Field(
        default=100,
        description="Média mínima de caracteres por página para considerar texto limpo (RF-02)"
    )
    max_pages_sample: int = Field(
        default=10,
        description="Número máximo de páginas amostradas para a classificação rápida de PDF"
    )
    math_symbol_threshold: int = Field(
        default=3,
        description="Contagem mínima de termos ou notações LaTeX/matemáticas para classificar como COMPLEX_LAYOUT"
    )
    marker_api_url: Optional[str] = Field(
        default=None,
        description="URL da API remota do Marker (ex: http://localhost:8000/convert ou endpoint em nuvem)"
    )
    marker_api_key: Optional[str] = Field(
        default=None,
        description="Chave de autenticação (Bearer Token) para API remota do Marker"
    )
    marker_timeout_seconds: float = Field(
        default=30.0,
        description="Timeout em segundos para inferência do Marker (local ou remoto)"
    )
    office_extensions: Set[str] = Field(
        default={
            ".docx", ".pptx", ".xlsx", ".csv", ".tsv",
            ".html", ".xml", ".json", ".txt", ".zip",
            ".doc", ".xls", ".ppt", ".rtf", ".odt", ".ods", ".odp"
        },
        description="Extensões de documentos nativos de escritório/web roteados diretamente para MarkItDown"
    )
    log_level: str = Field(
        default="INFO",
        description="Nível de log padrão (DEBUG, INFO, WARNING, ERROR)"
    )

    @classmethod
    def from_env(cls) -> "RouterConfig":
        """Instantiate RouterConfig reading overrides from environment variables."""
        min_chars = os.getenv("OMNI_MIN_CHARS_PER_PAGE")
        max_pages = os.getenv("OMNI_MAX_PAGES_SAMPLE")
        math_thresh = os.getenv("OMNI_MATH_SYMBOL_THRESHOLD")
        marker_url = os.getenv("MARKER_API_URL")
        marker_key = os.getenv("MARKER_API_KEY")
        marker_timeout = os.getenv("MARKER_TIMEOUT_SECONDS")
        log_lvl = os.getenv("OMNI_LOG_LEVEL", "INFO")

        return cls(
            min_chars_per_page=int(min_chars) if min_chars else 100,
            max_pages_sample=int(max_pages) if max_pages else 10,
            math_symbol_threshold=int(math_thresh) if math_thresh else 3,
            marker_api_url=marker_url,
            marker_api_key=marker_key,
            marker_timeout_seconds=float(marker_timeout) if marker_timeout else 30.0,
            log_level=log_lvl,
        )


# Default global configuration instance
default_config = RouterConfig.from_env()
