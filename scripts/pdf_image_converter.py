"""
Reusable PDF-to-image converter for Baugruppe documents.

Main use cases:
1. Convert one PDF into ordered page images plus a PDF-level manifest.
2. Convert all PDFs of one Baugruppe into separate PDF subfolders plus one
   Baugruppe-level manifest.

Dependency:
    pip install pymupdf pillow
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Literal

try:
    import fitz  # PyMuPDF
except ImportError as exc:  # pragma: no cover - helpful runtime message
    raise SystemExit(
        "Missing dependency: pymupdf. Install it with: pip install pymupdf pillow"
    ) from exc

try:
    from PIL import Image
except ImportError as exc:  # pragma: no cover - helpful runtime message
    raise SystemExit(
        "Missing dependency: pillow. Install it with: pip install pymupdf pillow"
    ) from exc


ImageFormat = Literal["png", "jpg", "jpeg"]


@dataclass(frozen=True)
class PageImage:
    page_number: int
    image_path: str
    width_px: int
    height_px: int
    file_size_bytes: int


@dataclass(frozen=True)
class PdfManifest:
    source_pdf: str
    source_pdf_name: str
    source_sha256: str
    source_mtime: float
    page_count: int
    dpi: int
    image_format: str
    max_side_px: int | None
    converted_at_utc: str
    images: list[PageImage]


def _safe_name(value: str, max_len: int = 90) -> str:
    """Create a stable Windows-friendly folder/file name."""
    value = re.sub(r"[^\w.\-]+", "_", value, flags=re.UNICODE).strip("._ ")
    return (value or "unnamed")[:max_len]


def _sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _save_json(path: Path, data: dict) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _manifest_is_current(
    manifest_path: Path,
    *,
    pdf_path: Path,
    pdf_sha256: str,
    dpi: int,
    image_format: str,
    max_side_px: int | None,
) -> bool:
    manifest = _load_json(manifest_path)
    if not manifest:
        return False

    images = manifest.get("images") or []
    image_paths_exist = all((manifest_path.parent / item["image_path"]).exists() for item in images)

    return (
        manifest.get("source_pdf_name") == pdf_path.name
        and manifest.get("source_sha256") == pdf_sha256
        and manifest.get("dpi") == dpi
        and manifest.get("image_format") == image_format
        and manifest.get("max_side_px") == max_side_px
        and image_paths_exist
    )


def _resize_if_needed(image_path: Path, max_side_px: int | None, image_format: str) -> tuple[int, int]:
    with Image.open(image_path) as img:
        width, height = img.size
        if max_side_px and max(width, height) > max_side_px:
            scale = max_side_px / max(width, height)
            new_size = (round(width * scale), round(height * scale))
            img = img.resize(new_size, Image.Resampling.LANCZOS)
            width, height = img.size

        if image_format in {"jpg", "jpeg"}:
            img = img.convert("RGB")
            img.save(image_path, quality=90, optimize=True)
        else:
            img.save(image_path, optimize=True)

        return width, height


def convert_pdf_to_images(
    pdf_path: str | Path,
    output_dir: str | Path,
    *,
    dpi: int = 200,
    image_format: ImageFormat = "png",
    max_side_px: int | None = 3000,
    force: bool = False,
) -> PdfManifest:
    """
    Convert one PDF into page images.

    Args:
        pdf_path: Source PDF path.
        output_dir: Parent output directory. A PDF-specific subfolder is created.
        dpi: Render resolution. 200 is a good default; 250-300 for tiny drawings.
        image_format: "png" for drawings/text, "jpg" for smaller files.
        max_side_px: Resize longest side after rendering. Use None to disable.
        force: Re-convert even if manifest and images are already current.

    Returns:
        PdfManifest with ordered page image metadata.
    """
    pdf_path = Path(pdf_path).resolve()
    output_dir = Path(output_dir).resolve()

    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError(f"Expected a .pdf file, got: {pdf_path}")
    if dpi <= 0:
        raise ValueError("dpi must be positive")
    if max_side_px is not None and max_side_px <= 0:
        raise ValueError("max_side_px must be positive or None")

    image_format = "jpg" if image_format == "jpeg" else image_format
    pdf_sha256 = _sha256(pdf_path)
    pdf_output_dir = output_dir / _safe_name(pdf_path.stem)
    manifest_path = pdf_output_dir / "manifest.json"

    if not force and _manifest_is_current(
        manifest_path,
        pdf_path=pdf_path,
        pdf_sha256=pdf_sha256,
        dpi=dpi,
        image_format=image_format,
        max_side_px=max_side_px,
    ):
        data = _load_json(manifest_path) or {}
        return PdfManifest(
            images=[PageImage(**item) for item in data.pop("images")],
            **data,
        )

    pdf_output_dir.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(pdf_path)
    page_images: list[PageImage] = []
    zoom = dpi / 72
    matrix = fitz.Matrix(zoom, zoom)

    try:
        for page_index in range(len(doc)):
            page_number = page_index + 1
            page = doc[page_index]
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            image_name = f"page_{page_number:03d}.{image_format}"
            image_path = pdf_output_dir / image_name
            pix.save(image_path)

            width, height = _resize_if_needed(image_path, max_side_px, image_format)
            page_images.append(
                PageImage(
                    page_number=page_number,
                    image_path=image_name,
                    width_px=width,
                    height_px=height,
                    file_size_bytes=image_path.stat().st_size,
                )
            )
    finally:
        doc.close()

    manifest = PdfManifest(
        source_pdf=str(pdf_path),
        source_pdf_name=pdf_path.name,
        source_sha256=pdf_sha256,
        source_mtime=pdf_path.stat().st_mtime,
        page_count=len(page_images),
        dpi=dpi,
        image_format=image_format,
        max_side_px=max_side_px,
        converted_at_utc=datetime.now(timezone.utc).isoformat(),
        images=page_images,
    )
    _save_json(manifest_path, asdict(manifest))
    return manifest


def convert_baugruppe_pdfs(
    baugruppe_dir: str | Path,
    output_root: str | Path,
    *,
    baugruppe_id: str | None = None,
    recursive: bool = True,
    dpi: int = 200,
    image_format: ImageFormat = "png",
    max_side_px: int | None = 3000,
    force: bool = False,
) -> dict:
    """
    Convert all PDFs inside one Baugruppe folder.

    Output structure:
        output_root/
        └── <baugruppe_id>/
            ├── <pdf_1_stem>/
            │   ├── page_001.png
            │   └── manifest.json
            ├── <pdf_2_stem>/
            │   └── ...
            └── baugruppe_manifest.json
    """
    baugruppe_dir = Path(baugruppe_dir).resolve()
    output_root = Path(output_root).resolve()

    if not baugruppe_dir.exists() or not baugruppe_dir.is_dir():
        raise NotADirectoryError(f"Baugruppe folder not found: {baugruppe_dir}")

    pdf_paths = sorted(
        baugruppe_dir.rglob("*.pdf") if recursive else baugruppe_dir.glob("*.pdf"),
        key=lambda path: str(path).lower(),
    )

    group_name = _safe_name(baugruppe_id or baugruppe_dir.name)
    group_output_dir = output_root / group_name
    group_output_dir.mkdir(parents=True, exist_ok=True)

    pdf_entries = []
    total_pages = 0
    for pdf_path in pdf_paths:
        manifest = convert_pdf_to_images(
            pdf_path,
            group_output_dir,
            dpi=dpi,
            image_format=image_format,
            max_side_px=max_side_px,
            force=force,
        )
        total_pages += manifest.page_count
        pdf_entries.append(
            {
                "source_pdf": str(pdf_path),
                "source_pdf_name": pdf_path.name,
                "pdf_folder": _safe_name(pdf_path.stem),
                "manifest": str(Path(_safe_name(pdf_path.stem)) / "manifest.json"),
                "page_count": manifest.page_count,
                "images": [
                    str(Path(_safe_name(pdf_path.stem)) / image.image_path)
                    for image in manifest.images
                ],
            }
        )

    group_manifest = {
        "baugruppe_id": baugruppe_id or baugruppe_dir.name,
        "source_baugruppe_dir": str(baugruppe_dir),
        "output_dir": str(group_output_dir),
        "pdf_count": len(pdf_entries),
        "total_pages": total_pages,
        "dpi": dpi,
        "image_format": "jpg" if image_format == "jpeg" else image_format,
        "max_side_px": max_side_px,
        "converted_at_utc": datetime.now(timezone.utc).isoformat(),
        "pdfs": pdf_entries,
    }
    _save_json(group_output_dir / "baugruppe_manifest.json", group_manifest)
    return group_manifest


def convert_many_baugruppen(
    baugruppen_root: str | Path,
    output_root: str | Path,
    *,
    recursive: bool = True,
    dpi: int = 200,
    image_format: ImageFormat = "png",
    max_side_px: int | None = 3000,
    force: bool = False,
) -> dict:
    """
    Convert every direct child folder under one root as a separate Baugruppe.

    Example:
        baugruppen_root/
        ├── BG_001/
        ├── BG_002/
        └── BG_003/
    """
    baugruppen_root = Path(baugruppen_root).resolve()
    output_root = Path(output_root).resolve()

    if not baugruppen_root.exists() or not baugruppen_root.is_dir():
        raise NotADirectoryError(f"Baugruppen root folder not found: {baugruppen_root}")

    baugruppe_dirs = sorted(
        [path for path in baugruppen_root.iterdir() if path.is_dir()],
        key=lambda path: path.name.lower(),
    )

    results = []
    for baugruppe_dir in baugruppe_dirs:
        manifest = convert_baugruppe_pdfs(
            baugruppe_dir,
            output_root,
            baugruppe_id=baugruppe_dir.name,
            recursive=recursive,
            dpi=dpi,
            image_format=image_format,
            max_side_px=max_side_px,
            force=force,
        )
        results.append(
            {
                "baugruppe_id": manifest["baugruppe_id"],
                "source_baugruppe_dir": manifest["source_baugruppe_dir"],
                "output_dir": manifest["output_dir"],
                "pdf_count": manifest["pdf_count"],
                "total_pages": manifest["total_pages"],
                "manifest": str(
                    Path(_safe_name(manifest["baugruppe_id"]))
                    / "baugruppe_manifest.json"
                ),
            }
        )

    batch_manifest = {
        "source_baugruppen_root": str(baugruppen_root),
        "output_root": str(output_root),
        "baugruppe_count": len(results),
        "total_pdfs": sum(item["pdf_count"] for item in results),
        "total_pages": sum(item["total_pages"] for item in results),
        "dpi": dpi,
        "image_format": "jpg" if image_format == "jpeg" else image_format,
        "max_side_px": max_side_px,
        "converted_at_utc": datetime.now(timezone.utc).isoformat(),
        "baugruppen": results,
    }
    _save_json(output_root / "batch_manifest.json", batch_manifest)
    return batch_manifest


def iter_llm_image_batches(
    baugruppe_manifest: dict,
    *,
    batch_size: int = 5,
) -> Iterable[list[str]]:
    """
    Yield ordered image-path batches for later LLM upload.

    The paths are absolute when baugruppe_manifest["output_dir"] is absolute.
    """
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")

    output_dir = Path(baugruppe_manifest["output_dir"])
    images: list[str] = []
    for pdf_entry in baugruppe_manifest.get("pdfs", []):
        for image in pdf_entry.get("images", []):
            images.append(str(output_dir / image))

    for start in range(0, len(images), batch_size):
        yield images[start : start + batch_size]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert PDF pages into cached images for later LLM input."
    )
    parser.add_argument("source", help="PDF file or Baugruppe folder")
    parser.add_argument("output", help="Output directory")
    parser.add_argument("--baugruppe-id", help="Optional Baugruppe ID/name")
    parser.add_argument("--dpi", type=int, default=200)
    parser.add_argument("--format", choices=["png", "jpg", "jpeg"], default="png")
    parser.add_argument("--max-side-px", type=int, default=3000)
    parser.add_argument("--no-recursive", action="store_true")
    parser.add_argument(
        "--batch",
        action="store_true",
        help="Treat source as a root folder containing multiple Baugruppe folders.",
    )
    parser.add_argument("--force", action="store_true")
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    source = Path(args.source)

    if args.batch:
        manifest = convert_many_baugruppen(
            source,
            args.output,
            recursive=not args.no_recursive,
            dpi=args.dpi,
            image_format=args.format,
            max_side_px=args.max_side_px,
            force=args.force,
        )
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
    elif source.is_file():
        manifest = convert_pdf_to_images(
            source,
            args.output,
            dpi=args.dpi,
            image_format=args.format,
            max_side_px=args.max_side_px,
            force=args.force,
        )
        print(json.dumps(asdict(manifest), ensure_ascii=False, indent=2))
    else:
        manifest = convert_baugruppe_pdfs(
            source,
            args.output,
            baugruppe_id=args.baugruppe_id,
            recursive=not args.no_recursive,
            dpi=args.dpi,
            image_format=args.format,
            max_side_px=args.max_side_px,
            force=args.force,
        )
        print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
