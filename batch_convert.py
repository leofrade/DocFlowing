"""DocFlow - Batch PDF to Markdown Converter.

Processes directories of PDFs recursively or flatly, routing each document
through OmniMarkdownRouter and saving .md files alongside original PDFs.
Supports multi-processing, progress reporting, and resume/skip of existing files.
"""

import argparse
import concurrent.futures
import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional, Tuple


def _init_worker():
    """Silence noisy third-party loggers in worker processes."""
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    logging.getLogger("pdfminer").setLevel(logging.ERROR)


def _convert_worker(
    task: Tuple[str, str, Optional[str], bool]
) -> Tuple[str, bool, float, int, Optional[str]]:
    """Worker function executed in separate process.

    Args:
        task: Tuple of (pdf_path, md_path, force_engine, overwrite).

    Returns:
        Tuple of (pdf_name, success, latency_s, char_count, error_msg).
    """
    pdf_path_str, md_path_str, force_engine, overwrite = task
    pdf_path = Path(pdf_path_str)
    md_path = Path(md_path_str)

    # Check if already exists and non-empty
    if not overwrite and md_path.exists() and md_path.stat().st_size > 0:
        return (pdf_path.name, True, 0.0, md_path.stat().st_size, "SKIPPED_EXISTING")

    start_time = time.perf_counter()
    try:
        from omni_router import OmniMarkdownRouter

        router = OmniMarkdownRouter()
        result = router.convert(pdf_path, force_engine=force_engine)

        # Write markdown content to file
        md_path.write_text(result.markdown, encoding="utf-8")
        latency_s = time.perf_counter() - start_time
        return (pdf_path.name, True, latency_s, len(result.markdown), None)
    except Exception as exc:
        latency_s = time.perf_counter() - start_time
        return (pdf_path.name, False, latency_s, 0, str(exc))


def batch_convert(
    input_dir: Path,
    output_dir: Optional[Path] = None,
    recursive: bool = True,
    max_workers: int = 4,
    overwrite: bool = False,
    force_engine: Optional[str] = None,
) -> None:
    """Run batch conversion across a directory.

    Args:
        input_dir: Directory containing PDFs.
        output_dir: Optional destination directory to replicate tree structure.
        recursive: Whether to scan subdirectories.
        max_workers: Number of parallel worker processes.
        overwrite: Overwrite existing .md files if True.
        force_engine: Optional engine override ('markitdown' or 'marker').
    """
    if not input_dir.is_dir():
        print(f"Erro: O diretório '{input_dir}' não existe.", file=sys.stderr)
        sys.exit(1)

    pattern = "**/*.pdf" if recursive else "*.pdf"
    pdf_files = sorted(list(input_dir.glob(pattern)))
    total_files = len(pdf_files)

    if total_files == 0:
        print(f"Nenhum arquivo PDF encontrado em '{input_dir}'.")
        return

    print("=" * 70)
    print("🚀 DocFlow - Conversão em Lote para Markdown")
    print("=" * 70)
    print(f"Diretório de Origem: {input_dir}")
    if output_dir:
        print(f"Diretório de Destino: {output_dir} (árvore replicada)")
    else:
        print("Destino:              Na mesma pasta de cada PDF (in-place)")
    print(f"Modo Recursivo:      {'Sim' if recursive else 'Não'}")
    print(f"Total de PDFs:       {total_files}")
    print(f"Processos (Workers): {max_workers}")
    print(f"Sobrescrever .md:    {'Sim' if overwrite else 'Não (pular já convertidos)'}")
    if force_engine:
        print(f"Engine Forçada:      {force_engine}")
    print("=" * 70)

    tasks = []
    for p in pdf_files:
        if output_dir:
            rel = p.relative_to(input_dir)
            target_md = (Path(output_dir) / rel).with_suffix(".md")
            target_md.parent.mkdir(parents=True, exist_ok=True)
        else:
            target_md = p.with_suffix(".md")
        tasks.append((str(p), str(target_md), force_engine, overwrite))

    completed_count = 0
    success_count = 0
    skipped_count = 0
    error_count = 0
    failed_files = []

    start_batch = time.perf_counter()

    with concurrent.futures.ProcessPoolExecutor(
        max_workers=max_workers, initializer=_init_worker
    ) as executor:
        future_to_pdf = {
            executor.submit(_convert_worker, t): t[0] for t in tasks
        }

        for future in concurrent.futures.as_completed(future_to_pdf):
            completed_count += 1
            pdf_name, success, latency_s, char_len, err_msg = future.result()
            pct = (completed_count / total_files) * 100

            if success:
                if err_msg == "SKIPPED_EXISTING":
                    skipped_count += 1
                    print(
                        f"[{completed_count:3d}/{total_files:3d}] ({pct:5.1f}%) ⏭️  PULADO (já existe): {pdf_name}"
                    )
                else:
                    success_count += 1
                    print(
                        f"[{completed_count:3d}/{total_files:3d}] ({pct:5.1f}%) ✅ CONVERTIDO: {pdf_name} "
                        f"({latency_s:.1f}s, {char_len:,} chars)"
                    )
            else:
                error_count += 1
                failed_files.append((pdf_name, err_msg))
                print(
                    f"[{completed_count:3d}/{total_files:3d}] ({pct:5.1f}%) ❌ ERRO: {pdf_name} - {err_msg}"
                )

    total_time = time.perf_counter() - start_batch

    print("\n" + "=" * 70)
    print("📊 Resumo do Processamento")
    print("=" * 70)
    print(f"Tempo total:        {total_time:.2f} segundos ({total_time / 60:.1f} minutos)")
    print(f"Total de arquivos:  {total_files}")
    print(f"Convertidos com sucesso: {success_count}")
    print(f"Já existentes (pulados): {skipped_count}")
    print(f"Falhas / Erros:          {error_count}")

    if failed_files:
        print("\nArquivos com erro:")
        for name, err in failed_files:
            print(f"  - {name}: {err}")
    print("=" * 70)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Converter PDFs em lote para Markdown via DocFlow OmniMarkdownRouter"
    )
    parser.add_argument("directory", help="Diretório contendo os PDFs")
    parser.add_argument(
        "-r", "--recursive", action="store_true", default=True, help="Buscar em subpastas"
    )
    parser.add_argument(
        "--no-recursive", action="store_false", dest="recursive", help="Apenas pasta raiz"
    )
    parser.add_argument(
        "-w",
        "--workers",
        type=int,
        default=min(4, os.cpu_count() or 4),
        help="Número de workers paralelos",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        default=None,
        help="Diretório de saída para replicar a árvore de pastas",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        default=False,
        help="Sobrescrever .md já existentes",
    )
    parser.add_argument(
        "--force",
        choices=["markitdown", "marker"],
        default=None,
        help="Forçar engine específica",
    )

    args = parser.parse_args()
    batch_convert(
        input_dir=Path(args.directory),
        output_dir=Path(args.output_dir) if args.output_dir else None,
        recursive=args.recursive,
        max_workers=args.workers,
        overwrite=args.overwrite,
        force_engine=args.force,
    )


if __name__ == "__main__":
    main()
