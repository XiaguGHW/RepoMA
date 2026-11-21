#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
merge_nachlauf.py

Führt Nachlauf-Dateien (erneut ausgeführte, zuvor EXCLUDED Baugruppen) mit den
ursprünglichen Lauf-Dateien zusammen, sodass wieder 10 vollständige Lauf-Dateien entstehen.

Zuordnung (Standard): Nur unvollständige Originale werden ergänzt, d. h. Läufe, in denen eine
Baugruppe der Nachlauf-Dateien fehlt oder keine gültige Vorhersage hat (EXCLUDED, leer, [EMPTY],
nicht zuordenbar, Processing-Fehler). Je unvollständigem Lauf wird eine eigene Nachlauf-Datei
verwendet (beide nach Zeitstempel sortiert). Gültige Zeilen bleiben unverändert, fehlende Zeilen
werden angehängt. So kann eine gemeinsame Nachlauf-Eingabe je Modell (Skript 16, --pro-modell)
so oft laufen, wie es unvollständige Läufe gibt.
Mit --ueberschreiben: altes Verhalten (alle Originale ↔ alle Nachlauf-Dateien, gleiche Anzahl).

Für jede Baugruppe (SAP-Nummer) aus der Nachlauf-Datei werden in der Originaldatei alle
gemeinsamen Spalten (z. B. Ground Truth, Register, Weitere zulässige Ground Truth,
Predicted_Label, Reasoning) mit den Nachlauf-Werten überschrieben. Allowed_Set_Status wird
neu berechnet (Synonyme laut Codebook); ein manuell eingetragener Status wird geprüft.
Formatierung und weitere Tabellenblätter der Originaldatei bleiben erhalten.

Aufruf:
    python merge_nachlauf.py                  # alle Unterordner des Skriptordners mit Nachlauf-Dateien
    python merge_nachlauf.py <Ordner> ...      # bestimmte Ordner
    python merge_nachlauf.py --dry-run <Ordner> # nur prüfen, nichts schreiben

Ergebnis je Ordner:
    - Originale und Nachlauf-Dateien werden nach <Ordner>/_backup_vor_merge/ verschoben.
    - Die 10 zusammengeführten Dateien liegen danach mit den ursprünglichen Namen im Ordner.
    - merge_protokoll.xlsx im Backup-Ordner listet jede Änderung.

