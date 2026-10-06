# Product Requirements Document (PRD)
## OmniMarkdown Router: Orquestrador Inteligente MarkItDown + Marker

- **Versão:** 1.0.0
- **Status:** Aprovado para Desenvolvimento
- **Público-alvo:** Agentes de Geração de Código (Antigravity), Engenheiros de RAG / ML Platform

---

## 1. Contexto e Problema

Pipelines modernos de RAG (Retrieval-Augmented Generation) exigem a ingestão de múltiplos formatos de documentos com saída unificada em Markdown. Atualmente, existem duas abordagens predominantes no ecossistema open-source:

1. **Parsers Rápidos / CPU-Bound (`microsoft/markitdown`):**
   - *Vantagens:* Excelente cobertura de formatos de escritório (`.docx`, `.xlsx`, `.pptx`, `.csv`, `.html`), latência na casa dos milissegundos e dependências extremamente leves.
   - *Desvantagens:* Falha em PDFs complexos (artigos científicos com colunas múltiplas, fórmulas matemáticas em LaTeX, tabelas sem bordas nítidas e documentos digitalizados/scans).

2. **Engines de Visão e Deep Learning (`datalab-to/marker`):**
   - *Vantagens:* Qualidade excepcional de extração semântica em PDFs, reconstrução de layout complexo e suporte nativo a equações LaTeX.
   - *Desvantagens:* Alto custo computacional (exige PyTorch/GPU), tempo de inicialização de modelos pesado e totalmente desnecessário para formatos nativos de texto ou planilhas.

### Solução Proposta
O **OmniMarkdown Router** atua como uma camada leve de orquestração e decisão. Ele avalia o tipo de documento de entrada e suas propriedades intrínsecas (como a presença de camadas de texto ou densidade estrutural) para rotear a carga dinamicamente entre MarkItDown e Marker, garantindo menor latência, menor custo de computação e máxima fidelidade semântica.

---

## 2. Objetivos de Negócio e Engenharia

1. **Eficiência de Recursos:** 0% de uso de GPU para formatos nativos de escritório e páginas web.
2. **Qualidade Máxima de Ingestão:** Manutenção da ordem natural de leitura e representação de equações em LaTeX quando o documento de entrada for técnico.
3. **Resiliência a Falhas:** Fallback automático caso a inferência pesada (GPU) sofra timeout ou falta de memória (OOM).
4. **Interface Unificada:** Assinatura única para o consumidor da biblioteca:
   ```python
   result = router.convert(file_path="document.pdf", force_engine=None)
   ```

---

## 3. Arquitetura do Sistema

### 3.1 Fluxo de Roteamento

```text
                        [ Arquivo de Entrada ]
                                  │
                                  ▼
                    [ Inspecionar Formato / MIME ]
                                  │
         ┌────────────────────────┴────────────────────────┐
         │                                                 │
   [ Formato Office / Web ]                             [ PDF ]
  (.docx, .xlsx, .pptx, .csv, ...)                         │
         │                                                 ▼
         │                                      [ PDFClassifier (Heurística) ]
         │                                                 │
         │                         ┌───────────────────────┴───────────────────────┐
         │                         ▼                                               ▼
         │                 [ PDF Textual Simples ]                        [ PDF Técnico / Scan ]
         │                 (camada de texto limpa)                        (scanned / multi-coluna)
         │                         │                                               │
         ▼                         ▼                                               ▼
  [ MarkItDown Engine ]  ◄────────────────── (Fallback em caso de erro) ───  [ Marker Engine ]
   (CPU / Sub-segundo)                                                         (Vision / GPU)
         │                                                                         │
         └─────────────────────────────────┬───────────────────────────────────────┘
                                           ▼
                                [ Standardized Output ]
                                 (ConversionResult)
```

### 3.2 Estrutura de Diretórios Recomendada

