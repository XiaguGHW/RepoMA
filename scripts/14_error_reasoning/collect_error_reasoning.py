#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
collect_error_reasoning.py

Sammelt für die Fehleranalyse (Abschnitt 5.7) die Reasoning-Texte der falschen
Läufe der vier finalen Konfigurationen in eine Datei (offline, keine Modellaufrufe).

Nutzt Ordnererkennung, finale GT und Labelnormalisierung aus
evaluate_validation_regimes.py (Skript 12). Diese Datei muss im selben Ordner
liegen wie dieses Skript oder in ../12_validation_regimes.

Falsch = Vorhersage nicht in der zulässigen Labelmenge der finalen GT.

Aufruf (PowerShell, im Ordner test_claude):
  python collect_error_reasoning.py --main . --supp ..\\70BG_Ergebnisse
  python collect_error_reasoning.py --main . --supp ..\\70BG_Ergebnisse --alle   # alle fehlerhaften BG

Ausgabe:
  Fehler_Reasoning.xlsx  Blatt "Zu_pruefen": je Baugruppe und Konfiguration ein Beispiel-Lauf
                                (häufigste falsche Vorhersage, kleinste Laufnummer) mit Reasoning,
                                leere Spalten "Kategorie" und "Notiz" zum Ausfüllen;
                         Blatt "Alle_Fehllaeufe": jeder falsche Lauf mit Reasoning.
  Fehler_Reasoning.md    Inhalt von "Zu_pruefen" als Text (zum Weitergeben).
