"""Unabhängige Gegenrechnung zu evaluate_r1.py (Blatt „Werte“ in Wiederhollaeufe_R1.xlsx).

Nutzt KEINEN Code aus evaluate_r1.py / evaluate_pdf_results.py / Skript 12/13: eigene Einlese-Logik für
R1.md und die Ergebnisdateien, eigene Label-Erkennung, eigene Berechnung. Verglichen werden je Modell,
Datensatz (115/185) und Teilmenge (alle/eindeutig/mehrdeutig): Anzahl BG, Läufe, Accuracy-Mittel, SD,
Macro-P/R/F1 (eindeutig) – exakt (±0,01). Das Bootstrap-KI ist zufallsabhängig: Es wird 20-mal unabhängig
(je 2000 Ziehungen) neu berechnet; die Grenze aus evaluate_r1 muss in der Spannweite dieser Wiederholungen liegen (±0,3 pp).

Erwartete Ordnerstruktur wie besprochen: <zehn>\\115BG\\<Konfiguration>\\*.xlsx und <zehn>\\70BG\\<Konfiguration>\\*.xlsx
(Datensatz aus dem Ordnernamen 115BG/70BG). Backups (_backup_vor_merge*), nachlauf_*-Dateien werden übersprungen.

Aufruf:
    python validate_r1.py --zehn "..\\03_Wiederholung_10runs" --gt R1.md --werte "..\\05_Ergebnisse\\Wiederhollaeufe_R1.xlsx"
"""

import argparse
import re
from pathlib import Path

import numpy as np
import pandas as pd

LABELS = ["Linear", "Rotation", "Greifer", "Gantry", "Roboter", "Kombi", "Keine"]


def label(x):
    """Eigene, einfache Label-Erkennung (unabhängig von canon())."""
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return None
    t = str(x).strip().lower()
    if not t or t in ("nan", "[empty]"):
        return None
    for keys, lab in ((("gantry", "multi-achs", "mehrachs", "portal"), "Gantry"), (("rotation", "dreh"), "Rotation"),
                      (("robot",), "Roboter"), (("greif", "gripper"), "Greifer"), (("linear", "hub"), "Linear"),
                      (("kombin", "combined"), "Kombi"), (("keine", "none", "sonstig"), "Keine")):
        if any(k in t for k in keys):
            return lab
    return "?"


def norm(s):
    s = "" if s is None or (isinstance(s, float) and np.isnan(s)) else str(s)
    return re.sub(r"[^0-9A-Z]", "", s.upper()).lstrip("0")


def bg_key(sap, tc):
    return ("S", norm(sap)) if norm(sap) else (("T", norm(tc)) if norm(tc) else None)


def read_r1(path):
    rows, head = [], None
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.startswith("|") or re.fullmatch(r"[|\-: ]+", line.strip()):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if head is None:
            if any("SAP" in c for c in cells):
                head = cells
            continue
        rows.append(dict(zip(head, cells + [""] * (len(head) - len(cells)))))
    col = lambda *ks: next(c for c in head if all(k.lower() in c.lower() for k in ks))  # noqa: E731
    c_sap, c_tc, c_gt, c_alt = col("SAP"), col("Teamcenter"), col("Ground Truth"), col("weitere")
    c_pe = next((c for c in head if "prompt" in c.lower() or "konfig" in c.lower()), None)
    gt = {}
    for r in rows:
        k = bg_key(r[c_sap], r[c_tc])
        if k is None or (c_pe and r[c_pe].strip().lower() == "yes"):
            continue
        g = label(r[c_gt])
        alts = {label(a) for a in re.split(r"[,;]", r[c_alt]) if a.strip()} - {g, None}
        gt[k] = (g, {g} | alts)
    return gt


def read_run(path):
    df = pd.read_excel(path, sheet_name="Sheet1" if "Sheet1" in pd.ExcelFile(path).sheet_names else 0, dtype=str)
    cs = next((c for c in df.columns if "sap" in str(c).lower()), None)
    ct = next((c for c in df.columns if "teamcenter" in str(c).lower()), None)
    cp = next((c for c in df.columns if "predicted" in str(c).lower()), None)
    ce = next((c for c in df.columns if "prompt" in str(c).lower() and "engineer" in str(c).lower()), None)
    run = {}
    for _, r in df.iterrows():
        if ce and str(r[ce]).strip().lower() == "yes":
            continue
        k = bg_key(r[cs] if cs else None, r[ct] if ct else None)
        p = label(r[cp])
        if k and p is not None and k not in run:
            run[k] = p
    return run


def model_of(name):
    t = name.lower()
    for k, m in (("deepseek", "DeepSeek-V4-Flash"), ("haiku", "Claude Haiku 4.5"), ("opus", "Claude Opus 4.8"),
                 ("gpt", "GPT-5.5")):
        if k in t:
            return m
    if "gemini" in t:
        return "Gemini 2.5 Flash" if "flash" in t else "Gemini 2.5 Pro"
    return None