```text
omni_markdown_router/
├── omni_router/
│   ├── __init__.py
│   ├── schemas.py              # Modelos Pydantic v2 (ConversionResult, EngineType, etc.)
│   ├── config.py               # Variáveis de ambiente e limiares de decisão
│   ├── classifiers/
│   │   ├── __init__.py
│   │   └── pdf_classifier.py   # Heurística rápida de complexidade de PDF
│   ├── adapters/
│   │   ├── __init__.py
│   │   ├── base.py             # Classe abstrata BaseAdapter
│   │   ├── markitdown_adapter.py
│   │   └── marker_adapter.py   # Suporte a execução local ou via API remota
│   └── router.py               # Orquestrador de decisão
├── tests/
│   ├── test_classifier.py
│   └── test_router.py
├── main.py                     # CLI para testes manuais
├── pyproject.toml
└── README.md
```

---

## 4. Requisitos Funcionais

### RF-01: Identificação de Tipo e Extensão
- O sistema deve validar a extensão e o MIME type do arquivo utilizando `mimetypes` ou análise de buffer (`python-magic`).
- Extensões suportadas diretamente pelo MarkItDown: `.docx`, `.pptx`, `.xlsx`, `.csv`, `.tsv`, `.html`, `.xml`, `.json`, `.txt`, `.zip`.

### RF-02: Classificação de Complexidade de PDF (`PDFClassifier`)
Para arquivos `.pdf`, o classificador executará uma inspeção inicial leve (utilizando `pypdf` ou `pdfminer.six`):
- **Detecção de Scan:** Se a média de caracteres extraídos for inferior a `min_chars_per_page` (padrão: 100 caracteres por página) e houver imagens embutidas, classificar como `COMPLEX_SCAN` $\to$ **Marker**.
- **Detecção Estrutural:** Se forem detectadas referências a blocos matemáticos ou fontes com padrão de colunas densas, classificar como `COMPLEX_LAYOUT` $\to$ **Marker**.
- **Caso Contrário:** Classificar como `SIMPLE_TEXT` $\to$ **MarkItDown**.

### RF-03: Abstração de Adaptadores (`Adapter Pattern`)
Cada motor deve herdar de uma interface base:
```python
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Union
from omni_router.schemas import ConversionResult

class BaseAdapter(ABC):
    @abstractmethod
    def convert(self, file_path: Union[str, Path], **kwargs) -> ConversionResult:
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Verifica se as dependências (e.g. PyTorch/CUDA) estão prontas."""
        pass
```

### RF-04: Contrato de Saída Padronizado
Toda conversão deve retornar um objeto estrito via Pydantic:
```python
from pydantic import BaseModel, Field
from typing import Literal, Optional, Dict, Any

class ConversionResult(BaseModel):
    markdown: str = Field(..., description="Conteúdo convertido em Markdown")
    engine_used: Literal["markitdown", "marker"] = Field(..., description="Motor efetivamente utilizado")
    fallback_triggered: bool = Field(default=False, description="Indica se houve fallback após falha do motor principal")
    latency_ms: float = Field(..., description="Tempo total de processamento em milissegundos")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadados do arquivo e do parser")
    error_message: Optional[str] = Field(default=None, description="Mensagem de erro em caso de resiliência parcial")
```

### RF-05: Mecanismo de Fallback e Sobrecarga (Override)
- **Override do Usuário:** O método `convert()` deve aceitar `force_engine: Optional[Literal["markitdown", "marker"]] = None`.
- **Graceful Fallback:** Caso o `marker` retorne exceção (por exemplo: falta de memória CUDA, falha de deserialização), o `router` deve capturar a falha, registrar log de aviso e executar automaticamente a conversão via `markitdown`, marcando `fallback_triggered=True`.

---

## 5. Requisitos Não Funcionais

- **Latência:** Arquivos de texto e planilhas de até 10 MB devem ser processados em menos de 1 segundo.
- **Isolamento de Dependência:** O módulo deve ser utilizável em ambientes sem GPU (CPU-only), degradando graciosamente o `MarkerAdapter` com aviso claro em vez de interromper o import geral do pacote.
- **Python Standard:** Compatível com Python 3.10+.

---

## 6. Prompt de Inicialização para o Antigravity

Ao alimentar o Antigravity com este arquivo, utilize o seguinte comando:

```text
Leia atentamente o arquivo prd_omni_markdown_router.md.
Crie a estrutura completa de pastas e o código funcional para o omni_markdown_router seguindo todas as definições das seções 3 e 4.
Garanta que as classes sejam tipadas com Pydantic v2 e que o classificador de PDF funcione de forma assíncrona/rápida com fallback defensivo.
```