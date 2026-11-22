#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
merge_nachlauf.py

Führt Nachlauf-Dateien (erneut ausgeführte, zuvor EXCLUDED Baugruppen) mit den
ursprünglichen Lauf-Dateien zusammen, sodass wieder 10 vollständige Lauf-Dateien entstehen.

Zuordnung (Standard): Ergänzt werden nur Lücken, d. h. Baugruppen der Nachlauf-Dateien, die in einem
Original fehlen oder keine gültige Vorhersage haben (EXCLUDED, leer, [EMPTY], nicht zuordenbar,
Processing-Fehler). Jede Lücke erhält ein eigenes Nachlauf-Ergebnis: Die k-te Lücke einer Baugruppe
(Originale nach Zeitstempel) wird aus der k-ten Nachlauf-Datei mit dieser Baugruppe gefüllt.
Fehlt jede Baugruppe nur in einem Lauf, genügt ein einziger Nachlauf je Modell. Gültige Zeilen
bleiben unverändert, fehlende Zeilen werden angehängt. Nicht füllbare Lücken werden gemeldet
(--wiederverwenden setzt dann dasselbe Ergebnis mehrfach ein, nicht empfohlen).
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
    rea_h = find(ho, "reasoning")
    st = str(ws.cell(row=r, column=ho[stat_h]).value or "").strip().upper() if stat_h else ""
    pred = ws.cell(row=r, column=ho[pred_h]).value if pred_h else None
    proc = str(ws.cell(row=r, column=ho[proc_h]).value or "").lower() if proc_h else ""
    rea = str(ws.cell(row=r, column=ho[rea_h]).value or "").strip() if rea_h else ""
    if st == "EXCLUDED" or empty(pred) or str(pred).strip().upper() == "[EMPTY]":
        return True
    if str(canon(pred)).startswith("?"):
        return True
    # Fehlermeldung, aber gültige Vorhersage mit Begründung (erfolgreicher Wiederholungsversuch): gilt als vorhanden
    if "error" in proc and not (len(rea) > 20 and "error" not in rea.lower()[:40]):
        return True
    return False


def ident(sap, tc):
    """Baugruppen-Kennung: SAP-Nummer, ersatzweise Teamcenter (3 BG des Ergänzungsdatensatzes ohne SAP)."""
    def n(x):
        return re.sub(r"[^0-9A-Z]", "", str(x).upper()).lstrip("0")
    if not empty(sap) and n(sap):
        return "SAP:" + n(sap)
    if not empty(tc) and n(tc):
        return "TC:" + n(tc)
    return None


def sap_rows(ws, ho):
    sap_h, tc_h = find(ho, "sap"), find(ho, "teamcenter")
    rows = {}
    for r in range(2, ws.max_row + 1):
        k = ident(ws.cell(row=r, column=ho[sap_h]).value,
                  ws.cell(row=r, column=ho[tc_h]).value if tc_h else None)
        if k:
            rows.setdefault(k, r)
    return rows


