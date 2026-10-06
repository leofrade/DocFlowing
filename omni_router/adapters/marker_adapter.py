"""OmniMarkdown Router - Marker Engine Adapter.

Implements the BaseAdapter interface for datalab-to/marker.
Supports both local execution (GPU/CPU via PyTorch) and remote execution (via HTTP API microservice),
with graceful degradation when dependencies or hardware are unavailable.
"""

import asyncio
import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional, Union

import httpx

from omni_router.adapters.base import BaseAdapter
from omni_router.config import RouterConfig, default_config
from omni_router.schemas import ConversionResult

logger = logging.getLogger(__name__)

# Dynamic inspection of local Marker installation without failing imports
MARKER_LOCAL_AVAILABLE = False
_local_marker_entrypoint = None

try:
    # Marker v0.2+ or v1.0+ converters inspection
    try:
        from marker.converters.pdf import PdfConverter  # type: ignore
        MARKER_LOCAL_AVAILABLE = True
        _local_marker_entrypoint = "PdfConverter"
    except ImportError:
        try:
            from marker.convert import convert_single_pdf  # type: ignore
            MARKER_LOCAL_AVAILABLE = True
            _local_marker_entrypoint = "convert_single_pdf"
        except ImportError:
            MARKER_LOCAL_AVAILABLE = False
except Exception as exc:
    logger.debug(f"Marker local module check encountered: {exc}")
    MARKER_LOCAL_AVAILABLE = False


class MarkerAdapter(BaseAdapter):
    """Adapter for Marker engine with dual local/remote execution support."""

    def __init__(
        self,
        api_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: Optional[float] = None,
        config: Optional[RouterConfig] = None,
    ) -> None:
        """Initialize Marker adapter.

        Args:
            api_url: Optional remote Marker API URL (e.g., http://localhost:8000/convert).
            api_key: Optional API Bearer token for remote Marker service.
            timeout: Optional HTTP request or inference timeout in seconds.
            config: Optional RouterConfig instance.
        """
        cfg = config or default_config
        self.api_url = api_url or cfg.marker_api_url
        self.api_key = api_key or cfg.marker_api_key
        self.timeout = timeout or cfg.marker_timeout_seconds
        self.local_available = MARKER_LOCAL_AVAILABLE

    def is_available(self) -> bool:
        """Check if Marker is available via remote API or local dependencies."""
        if bool(self.api_url):
            return True
        return self.local_available

    def convert(self, file_path: Union[str, Path], **kwargs: Any) -> ConversionResult:
        """Convert PDF to Markdown using Marker (remote API or local engine).

        Args:
            file_path: Path to target PDF file.
            **kwargs: Extra parameters passed to the engine.

        Returns:
            ConversionResult with high-fidelity Markdown output.
        """
        if not self.is_available():
            raise RuntimeError(
                "Marker engine is not available. Please install 'marker-pdf' "
                "or set the MARKER_API_URL environment variable."
            )

        path = Path(file_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        start_time = time.perf_counter()

        if self.api_url:
            markdown, meta = self._convert_remote(path, **kwargs)
        else:
            markdown, meta = self._convert_local(path, **kwargs)

        latency_ms = (time.perf_counter() - start_time) * 1000.0

        return ConversionResult(
            markdown=markdown,
            engine_used="marker",
            fallback_triggered=False,
            latency_ms=round(latency_ms, 2),
            metadata=meta,
            error_message=None,
        )

    async def aconvert(self, file_path: Union[str, Path], **kwargs: Any) -> ConversionResult:
        """Asynchronously convert PDF to Markdown using Marker."""
        if not self.is_available():
            raise RuntimeError(
                "Marker engine is not available. Please install 'marker-pdf' "
                "or set the MARKER_API_URL environment variable."
            )

        path = Path(file_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        start_time = time.perf_counter()

        if self.api_url:
            markdown, meta = await self._aconvert_remote(path, **kwargs)
        else:
            markdown, meta = await asyncio.to_thread(self._convert_local, path, **kwargs)

        latency_ms = (time.perf_counter() - start_time) * 1000.0

        return ConversionResult(
            markdown=markdown,
            engine_used="marker",
            fallback_triggered=False,
            latency_ms=round(latency_ms, 2),
            metadata=meta,
            error_message=None,
        )

    def _convert_remote(self, path: Path, **kwargs: Any) -> tuple[str, Dict[str, Any]]:
        """Call remote Marker HTTP API microservice synchronously."""
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        with open(path, "rb") as f:
            files = {"file": (path.name, f, "application/pdf")}
            data = {k: str(v) for k, v in kwargs.items()}

            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(
                    self.api_url,  # type: ignore
                    headers=headers,
                    files=files,
                    data=data,
                )
                response.raise_for_status()

                try:
                    res_json = response.json()
                    markdown = res_json.get("markdown", "")
                    meta = res_json.get("metadata", {})
                except Exception:
                    # In case the remote server returns plain markdown text
                    markdown = response.text
                    meta = {}

                meta["remote_api"] = self.api_url
                meta["file_name"] = path.name
                return markdown, meta

    async def _aconvert_remote(self, path: Path, **kwargs: Any) -> tuple[str, Dict[str, Any]]:
        """Call remote Marker HTTP API microservice asynchronously."""
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        file_bytes = path.read_bytes()
        files = {"file": (path.name, file_bytes, "application/pdf")}
        data = {k: str(v) for k, v in kwargs.items()}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                self.api_url,  # type: ignore
                headers=headers,
                files=files,
                data=data,
            )
            response.raise_for_status()

            try:
                res_json = response.json()
                markdown = res_json.get("markdown", "")
                meta = res_json.get("metadata", {})
            except Exception:
                markdown = response.text
                meta = {}

            meta["remote_api"] = self.api_url
            meta["file_name"] = path.name
            return markdown, meta

    def _convert_local(self, path: Path, **kwargs: Any) -> tuple[str, Dict[str, Any]]:
        """Run local Marker inference with PyTorch/Vision models."""
        if not self.local_available:
            raise RuntimeError("Marker local dependencies are not available.")

        # Dynamically execute local converter based on available entry point
        try:
            if _local_marker_entrypoint == "PdfConverter":
                from marker.converters.pdf import PdfConverter  # type: ignore
                from marker.models import load_all_models  # type: ignore

                models = load_all_models()
                converter = PdfConverter(artifact_dict=models)
                rendered = converter(str(path))
                text, _, out_meta = rendered
                return text, {"local": True, "out_meta": out_meta}
            elif _local_marker_entrypoint == "convert_single_pdf":
                from marker.convert import convert_single_pdf  # type: ignore
                from marker.models import load_all_models  # type: ignore

                model_lst = load_all_models()
                full_text, images, out_meta = convert_single_pdf(str(path), model_lst)
                return full_text, {"local": True, "out_meta": out_meta}
            else:
                raise NotImplementedError(
                    f"Unsupported Marker local entrypoint: {_local_marker_entrypoint}"
                )
        except Exception as exc:
            logger.error(f"Local Marker inference failed: {exc}")
            raise