def macro(pairs):
    P, R, F = [], [], []
    for c in LABELS:
        tp = sum(1 for g, p in pairs if g == c and p == c)
        pc = sum(1 for g, p in pairs if p == c)
        gc = sum(1 for g, p in pairs if g == c)
        if pc:
            P.append(tp / pc)
        if gc:
            R.append(tp / gc)
        if pc or gc:
            F.append(2 * tp / (pc + gc))
    return np.mean(P) * 100, np.mean(R) * 100, np.mean(F) * 100


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--zehn", required=True)
    ap.add_argument("--gt", required=True)
    ap.add_argument("--werte", required=True, help="Wiederhollaeufe_R1.xlsx von evaluate_r1.py")
    a = ap.parse_args()
    gt = read_r1(a.gt)
    data = {}  # model -> ds -> [run]
    for f in sorted(Path(a.zehn).rglob("*.xlsx")):
        parts = [p.lower() for p in f.parts]
        if f.name.startswith("~$") or f.name.lower().startswith("nachlauf_") or any(p.startswith("_backup_vor_merge") for p in parts):
            continue
        ds = "70" if any("70bg" in p for p in parts) else "115"
        m = model_of(f.parent.name)
        if m:
            data.setdefault(m, {}).setdefault(ds, []).append(read_run(f))
    ref = pd.read_excel(a.werte, sheet_name="Werte")
    rng = np.random.default_rng(7)
    ok = bad = 0
    for m, d in data.items():
        for scope in ("115", "185"):
            if scope == "115":
                runs = d.get("115", [])
                strata = None
            else:
                if not d.get("70"):
                    continue
                n = min(len(d["115"]), len(d["70"]))
                runs = [{**d["115"][i], **d["70"][i]} for i in range(n)]
            for sub in ("alle", "eindeutig", "mehrdeutig"):
                keys = [k for k in gt if sub == "alle" or (len(gt[k][1]) > 1) == (sub == "mehrdeutig")]
                keys = [k for k in keys if any(k in r for r in runs)]
                accs = [np.mean([r[k] in gt[k][1] for k in keys if k in r]) * 100 for r in runs]
                mine = {"n BG": len(keys), "Läufe": len(runs), "Accuracy Mittel (%)": np.mean(accs),
                        "SD (pp)": np.std(accs, ddof=1) if len(accs) > 1 else np.nan}
                if sub == "eindeutig":
                    prf = [macro([(gt[k][0], r[k]) for k in keys if k in r]) for r in runs]
                    mine.update({"Macro-P (%)": np.mean([x[0] for x in prf]), "Macro-R (%)": np.mean([x[1] for x in prf]),
                                 "Macro-F1 (%)": np.mean([x[2] for x in prf])})
                # eigenes Bootstrap (je Datensatz getrennt bei 185)
                share = {k: np.mean([r[k] in gt[k][1] for r in runs if k in r]) for k in keys}
                main_keys = set(d["115"][0]) if d.get("115") else set()
                groups = [np.array([v for k, v in share.items() if k in main_keys]),
                          np.array([v for k, v in share.items() if k not in main_keys])] if scope == "185" else [np.array(list(share.values()))]
                groups = [g for g in groups if len(g)]
                # Bootstrap-Grenzen schwanken zufällig (Monte-Carlo-Fehler, bei kleinem n deutlich):
                # 20 unabhängige Wiederholungen à 2000 Ziehungen -> Spannweite der Grenzen als Toleranzbereich
                lo_hi = []
                for _ in range(20):
                    boots = [np.concatenate([g[rng.integers(0, len(g), len(g))] for g in groups]).mean() * 100
                             for _ in range(2000)]
                    lo_hi.append((np.percentile(boots, 2.5), np.percentile(boots, 97.5)))
                ci_range = {"KI unten (%)": (min(x[0] for x in lo_hi), max(x[0] for x in lo_hi)),
                            "KI oben (%)": (min(x[1] for x in lo_hi), max(x[1] for x in lo_hi))}
                row = ref[(ref["Modell"] == m) & (ref["Datensatz"].astype(str) == scope) & (ref["Teilmenge"] == sub)]
                if row.empty:
                    print(f"FEHLT in Werte: {m} {scope} {sub}")
                    bad += 1
                    continue
                row = row.iloc[0]
                for col, v in mine.items():
                    if col not in row or (isinstance(v, float) and np.isnan(v)):
                        continue
                    if abs(float(row[col]) - float(v)) <= 0.011:
                        ok += 1
                    else:
                        bad += 1
                        print(f"ABWEICHUNG {m} {scope} {sub} {col}: evaluate_r1 {row[col]} / Gegenrechnung {v:.3f}")
                for col, (lo, hi) in ci_range.items():
                    x = float(row[col])
                    if lo - 0.3 <= x <= hi + 0.3:
                        ok += 1
                    else:
                        bad += 1
                        print(f"ABWEICHUNG {m} {scope} {sub} {col}: evaluate_r1 {x:.2f} außerhalb der Spannweite "
                              f"unabhängiger Bootstraps [{lo:.2f}; {hi:.2f}]")
    print(f"\nGegenrechnung: {ok} Werte übereinstimmend, {bad} Abweichungen.")
    if bad == 0:
        print("OK – alle Werte unabhängig bestätigt.")


if __name__ == "__main__":
    main()