def merge_pair(orig, nach, out, log, dry, overwrite=False, only=None, wo=None, save=True):
    """Nachlauf-Zeilen in das Original übernehmen. only: nur diese SAP-Nummern; wo: bereits geöffnetes Original."""
    wo = wo if wo is not None else load_workbook(orig)
    wn = load_workbook(nach, read_only=True, data_only=True)
    so, sn = wo[SHEET_NAME], wn[SHEET_NAME]
    ho, hn = header_map(so), {str(c.value).strip(): i for i, c in enumerate(next(sn.iter_rows(min_row=1, max_row=1)))
                              if c.value is not None}

    sap_o, sap_n = find(ho, "sap"), find(hn, "sap")
    tc_o, tc_n = find(ho, "teamcenter"), find(hn, "teamcenter")
    gt_h = find(ho, exact="Ground Truth")
    alt_h, pred_h = find(ho, "weitere"), find(ho, "predicted")
    stat_h = find(ho, "allowed")  # optional (z. B. fehlt in den 70BG-Dateien)
    if not (sap_o and sap_n and gt_h and pred_h):
        raise ValueError(f"Spalten fehlen in {orig.name} oder {nach.name}")

    rows_o = sap_rows(so, ho)

    # prompt_engineering NICHT übernehmen: im Nachlauf steht dort "yes" (Auswahl der Zeilen),
    # in den Ergebnisdateien kennzeichnet "yes" aber Vorversuchs-Baugruppen, die ausgeschlossen werden.
    skip = {sap_o, stat_h} | {h for h in ho if "prompt" in h.lower() and "engineer" in h.lower()}
    common = [h for h in hn if h in ho and h not in skip]
    stat_n = find(hn, "allowed")
    changed = 0
    for row in sn.iter_rows(min_row=2, values_only=True):
        sap_v = row[hn[sap_n]]
        tc_v = row[hn[tc_n]] if tc_n else None
        sap = ident(sap_v, tc_v)
        if sap is None:
            continue
        if only is not None and sap not in only:
            continue
        base = dict(Original=orig.name, Nachlauf=nach.name, SAP=str(sap_v or tc_v).strip())
        note = []
        if sap not in rows_o:
            # Zeile fehlte im Original: am Ende anhängen (SAP und alle gemeinsamen Spalten)
            r = so.max_row + 1
            so.cell(row=r, column=ho[sap_o]).value = sap_v
            if sap in GT_LOOKUP:  # GT-Stand der übrigen Läufe bzw. der Referenz, nicht der Nachlauf-Eingabe
                for h, v in GT_LOOKUP[sap].items():
                    if h in ho:
                        so.cell(row=r, column=ho[h]).value = v
                gt_from_lookup = True
            else:
                gt_from_lookup = False
            rows_o[sap] = r
            old_status = "fehlte"
            note.append("Zeile fehlte im Original – ergänzt")
        else:
            gt_from_lookup = False
            r = rows_o[sap]
            old_status = str(so.cell(row=r, column=ho[stat_h]).value or "").strip().upper() if stat_h else ""
            if not overwrite and not needs_fill(so, r, ho):
                log.append({**base, "Excel-Zeile": r, "Vorher": old_status, "Aktion": "nicht ersetzt (Original gültig)"})
                continue
            if overwrite and not needs_fill(so, r, ho):
                note.append(f"Original war gültig ({old_status}) – überschrieben (--ueberschreiben)")

        new = {h: row[hn[h]] for h in common}
        # GT-Spalten (Ground Truth, Register, weitere zulässige) des Originals behalten: Die Nachlauf-Eingabe
        # kann einen anderen GT-Stand haben; eine Datei soll nicht zeilenweise gemischte GT-Stände enthalten.
        # Nur bei angehängten (vorher fehlenden) Zeilen werden sie aus dem Nachlauf übernommen.
        reg_h = find(ho, exact="Register") or find(ho, "regist")
        if old_status == "fehlte" and not gt_from_lookup:
            note.append("GT-Spalten aus der Nachlauf-Eingabe übernommen (BG in keinem Lauf/keiner Referenz) – bitte prüfen")
        if old_status != "fehlte" or gt_from_lookup:
            for h in (gt_h, alt_h, reg_h):
                if h and h in new:
                    if old_status != "fehlte" and _norm(so.cell(row=r, column=ho[h]).value or "") != _norm(new[h] or ""):
                        note.append(f"{h}: Nachlauf-Eingabe hat anderen GT-Stand "
                                    f"('{new[h] or ''}' statt '{so.cell(row=r, column=ho[h]).value or ''}') – Original beibehalten")
                    del new[h]

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
        if stat_h:
            sc = so.cell(row=r, column=ho[stat_h])
            sc.value = status
            ref = style_for_status(so, ho[stat_h], status)
            if ref is not None and ref.row != r:
                sc._style = copy.copy(ref._style)
        changed += 1
        log.append({**base, "Excel-Zeile": r, "Vorher": old_status or "leer", "Aktion": "ersetzt",
                    "Predicted_Label neu": pred, "Status neu": status, "Hinweis": "; ".join(note)})

    if save and not dry:
        wo.save(out)
    wn.close()
    return changed