"""

import argparse
import importlib.util
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
for cand in (HERE / "evaluate_validation_regimes.py",
             HERE.parent / "12_validation_regimes" / "evaluate_validation_regimes.py"):
    if cand.exists():
        spec = importlib.util.spec_from_file_location("s12", cand)
        s12 = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(s12)
        break
else:
    sys.exit("evaluate_validation_regimes.py (Skript 12) nicht gefunden – bitte in denselben Ordner legen.")

# Zu prüfende Baugruppen (Stand 2026-11-11, thesis/error_cause_mapping.md)
ZU_PRUEFEN = [
    # neu, Primärdatensatz
    "0804FZ8322", "0804GV7647", "0804LG6553", "0804KT1289", "0804LK3617", "3843CE1617",
    # neu, Ergänzungsdatensatz
    "0804BN2123", "0804EM7937", "0804JW4969", "0804KF8538", "0804LD6387", "0804LM7661",
    "0804LS4641", "0804LW5713",
    # Stichprobe (anderes Fehlerbild als in der bisherigen Analyse)
    "0804DN9616", "0804FT6844", "0804HX0679",
]
GRUPPE = {s: "neu (115)" for s in ZU_PRUEFEN[:6]}
GRUPPE.update({s: "neu (70)" for s in ZU_PRUEFEN[6:14]})
GRUPPE.update({s: "Stichprobe" for s in ZU_PRUEFEN[14:]})


def key(s):
    return str(s).strip().lstrip("0")


def read_runs(path, cfg, source, run):
    xl = pd.ExcelFile(path)
    sheet = "Sheet1" if "Sheet1" in xl.sheet_names else xl.sheet_names[0]
    df = pd.read_excel(path, sheet_name=sheet, dtype=str)
    cols = list(df.columns)
    c_sap = s12.find_col(cols, contains=["sap"])
    c_pred = s12.find_col(cols, contains=["predicted"])
    c_rea = s12.find_col(cols, exact="Reasoning") or s12.find_col(cols, contains=["reasoning"])
    c_name = s12.find_col(cols, contains=["benennung", "(e)"]) or s12.find_col(cols, contains=["benennung"])
    if not (c_sap and c_pred):
        sys.exit(f"Spalten SAP/Predicted nicht gefunden in {path.name}: {cols}")
    if c_rea is None:
        print(f"WARNUNG: keine Reasoning-Spalte in {path.name}")
    final = {key(k): (k, v) for k, v in s12.FINAL_GT.items()}
    out = []
    for _, row in df.iterrows():
        if s12.is_empty(row[c_sap]) or key(row[c_sap]) not in final:
            continue
        sap, (gt, _reg, alts) = final[key(row[c_sap])]
        gt = s12.canon(gt)
        allowed = {gt} | {s12.canon(a) for a in alts}
        pred = s12.canon(row[c_pred])
        if pred is None or pred in allowed:
            continue
        out.append(dict(Datensatz=source, SAP=sap,
                        Benennung="" if c_name is None or s12.is_empty(row[c_name]) else str(row[c_name]).strip(),
                        GT=gt, Weitere_zulaessige=", ".join(sorted(a for a in allowed if a != gt)) or "—",
                        Konfiguration=cfg, Lauf=run, Datei=path.name, Vorhersage=pred,
                        Reasoning="" if c_rea is None or s12.is_empty(row[c_rea]) else str(row[c_rea]).strip()))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--main", required=True, help="Ordner mit den 10-Lauf-Ordnern (115 BG)")
    ap.add_argument("--supp", required=True, help="Ordner mit den Ergebnisdateien der 70 BG")
    ap.add_argument("--alle", action="store_true", help="alle fehlerhaften Baugruppen statt der Prüfliste")
    ap.add_argument("--out", default="Fehler_Reasoning.xlsx")
    a = ap.parse_args()
    main_dir, supp_dir = Path(a.main), Path(a.supp)

    rows, n_runs = [], {}
    for cfg, k in s12.CONFIGS:
        folders = [d for d in main_dir.iterdir() if d.is_dir() and k in d.name.lower()]
        folders = [d for d in folders if "flash" not in d.name.lower() or k == "deepseek"]
        if len(folders) != 1:
            sys.exit(f"115 BG: für '{cfg}' {len(folders)} Ordner gefunden: {[d.name for d in folders]}")
        files = sorted(s12.list_xlsx(folders[0]), key=s12.run_key)
        n_runs[(cfg, "115")] = len(files)
        for r, f in enumerate(files, 1):
            rows += read_runs(f, cfg, "115", r)
        sfiles = [f for f in s12.list_xlsx(supp_dir) if k in f.name.lower()]
        sfiles = [f for f in sfiles if "flash" not in f.name.lower() or k == "deepseek"]
        if len(sfiles) != 1:
            sys.exit(f"70 BG: für '{cfg}' {len(sfiles)} Dateien gefunden: {[f.name for f in sfiles]}")
        n_runs[(cfg, "70")] = 1
        rows += read_runs(sfiles[0], cfg, "70", 1)

    alle = pd.DataFrame(rows)
    if alle.empty:
        sys.exit("Keine falschen Läufe gefunden.")
    if not a.alle:
        ziel = {key(s) for s in ZU_PRUEFEN}
        alle = alle[alle.SAP.map(key).isin(ziel)]
        fehlt = [s for s in ZU_PRUEFEN if key(s) not in set(alle.SAP.map(key))]
        if fehlt:
            print("WARNUNG: kein falscher Lauf gefunden für:", ", ".join(fehlt))
    order = {key(s): i for i, s in enumerate(ZU_PRUEFEN)}
    cfg_order = {c: i for i, (c, _) in enumerate(s12.CONFIGS)}
    alle = alle.assign(_o=alle.SAP.map(lambda s: order.get(key(s), 999)),
                       _c=alle.Konfiguration.map(cfg_order)).sort_values(["_o", "Datensatz", "SAP", "_c", "Lauf"])

    zp = []
    for (sap, cfg), g in alle.groupby(["SAP", "Konfiguration"], sort=False):
        haeufig = g.Vorhersage.value_counts()
        bsp = g[g.Vorhersage == haeufig.index[0]].iloc[0]
        n = n_runs[(cfg, bsp.Datensatz)]
        zp.append({"Gruppe": GRUPPE.get(sap, "alle" if a.alle else ""), "Datensatz": bsp.Datensatz, "SAP": sap,
                   "Benennung": bsp.Benennung, "GT": bsp.GT, "Weitere zulässige": bsp.Weitere_zulaessige,
                   "Konfiguration": cfg, "Falsche Läufe": f"{len(g)}/{n}",
                   "Vorhersagen": ", ".join(f"{p} ×{c}" for p, c in haeufig.items()),
                   "Beispiel-Lauf": int(bsp.Lauf), "Datei": bsp.Datei, "Vorhersage (Beispiel)": bsp.Vorhersage,
                   "Reasoning (Beispiel)": bsp.Reasoning,
                   "Unterschiedliche Reasonings": g.Reasoning.nunique(), "Kategorie": "", "Notiz": ""})
    zp = pd.DataFrame(zp)
    alle = alle.drop(columns=["_o", "_c"])

    with pd.ExcelWriter(a.out, engine="openpyxl") as xw:
        zp.to_excel(xw, sheet_name="Zu_pruefen", index=False)
        alle.to_excel(xw, sheet_name="Alle_Fehllaeufe", index=False)
        for ws in xw.book.worksheets:
            for col in ws.columns:
                head = str(col[0].value)
                ws.column_dimensions[col[0].column_letter].width = 90 if "Reasoning" in head else 22
            ws.freeze_panes = "A2"

    md = ["# Reasoning der falschen Läufe (finale Konfigurationen)", ""]
    for r in zp.itertuples(index=False):
        md += [f"## {r.SAP} ({r.Benennung}) – {r[6]}",
               f"Datensatz {r.Datensatz} | GT: {r.GT} | weitere zulässige: {r[5]} | "
               f"falsch: {r[7]} ({r.Vorhersagen}) | Beispiel: Lauf {r[9]}, Vorhersage {r[11]}",
               "", r[12] or "[kein Reasoning]", ""]
    Path(a.out).with_suffix(".md").write_text("\n".join(md), encoding="utf-8")
    print(f"{zp.SAP.nunique()} Baugruppen, {len(zp)} Baugruppe×Konfiguration, {len(alle)} falsche Läufe.")
    print(f"Ausgabe: {Path(a.out).resolve()} und {Path(a.out).with_suffix('.md').name}")


if __name__ == "__main__":
    main()
