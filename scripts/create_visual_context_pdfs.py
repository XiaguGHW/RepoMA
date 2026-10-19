#!/usr/bin/env python3
"""Create one visual-context PDF per Baugruppe folder.

The script recursively finds BG folders below --bg-root that contain one direct
screenshot subfolder (normally named Bilder).  For each BG it creates one PDF
containing, in this exact order:

1. The first eight screenshots after natural filename sorting (or all of them
   if there are fewer than eight).
2. Every DFC screenshot found anywhere inside the same BG folder, appended
   after the regular screenshots.  Files already included in step 1 are never
   added twice.

The derived visual-context PDF is written directly into its own BG folder so
the later PDF experiment can collect it together with that BG's original PDFs.
The root folder receives visual_context_selection_log.csv, which records the
exact selection for reproducibility.
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
MAX_SCREENSHOTS = 8
NATURAL_SORT_RE = re.compile(r"(\\d+)")


def natural_key(path: Path) -> list[object]:
    """Sort names as humans expect: image2.png before image10.png."""
    return [
        int(part) if part.isdigit() else part.casefold()
        for part in NATURAL_SORT_RE.split(path.name)
    ]


def is_image(path: Path) -> bool:
    return path.is_file() and path.suffix.casefold() in IMAGE_EXTENSIONS


def is_dfc_screenshot(path: Path, bg_folder: Path) -> bool:
    """Recognise image files that are explicitly identified as DFC screenshots."""
    relative_name = str(path.relative_to(bg_folder)).casefold()
    normalised = " ".join(relative_name.replace("_", " ").replace("-", " ").split())
    return "dfc" in normalised


def select_screenshots(images: list[Path]) -> list[Path]:
    """Keep the first eight naturally sorted screenshot files."""
    return images[:MAX_SCREENSHOTS]


def image_to_page(image_path: Path, max_width: int, max_height: int) -> Image.Image:
    """Open one image safely and fit it onto a white, landscape PDF page."""
    with Image.open(image_path) as source:
        image = ImageOps.exif_transpose(source)
        if image.mode in {"RGBA", "LA"} or (
            image.mode == "P" and "transparency" in image.info
        ):
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
    """Return the only direct child folder intended for ordinary screenshots."""
    folders = sorted(
        (child for child in bg_folder.iterdir() if child.is_dir() and not child.name.startswith(".")),
        key=natural_key,
    )
    if len(folders) != 1:
        return None

    candidate = folders[0]
    if any(is_image(path) for path in candidate.iterdir()):
        return candidate
    return None


def find_bg_folders(bg_root: Path) -> list[Path]:
    """Find BG folders at any depth that contain one direct screenshot folder."""
    return [
        folder
        for folder in sorted(
            (path for path in bg_root.rglob("*") if path.is_dir()),
            key=natural_key,
        )
        if direct_image_folder(folder) is not None
    ]


def display_path(path: Path, parent: Path) -> str:
    return str(path.relative_to(parent))


def write_log(log_path: Path, rows: Iterable[dict[str, str]]) -> None:
    fieldnames = [
        "bg_folder",
        "screenshot_folder",
        "status",
        "screenshots_found",
        "screenshots_selected",
        "selected_screenshot_files",
        "dfc_images_found",
        "dfc_images_added",
        "added_dfc_files",
        "output_pdf",
        "message",
    ]
    with log_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create visual-context PDFs from BG screenshot and DFC images."
    )
    parser.add_argument(
        "--bg-root",
        type=Path,
        required=True,
        help="Root below which the BG folders are located; class/BG nesting is supported.",
    )
    parser.add_argument(
        "--page-width",
        type=int,
        default=2400,
        help="Generated PDF page width in pixels (default: 2400).",
    )
    parser.add_argument(
        "--page-height",
        type=int,
        default=1800,
        help="Generated PDF page height in pixels (default: 1800).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    bg_root = args.bg_root.expanduser().resolve()
    if not bg_root.is_dir():
        print(f"BG root does not exist or is not a folder: {bg_root}", file=sys.stderr)
        return 2
    if args.page_width < 1 or args.page_height < 1:
        print("Page width and page height must be at least 1.", file=sys.stderr)
        return 2

    bg_folders = find_bg_folders(bg_root)
    if not bg_folders:
        print(f"No BG folders with a direct screenshot folder found below: {bg_root}", file=sys.stderr)
        return 2

    log_rows: list[dict[str, str]] = []
    created = failed = 0

    for bg_folder in bg_folders:
        image_folder = direct_image_folder(bg_folder)
        assert image_folder is not None

        dfc_images = sorted(
            (
                path
                for path in bg_folder.rglob("*")
                if is_image(path) and is_dfc_screenshot(path, bg_folder)
            ),
            key=natural_key,
        )
        dfc_set = set(dfc_images)
        screenshot_images = sorted(
            (
                path
                for path in image_folder.iterdir()
                if is_image(path) and path not in dfc_set
            ),
            key=natural_key,
        )
        selected_screenshots = select_screenshots(screenshot_images)

        # DFC pages are deliberately excluded from the regular screenshot
        # selection and always appended after the selected screenshots.
        added_dfc_images = dfc_images
        ordered_images = selected_screenshots + added_dfc_images

        base_row = {
            "bg_folder": display_path(bg_folder, bg_root),
            "screenshot_folder": display_path(image_folder, bg_folder),
            "status": "",
            "screenshots_found": str(len(screenshot_images)),
            "screenshots_selected": str(len(selected_screenshots)),
            "selected_screenshot_files": " | ".join(
                display_path(path, bg_folder) for path in selected_screenshots
            ),
            "dfc_images_found": str(len(dfc_images)),
            "dfc_images_added": str(len(added_dfc_images)),
            "added_dfc_files": " | ".join(
                display_path(path, bg_folder) for path in added_dfc_images
            ),
            "output_pdf": "",
            "message": "",
        }

        if not ordered_images:
            base_row.update(status="skipped", message="No PNG/JPG/JPEG files found.")
            log_rows.append(base_row)
            print(f"SKIP  {bg_folder}: no supported images")
            continue

        output_pdf = bg_folder / f"{bg_folder.name}_visual_context.pdf"
        base_row["output_pdf"] = str(output_pdf)

        try:
            pages = [
                image_to_page(path, args.page_width, args.page_height)
                for path in ordered_images
            ]
            pages[0].save(
                output_pdf,
                "PDF",
                save_all=True,
                append_images=pages[1:],
                resolution=200.0,
            )
        except Exception as error:
            base_row.update(status="failed", message=f"{type(error).__name__}: {error}")
            log_rows.append(base_row)
            failed += 1
            print(f"FAIL  {bg_folder}: {error}", file=sys.stderr)
            continue

        base_row.update(status="created")
        log_rows.append(base_row)
        created += 1
        print(
            f"OK    {bg_folder}: {len(screenshot_images)} regular screenshots -> "
            f"{len(selected_screenshots)} used; {len(dfc_images)} DFC found -> "
            f"{len(added_dfc_images)} appended"
        )

    log_path = bg_root / "visual_context_selection_log.csv"
    write_log(log_path, log_rows)
    print(f"\nFinished: {created} created, {failed} failed.")
    print(f"Log: {log_path}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())


# -----------------------------------------------------------------------------
# 70 BG: create visual-context PDFs (PowerShell)
#
# Run from the 70BG folder.  The command processes all BG folders below the
# seven class folders.  Each PDF is written into its own BG folder and contains
# the first eight Bilder screenshots (natural filename order), followed by all
# DFC screenshots found in that BG folder.
#
# python .\scripts\create_visual_context_pdfs.py `
#   --bg-root "$env:USERPROFILE\Downloads\70BG"
# -----------------------------------------------------------------------------