def nach_saps(path, with_empty=False):
    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb[SHEET_NAME]
    head = [str(c.value).strip() if c.value is not None else "" for c in next(ws.iter_rows(min_row=1, max_row=1))]
    hm = {h: i for i, h in enumerate(head) if h}
    sh, th, ph = find(hm, "sap"), find(hm, "teamcenter"), find(hm, "predicted")
    saps, leer = set(), set()
    for r in ws.iter_rows(min_row=2, values_only=True):
        k = ident(r[hm[sh]], r[hm[th]] if th else None)
        if not k:
            continue
        pred = r[hm[ph]] if ph else None
        # nur gültige Nachlauf-Ergebnisse verwenden; leere/ungültige bleiben Lücken
        if empty(pred) or str(pred).strip().upper() == "[EMPTY]" or str(canon(pred)).startswith("?"):
            leer.add(k)
        else:
            saps.add(k)
    wb.close()
    if leer:
        print(f"  ! {path.name[-40:]}: {len(leer)} Baugruppe(n) wieder ohne gültiges Ergebnis "
              f"(werden nicht eingesetzt): {', '.join(sorted(leer))}")
    return (saps, leer) if with_empty else saps


REF_PATH = None
GT_LOOKUP = {}  # Baugruppe -> {"Ground Truth": ..., "Register": ..., "Weitere ...": ...} aus Originalen/Referenz


def add_gt_lookup(path):
    """GT-Spalten einer vollständigen Datei (Original oder Referenz) für angehängte Zeilen merken."""
    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb[SHEET_NAME]
    head = [str(c.value).strip() if c.value is not None else "" for c in next(ws.iter_rows(min_row=1, max_row=1))]
    hm = {h: i for i, h in enumerate(head) if h}
    sh, th = find(hm, "sap"), find(hm, "teamcenter")
    cols = [h for h in (find(hm, exact="Ground Truth"), find(hm, exact="Register") or find(hm, "regist"),
                        find(hm, "weitere")) if h]
    for r in ws.iter_rows(min_row=2, values_only=True):
        k = ident(r[hm[sh]], r[hm[th]] if th else None)
        if k and k not in GT_LOOKUP:
            GT_LOOKUP[k] = {h: r[hm[h]] for h in cols}
    wb.close()


def original_ids(path):
    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb[SHEET_NAME]
    head = [str(c.value).strip() if c.value is not None else "" for c in next(ws.iter_rows(min_row=1, max_row=1))]
    hm = {h: i for i, h in enumerate(head) if h}
    sh, th = find(hm, "sap"), find(hm, "teamcenter")
    ids = {ident(r[hm[sh]], r[hm[th]] if th else None) for r in ws.iter_rows(min_row=2, values_only=True)}
    wb.close()
    return {x for x in ids if x}


def missing_in(orig, saps):
    """Baugruppen aus `saps`, die im Original fehlen oder keine gültige Vorhersage haben."""
    wb = load_workbook(orig, read_only=False, data_only=True)
    ws = wb[SHEET_NAME]
    ho = header_map(ws)
    rows = sap_rows(ws, ho)
    out = sorted(s for s in saps if s not in rows or needs_fill(ws, rows[s], ho))
    wb.close()
    return out


MODEL_KEYS = [("deepseek", "deepseek"), ("haiku", "haiku"), ("opus", "opus"), ("gemini-2.5-pro", "gemini-pro"),
              ("gemini-2.5-flash", "gemini-flash"), ("gpt", "gpt")]


def config_tokens(name):
    t = re.sub(r"[\s_]+", "-", name.lower())
    model = next((v for k, v in MODEL_KEYS if k in t), None)
    pr = re.findall(r"(?<![a-z0-9])p([1-4])(?![0-9])", t)
    prompt = f"P{pr[0]}" if len(set(pr)) == 1 else None
    inp = next((lab for key, lab in (("pdf", "pdf"), ("image", "image"), ("bild", "image"), ("text", "text"))
                if re.search(rf"(?<![a-z]){key}(?![a-z])", t)), None)
    return model, prompt, inp


def check_config(folder, orig, nach):
    """Abbruch, wenn eine Nachlauf-Datei erkennbar zu einem anderen Modell/Prompt/Eingabe gehört."""
    ref = [config_tokens(folder.name)] + [config_tokens(o.name) for o in orig]
    want = tuple(next((t[i] for t in ref if t[i]), None) for i in range(3))
    bad = []
    for n in nach:
        got = config_tokens(n.name)
        for i, what in enumerate(("Modell", "Prompt", "Eingabe")):
            if want[i] and got[i] and want[i] != got[i]:
                bad.append(f"{n.name}: {what} {got[i]} ≠ {want[i]}")
    return bad


