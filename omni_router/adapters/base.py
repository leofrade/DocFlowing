"""OmniMarkdown Router - Base Adapter Contract (RF-03)."""

import asyncio
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Union
from omni_router.schemas import ConversionResult


class BaseAdapter(ABC):
    """Abstract base class defining the engine adapter contract."""

    @abstractmethod
    def convert(self, file_path: Union[str, Path], **kwargs) -> ConversionResult:
        """Converte o documento para Markdown de forma síncrona."""
        pass

    async def aconvert(self, file_path: Union[str, Path], **kwargs) -> ConversionResult:
        """Converte o documento para Markdown de forma assíncrona."""
        return await asyncio.to_thread(self.convert, file_path, **kwargs)

    @abstractmethod
    def is_available(self) -> bool:
        """Verifica se as dependências (e.g. PyTorch/CUDA ou pacotes) estão prontas."""
        pass
