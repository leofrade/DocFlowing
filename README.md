# OmniMarkdown Router

**Orquestrador Inteligente MarkItDown + Marker para Pipelines RAG**

O **OmniMarkdown Router** atua como uma camada leve de orquestração e decisão para pipelines de conversão de documentos em Markdown. Ele avalia o formato de entrada e propriedades estruturais intrínsecas (como densidade de caracteres, presença de imagens ou notações matemáticas) para rotear a carga dinamicamente entre **Microsoft MarkItDown** e **Marker**, garantindo menor latência, menor custo de computação (0% de GPU para formatos nativos) e máxima fidelidade semântica.

---

## 🚀 Arquitetura de Roteamento

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

---

## 🎯 Objetivos de Engenharia

1. **Eficiência de Recursos:** 0% de uso de GPU para formatos nativos de escritório (`.docx`, `.xlsx`, `.pptx`, `.csv`, `.tsv`, `.html`, `.xml`, `.json`, `.txt`, `.zip`).
2. **Qualidade Máxima de Ingestão:** Manutenção da ordem natural de leitura, suporte a multi-colunas e equações em LaTeX quando o documento for técnico.
3. **Resiliência a Falhas:** Fallback automático para `markitdown` caso o `marker` sofra timeout, erro de conexão ou falta de memória GPU (CUDA OOM).
4. **Isolamento de Dependências:** O pacote funciona perfeitamente em ambientes CPU-only sem quebrar imports quando `torch` ou `marker-pdf` não estiverem instalados.
5. **Tipagem Estrita:** Modelos de entrada e saída validados com **Pydantic v2**.
6. **Suporte Assíncrono:** Métodos `convert()` (síncrono) e `aconvert()` (assíncrono) nativos.

---

## 📦 Instalação

### Instalação Básica (MarkItDown + PDF Classifier)
```bash
pip install "markitdown[pdf]" pydantic pypdf httpx python-dotenv
```
ou utilizando `uv`:
```bash
uv pip install -e .
```

### Opcional: Suporte a Marker Local (Deep Learning / GPU)
```bash
pip install marker-pdf
```

> **Dica:** O Marker também pode ser executado como um microserviço HTTP remoto configurando a variável `MARKER_API_URL` sem necessidade de instalar PyTorch na máquina do cliente.

---

## 🛠️ Como Usar (Python)

### 1. Conversão Básica (Roteamento Automático)

```python
from omni_router import OmniMarkdownRouter

router = OmniMarkdownRouter()

# Roteamento automático baseado no tipo e complexidade
result = router.convert("artigo_cientifico.pdf")

print(f"Engine utilizado: {result.engine_used}")
print(f"Fallback acionado: {result.fallback_triggered}")
print(f"Latência: {result.latency_ms:.2f} ms")
print(result.markdown)
```

### 2. Contrato de Saída (`ConversionResult`)

Toda conversão retorna uma instância do modelo Pydantic v2 `ConversionResult`:

```python
class ConversionResult(BaseModel):
    markdown: str                     # Conteúdo convertido em Markdown
    engine_used: Literal["markitdown", "marker"]  # Motor utilizado
    fallback_triggered: bool          # Indica se houve fallback após falha
    latency_ms: float                 # Tempo total de processamento em ms
    metadata: Dict[str, Any]          # Metadados do arquivo, inspeção e parser
    error_message: Optional[str]      # Mensagem de erro em caso de resiliência
```

### 3. Forçando um Motor (`force_engine`)

```python
# Forçar MarkItDown em qualquer documento
result_cpu = router.convert("documento.pdf", force_engine="markitdown")

# Forçar Marker (com fallback automático se Marker falhar)
result_gpu = router.convert("planilha.csv", force_engine="marker")
```

### 4. Uso Assíncrono (`aconvert`)

```python
import asyncio
from omni_router import OmniMarkdownRouter

async def main():
    router = OmniMarkdownRouter()
    result = await router.aconvert("relatorio.docx")
    print(f"Pronto em {result.latency_ms} ms via {result.engine_used}")

asyncio.run(main())
```

### 5. Inspeção Heurística sem Conversão

```python
from omni_router import OmniMarkdownRouter

router = OmniMarkdownRouter()
info = router.inspect_file("documento.pdf")
print(info)
# {
#   "file_name": "documento.pdf",
#   "is_pdf": True,
#   "recommended_engine": "marker",
#   "pdf_inspection": {
#     "classification": "COMPLEX_LAYOUT",
#     "avg_chars_per_page": 240.5,
#     "has_math_symbols": True,
#     "is_multi_column": True
#   }
# }
```

---

## ⚙️ Configuração via Variáveis de Ambiente

Crie um arquivo `.env` ou configure no seu ambiente:

| Variável | Padrão | Descrição |
|---|---|---|
| `OMNI_MIN_CHARS_PER_PAGE` | `100` | Mínimo de caracteres/página para classificar texto limpo vs scan |
| `OMNI_MAX_PAGES_SAMPLE` | `10` | Páginas máximas inspecionadas pelo classificador |
| `OMNI_MATH_SYMBOL_THRESHOLD` | `3` | Limiar de símbolos matemáticos/LaTeX para `COMPLEX_LAYOUT` |
| `MARKER_API_URL` | `None` | URL do microserviço HTTP remoto do Marker |
| `MARKER_API_KEY` | `None` | Token de autorização Bearer para API remota do Marker |
| `MARKER_TIMEOUT_SECONDS` | `30.0` | Timeout para resposta do Marker |
| `OMNI_LOG_LEVEL` | `INFO` | Nível de log (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

---

## 💻 CLI (Linha de Comando)

A ferramenta inclui uma interface CLI para testes manuais e diagnósticos:

```bash
# Converter documento e exibir no terminal
python main.py convert relatorio.docx

# Converter PDF forçando motor e salvando saída
python main.py convert artigo.pdf --force marker -o out.md

# Inspecionar complexidade de um PDF
python main.py inspect documento.pdf

# Verificar status dos motores e configurações
python main.py status
```

---

## 🧪 Testes Automatizados

A suíte de testes cobre todos os requisitos funcionais e não-funcionais:

```bash
# Executar todos os testes com pytest
uv run pytest -v
```

Cenários cobertos:
- [x] Classificação de texto simples (`SIMPLE_TEXT`)
- [x] Detecção de documentos digitalizados/scans (`COMPLEX_SCAN`)
- [x] Detecção de fórmulas matemáticas e blocos LaTeX (`COMPLEX_LAYOUT`)
- [x] Detecção de layout multi-coluna
- [x] Resiliência defensiva com arquivos corrompidos
- [x] Roteamento de formatos de escritório (0% GPU)
- [x] Fallback automático para `markitdown` em falhas do `marker` (CUDA OOM, timeouts)
- [x] Fallback gracioso em ambientes CPU-only sem Marker instalado
- [x] Validação de contrato de saída Pydantic v2
- [x] Execução síncrona e assíncrona (`convert` e `aconvert`)

---

## 📄 Licença

MIT License.
