#!/usr/bin/env python3
"""Create one visual-context PDF per Baugruppe folder.

Expected input layout (names are arbitrary):
    BG_ROOT/
      BG_001/
        screenshots/     <- the only direct subfolder; contains PNG/JPG files
      BG_002/
        Bilder/          <- the only direct subfolder; contains PNG/JPG files

The script never changes the source folders.  It writes one PDF per BG and a
CSV log to the output directory.  If a screenshot folder contains more than
eight images, it uses five evenly distributed images after natural filename
sorting, so the selection is deterministic and reproducible.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path
from typing import Iterable

try:
    from PIL import Image, ImageOps
except ImportError:  # pragma: no cover - depends on the local environment
    print("Missing dependency: Pillow. Install it with: pip install Pillow", file=sys.stderr)
    raise SystemExit(2)


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}
NATURAL_SORT_RE = re.compile(r"(\d+)")


def natural_key(path: Path) -> list[object]:
    """Sort names as humans expect: image2.png before image10.png."""
    return [int(part) if part.isdigit() else part.casefold()
            for part in NATURAL_SORT_RE.split(path.name)]


def select_images(images: list[Path], threshold: int, maximum: int) -> list[Path]:
    """Keep all small sets; otherwise select evenly across the ordered list."""
    if len(images) <= threshold:
        return images
    if maximum < 1:
        raise ValueError("maximum must be at least 1")
    if maximum == 1:
        return [images[0]]

    last_index = len(images) - 1
    indices = [round(position * last_index / (maximum - 1)) for position in range(maximum)]
    return [images[index] for index in indices]


def image_to_page(image_path: Path, max_width: int, max_height: int) -> Image.Image:
    """Open one image safely and fit it onto a white, landscape PDF page."""
    with Image.open(image_path) as source:
        image = ImageOps.exif_transpose(source)
        if image.mode in {"RGBA", "LA"} or (image.mode == "P" and "transparency" in image.info):
            rgba = image.convert("RGBA")
            page_image = Image.new("RGB", rgba.size, "white")
            page_image.paste(rgba, mask=rgba.getchannel("A"))
        else:
            page_image = image.convert("RGB")

    page_image.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
    page = Image.new("RGB", (max_width, max_height), "white")
    x_offset = (max_width - page_image.width) // 2
    y_offset = (max_height - page_image.height) // 2
    page.paste(page_image, (x_offset, y_offset))
    return page


def direct_image_folder(bg_folder: Path) -> Path | None:
    """Return the only direct child directory, independent of its name."""
    folders = sorted(
        (child for child in bg_folder.iterdir() if child.is_dir() and not child.name.startswith(".")),
        key=natural_key,
    )
    return folders[0] if len(folders) == 1 else None


def write_log(log_path: Path, rows: Iterable[dict[str, str]]) -> None:
    fieldnames = [
        "bg_folder", "screenshot_folder", "status", "images_found",
        "images_selected", "selected_files", "output_pdf", "message",
    ]
    with log_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create visual-context PDFs from BG screenshot folders.")
    parser.add_argument("--bg-root", type=Path, required=True,
                        help="Folder whose direct subfolders are the BG folders.")
    parser.add_argument("--output-dir", type=Path, required=True,
                        help="Folder for generated PDFs and visual_context_selection_log.csv.")
    parser.add_argument("--threshold", type=int, default=8,
                        help="Use every image when at most this many are found (default: 8).")
    parser.add_argument("--max-images", type=int, default=5,
                        help="When image count exceeds --threshold, select this many images (default: 5).")
    parser.add_argument("--page-width", type=int, default=2400,
                        help="Generated PDF page width in pixels (default: 2400).")
    parser.add_argument("--page-height", type=int, default=1800,
                        help="Generated PDF page height in pixels (default: 1800).")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    bg_root = args.bg_root.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()

    if not bg_root.is_dir():
        print(f"BG root does not exist or is not a folder: {bg_root}", file=sys.stderr)
        return 2
    if args.threshold < 0 or args.max_images < 1 or args.page_width < 1 or args.page_height < 1:
        print("Threshold must be >= 0; max-images, page-width and page-height must be >= 1.", file=sys.stderr)
        return 2

    output_dir.mkdir(parents=True, exist_ok=True)
    log_rows: list[dict[str, str]] = []
    created = skipped = failed = 0

    bg_folders = sorted(
        (folder for folder in bg_root.iterdir() if folder.is_dir() and not folder.name.startswith(".")),
        key=natural_key,
    )
    if not bg_folders:
        print(f"No BG folders found directly inside: {bg_root}", file=sys.stderr)
        return 2

    for bg_folder in bg_folders:
        base_row = {
            "bg_folder": bg_folder.name,
            "screenshot_folder": "",
            "status": "",
            "images_found": "0",
            "images_selected": "0",
            "selected_files": "",
            "output_pdf": "",
            "message": "",
        }
        image_folder = direct_image_folder(bg_folder)
        if image_folder is None:
            base_row.update(status="skipped", message="Expected exactly one direct screenshot subfolder.")
            log_rows.append(base_row)
            skipped += 1
            print(f"SKIP  {bg_folder.name}: expected exactly one direct screenshot subfolder")
            continue

        images = sorted(
            (path for path in image_folder.iterdir()
             if path.is_file() and path.suffix.casefold() in IMAGE_EXTENSIONS),
            key=natural_key,
        )
        base_row["screenshot_folder"] = image_folder.name
        base_row["images_found"] = str(len(images))
        if not images:
            base_row.update(status="skipped", message="No PNG/JPG/JPEG files found in screenshot folder.")
            log_rows.append(base_row)
            skipped += 1
            print(f"SKIP  {bg_folder.name}: no supported images")
            continue

        selected = select_images(images, args.threshold, args.max_images)
        output_pdf = output_dir / f"{bg_folder.name}_visual_context.pdf"
        base_row["images_selected"] = str(len(selected))
        base_row["selected_files"] = " | ".join(path.name for path in selected)
        base_row["output_pdf"] = str(output_pdf)

        try:
            pages = [image_to_page(path, args.page_width, args.page_height) for path in selected]
            pages[0].save(output_pdf, "PDF", save_all=True, append_images=pages[1:], resolution=200.0)
        except Exception as error:
            base_row.update(status="failed", message=f"{type(error).__name__}: {error}")
            log_rows.append(base_row)
            failed += 1
            print(f"FAIL  {bg_folder.name}: {error}", file=sys.stderr)
            continue

        base_row.update(status="created", message="")
        log_rows.append(base_row)
        created += 1
        print(f"OK    {bg_folder.name}: {len(images)} found -> {len(selected)} selected -> {output_pdf.name}")

    log_path = output_dir / "visual_context_selection_log.csv"
    write_log(log_path, log_rows)
    print(f"\nFinished: {created} created, {skipped} skipped, {failed} failed.")
    print(f"Log: {log_path}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
