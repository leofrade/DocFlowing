# AGENTS.md - OmniMarkdown Router (DocFlow)

Guia de referência e instruções operacionais para agentes de IA (Antigravity/agy, Claude Code, etc.) que atuam neste repositório.

---

## 1. Visão Geral do Projeto

O **OmniMarkdown Router** (DocFlow) é um orquestrador inteligente de conversão de documentos para Markdown em pipelines RAG.
Ele avalia o formato de entrada e heurísticas estruturais de PDFs para rotear dinamicamente entre:
- **Microsoft MarkItDown**: CPU-bound, sub-segundo, 0% GPU. Formatos Office (`.docx`, `.xlsx`, `.pptx`, `.csv`, `.html`, `.txt`) e PDFs textuais limpos.
- **Marker**: Deep Learning / Vision (GPU local ou microserviço HTTP remoto). PDFs escaneados, layouts multi-coluna complexos e fórmulas matemáticas em LaTeX.

---

## 2. Comandos e Ambiente

O projeto utiliza `uv` como gerenciador de pacotes e ambiente virtual Python (3.10+):

```bash
# Instalação das dependências do projeto
uv sync

# Execução da suíte de testes (com dependências de desenvolvimento)
uv run --extra dev pytest

# Execução da CLI principal
uv run python main.py convert documento.pdf
uv run python main.py inspect documento.pdf
uv run python main.py status

# Conversão em lote (Batch)
uv run python batch_convert.py /caminho/dos/pdfs -o /caminho/saida -w 4
```

---

## 3. Arquitetura e Estrutura de Código

```text
docflow/
├── omni_router/
│   ├── schemas.py              # Modelos Pydantic v2 (ConversionResult, ComplexityType)
│   ├── config.py               # RouterConfig, variáveis de ambiente (pydantic-settings/dotenv)
│   ├── router.py               # Orquestrador OmniMarkdownRouter (síncrono e assíncrono)
│   ├── classifiers/
│   │   └── pdf_classifier.py   # Heurística rápida de complexidade (caracteres, LaTeX, colunas)
│   └── adapters/
│       ├── base.py             # Interface BaseAdapter
│       ├── markitdown_adapter.py # Adaptador MarkItDown (CPU)
│       └── marker_adapter.py   # Adaptador Marker (GPU local ou API HTTP remota)
├── tests/
│   ├── test_classifier.py      # Testes unitários do classificador heurístico
│   └── test_router.py          # Testes unitários de roteamento e fallback defensivo
├── batch_convert.py            # Conversor concorrente em lote com multiprocessing
├── main.py                     # Ponto de entrada CLI (convert, inspect, status, batch)
├── pyproject.toml              # Metadados e dependências (hatchling build)
└── README.md                   # Documentação pública
```

### Princípios de Engenharia
- **Tipagem Estrita com Pydantic v2**: Toda conversão retorna uma instância imutável/validada de `ConversionResult`.
- **Resiliência e Fallback Defensivo**: Se o Marker falhar (CUDA OOM, timeout HTTP ou ausência de GPU), o roteador deve capturar o erro, registrar em log e fazer fallback automático para o MarkItDown (`fallback_triggered=True`).
- **Isolamento de Dependências**: O pacote deve rodar perfeitamente em ambientes CPU-only (`marker-pdf` é dependência opcional).

---

## 4. Diretrizes de Segurança, Privacidade e Publicação

Ao preparar ou modificar código neste repositório para disponibilização pública ou commits:

1. **Nunca commitar caminhos locais e dados pessoais (PII):**
   - Não incluir caminhos absolutos do sistema operacional (ex: `/Users/...`, `/home/...`).
   - Não incluir e-mails pessoais em nomes de caminhos (como estruturas do Google Drive).
   - Scripts ad-hoc com caminhos de pastas privadas/locais (ex: `pipeline.py`) devem permanecer fora do versionamento ou no `.gitignore`.
2. **Gerenciamento de Segredos e Chaves:**
   - Chaves de API (como `MARKER_API_KEY`) devem ser lidas exclusivamente de variáveis de ambiente (`os.getenv`).
   - Nunca commitar arquivos `.env` com valores reais. Manter apenas um `.env.example` com placeholders.
3. **Portabilidade de Caminhos:**
   - Evitar suposições sobre a existência de pastas de desktop (ex: `~/Desktop`). Garantir fallback seguro para o diretório atual (`Path.cwd()`) em ambientes headless ou servidores Linux.
