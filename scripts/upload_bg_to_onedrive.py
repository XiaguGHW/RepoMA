#!/usr/bin/env python3
"""Copy Baugruppen from an Excel list into a locally synchronized OneDrive folder.

The script never moves or renames source files.  It copies each complete BG
folder to <target>/<Ground Truth>/<SAP-Nummer>/ and verifies each destination
file with SHA-256.  OneDrive itself performs the cloud upload afterwards.

Requires: Python 3.9+ and openpyxl (pip install openpyxl)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from openpyxl import Workbook, load_workbook
except ImportError:  # pragma: no cover - executed only on a new user system
    print("Fehlendes Paket: openpyxl. Bitte ausführen: py -m pip install openpyxl")
    raise SystemExit(2)


REQUIRED_HEADERS = ("SAP-Nummer", "Ground Truth", "Data_Folder_Path")
CHUNK_SIZE = 8 * 1024 * 1024
INVALID_WINDOWS_NAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def norm_header(value: Any) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def display_path(path: Path) -> str:
    """Use a normal Windows string without resolving unavailable network paths."""
    return str(path)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(CHUNK_SIZE), b""):
            digest.update(block)
    return digest.hexdigest()


class Progress:
    def __init__(self, total_bytes: int, enabled: bool = True) -> None:
        self.total = max(total_bytes, 1)
        self.done = 0
        self.enabled = enabled
        self.last_draw = 0.0

    def add(self, amount: int, bg: int, file_name: str) -> None:
        self.done += amount
        if not self.enabled:
            return
        timestamp = time.monotonic()
        if timestamp - self.last_draw < 0.12 and self.done < self.total:
            return
        self.last_draw = timestamp
        width = 24
        fraction = min(self.done / self.total, 1.0)
        filled = int(width * fraction)
        bar = "#" * filled + "-" * (width - filled)
        text = f"[{bar}] {fraction:6.1%} | BG {bg} | {file_name[:42]}"
        print("\r" + text.ljust(100), end="", flush=True)

    def finish(self) -> None:
        if self.enabled:
            print()


def load_excel_rows(excel_path: Path, sheet_name: str | None) -> list[dict[str, str]]:
    workbook = load_workbook(excel_path, read_only=True, data_only=True)
    try:
        sheet = workbook[sheet_name] if sheet_name else workbook.active
    except KeyError as exc:
        available = ", ".join(workbook.sheetnames)
        raise ValueError(f"Arbeitsblatt '{sheet_name}' nicht gefunden. Verfügbar: {available}") from exc

    iterator = sheet.iter_rows(values_only=True)
    try:
        header_values = next(iterator)
    except StopIteration as exc:
        raise ValueError("Die Excel-Datei ist leer.") from exc
    headers = {norm_header(value): position for position, value in enumerate(header_values) if value is not None}
    missing = [header for header in REQUIRED_HEADERS if norm_header(header) not in headers]
    if missing:
        raise ValueError(
            "Pflichtspalten nicht gefunden: " + ", ".join(missing) +
            ". Erwartet werden: " + ", ".join(REQUIRED_HEADERS)
        )

    rows: list[dict[str, str]] = []
    for excel_row, values in enumerate(iterator, start=2):
        def get(header: str) -> str:
            value = values[headers[norm_header(header)]] if headers[norm_header(header)] < len(values) else None
            return str(value).strip() if value is not None else ""

        sap, ground_truth, source_folder = (get(header) for header in REQUIRED_HEADERS)
        if not any((sap, ground_truth, source_folder)):
            continue
        rows.append({
            "excel_row": str(excel_row), "sap": sap, "ground_truth": ground_truth,
            "source_folder": source_folder,
        })
    return rows


def build_manifest(excel_path: Path, sheet_name: str | None, manifest_path: Path) -> dict[str, Any]:
    rows = load_excel_rows(excel_path, sheet_name)
    bg_rows: list[dict[str, Any]] = []
    files: list[dict[str, Any]] = []

    for bg_index, row in enumerate(rows, start=1):
        source_root = Path(row["source_folder"])
        bg = {**row, "bg_index": bg_index, "scan_status": "ok", "file_count": 0, "total_bytes": 0}
        if not row["sap"] or not row["ground_truth"] or not row["source_folder"]:
            bg["scan_status"] = "missing_required_value"
        elif not source_root.is_dir():
            bg["scan_status"] = "source_folder_not_found"
        else:
            try:
                for source in sorted((item for item in source_root.rglob("*") if item.is_file()), key=lambda p: str(p).casefold()):
                    try:
                        size = source.stat().st_size
                    except OSError as exc:
                        files.append({
                            "bg_index": bg_index, "sap": row["sap"], "ground_truth": row["ground_truth"],
                            "source": str(source), "relative_path": "", "size": 0,
                            "status": "source_stat_failed", "message": repr(exc), "updated_at": now(),
                        })
                        continue
                    relative = source.relative_to(source_root)
                    files.append({
                        "bg_index": bg_index, "sap": row["sap"], "ground_truth": row["ground_truth"],
                        "source": str(source), "relative_path": str(relative), "size": size,
                        "status": "pending", "message": "", "destination": "", "sha256": "", "updated_at": now(),
                    })
                    bg["file_count"] += 1
                    bg["total_bytes"] += size
            except OSError as exc:
                bg["scan_status"] = "source_scan_failed"
                bg["scan_message"] = repr(exc)
        bg_rows.append(bg)

    manifest = {
        "schema_version": 1, "created_at": now(), "excel_path": str(excel_path),
        "sheet": sheet_name, "bg_rows": bg_rows, "files": files,
    }
    save_json(manifest_path, manifest)
    return manifest


def save_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def load_manifest(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def safe_component(value: str) -> str:
    # We intentionally do not silently rename anything. This is only used to
    # detect an impossible destination path before copy is attempted.
    return value


def suggested_name(name: str, destination: Path) -> str:
    suffix = Path(name).suffix
    stem = Path(name).stem or "file"
    safe_stem = INVALID_WINDOWS_NAME.sub("_", stem).strip(" .") or "file"
    marker = hashlib.sha1(name.encode("utf-8", errors="replace")).hexdigest()[:8]
    candidate = f"{safe_stem[:80]}__{marker}{suffix[:20]}"
    # Leave enough room for Windows Explorer's practical 260-character limit.
    max_name = max(20, 245 - len(str(destination.parent)))
    return candidate[:max_name - len(suffix)] + suffix if len(candidate) > max_name else candidate


def destination_for(record: dict[str, Any], target: Path) -> Path:
    saved = record.get("destination", "")
    if saved:
        return Path(saved)
    return target / safe_component(record["ground_truth"]) / safe_component(record["sap"]) / record["relative_path"]


def destination_matches(record: dict[str, Any], destination: Path) -> bool:
    source = Path(record["source"])
    if not source.is_file() or not destination.is_file():
        return False
    try:
        if source.stat().st_size != destination.stat().st_size:
            return False
        # Always hash the current source.  A source file may have changed after
        # an earlier interrupted run, and an old manifest hash must not cause
        # us to incorrectly treat the destination as current.
        source_hash = sha256(source)
        target_hash = sha256(destination)
    except OSError:
        return False
    record["sha256"] = source_hash
    return source_hash == target_hash


def copy_with_progress(source: Path, destination: Path, progress: Progress, bg_index: int) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".copying")
    if temporary.exists():
        temporary.unlink()
    try:
        with source.open("rb") as read_handle, temporary.open("wb") as write_handle:
            while True:
                block = read_handle.read(CHUNK_SIZE)
                if not block:
                    break
                write_handle.write(block)
                progress.add(len(block), bg_index, source.name)
        shutil.copystat(source, temporary)
        os.replace(temporary, destination)
    except Exception:
        try:
            if temporary.exists():
                temporary.unlink()
        except OSError:
            pass
        raise


def user_resolution(record: dict[str, Any], destination: Path, error: Exception, non_interactive: bool) -> str:
    print("\n\nKopieren fehlgeschlagen:")
    print(f"  BG {record['bg_index']} | SAP {record['sap']}")
    print(f"  Quelle: {record['source']}")
    print(f"  Ziel:   {display_path(destination)}")
    print(f"  Grund:  {error}")
    if non_interactive or not sys.stdin.isatty():
        print("  Nicht-interaktiver Modus: Datei wird übersprungen.")
        return "skip"
    print("\n[R] vorgeschlagenen Ziel-Dateinamen verwenden  [E] selbst eingeben")
    print("[S] diese Datei überspringen  [Q] gesamten Lauf beenden")
    while True:
        choice = input("Auswahl: ").strip().lower()
        if choice == "r":
            record["destination"] = str(destination.with_name(suggested_name(destination.name, destination)))
            return "retry"
        if choice == "e":
            new_name = input("Neuer DATEINAME (kein Pfad): ").strip()
            if not new_name or Path(new_name).name != new_name:
                print("Bitte nur einen nicht-leeren Dateinamen ohne Ordner angeben.")
                continue
            record["destination"] = str(destination.with_name(new_name))
            return "retry"
        if choice == "s":
            return "skip"
        if choice == "q":
            return "quit"
        print("Bitte R, E, S oder Q eingeben.")


def report_xlsx(manifest: dict[str, Any], report_path: Path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "File_Report"
    headers = ["BG_Index", "SAP-Nummer", "Ground Truth", "Status", "Quelle", "Ziel", "Bytes", "SHA-256", "Meldung", "Aktualisiert"]
    sheet.append(headers)
    for record in manifest["files"]:
        sheet.append([
            record.get("bg_index"), record.get("sap"), record.get("ground_truth"), record.get("status"),
            record.get("source"), record.get("destination"), record.get("size"), record.get("sha256"),
            record.get("message"), record.get("updated_at"),
        ])
    summary = workbook.create_sheet("BG_Summary")
    summary.append(["BG_Index", "SAP-Nummer", "Ground Truth", "Scan-Status", "Anzahl Dateien", "Bytes", "Excel-Zeile"])
    for bg in manifest["bg_rows"]:
        summary.append([bg["bg_index"], bg["sap"], bg["ground_truth"], bg["scan_status"], bg["file_count"], bg["total_bytes"], bg["excel_row"]])
    for ws in workbook.worksheets:
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        for column in ws.columns:
            width = min(max(len(str(cell.value or "")) for cell in column) + 2, 55)
            ws.column_dimensions[column[0].column_letter].width = width
    report_path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(report_path)


def selected_bg_indices(manifest: dict[str, Any], from_index: int, count: int | None) -> set[int]:
    highest = len(manifest["bg_rows"])
    if from_index < 1 or from_index > highest:
        raise ValueError(f"--from muss zwischen 1 und {highest} liegen.")
    end = highest if count is None else min(highest, from_index + count - 1)
    return set(range(from_index, end + 1))


def process(args: argparse.Namespace) -> int:
    excel = Path(args.excel).expanduser()
    target = Path(args.target).expanduser()
    state_dir = Path(args.state_dir).expanduser() if args.state_dir else excel.parent / "bg_onedrive_upload_state"
    manifest_path = state_dir / "bg_upload_manifest.json"
    report_path = state_dir / "bg_upload_report.xlsx"

    if args.rebuild_manifest or not manifest_path.exists():
        print("Scanne Excel und alle BG-Ordner. Das kann bei vielen Dateien etwas dauern …")
        manifest = build_manifest(excel, args.sheet, manifest_path)
    else:
        manifest = load_manifest(manifest_path)
        if Path(manifest.get("excel_path", "")) != excel:
            raise ValueError("Die vorhandene Manifest-Datei gehört zu einer anderen Excel-Datei. Bitte --rebuild-manifest verwenden.")

    indices = selected_bg_indices(manifest, args.from_index, args.count)
    records = [record for record in manifest["files"] if record["bg_index"] in indices]
    bytes_to_copy = sum(record["size"] for record in records if record["status"] != "verified")
    progress = Progress(bytes_to_copy, enabled=not args.no_progress)
    print(f"Verarbeite BG {min(indices)}–{max(indices)}: {len(records)} Dateien, {bytes_to_copy / 1024**3:.2f} GiB (vorhandene verifizierte Dateien werden übersprungen).")

    completed = skipped = failed = 0
    for record in records:
        if record["status"] == "source_stat_failed":
            failed += 1
            continue
        source = Path(record["source"])
        if not source.is_file():
            record.update(status="source_missing", message="Quelldatei nicht mehr vorhanden", updated_at=now())
            failed += 1
            save_json(manifest_path, manifest)
            continue
        destination = destination_for(record, target)
        try:
            if destination_matches(record, destination):
                record.update(status="verified", destination=str(destination), message="Bereits vorhanden; Größe und SHA-256 stimmen überein.", updated_at=now())
                completed += 1
                save_json(manifest_path, manifest)
                continue
            # Requirement: first try the original target path. No automatic rename.
            copy_with_progress(source, destination, progress, record["bg_index"])
            if not destination_matches(record, destination):
                raise IOError("Kopie erstellt, aber Größe oder SHA-256 stimmt nicht überein.")
            record.update(status="verified", destination=str(destination), message="Lokal kopiert und mit SHA-256 verifiziert; OneDrive-Synchronisierung steht noch aus.", updated_at=now())
            completed += 1
        except Exception as exc:
            action = user_resolution(record, destination, exc, args.non_interactive)
            if action == "retry":
                save_json(manifest_path, manifest)
                # Retry this same record; its newly confirmed target name is persisted.
                try:
                    destination = destination_for(record, target)
                    copy_with_progress(source, destination, progress, record["bg_index"])
                    if not destination_matches(record, destination):
                        raise IOError("Kopie erstellt, aber Größe oder SHA-256 stimmt nicht überein.")
                    record.update(status="verified", destination=str(destination), message="Nach bestätigter Umbenennung lokal kopiert und mit SHA-256 verifiziert; OneDrive-Synchronisierung steht noch aus.", updated_at=now())
                    completed += 1
                except Exception as retry_error:
                    record.update(status="failed", message=f"Auch nach Änderung fehlgeschlagen: {retry_error}", updated_at=now())
                    failed += 1
            elif action == "quit":
                record.update(status="interrupted", message=f"Abbruch nach Fehler: {exc}", updated_at=now())
                save_json(manifest_path, manifest)
                progress.finish()
                report_xlsx(manifest, report_path)
                print(f"Abgebrochen. Bericht: {report_path}")
                return 1
            else:
                record.update(status="skipped", message=f"Nach Kopierfehler übersprungen: {exc}", updated_at=now())
                skipped += 1
        finally:
            save_json(manifest_path, manifest)

    progress.finish()
    report_xlsx(manifest, report_path)
    print(f"Fertig. Verifiziert: {completed} | übersprungen: {skipped} | Fehler: {failed}")
    print(f"Bericht: {report_path}")
    print("Hinweis: 'verified' bedeutet lokale Kopie + SHA-256 geprüft. Bitte erst nach dem grünen OneDrive-Haken als cloudseitig hochgeladen betrachten.")
    return 0 if failed == 0 else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="BG-Dateien nach Ground Truth in einen lokal synchronisierten OneDrive-Ordner kopieren.")
    parser.add_argument("--excel", required=True, help="Pfad zur Excel-Datei mit SAP-Nummer, Ground Truth und Data_Folder_Path.")
    parser.add_argument("--target", required=True, help="Lokaler Bosch-OneDrive-Zielordner (nicht die Web-URL).")
    parser.add_argument("--sheet", help="Optionaler Arbeitsblattname; ohne Angabe wird das aktive Blatt verwendet.")
    parser.add_argument("--from", dest="from_index", type=int, default=1, help="Erster BG-Index aus der stabilen Manifest-Reihenfolge (1-basiert).")
    parser.add_argument("--count", type=int, help="Anzahl der zu verarbeitenden BGs; ohne Angabe bis zum letzten BG.")
    parser.add_argument("--state-dir", help="Ordner für Manifest und Bericht; Standard: neben der Excel-Datei.")
    parser.add_argument("--rebuild-manifest", action="store_true", help="Excel und Quelle neu scannen. Nur verwenden, wenn sich diese geändert haben.")
    parser.add_argument("--non-interactive", action="store_true", help="Bei Fehlern nicht fragen, sondern Datei als übersprungen markieren.")
    parser.add_argument("--no-progress", action="store_true", help="Fortschrittsanzeige deaktivieren.")
    return parser.parse_args()


if __name__ == "__main__":
    try:
        raise SystemExit(process(parse_args()))
    except KeyboardInterrupt:
        print("\nDurch Benutzer abgebrochen.")
        raise SystemExit(130)
    except Exception as exc:
        print(f"FEHLER: {exc}", file=sys.stderr)
        raise SystemExit(2)


# Windows / PowerShell examples (copy these commands; adapt only the paths):
#
# 0) Install the only external dependency once:
#    py -m pip install openpyxl
#
# 1) First formal batch: BG 1 to 10.  It scans the 129 entries and persists
#    bg_upload_manifest.json, then copies this first batch only.
#    py .\upload_bg_to_onedrive.py `
#      --excel "C:\\Users\\wdu4fel\\Documents\\Python_Projects\\Experimentelle\\your_data.xlsx" `
#      --target "C:\\Users\\wdu4fel\\OneDrive - Bosch Group\\MA_BG_Export" `
#      --from 1 --count 10
#
# 2) After confirming the first ten folders have a green OneDrive checkmark,
#    continue with every remaining BG (11 to 129):
#    py .\upload_bg_to_onedrive.py `
#      --excel "C:\\Users\\wdu4fel\\Documents\\Python_Projects\\Experimentelle\\your_data.xlsx" `
#      --target "C:\\Users\\wdu4fel\\OneDrive - Bosch Group\\MA_BG_Export" `
#      --from 11 --count 119
#
# 3) Or continue in batches of 20 BGs:
#    py .\upload_bg_to_onedrive.py --excel "C:\\...\\your_data.xlsx" --target "C:\\...\\MA_BG_Export" --from 11 --count 20
#    py .\upload_bg_to_onedrive.py --excel "C:\\...\\your_data.xlsx" --target "C:\\...\\MA_BG_Export" --from 31 --count 20
#
# 4) If the Excel paths or folder contents changed before the first real run,
#    rebuild the stable manifest explicitly:
#    py .\upload_bg_to_onedrive.py --excel "C:\\...\\your_data.xlsx" --target "C:\\...\\MA_BG_Export" --rebuild-manifest --from 1 --count 10