def plan_group(orig, nach, reuse, ref_ids):
    """Jede Lücke (Lauf, Baugruppe) bekommt ein eigenes Nachlauf-Ergebnis: die k-te Lücke einer
    Baugruppe wird aus der k-ten Nachlauf-Datei gefüllt, die diese Baugruppe enthält."""
    both = {n: nach_saps(n, with_empty=True) for n in nach}
    nsaps = {n: v for n, (v, _) in both.items()}          # gültige Ergebnisse je Nachlauf-Datei
    saps = set().union(*(v | e for v, e in both.values()))  # alle nachgelaufenen BG (für die Lückensuche)
    # Schutz: nur Baugruppen dieses Experiments (in einem Original oder in der Referenzdatei)
    known = set().union(*(set(original_ids(o)) for o in orig))
    if ref_ids:
        known |= ref_ids
    foreign = sorted(saps - known)
    if foreign:
        print(f"  ! {len(foreign)} Baugruppe(n) der Nachlauf-Dateien kommen in keinem Original vor und werden "
              f"nicht ergänzt: {', '.join(foreign)}" + ("" if ref_ids else
              " (fehlt eine BG in allen Läufen, --referenz <vollständige Datei> angeben)"))
    saps -= set(foreign)
    used, plan, unfilled = {}, {}, []
    for o in orig:
        for sp in missing_in(o, saps):
            srcs = [n for n in nach if sp in nsaps[n]]
            k = used.get(sp, 0)
            if k < len(srcs):
                plan.setdefault(o, []).append((srcs[k], sp))
                used[sp] = k + 1
            elif reuse and srcs:
                plan.setdefault(o, []).append((srcs[k % len(srcs)], sp))
                used[sp] = k + 1
                print(f"  ! {sp} in {o.name[-30:]}: Nachlauf-Ergebnis wiederverwendet (--wiederverwenden)")
            else:
                unfilled.append((o.name, sp))
    plan = {o: [(n, {sp for m, sp in items if m == n}) for n in dict.fromkeys(m for m, _ in items)]
            for o, items in plan.items()}
    for o, items in plan.items():
        print(f"  ergänzt: {o.name[-40:]}  ← " + "; ".join(f"{n.name[-26:]}: {', '.join(sorted(x))}" for n, x in items))
    if unfilled:
        need = {}
        for _, sp in unfilled:
            need[sp] = need.get(sp, 0) + 1
        print(f"  NICHT gefüllt ({len(unfilled)} Lücken, zu wenige Nachlauf-Ergebnisse):")
        for sp, c in sorted(need.items()):
            print(f"    {sp}: noch {c} Nachlauf(e) nötig")
    return plan


