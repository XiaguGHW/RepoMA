"""Hauptauswertung mit R1 als Ground Truth: Wiederholungsläufe (10 runs) auf 115 und 185 Baugruppen.

Struktur nach Absprache mit dem Betreuer (22.11.2026):
  - Allowed-Label-Set Accuracy (Mittel über die Läufe, Standardabweichung, 95%-Bootstrap-KI)
    für alle Baugruppen, nur eindeutige (keine weiteren zulässigen Labels) und nur mehrdeutige.
  - Macro-Precision, -Recall, -F1 nur auf den eindeutigen Baugruppen (Standardformeln, je Lauf, gemittelt;
    ohne Bootstrap). Dort ist das zulässige Set = {Primärlabel}, also Allowed = Strict.
  - Keine Trennung E1/E2 mehr. M ohne weiteres zulässiges Label zählt als eindeutig.

GT: R1 aus thesis/R1.md (Markdown-Tabelle) oder einer Excel-Datei mit den Spalten SAP-Nummer, Teamcenter,
Ground Truth, Register, Weitere zulässige Ground Truth (optional prompt_engineering). GT, Register und
zulässige Labels der Ergebnisdateien werden ignoriert. Prompt-Engineering-BG (14) sind ausgeschlossen.

Eingabe: --dir mit Konfigurationsordnern (z. B. gemini-2.5-flash_pdf_P3_10_runs, ..._70BG_10_runs).
Modell aus dem Ordnernamen; Hauptdatensatz (115) oder Ergänzung (70) wird aus den Baugruppen erkannt,
daher dürfen Ordner beliebig heißen. Läufe werden je Datensatz nach Dateiname (Zeitstempel) sortiert;
für 185 BG wird Lauf i (115) mit Lauf i (70) zusammengelegt.

Bootstrap: 2000 Wiederholungen, Baugruppen mit Zurücklegen, jede mit allen ihren Läufen
(Wert je BG = Anteil korrekter Läufe; bei 185 BG getrennt nach Datensatz gezogen).

Benötigt im selben Ordner: evaluate_pdf_results.py, evaluate_70bg_results.py, evaluate_prompt_results.py,
confusion_human_llm.py, evaluate_validation_regimes.py.

Aufruf (PowerShell):
    python evaluate_r1.py --dir "C:\\...\\stability" --gt "C:\\...\\R1.md" --out "C:\\...\\Ergebnis_R1"
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import evaluate_pdf_results as E  # noqa: E402
import evaluate_70bg_results as S  # noqa: E402

cm = E.cm
B, SEED = 2000, 42
MODEL_ORDER = ["Gemini 2.5 Pro", "Gemini 2.5 Flash", "Claude Haiku 4.5", "GPT-5.5", "DeepSeek-V4-Flash"]
SKIP_DIRS = {"backup_original", "__pycache__", "nachlauf"}


# ---------------------------------------------------------------- GT (R1)
def load_gt(path):
    path = Path(path)
    if path.suffix.lower() == ".md":
        rows = []
        head = None
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.startswith("|") or set(line.replace("|", "").strip()) <= set("-: "):
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if head is None and any("SAP" in c for c in cells):
                head = cells
                continue
            if head and len(cells) >= len(head) - 1:
                rows.append(dict(zip(head, cells + [""] * (len(head) - len(cells)))))
        df = pd.DataFrame(rows)
    else:
        df = pd.read_excel(path, dtype=str)
    cols = list(df.columns)
    c = dict(sap=E.find_col(cols, contains=["sap"]), tc=E.find_col(cols, contains=["teamcenter"]),
             gt=E.find_col(cols, exact="Ground Truth"), reg=E.find_col(cols, contains=["regist"]),
             alt=E.find_col(cols, contains=["weitere"]),
             pe=E.find_col(cols, contains=["prompt"]) or next((x for x in cols if "Prompt Engineering" in x), None))
    gt, pe, issues = {}, set(), []
    for _, r in df.iterrows():
        sap = r[c["sap"]] if c["sap"] else None
        tc = r[c["tc"]] if c["tc"] else None
        k = cm.match_key(sap if sap else None, tc if tc else None)
        if k is None:
            issues.append(f"GT-Zeile ohne Zuordnung: {sap} / {tc}")
            continue
        g = cm.canon(str(r[c["gt"]]).strip())
        alts = {cm.canon(a.strip()) for a in re.split(r"[,;\n|]", str(r[c["alt"]] or "")) if a.strip()} - {g}
        alts = {a for a in alts if a and not a.startswith("UNGÜLTIG")}
        gt[k] = (g, frozenset({g} | alts))
        if c["pe"] and str(r[c["pe"]]).strip().lower() == "yes":
            pe.add(k)
    return gt, pe, issues


# ---------------------------------------------------------------- Läufe einlesen
def collect(root, sheet, gt, pe, issues):
    """{Modell: {"main": [Lauf...], "supp": [Lauf...]}}; Lauf = {BG: (pred oder None)}."""
    main_keys = set(cm.MAIN_115)
    out, info = {}, []
    for d in sorted(p for p in Path(root).iterdir() if p.is_dir() and p.name.lower() not in SKIP_DIRS
                    and not p.name.lower().startswith("_backup_vor_merge")):
        files = sorted(f for f in d.rglob("*") if f.suffix.lower() in (".xlsx", ".xlsm")
                       and not E.is_output_or_backup(f))
        if not files:
            continue
        model = E.model_name(d)
        for f in files:
            recs = E.read_file(f, sheet, f"{model} | {d.name}", issues)
            run = {}
            for r in recs:
                k = r["SAP"]
                if k in pe or k not in gt:
                    if k not in gt and k not in pe:
                        issues.append(dict(Modell=model, Typ="BG nicht in R1", SAP=k))
                    continue
                run[k] = r["pred"] if r["pred"] is not None else ("UNGÜLTIG:" + r["pred_raw"])
            ds = "main" if len(set(run) & main_keys) >= len(run) / 2 else "supp"
            out.setdefault(model, {"main": [], "supp": []})[ds].append((f, run))
        info.append((model, d.name))
    return out, info


def correct(gt, k, pred):
    return pred is not None and not str(pred).startswith("UNGÜLTIG") and pred in gt[k][1]


# ---------------------------------------------------------------- Kennzahlen
def macro_prf(pairs):
    """Standard-Macro-P/R/F1 (eindeutige BG): P über vorhergesagte, R über GT-Klassen, F1 über beide."""
    K, IDX = len(cm.CLASSES), cm.IDX
    gtc, pc, tp = np.zeros(K), np.zeros(K), np.zeros(K)
    for g, p in pairs:
        gtc[IDX[g]] += 1
        if p in IDX:
            pc[IDX[p]] += 1
            if p == g:
                tp[IDX[p]] += 1
    with np.errstate(divide="ignore", invalid="ignore"):
        P = np.where(pc > 0, tp / pc, np.nan)
        R = np.where(gtc > 0, tp / gtc, np.nan)
        F = np.where(gtc + pc > 0, 2 * tp / (gtc + pc), np.nan)
    return float(np.nanmean(P)), float(np.nanmean(R)), float(np.nanmean(F))


def subset_keys(gt, keys, which):
    if which == "alle":
        return list(keys)
    amb = which == "mehrdeutig"
    return [k for k in keys if (len(gt[k][1]) > 1) == amb]


def evaluate(gt, runs_main, runs_supp, scope, rng):
    """scope: '115' oder '185'. Rückgabe: dict je Teilmenge."""
    if scope == "115":
        runs = [r for _, r in runs_main]
        strata = [set(cm.MAIN_115) - set()]
    else:
        n = min(len(runs_main), len(runs_supp))
        runs = [{**runs_main[i][1], **runs_supp[i][1]} for i in range(n)]
        strata = [set(cm.MAIN_115), None]  # None = Ergänzung (alle übrigen)
    if not runs:
        return None
    allkeys = sorted(set().union(*runs))
    res = {}
    for which in ("alle", "eindeutig", "mehrdeutig"):
        keys = subset_keys(gt, allkeys, which)
        # je Lauf: Accuracy über die in diesem Lauf gültig vorhandenen BG
        accs = []
        for run in runs:
            ks = [k for k in keys if k in run]
            if ks:
                accs.append(np.mean([correct(gt, k, run[k]) for k in ks]))
        # je BG: Anteil korrekter Läufe (für Bootstrap)
        share = {k: np.mean([correct(gt, k, run[k]) for run in runs if k in run]) for k in keys
                 if any(k in run for run in runs)}
        # Bootstrap (bei 185 je Datensatz getrennt gezogen)
        if scope == "185":
            groups = [[k for k in share if k in strata[0]], [k for k in share if k not in strata[0]]]
        else:
            groups = [list(share)]
        groups = [np.array([share[k] for k in g]) for g in groups if g]
        boots = np.empty(B)
        for b in range(B):
            draws = [g[rng.integers(0, len(g), len(g))] for g in groups]
            boots[b] = np.concatenate(draws).mean()
        row = dict(n=len(share), runs=len(runs), acc=float(np.mean(accs)) if accs else np.nan,
                   sd=float(np.std(accs, ddof=1) * 100) if len(accs) > 1 else np.nan,
                   ci_lo=float(np.percentile(boots, 2.5)), ci_hi=float(np.percentile(boots, 97.5)),
                   acc_bg=float(np.mean(list(share.values()))))
        if which == "eindeutig":
            prf = []
            for run in runs:
                pairs = [(gt[k][0], run[k]) for k in keys if k in run]
                prf.append(macro_prf(pairs))
            row["prec"], row["rec"], row["f1"] = (float(np.mean([x[i] for x in prf])) for i in range(3))
        res[which] = row
    return res


# ---------------------------------------------------------------- Excel
def write_excel(path, results, gt_name):
    from openpyxl import Workbook
    from openpyxl.utils import get_column_letter
    St = E.styles()
    Font = St["Font"]
    wb = Workbook()
    ws = wb.active
    ws.title = "Wiederholläufe"
    ws.sheet_view.showGridLines = False
    ws.column_dimensions["A"].width = 2
    widths = [22, 9, 7, 14, 14, 20, 3, 14, 14, 20, 3, 14, 14, 20, 3, 12, 12, 12]
    for j, w in enumerate(widths):
        ws.column_dimensions[get_column_letter(2 + j)].width = w
    r = 2
    for scope, label in [("185", "185 Baugruppen"), ("115", "115 Baugruppen")]:
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=2 + len(widths) - 1)
        t = ws.cell(r, 2, f"Wiederholläufe (10 runs) mit {label} – Ground Truth {gt_name}, Allowed-Label-Set Accuracy")
        t.font = Font(bold=True, color="FFFFFF", size=12)
        t.alignment = St["left"]
        for j in range(len(widths)):
            ws.cell(r, 2 + j).fill = St["fill"](cm.NAVY)
        # Kopf zweizeilig
        groups = [("Alle Baugruppen", 4), ("Eindeutige Baugruppen", 8), ("Mehrdeutige Baugruppen", 12),
                  ("Eindeutige: Macro (Mittel der Läufe)", 16)]
        for txt, c0 in groups:
            span = 3
            ws.merge_cells(start_row=r + 1, start_column=2 + c0 - 1 + (0 if c0 != 4 else 0),
                           end_row=r + 1, end_column=2 + c0 - 1 + span - 1 + (0 if c0 != 4 else 0))
        heads1 = ["Modell", "Läufe", "", "Alle Baugruppen", "", "", "", "Eindeutige Baugruppen", "", "", "",
                  "Mehrdeutige Baugruppen", "", "", "", "Eindeutige: Macro-Werte", "", ""]
        heads2 = ["", "", "", "Mittelwert", "SD (pp)", "95%-KI", "", "Mittelwert", "SD (pp)", "95%-KI", "",
                  "Mittelwert", "SD (pp)", "95%-KI", "", "Precision", "Recall", "F1"]
        for j, (h1, h2) in enumerate(zip(heads1, heads2)):
            for rr, h in ((r + 1, h1), (r + 2, h2)):
                c = ws.cell(rr, 2 + j, h if h else None)
                if widths[j] > 3:
                    c.font = Font(bold=True, color="FFFFFF")
                    c.fill = St["fill"](cm.HEAD)
                    c.alignment = St["center"] if j else St["left"]
                    c.border = St["border"]
        # n-Zeile im Kopf
        rr = r + 3
        for i, m in enumerate([m for m in MODEL_ORDER if m in results] + [m for m in results if m not in MODEL_ORDER]):
            res = results[m].get(scope)
            bg = E.ODD_ROW_BG if i % 2 else "#FFFFFF"
            vals = [m, res["alle"]["runs"] if res else "fehlt", None]
            for which in ("alle", "eindeutig", "mehrdeutig"):
                x = res[which] if res else None
                vals += [x["acc"] if x else None, x["sd"] if x else None,
                         f"[{x['ci_lo']*100:.1f}; {x['ci_hi']*100:.1f}]" if x else None, None]
            x = res["eindeutig"] if res else None
            vals += [x["prec"] if x else None, x["rec"] if x else None, x["f1"] if x else None]
            for j, v in enumerate(vals):
                if widths[j] <= 3:
                    continue
                c = ws.cell(rr, 2 + j, v)
                c.fill, c.border = St["fill"](bg), St["border"]
                c.alignment = St["left"] if j == 0 else St["right"]
                hd = heads2[j]
                c.number_format = "0.0%" if hd in ("Mittelwert", "Precision", "Recall", "F1") else (
                    "0.00" if hd == "SD (pp)" else "General")
                c.font = Font(bold=hd == "Mittelwert" and j == 4)
            rr += 1
        # n
        any_res = next((results[m][scope] for m in results if results[m].get(scope)), None)
        if any_res:
            ws.cell(rr, 2, f"n: alle {any_res['alle']['n']}, eindeutig {any_res['eindeutig']['n']}, "
                           f"mehrdeutig {any_res['mehrdeutig']['n']} Baugruppen").font = Font(italic=True, size=9, color="595959")
        r = rr + 3
    notes = [
        "Mittelwert: Allowed-Label-Set Accuracy je Lauf, gemittelt über die Läufe. SD: Standardabweichung dieser Lauf-Werte (Prozentpunkte).",
        "95%-KI: Bootstrap über Baugruppen (2000 Wiederholungen, mit Zurücklegen, je BG alle Läufe; bei 185 BG getrennt nach Haupt- und Ergänzungsdatensatz).",
        "Eindeutig: keine weiteren zulässigen Labels (Allowed = Strict). Mehrdeutig: mindestens ein weiteres zulässiges Label.",
        "Macro-Precision/-Recall/-F1 nur auf eindeutigen Baugruppen (Standardformeln je Lauf, gemittelt). Precision über vorhergesagte Klassen, Recall über GT-Klassen, F1 = Mittel der Klassen-F1.",
        f"Ground Truth: {gt_name}; Prompt-Engineering-Baugruppen ausgeschlossen. Leere Vorhersagen zählen im jeweiligen Lauf nicht.",
    ]
    for i, txt in enumerate(notes):
        ws.cell(r + i, 2, txt).font = Font(italic=True, size=9, color="595959")

    # Tabellarische Rohwerte
    rows = []
    for m, sc in results.items():
        for scope, res in sc.items():
            if not res:
                continue
            for which, x in res.items():
                rows.append({"Modell": m, "Datensatz": scope, "Teilmenge": which, "n BG": x["n"], "Läufe": x["runs"],
                             "Accuracy Mittel (%)": round(x["acc"] * 100, 2), "SD (pp)": None if np.isnan(x["sd"]) else round(x["sd"], 2),
                             "KI unten (%)": round(x["ci_lo"] * 100, 2), "KI oben (%)": round(x["ci_hi"] * 100, 2),
                             "Accuracy je BG gemittelt (%)": round(x["acc_bg"] * 100, 2),
                             "Macro-P (%)": round(x["prec"] * 100, 2) if "prec" in x else None,
                             "Macro-R (%)": round(x["rec"] * 100, 2) if "rec" in x else None,
                             "Macro-F1 (%)": round(x["f1"] * 100, 2) if "f1" in x else None})
    ws2 = wb.create_sheet("Werte")
    df = pd.DataFrame(rows)
    ws2.append(list(df.columns))
    for v in df.itertuples(index=False):
        ws2.append(list(v))
    for c in ws2[1]:
        c.font = Font(bold=True)
    E.autosize(ws2)
    wb.save(path)
    return df


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", required=True, help="Ordner mit den Konfigurationsordnern (115 und 70BG)")
    ap.add_argument("--gt", required=True, help="R1.md oder Excel mit der Ground Truth")
    ap.add_argument("--gt-name", default="R1")
    ap.add_argument("--sheet", default="Sheet1")
    ap.add_argument("--out", default="Ergebnis_R1")
    a = ap.parse_args(argv)

    gt, pe, gt_issues = load_gt(a.gt)
    for i in gt_issues:
        print("! " + i)
    print(f"GT {a.gt_name}: {len(gt)} BG, davon Prompt-Engineering {len(pe)}; "
          f"mehrdeutig (ohne PE): {sum(len(v[1]) > 1 for k, v in gt.items() if k not in pe)}")
    issues = []
    data, info = collect(a.dir, a.sheet, gt, pe, issues)
    rng = np.random.default_rng(SEED)
    results = {}
    for m in [x for x in MODEL_ORDER if x in data] + [x for x in data if x not in MODEL_ORDER]:
        rm, rs = data[m]["main"], data[m]["supp"]
        print(f"\n{m}: {len(rm)} Läufe 115 BG, {len(rs)} Läufe 70 BG")
        for name, rr, exp in (("115", rm, 115), ("70", rs, 70)):
            for f, run in rr:
                if len(run) != exp:
                    print(f"  ! {name}: {f.name[-45:]} hat {len(run)} gewertete BG (erwartet {exp})")
        if rs and len(rs) != len(rm):
            print(f"  ! unterschiedliche Laufzahl (115: {len(rm)}, 70: {len(rs)}) – für 185 werden {min(len(rm), len(rs))} Paare genutzt")
        results[m] = {"115": evaluate(gt, rm, rs, "115", rng) if rm else None,
                      "185": evaluate(gt, rm, rs, "185", rng) if rm and rs else None}
        for scope in ("185", "115"):
            res = results[m][scope]
            if res:
                x = res["alle"]
                print(f"  {scope} BG: Accuracy {x['acc']*100:.1f} % (SD {x['sd']:.2f} pp, KI {x['ci_lo']*100:.1f}–{x['ci_hi']*100:.1f}), "
                      f"eindeutig {res['eindeutig']['acc']*100:.1f} %, mehrdeutig {res['mehrdeutig']['acc']*100:.1f} %, "
                      f"Macro-F1 eindeutig {res['eindeutig']['f1']*100:.1f} %")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    xlsx = out / f"Wiederhollaeufe_{a.gt_name}.xlsx"
    write_excel(xlsx, results, a.gt_name)
    print(f"\nAusgabe: {xlsx}")
    shown = [i for i in issues if not i["Typ"].startswith("Info:") and "Register" not in i["Typ"]
             and "Allowed_Set_Status" not in i["Typ"]]
    if shown:
        print("Hinweise:")
        groups = {}
        for i in shown:
            groups.setdefault((i["Typ"], i.get("SAP"), i.get("Detail")), []).append(i.get("Modell"))
        for (typ, sap, det), who in groups.items():
            print("   - " + " | ".join(str(x) for x in [typ, sap, det, f"{len(who)} Dateien"] if x))
    return results


if __name__ == "__main__":
    main()
