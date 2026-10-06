"""OmniMarkdown Router - Command Line Interface (CLI).

Provides commands for manual testing, inspecting documents, and converting files:
- python main.py convert document.pdf [--force markitdown|marker] [--output out.md]
- python main.py inspect document.pdf
- python main.py status
"""

import argparse
import json
import logging
import sys
from pathlib import Path

from omni_router import OmniMarkdownRouter, default_config


def setup_logger(verbose: bool = False) -> None:
    """Setup logging configuration."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def cmd_convert(args: argparse.Namespace) -> int:
    """Handle the 'convert' command."""
    file_path = Path(args.file)
    if not file_path.exists():
        print(f"Error: File '{file_path}' does not exist.", file=sys.stderr)
        return 1

    router = OmniMarkdownRouter()
    print(f"Converting '{file_path.name}'...")
    if args.force:
        print(f"Forcing engine: {args.force}")

    try:
        result = router.convert(file_path, force_engine=args.force)

        print("-" * 50)
        print(f"Engine Used:        {result.engine_used}")
        print(f"Fallback Triggered: {result.fallback_triggered}")
        print(f"Latency:            {result.latency_ms:.2f} ms")
        if result.error_message:
            print(f"Error / Fallback:   {result.error_message}")
        print("-" * 50)

        if args.output:
            out_path = Path(args.output)
            out_path.write_text(result.markdown, encoding="utf-8")
            print(f"Saved Markdown to '{out_path}'")
        else:
            print("\n--- Markdown Output Preview (first 500 chars) ---")
            preview = result.markdown[:500]
            print(preview)
            if len(result.markdown) > 500:
                print("... [truncated]")

        return 0
    except Exception as exc:
        print(f"Conversion failed: {exc}", file=sys.stderr)
        return 1


def cmd_inspect(args: argparse.Namespace) -> int:
    """Handle the 'inspect' command."""
    file_path = Path(args.file)
    if not file_path.exists():
        print(f"Error: File '{file_path}' does not exist.", file=sys.stderr)
        return 1

    router = OmniMarkdownRouter()
    try:
        info = router.inspect_file(file_path)
        print(json.dumps(info, indent=2, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(f"Inspection failed: {exc}", file=sys.stderr)
        return 1


def cmd_status(_args: argparse.Namespace) -> int:
    """Handle the 'status' command."""
    router = OmniMarkdownRouter()
    print("OmniMarkdown Router Status:")
    print("-" * 40)
    print(f"MarkItDown Adapter Available: {router.markitdown_adapter.is_available()}")
    print(f"Marker Adapter Available:     {router.marker_adapter.is_available()}")
    print(f"  - Remote API URL:           {router.marker_adapter.api_url or 'None'}")
    print(f"  - Local Models Ready:       {router.marker_adapter.local_available}")
    print(f"Min Chars/Page Threshold:     {default_config.min_chars_per_page}")
    print(f"Math Indicators Threshold:    {default_config.math_symbol_threshold}")
    print(f"Sample Pages:                 {default_config.max_pages_sample}")
    print("-" * 40)
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Construct CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="OmniMarkdown Router: Smart MarkItDown + Marker Orchestrator",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose debug logging")

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # convert
    convert_parser = subparsers.add_parser("convert", help="Convert a document to Markdown")
    convert_parser.add_argument("file", help="Path to file to convert")
    convert_parser.add_argument(
        "--force",
        choices=["markitdown", "marker"],
        default=None,
        help="Force specific engine",
    )
    convert_parser.add_argument(
        "-o", "--output",
        default=None,
        help="File path to save Markdown output",
    )

    # inspect
    inspect_parser = subparsers.add_parser("inspect", help="Inspect file complexity heuristics")
    inspect_parser.add_argument("file", help="Path to file to inspect")

    # status
    subparsers.add_parser("status", help="Show system and engine status")

    return parser


def cli() -> None:
    """Entrypoint function for CLI script."""
    parser = build_parser()
    args = parser.parse_args()
    setup_logger(args.verbose)

    if args.command == "convert":
        sys.exit(cmd_convert(args))
    elif args.command == "inspect":
        sys.exit(cmd_inspect(args))
    elif args.command == "status":
        sys.exit(cmd_status(args))
    else:
        parser.print_help()
        sys.exit(0)


if __name__ == "__main__":
    cli()