def process(folder, dry, overwrite=False, reuse=False, ref_ids=None):
    files = [f for f in folder.glob("*.xlsx") if not f.name.startswith("~$")]
    nach = sorted([f for f in files if f.name.lower().startswith(NACHLAUF_PREFIX)], key=lambda f: stamp(f.name))
    orig = sorted([f for f in files if not f.name.lower().startswith(NACHLAUF_PREFIX)], key=lambda f: stamp(f.name))
    if not nach:
        return None
    print(f"\n{folder.name}: {len(orig)} Originale, {len(nach)} Nachlauf-Dateien")
    # Konfigurationen im Ordner (Modell/Prompt/Eingabe aus den Dateinamen); ein Ordner mit mehreren
    # Konfigurationen (z. B. Prompt-Vergleich) wird je Konfiguration getrennt zusammengeführt.
    gtok = {o: config_tokens(o.name) for o in orig}
    groups = sorted(set(gtok.values()), key=str)
    if len(groups) <= 1:
        wrong = check_config(folder, orig, nach)
        if wrong:
            print("  ABBRUCH: Nachlauf-Datei passt nicht zu diesem Ordner:")
            for w in wrong:
                print("    " + w)
            return False
        assign = {groups[0] if groups else None: nach}
    else:
        if overwrite:
            print("  ABBRUCH: --ueberschreiben ist für Ordner mit mehreren Konfigurationen nicht möglich.")
            return False
        assign = {g: [] for g in groups}
        for n in nach:
            tn = config_tokens(n.name)
            cand = [g for g in groups if all(not (tn[i] and g[i] and tn[i] != g[i]) for i in range(3))]
            if len(cand) != 1:
                print(f"  ABBRUCH: {n.name} lässt sich keiner Konfiguration eindeutig zuordnen "
                      f"(erkannt: {tn}; im Ordner: {groups}).")
                return False
            assign[cand[0]].append(n)
        print("  Konfigurationen: " + "; ".join(f"{'/'.join(x or '?' for x in g)}: "
                                               f"{sum(1 for o in orig if gtok[o] == g)} Original(e), "
                                               f"{len(assign[g])} Nachlauf" for g in groups))

    if overwrite:
        # altes Verhalten: alle Originale der Reihe nach mit allen Nachlauf-Dateien paaren
        if len(orig) != len(nach):
            print("  ABBRUCH: Anzahl Originale und Nachlauf-Dateien unterschiedlich.")
            return False
        plan = {o: [(n, None)] for o, n in zip(orig, nach)}
    else:
        plan = {}
        for g, nach_g in assign.items():
            if not nach_g:
                continue
            orig_g = [o for o in orig if gtok[o] == g] if g is not None else orig
            plan.update(plan_group(orig_g, nach_g, reuse, ref_ids))
        if not plan:
            print("  Nichts zu ergänzen.")
            return True

    backup = folder / BACKUP_DIR
    i = 2
    while backup.exists():  # weiterer Merge (z. B. zweite Nachlauf-Runde): neuer Sicherungsordner
        backup = folder / f"{BACKUP_DIR}_{i}"
        i += 1
    if not dry:
        backup.mkdir()
        for f in orig + nach:
            shutil.move(str(f), backup / f.name)
        for o in orig:  # nicht betroffene Originale unverändert zurückkopieren
            if o not in plan:
                shutil.copy2(backup / o.name, folder / o.name)

    GT_LOOKUP.clear()
    for o in orig:  # GT-Stand der Originale dieses Ordners (vor Änderungen)
        add_gt_lookup(o if dry else backup / o.name)
    if REF_PATH:
        add_gt_lookup(REF_PATH)
    log = []
    for o, items in plan.items():
        src_o = o if dry else backup / o.name
        wo = load_workbook(src_o)
        k = 0
        for i, (n, only) in enumerate(items):
            src_n = n if dry else backup / n.name
            k += merge_pair(src_o, src_n, folder / o.name, log, dry, overwrite, only=only, wo=wo,
                            save=(i == len(items) - 1))
        print(f"  {o.name[-40:]}: {k} Zeilen ersetzt/ergänzt")

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
    ap.add_argument("--referenz", help="vollständige Ergebnisdatei (Sheet1): legt fest, welche Baugruppen zum Experiment gehören")
    ap.add_argument("--wiederverwenden", action="store_true",
                    help="Notlösung: fehlt eine Baugruppe in mehreren Läufen, dasselbe Nachlauf-Ergebnis mehrfach einsetzen")
    ap.add_argument("--ueberschreiben", action="store_true",
                    help="altes Verhalten: alle Originale mit allen Nachlauf-Dateien paaren und auch gültige Zeilen ersetzen")
    a = ap.parse_args()
    if a.ordner:
        folders = [Path(x) for x in a.ordner]
    else:
        base = Path(__file__).resolve().parent
        folders = [d for d in sorted(base.iterdir()) if d.is_dir() and not d.name.startswith(BACKUP_DIR)]
    global REF_PATH
    REF_PATH = Path(a.referenz) if a.referenz else None
    ref_ids = original_ids(REF_PATH) if a.referenz else None
    results = [process(f, a.dry_run, a.ueberschreiben, a.wiederverwenden, ref_ids) for f in folders]
    if not any(r is not None for r in results):
        sys.exit("Keine Ordner mit Nachlauf-Dateien gefunden.")


if __name__ == "__main__":
    main()
