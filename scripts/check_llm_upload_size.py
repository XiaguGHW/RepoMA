#!/usr/bin/env python3
"""Estimate and optionally probe the LLM request size for one BG folder.

This mirrors the PDF handling in llm_connector.py: the first four PDF pages
are rendered at 150 dpi as JPEGs before they are Base64-encoded.  It therefore
reports a useful approximation of the request payload, not only the on-disk
PDF size.

Examples
--------
Estimate only (no API request):
    python .\\check_llm_upload_size.py "C:\\data\\one_BG"

Probe the largest files cumulatively against the currently configured API:
    python .\\check_llm_upload_size.py "C:\\data\\one_BG" --probe
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    import fitz
except ImportError:
    fitz = None

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*_args, **_kwargs) -> bool:
        return False


PROJECT_DIR = Path(__file__).resolve().parent
SUPPORTED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}
BASE64_FACTOR = 4 / 3


@dataclass
class FileEstimate:
    path: Path
    raw_bytes: int
    prepared_bytes: int
    pages_or_images: int
    note: str = ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="One PDF/image file or a BG folder.")
    parser.add_argument("--pages-per-pdf", type=int, default=4)
    parser.add_argument("--dpi", type=int, default=150)
    parser.add_argument(
        "--probe", action="store_true",
        help="Actually send progressively larger file batches to the LLM API.",
    )
    parser.add_argument("--model", default="gemini-2.5-pro")
    parser.add_argument(
        "--max-probes", type=int, default=12,
        help="Maximum number of API probe requests. Default: 12.",
    )
    return parser.parse_args()


def collect_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path] if path.suffix.casefold() in SUPPORTED_EXTENSIONS else []
    if path.is_dir():
        return sorted(
            item for item in path.rglob("*")
            if item.is_file() and item.suffix.casefold() in SUPPORTED_EXTENSIONS
        )
    raise FileNotFoundError(f"Path not found: {path}")


def estimate_file(path: Path, pages_per_pdf: int, dpi: int) -> FileEstimate:
    raw_bytes = path.stat().st_size
    if path.suffix.casefold() != ".pdf":
        return FileEstimate(path, raw_bytes, int(raw_bytes * BASE64_FACTOR), 1)
    if fitz is None:
        return FileEstimate(path, raw_bytes, int(raw_bytes * BASE64_FACTOR), 0, "fitz unavailable")

    images_size = 0
    pages = 0
    try:
        document = fitz.open(path)
        matrix = fitz.Matrix(dpi / 72, dpi / 72)
        for index, page in enumerate(document):
            if index >= pages_per_pdf:
                break
            images_size += len(page.get_pixmap(matrix=matrix).tobytes("jpeg"))
            pages += 1
        document.close()
    except Exception as error:
        return FileEstimate(path, raw_bytes, int(raw_bytes * BASE64_FACTOR), 0, f"render failed: {error}")
    return FileEstimate(path, raw_bytes, int(images_size * BASE64_FACTOR), pages)


def mib(value: int) -> str:
    return f"{value / 1024 / 1024:.2f} MiB"


def display_report(estimates: list[FileEstimate]) -> None:
    print("\nPrepared-upload estimate (largest first)")
    print("-" * 112)
    print(f"{'Prepared':>12}  {'On disk':>12}  {'Pages':>5}  File")
    print("-" * 112)
    for item in estimates:
        suffix = f"  [{item.note}]" if item.note else ""
        print(f"{mib(item.prepared_bytes):>12}  {mib(item.raw_bytes):>12}  {item.pages_or_images:>5}  {item.path}{suffix}")
    print("-" * 112)
    print(f"Total prepared Base64 payload: {mib(sum(item.prepared_bytes for item in estimates))}")
    print(f"Files: {len(estimates)}")


def looks_like_request_error(response: object) -> bool:
    text = str(response).casefold()
    return any(marker in text for marker in ("413", "request entity too large", "max retries exceeded", "proxyerror"))


def probe(estimates: list[FileEstimate], model: str, max_probes: int) -> None:
    api_key = os.getenv("BOSCH_FARM_SUBSCRIPTION_KEY")
    if not api_key:
        raise EnvironmentError("BOSCH_FARM_SUBSCRIPTION_KEY is not set in .env.")
    try:
        from llm_connector import LLMConnector
    except ImportError as error:
        raise ImportError("Place llm_connector.py beside this script.") from error

    largest_first = sorted(estimates, key=lambda item: item.prepared_bytes, reverse=True)
    if len(largest_first) > max_probes:
        largest_first = largest_first[:max_probes]
        print(f"\nOnly the {max_probes} largest files will be probed.")
    connector = LLMConnector(model, api_key)
    selected: list[str] = []
    print("\nAPI probe (largest file first; each step adds one file)")
    for number, item in enumerate(largest_first, start=1):
        selected.append(str(item.path))
        response = connector.ask_about_files(
            file_paths=selected,
            question="Antworte ausschließlich mit OK.",
            system_prompt="Antworte ausschließlich mit OK.",
            generation_config={"temperature": 0.0, "maxOutputTokens": 256},
        )
        estimated = sum(entry.prepared_bytes for entry in largest_first[:number])
        if looks_like_request_error(response):
            print(f"FAIL at {number} file(s), estimated {mib(estimated)}")
            print(f"Response: {str(response)[:300]}")
            return
        print(f"OK   at {number} file(s), estimated {mib(estimated)}")
    print("No request-size failure in the probed files.")


def main() -> None:
    args = parse_args()
    if args.pages_per_pdf <= 0 or args.dpi <= 0 or args.max_probes <= 0:
        raise ValueError("--pages-per-pdf, --dpi and --max-probes must be positive.")
    files = collect_files(args.path)
    if not files:
        raise ValueError("No supported PDF/PNG/JPG/JPEG files found.")
    estimates = sorted(
        (estimate_file(path, args.pages_per_pdf, args.dpi) for path in files),
        key=lambda item: item.prepared_bytes,
        reverse=True,
    )
    display_report(estimates)
    if args.probe:
        probe(estimates, args.model, args.max_probes)


if __name__ == "__main__":
    load_dotenv(PROJECT_DIR / ".env")
    try:
        main()
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
