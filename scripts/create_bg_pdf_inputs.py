#!/usr/bin/env python3
"""Create one PDF input file per Baugruppe from CAD screenshots and DFC images.

The script reads ``Data_Folder_Path`` from ``Experiment_Dataset.xlsx``.  For
each valid BG folder it:

1. takes up to eight regular image files from its ``Bilder`` folder;
2. appends every DFC image found in the BG folder (including subfolders);
3. writes the combined PDF directly into that BG folder.

The same source image is never added twice.  Existing output PDFs are skipped
unless ``--overwrite`` is passed.  Nothing is renamed, moved, or deleted.

Dependencies: ``pip install pillow openpyxl``
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    from openpyxl import load_workbook
except ImportError as exc:  # pragma: no cover
    raise SystemExit("Missing dependency: openpyxl. Install it with: pip install openpyxl") from exc

try:
    from PIL import Image, ImageOps, UnidentifiedImageError
except ImportError as exc:  # pragma: no cover
    raise SystemExit("Missing dependency: Pillow. Install it with: pip install pillow") from exc


IMAGE_SUFFIXES = {".bmp", ".gif", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}
DEFAULT_SHEET = "Experiment_Dataset"
DEFAULT_PATH_COLUMN = "Data_Folder_Path"
DEFAULT_OUTPUT_NAME = "visual_context.pdf"
GENERATED_PDF_PATTERNS = ("visual_context_*.pdf", "*_visual_context.pdf")
LEGACY_GENERATED_PDF_NAMES = {"pdf_input.pdf"}


def normalise_header(value: object) -> str:
    return " ".join(str(value or "").strip().casefold().replace("_", " ").split())


def natural_key(path: Path) -> list[tuple[int, int | str]]:
    """Sort Screenshot_2 before Screenshot_10, independent of upper/lower case."""
    return [
        (0, int(part)) if part.isdigit() else (1, part.casefold())
        for part in re.split(r"(\d+)", path.name)
    ]


def is_image(path: Path) -> bool:
    return path.is_file() and path.suffix.casefold() in IMAGE_SUFFIXES


def is_dfc(path: Path) -> bool:
    return "dfc" in path.name.casefold()


def find_bilder_dir(bg_folder: Path) -> Path | None:
    direct = bg_folder / "Bilder"
    if direct.is_dir():
        return direct
    candidates = sorted(
        (item for item in bg_folder.iterdir() if item.is_dir() and item.name.casefold() == "bilder"),
        key=natural_key,
    )
    return candidates[0] if candidates else None


def delete_previous_generated_pdfs(bg_folder: Path) -> list[Path]:
    """Delete only PDFs created by this visual-context workflow in one BG folder."""
    candidates: set[Path] = set()
    for pattern in GENERATED_PDF_PATTERNS:
        candidates.update(path for path in bg_folder.glob(pattern) if path.is_file())
    candidates.update(
        path
        for path in bg_folder.iterdir()
        if path.is_file() and path.name.casefold() in LEGACY_GENERATED_PDF_NAMES
    )

    deleted: list[Path] = []
    for pdf_path in sorted(candidates, key=natural_key):
        pdf_path.unlink()
        deleted.append(pdf_path)
    return deleted


def collect_images(bg_folder: Path, max_screenshots: int) -> tuple[list[Path], list[Path]]:
    """Return normal screenshots first and DFC images second."""
    bilder_dir = find_bilder_dir(bg_folder)
    screenshots: list[Path] = []
    if bilder_dir:
        screenshots = sorted(
            (item for item in bilder_dir.rglob("*") if is_image(item) and not is_dfc(item)),
            key=natural_key,
        )[:max_screenshots]

    # DFC images may sit directly in the BG folder or in a nested folder.  They
    # are selected by filename and are deliberately appended after screenshots.
    # Output PDFs are not images, so a rerun cannot accidentally include them.
    dfc_images = sorted(
        (item for item in bg_folder.rglob("*") if is_image(item) and is_dfc(item)),
        key=natural_key,
    )

    selected: set[Path] = set(screenshots)
    dfc_images = [item for item in dfc_images if item not in selected]
    return screenshots, dfc_images


def open_as_rgb(path: Path) -> Image.Image:
    """Open and normalize an image for reliable PDF output."""
    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source)
        if image.mode == "RGBA":
            background = Image.new("RGB", image.size, "white")
            background.paste(image, mask=image.getchannel("A"))
            return background
        return image.convert("RGB")


@dataclass
class Result:
    folder: Path
    status: str
    screenshots: int = 0
    dfc_images: int = 0
    detail: str = ""


def build_pdf(
    bg_folder: Path,
    *,
    output_name: str,
    max_screenshots: int,
    overwrite: bool,
) -> Result:
    output_path = bg_folder / (
        f"visual_context_{bg_folder.name}.pdf"
        if output_name == DEFAULT_OUTPUT_NAME
        else output_name
    )
    screenshots, dfc_images = collect_images(bg_folder, max_screenshots)
    selected = screenshots + dfc_images

    if not selected:
        return Result(bg_folder, "SKIPPED_NO_IMAGES", detail="No regular Bilder screenshots or DFC images found")
    if output_path.exists() and not overwrite:
        return Result(
            bg_folder,
            "SKIPPED_EXISTS",
            len(screenshots),
            len(dfc_images),
            f"Already exists: {output_path.name} (use --overwrite to recreate)",
        )

    pages: list[Image.Image] = []
    unreadable: list[str] = []
    for image_path in selected:
        try:
            pages.append(open_as_rgb(image_path))
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            unreadable.append(f"{image_path.name}: {exc}")

    if not pages:
        return Result(bg_folder, "SKIPPED_UNREADABLE", detail="; ".join(unreadable))

    try:
        pages[0].save(output_path, "PDF", save_all=True, append_images=pages[1:], resolution=150.0)
    finally:
        for page in pages:
            page.close()

    detail = f"Created {output_path.name} ({len(pages)} pages)"
    if unreadable:
        detail += f"; skipped unreadable: {'; '.join(unreadable)}"
    return Result(bg_folder, "CREATED", len(screenshots), len(dfc_images), detail)


def read_paths(excel_path: Path, sheet_name: str, path_column: str) -> list[Path]:
    workbook = load_workbook(excel_path, read_only=True, data_only=True)
    try:
        if sheet_name not in workbook.sheetnames:
            raise ValueError(f"Worksheet {sheet_name!r} not found. Available: {', '.join(workbook.sheetnames)}")
        worksheet = workbook[sheet_name]
        header = next(worksheet.iter_rows(min_row=1, max_row=1, values_only=True))
        expected = normalise_header(path_column)
        matches = [index for index, value in enumerate(header) if normalise_header(value) == expected]
        if len(matches) != 1:
            raise ValueError(
                f"Column {path_column!r} not found exactly once. Available: {', '.join(str(v) for v in header if v)}"
            )
        index = matches[0]
        paths: list[Path] = []
        seen: set[str] = set()
        for row in worksheet.iter_rows(min_row=2, values_only=True):
            value = row[index] if index < len(row) else None
            text = str(value or "").strip()
            if text:
                key = text.casefold()
                if key not in seen:
                    seen.add(key)
                    paths.append(Path(text))
        return paths
    finally:
        workbook.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-excel", type=Path, required=True, help="Experiment_Dataset.xlsx with Data_Folder_Path")
    parser.add_argument("--sheet-name", default=DEFAULT_SHEET)
    parser.add_argument("--path-column", default=DEFAULT_PATH_COLUMN)
    parser.add_argument("--output-file-name", default=DEFAULT_OUTPUT_NAME)
    parser.add_argument("--max-screenshots", type=int, default=8)
    parser.add_argument("--overwrite", action="store_true", help="Replace an existing visual-context PDF")
    parser.add_argument(
        "--delete-existing-generated-pdfs",
        action="store_true",
        help=(
            "Before creating PDFs, delete only prior generated visual-context PDFs "
            "in the listed BG folders."
        ),
    )
    args = parser.parse_args()

    if args.max_screenshots < 1:
        parser.error("--max-screenshots must be at least 1")
    if Path(args.output_file_name).name != args.output_file_name or not args.output_file_name.casefold().endswith(".pdf"):
        parser.error("--output-file-name must be a PDF file name only, for example PDF_Input.pdf")
    if not args.input_excel.is_file():
        parser.error(f"Input Excel was not found: {args.input_excel}")

    paths = read_paths(args.input_excel, args.sheet_name, args.path_column)
    if not paths:
        print("No non-empty BG paths were found in the Excel column.")
        return 1

    results: list[Result] = []
    deleted_count = 0
    for folder in paths:
        if not folder.is_dir():
            results.append(Result(folder, "SKIPPED_MISSING_FOLDER", detail="Folder does not exist"))
            continue
        if args.delete_existing_generated_pdfs:
            deleted = delete_previous_generated_pdfs(folder)
            deleted_count += len(deleted)
            for pdf_path in deleted:
                print(f"DELETED {pdf_path}")
        results.append(
            build_pdf(
                folder,
                output_name=args.output_file_name,
                max_screenshots=args.max_screenshots,
                overwrite=args.overwrite,
            )
        )

    print("\nPDF input creation report")
    print("=" * 78)
    for result in results:
        print(f"{result.status:23} | screenshots={result.screenshots:2} | DFC={result.dfc_images:2} | {result.folder}")
        print(f"  {result.detail}")
    print("=" * 78)
    counts: dict[str, int] = {}
    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1
    print(f"Total BG paths: {len(results)} | " + " | ".join(f"{key}={value}" for key, value in sorted(counts.items())))
    if args.delete_existing_generated_pdfs:
        print(f"Deleted prior generated PDFs: {deleted_count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())


# -----------------------------------------------------------------------------
# 70 BG: create one PDF per BG from Bilder screenshots and DFC images
#
# Prerequisites
# -------------
# 1. Experiment_Dataset.xlsx is stored in Downloads\70BG and has the column
#    Data_Folder_Path (created by build_experiment_dataset.py).
# 2. Install dependencies once:
#      pip install pillow openpyxl
# 3. Run the following command from the RepoMA root folder in PowerShell:
#
# python .\scripts\create_bg_pdf_inputs.py `
#   --input-excel "$env:USERPROFILE\Downloads\70BG\Experiment_Dataset.xlsx"
#
# Result
# ------
# Every BG folder listed in Data_Folder_Path receives\n# visual_context_<BG folder name>.pdf. Its pages
# are: up to the first eight non-DFC screenshots from Bilder, then all image
# files whose name contains DFC.  It does not change the original image files.
#
# Delete prior generated PDFs, then recreate from the current images
# ------------------------------------------------------------------
# This deletes only visual_context_*.pdf, legacy *_visual_context.pdf, and
# legacy PDF_Input.pdf inside the BG folders listed in the Excel file.
#
# python .\scripts\create_bg_pdf_inputs.py `
#   --input-excel "$env:USERPROFILE\Downloads\70BG\Experiment_Dataset.xlsx" `
#   --delete-existing-generated-pdfs
# -----------------------------------------------------------------------------