Benötigt: openpyxl, pandas
"""

import argparse
import copy
import re
import shutil
import sys
import unicodedata
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook

SHEET_NAME = "Sheet1"
NACHLAUF_PREFIX = "nachlauf_"
BACKUP_DIR = "_backup_vor_merge"
STATUS_COL = "Allowed_Set_Status"

CLASSES = [
    "Lineareinheit", "Greifer", "Roboter", "Rotationseinheit",
    "Multi-Achs-System (Gantry)", "Kombinierte Einheit", "Keine der verfügbaren Klassen",
]
SYNONYMS = {
    "gantry": "Multi-Achs-System (Gantry)",
    "umsetzeinheit": "Kombinierte Einheit",
    "keine der verfgbaren klassen": "Keine der verfügbaren Klassen",
}


def _norm(s):
    s = unicodedata.normalize("NFC", str(s)).replace(" ", " ")
    return re.sub(r"\s+", " ", s).strip().lower()


LOOKUP = {_norm(c): c for c in CLASSES}
LOOKUP.update({_norm(k): v for k, v in SYNONYMS.items()})


def empty(v):
    return v is None or str(v).strip() == "" or str(v).strip().lower() in {"nan", "none"}


def canon(v):
    if empty(v):
        return None
    n = _norm(re.sub(r"^\[[A-Ga-g]\]\s*", "", str(v).strip()))
    if n in LOOKUP:
        return LOOKUP[n]
    if n.startswith("keine der"):
        return "Keine der verfügbaren Klassen"
    return "?" + str(v)


def expected_status(gt, alt, pred):
    p = canon(pred)
    if p is None:
        return "EXCLUDED"
    allowed = {canon(gt)} | {canon(a) for a in str(alt or "").split(",") if a.strip()}
    return "CORRECT" if p in allowed else "INCORRECT"


def stamp(name):
    m = re.search(r"(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})", name)
    return m.group(1) if m else name


def header_map(ws):
    return {str(c.value).strip(): c.column for c in ws[1] if c.value is not None}


def find(hm, *parts, exact=None):
    if exact and exact in hm:
        return exact
    for h in hm:
        if all(p.lower() in h.lower() for p in parts):
            return h
    return None


def style_for_status(ws, col, status):
    """Formatierung einer vorhandenen Zelle mit gleichem Status übernehmen (z. B. grüne/rote Füllung)."""
    for r in range(2, ws.max_row + 1):
        c = ws.cell(row=r, column=col)
        if str(c.value or "").strip().upper() == status:
            return c
    return None


def needs_fill(ws, r, ho):
    """Zeile ohne gültige Vorhersage: EXCLUDED, leer, [EMPTY], nicht zuordenbar oder Processing-Fehler."""
    stat_h, pred_h, proc_h = find(ho, "allowed"), find(ho, "predicted"), find(ho, "processing")
    st = str(ws.cell(row=r, column=ho[stat_h]).value or "").strip().upper() if stat_h else ""
    pred = ws.cell(row=r, column=ho[pred_h]).value if pred_h else None
    proc = str(ws.cell(row=r, column=ho[proc_h]).value or "").lower() if proc_h else ""
    if st == "EXCLUDED" or "error" in proc or empty(pred) or str(pred).strip().upper() == "[EMPTY]":
        return True
    return str(canon(pred)).startswith("?")


def sap_rows(ws, ho):
    sap_h = find(ho, "sap")
    rows = {}
    for r in range(2, ws.max_row + 1):
        v = ws.cell(row=r, column=ho[sap_h]).value
        if not empty(v):
            rows.setdefault(str(v).strip(), r)
    return rows


def merge_pair(orig, nach, out, log, dry, overwrite=False):
    wo = load_workbook(orig)
    wn = load_workbook(nach, read_only=True, data_only=True)
    so, sn = wo[SHEET_NAME], wn[SHEET_NAME]
    ho, hn = header_map(so), {str(c.value).strip(): i for i, c in enumerate(next(sn.iter_rows(min_row=1, max_row=1)))
                              if c.value is not None}

    sap_o, sap_n = find(ho, "sap"), find(hn, "sap")
    gt_h = find(ho, exact="Ground Truth")
    alt_h, pred_h = find(ho, "weitere"), find(ho, "predicted")
    stat_h = find(ho, "allowed")
    if not (sap_o and sap_n and gt_h and pred_h and stat_h):
        raise ValueError(f"Spalten fehlen in {orig.name} oder {nach.name}")

    rows_o = sap_rows(so, ho)

    common = [h for h in hn if h in ho and h not in (sap_o, stat_h)]
    stat_n = find(hn, "allowed")
    changed = 0
    for row in sn.iter_rows(min_row=2, values_only=True):
        sap = row[hn[sap_n]]
        if empty(sap):
            continue
        sap = str(sap).strip()
        base = dict(Original=orig.name, Nachlauf=nach.name, SAP=sap)
        note = []
        if sap not in rows_o:
            # Zeile fehlte im Original: am Ende anhängen (SAP und alle gemeinsamen Spalten)
            r = so.max_row + 1
            so.cell(row=r, column=ho[sap_o]).value = row[hn[sap_n]]
            rows_o[sap] = r
            old_status = "fehlte"
            note.append("Zeile fehlte im Original – ergänzt")
        else:
            r = rows_o[sap]
            old_status = str(so.cell(row=r, column=ho[stat_h]).value or "").strip().upper()
            if not overwrite and not needs_fill(so, r, ho):
                log.append({**base, "Excel-Zeile": r, "Vorher": old_status, "Aktion": "nicht ersetzt (Original gültig)"})
                continue
            if overwrite and not needs_fill(so, r, ho):
                note.append(f"Original war gültig ({old_status}) – überschrieben (--ueberschreiben)")

        new = {h: row[hn[h]] for h in common}
        for h in (gt_h, alt_h):
            if old_status != "fehlte" and h and h in new and _norm(so.cell(row=r, column=ho[h]).value or "") != _norm(new[h] or ""):
                note.append(f"{h} geändert: '{so.cell(row=r, column=ho[h]).value or ''}' → '{new[h] or ''}'")

        gt = new.get(gt_h, so.cell(row=r, column=ho[gt_h]).value)
        alt = new.get(alt_h, so.cell(row=r, column=ho[alt_h]).value if alt_h else "")
        pred = new.get(pred_h)
        status = expected_status(gt, alt, pred)
        if str(pred or "").strip() and str(canon(pred)).startswith("?"):
            note.append(f"Vorhersage nicht zuordenbar: {pred}")
        if stat_n is not None:
            manual = str(row[hn[stat_n]] or "").strip().upper()
            if manual and manual != status:
                note.append(f"Manueller Status {manual} ≠ berechnet {status} – berechneter Wert verwendet")

        for h, v in new.items():
            so.cell(row=r, column=ho[h]).value = v
        sc = so.cell(row=r, column=ho[stat_h])
        sc.value = status
        ref = style_for_status(so, ho[stat_h], status)
        if ref is not None and ref.row != r:
            sc._style = copy.copy(ref._style)
        changed += 1
        log.append({**base, "Excel-Zeile": r, "Vorher": old_status or "leer", "Aktion": "ersetzt",
                    "Predicted_Label neu": pred, "Status neu": status, "Hinweis": "; ".join(note)})

    if not dry:
        wo.save(out)
    wn.close()
    return changed


def nach_saps(path):
    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb[SHEET_NAME]
    head = [str(c.value).strip() if c.value is not None else "" for c in next(ws.iter_rows(min_row=1, max_row=1))]
    hm = {h: i for i, h in enumerate(head) if h}
    sh = find(hm, "sap")
    saps = {str(r[hm[sh]]).strip() for r in ws.iter_rows(min_row=2, values_only=True) if not empty(r[hm[sh]])}
    wb.close()
    return saps


def missing_in(orig, saps):
    """Baugruppen aus `saps`, die im Original fehlen oder keine gültige Vorhersage haben."""
    wb = load_workbook(orig, read_only=False, data_only=True)
    ws = wb[SHEET_NAME]
    ho = header_map(ws)
    rows = sap_rows(ws, ho)
    out = sorted(s for s in saps if s not in rows or needs_fill(ws, rows[s], ho))
    wb.close()
    return out


def process(folder, dry, overwrite=False):
    files = [f for f in folder.glob("*.xlsx") if not f.name.startswith("~$")]
    nach = sorted([f for f in files if f.name.lower().startswith(NACHLAUF_PREFIX)], key=lambda f: stamp(f.name))
    orig = sorted([f for f in files if not f.name.lower().startswith(NACHLAUF_PREFIX)], key=lambda f: stamp(f.name))
    if not nach:
        return None
    print(f"\n{folder.name}: {len(orig)} Originale, {len(nach)} Nachlauf-Dateien")

    if overwrite:
        # altes Verhalten: alle Originale der Reihe nach mit allen Nachlauf-Dateien paaren
        if len(orig) != len(nach):
            print("  ABBRUCH: Anzahl Originale und Nachlauf-Dateien unterschiedlich.")
            return False
        pairs = list(zip(orig, nach))
    else:
        # nur unvollständige Originale ergänzen; je unvollständigem Lauf eine eigene Nachlauf-Datei
        saps = set().union(*(nach_saps(n) for n in nach))
        need = [(o, missing_in(o, saps)) for o in orig]
        incomplete = [(o, m) for o, m in need if m]
        for o, m in incomplete:
            print(f"  unvollständig: {o.name[-40:]}  ({len(m)}: {', '.join(m)})")
        if len(nach) < len(incomplete):
            print(f"  ABBRUCH: {len(incomplete)} unvollständige Läufe, aber nur {len(nach)} Nachlauf-Dateien. "
                  f"Die Nachlauf-Eingabe bitte {len(incomplete)}-mal laufen lassen.")
            return False
        if len(nach) > len(incomplete):
            print(f"  Hinweis: {len(nach) - len(incomplete)} Nachlauf-Datei(en) werden nicht benötigt.")
        pairs = [(o, n) for (o, _), n in zip(incomplete, nach)]
        if not pairs:
            print("  Alle Originale vollständig – nichts zu tun.")
            return True

    backup = folder / BACKUP_DIR
    if not dry:
        if backup.exists():
            print(f"  ABBRUCH: {backup} existiert bereits (Merge schon ausgeführt?).")
            return False
        backup.mkdir()
        for f in orig + nach:
            shutil.move(str(f), backup / f.name)
        paired = {o for o, _ in pairs}
        for o in orig:  # nicht betroffene Originale unverändert zurückkopieren
            if o not in paired:
                shutil.copy2(backup / o.name, folder / o.name)

    log = []
    for i, (o, n) in enumerate(pairs, 1):
        src_o = o if dry else backup / o.name
        src_n = n if dry else backup / n.name
        k = merge_pair(src_o, src_n, folder / o.name, log, dry, overwrite)
        print(f"  {o.name[-30:]} ← {n.name[-30:]}  ({k} Zeilen ersetzt/ergänzt)")

    df = pd.DataFrame(log)
    flagged = df[df["Hinweis"].fillna("") != ""] if "Hinweis" in df else df.iloc[0:0]
    for _, r in flagged.iterrows():
        print(f"  Hinweis {r['SAP']}: {r['Hinweis']}")
    if not dry:
        df.to_excel(backup / "merge_protokoll.xlsx", index=False)
        print(f"  Fertig. Backup und Protokoll: {backup}")
    else:
        print("  Dry-Run: nichts geschrieben.")
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ordner", nargs="*")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--ueberschreiben", action="store_true",
                    help="altes Verhalten: alle Originale mit allen Nachlauf-Dateien paaren und auch gültige Zeilen ersetzen")
    a = ap.parse_args()
    if a.ordner:
        folders = [Path(x) for x in a.ordner]
    else:
        base = Path(__file__).resolve().parent
        folders = [d for d in sorted(base.iterdir()) if d.is_dir() and d.name != BACKUP_DIR]
    results = [process(f, a.dry_run, a.ueberschreiben) for f in folders]
    if not any(r is not None for r in results):
        sys.exit("Keine Ordner mit Nachlauf-Dateien gefunden.")


if __name__ == "__main__":
    main()
