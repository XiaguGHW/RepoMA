"""Selbsttest mit Simulationsdaten für confusion_human_llm.py (keine echten Daten nötig).

    python selftest_confusion_human_llm.py

Erzeugt im Ordner _selftest/ eine Workshop-Tabelle im Aufbau von "Klassifikation_Übersicht_Gesamt"
(WS_1/WS_2 Primärdatensatz, WS_4 Ergänzung ab Zeile 132, TN_-Spalten, Trennspalte, Eindeutigkeit)
und vier LLM-Ergebnisdateien, führt das Skript aus und vergleicht alle Zahlen mit einer unabhängig
berechneten Erwartung. Zusätzlich werden die Farben der geteilten Zellen im gerenderten Bild geprüft.
"""

import random
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from openpyxl import Workbook

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import confusion_human_llm as C  # noqa: E402

OUT = HERE / "_selftest"
rng = random.Random(7)

G1 = ["TN_A_P1", "TN_B_P2", "TN_C_P3", "TN_D_P4", "TN_E_P5"]           # I–M
G2 = ["TN_A_Q1", "TN_B_Q2", "TN_C_Q3", "TN_D_Q4", "TN_E_Q5"]           # O–S
G3 = ["TN_B_R1"]                                                     # T
G4 = ["TN_A_S1", "TN_B_S2", "TN_C_S3", "TN_D_S4", "TN_E_S5"]           # U–Y
HEADER = (["Workshop", "ID", "SAP-Nummer", "Teamcenter", "Benennung (E)", "Benennung (D)",
           "Baugruppenebene", "Ground Truth"] + G1 + [None] + G2 + G3 + G4 + ["Eindeutigkeit"])

RAW_VARIANTS = {
    C.GANTRY: ["Multi-Achs-System (Gantry)", "Gantry", "Multi-Achs-System(Gantry)"],
    "Kombinierte Einheit": ["Kombinierte Einheit", "Umsetzeinheit"],
    C.NONE_CLS: ["Keine der verfügbaren Klassen", "Keine der verfÃ¼gbaren Klassen", "Keine der verfügbaren Klasse"],
}


def raw_of(label):
    return rng.choice(RAW_VARIANTS.get(label, [label])) + rng.choice(["", "", " "])


def draw_label(key):
    g, allowed, _ = C.gt_info(key)
    u = rng.random()
    if u < 0.70:
        return g
    alts = sorted(allowed - {g})
    if alts and u < 0.85:
        return rng.choice(alts)
    return rng.choice([c for c in C.CLASSES if c not in allowed] or C.CLASSES)


def main():
    OUT.mkdir(exist_ok=True)
    supp = [k for k in C.FINAL_GT if k not in C.MAIN_129]
    assert len(supp) == 70
    wb = Workbook()
    wb.active.title = "Final_Ground_Truth_after_Review"
    ws = wb.create_sheet("Klassifikation_Übersicht_Gesamt")
    wb.create_sheet("Data")
    ws.append(HEADER)
    col = {h: i for i, h in enumerate(HEADER) if h}

    truth = []  # (key, Teilnehmer, kanonisches Label | None bei unbekannt, Excel-Zeile)
    rows = []
    for n, key in enumerate(C.MAIN_129):
        wsn = "WS_1" if n < 60 else "WS_2"
        who = list(G1)
        if 29 <= n < 60 and key != "0804DN9616":
            who += G2
        if n >= 60:
            who += rng.sample(G2 + G3, rng.randint(0, 5))
        rows.append((wsn, key, who))
    # zusätzliche Zeile: dieselbe BG erneut (eine Person doppelt, eine neu)
    rows.append(("WS_2", "0804LV8630", ["TN_A_P1", "TN_B_R1"]))
    for key in supp:
        rows.append(("WS_4", key, G4 + (["TN_A_P1"] if key == supp[0] else [])))

    for wsn, key, who in rows:
        xrow = ws.max_row + 1
        line = [None] * len(HEADER)
        line[col["Workshop"]] = wsn
        if key.startswith("TC:"):
            line[col["Teamcenter"]] = key[3:]
        elif key == "0804306221":
            line[col["SAP-Nummer"]] = 804306221           # Zahl ohne führende Null
        elif key == "0804FT0436":
            line[col["SAP-Nummer"]] = " 804FT0436"        # führende Null fehlt, Leerzeichen
        else:
            line[col["SAP-Nummer"]] = key
        g, allowed, reg = C.gt_info(key)
        line[col["Ground Truth"]] = "Lineareinheit" if key == "0804KZ9027" else g   # alte GT
        line[col["Eindeutigkeit"]] = "Mehrdeutig" if reg == "M" else "Eindeutig"
        for p in who:
            lab = draw_label(key)
            raw = raw_of(lab)
            if key == "0804FA3834" and p == "TN_C_P3":
                raw, lab = "Förderband", None                 # unbekannter Klassenname
            if key == "0804FZ8322" and p == "TN_D_P4":
                raw = ""                                      # leere Zelle (Formel "")
                continue
            line[col[p]] = raw
            truth.append((key, p, lab, xrow))
        ws.append(line)
    # Leerzeilen am Ende (wie Formeln mit "")
    ws.append([None] * len(HEADER))
    wpath = OUT / "Workshop_Simulation.xlsx"
    wb.save(wpath)

    # ---------------- LLM-Dateien (Format wie Skript 12)
    llm_files, llm_truth = {}, {}
    for arg, name, expect in C.CONFIGS:
        recs, exp = [], []
        for key in C.MAIN_115 + ["0804KM9320"]:          # eine Vorversuch-BG zu viel
            g, allowed, reg = C.gt_info(key)
            pred = draw_label(key)
            stat = ""
            raw = raw_of(pred)
            if arg == "gpt" and key == "0804FK2694":
                raw, pred, stat = "", None, "EXCLUDED"
            gt_file, alt_file = g, ", ".join(sorted(allowed - {g}))
            if key == "0804KZ9027":
                gt_file, alt_file = "Lineareinheit", ""       # alte GT -> wird ersetzt
            if key == "0804GE7738":
                gt_file, alt_file = "Umsetzeinheit", ""
            recs.append({"SAP-Nummer": key.lstrip("0") if key == "0804306221" else key, "Teamcenter": "",
                         "Benennung (E)": "x", "Ground Truth": gt_file, "Weitere zulässige Ground Truth": alt_file,
                         "Register": reg, "Predicted Class": raw, "Allowed_Set_Status": stat})
            if key in C.SET_115 and pred is not None:
                exp.append((key, pred))
        p = OUT / f"{expect}_P3_run1.xlsx"
        pd.DataFrame(recs).to_excel(p, sheet_name="Sheet1", index=False)
        llm_files[arg] = p
        llm_truth[name] = exp

    args = C.parse_args(["--workshop", str(wpath), "--out", str(OUT / "out"),
                         "--haiku", str(llm_files["haiku"]), "--gemini", str(llm_files["gemini"]),
                         "--gpt", str(llm_files["gpt"]), "--deepseek", str(llm_files["deepseek"])])
    res = C.run(args)

    # ---------------- unabhängige Erwartung
    def expected(pairs):
        K = 7
        diag, red, green = np.zeros(K, int), np.zeros((K, K), int), np.zeros((K, K), int)
        for key, pred in pairs:
            g, reg, alts = C.FINAL_GT[key]
            g = C.canon(g)
            allowed = {g} | {C.canon(a) for a in alts}
            i, j = C.CLASSES.index(g), C.CLASSES.index(pred)
            if pred == g:
                diag[i] += 1
            elif pred in allowed:
                green[i, j] += 1
            else:
                red[i, j] += 1
        return diag, red, green

    seen, hp = set(), []
    for key, p, lab, _ in truth:
        if key not in C.SET_115 or (key, p) in seen:
            continue
        seen.add((key, p))
        if lab is not None:
            hp.append((key, lab))
    checks = [("Mensch", res["human"], expected(hp))]
    checks += [(n, res["llm"][n], expected(v)) for n, v in llm_truth.items()]
    for name, m, (d, r, g) in checks:
        assert (m["diag"] == d).all() and (m["red"] == r).all() and (m["green"] == g).all(), name
        assert m["n"] == d.sum() + r.sum() + g.sum(), name
        print(f"OK  Matrix {name}: n = {m['n']}")
    assert res["llm"]["GPT-5.5 (Image)"]["n"] == 114

    # grün nur in Zeilen mit M-Baugruppen und nur für dort zulässige Labels
    possible = np.zeros((7, 7), bool)
    for key in C.MAIN_115:
        g, allowed, reg = C.gt_info(key)
        for a in allowed - {g}:
            possible[C.IDX[g], C.IDX[a]] = True
    for name, m, _ in checks:
        assert not (m["green"] > 0)[~possible].any(), f"grün an unmöglicher Stelle: {name}"
    print("OK  grün nur bei weiteren zulässigen Labels (M)")

    # Prüfungen
    typ = [i["Typ"] for i in res["issues"]]
    assert any("nicht erkannt" in t for t in typ), "unbekanntes Label fehlt"
    assert any(i["Typ"].startswith("Mensch: doppelte") and i["SAP"] == "0804LV8630" for i in res["issues"])
    assert any(i["Typ"].startswith("Mensch: Baugruppe in mehreren") for i in res["issues"])
    assert any("ersetzt" in t and i.get("SAP") == "0804KZ9027" for i, t in zip(res["issues"], typ))
    assert any(i["Typ"].startswith("Mensch: Spalte 'Ground Truth'") and i["SAP"] == "0804KZ9027" for i in res["issues"])
    assert any("nicht im 115er-Satz" in t for t in typ)
    assert any("EXCLUDED" in t for t in typ)
    assert res["n_supp"] == 70 * 5 + 1
    bg = {r["SAP"]: r for r in res["bg"]}
    assert bg["0804306221"]["Anzahl Personen"] >= 5 and bg["0804FT0436"]["Anzahl Personen"] >= 5
    assert bg["0804DN9616"]["Anzahl Personen"] == 5
    assert bg["0804FZ8322"]["Anzahl Personen"] == 4 and bg["0804FZ8322"]["5–10 Personen"] == "PRÜFEN"
    assert bg["0804FK2694"]["GPT-5.5 (Image)"] == "FEHLT"
    print("OK  Prüfungen (unbekannte Labels, Duplikate, GT-Ersetzung, Abdeckung, Personen je BG)")

    # Excel zurücklesen
    lang = pd.read_excel(res["xlsx"], sheet_name="Lang")
    for name, m, _ in checks:
        key = C.TXT["en"]["human"] if name == "Mensch" else name
        sub = lang[lang["Matrix"] == key]
        assert sub["Anzahl"].sum() == m["n"] and sub["rot"].sum() == m["red"].sum()
        assert sub["grün"].sum() == m["green"].sum() and sub["Diagonale"].sum() == m["diag"].sum()
    xl = pd.ExcelFile(res["xlsx"]).sheet_names
    for s in ["Uebersicht", "M_Mensch", "M_Haiku", "M_Gemini", "M_GPT", "M_DeepSeek", "Lang", "Pruefung_Zusammenfassung",
              "Pruefung_BG", "Pruefung_Teilnehmer", "Pruefung_GT_ersetzt", "Pruefung_Labels_unbekannt", "Pruefung_Hinweise"]:
        assert s in xl, s
    print("OK  Excel")

    # ---------------- Farben im gerenderten Bild (A1)
    pixel_test()
    for p in res["pngs"]:
        assert p.exists() and p.stat().st_size > 10000, p
    print("OK  PNGs:", ", ".join(p.name for p in res["pngs"]))
    print("\nAlle Tests bestanden.")


def pixel_test():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import to_rgb

    K = 7
    m = dict(diag=np.array([15, 15, 18, 0, 17, 13, 5]), red=np.zeros((K, K), int), green=np.zeros((K, K), int))
    m["red"][0, 4] = 1           # nur rot
    m["green"][1, 5] = 2         # nur grün
    m["red"][4, 5] = 1           # rot + grün
    m["green"][4, 5] = 1
    m["red"][5, 0] = 12
    m["green"][5, 0] = 3
    total = m["red"] + m["green"]
    total[np.diag_indices(K)] = m["diag"]
    m["total"], m["n"] = total, int(total.sum())

    fig = plt.figure(figsize=(8.6, 4.8), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1])
    C.draw_matrix(ax, m, "Pixeltest")
    fig.canvas.draw()
    img = np.asarray(fig.canvas.buffer_rgba())[:, :, :3] / 255.0
    H = img.shape[0]
    lw, cw, th, hh, rh = 1.3, 1.0, 0.75, 0.6, 0.7

    def color_at(i, j, part):
        x = lw + j * cw + {"left": 0.12, "right": 0.88, "full": 0.12}[part] * cw
        y = th + hh + (i + 0.15) * rh                  # oberer Rand der Zelle, nicht auf der Zahl
        px, py = ax.transData.transform((x, y))
        return img[int(H - py), int(px)]

    def near(a, b):
        return np.abs(np.array(a) - np.array(to_rgb(b))).max() < 0.03

    cases = [((0, 0, "full"), C.BLUE_BG), ((3, 3, "full"), C.WHITE),           # Diagonale 15 / 0
             ((0, 1, "full"), C.WHITE),                                        # 0-Zelle
             ((0, 4, "left"), C.RED_BG), ((0, 4, "right"), C.WHITE),           # nur rot
             ((1, 5, "left"), C.WHITE), ((1, 5, "right"), C.GREEN_BG),         # nur grün
             ((4, 5, "left"), C.RED_BG), ((4, 5, "right"), C.GREEN_BG),        # beides
             ((5, 0, "left"), C.RED_BG), ((5, 0, "right"), C.GREEN_BG)]
    for (i, j, part), col in cases:
        got = color_at(i, j, part)
        assert near(got, col), f"Zelle ({i},{j},{part}): {got} statt {col}"
    # Zahlen und Textfarben über cell_spec
    assert C.cell_spec(m, 0, 4) == [("left", C.RED_BG, 1, C.RED_TXT, True), ("right", C.WHITE, 0, C.ZERO_TXT, False)]
    assert C.cell_spec(m, 1, 5) == [("left", C.WHITE, 0, C.ZERO_TXT, False), ("right", C.GREEN_BG, 2, C.GREEN_TXT, True)]
    assert C.cell_spec(m, 5, 0) == [("left", C.RED_BG, 12, C.RED_TXT, True), ("right", C.GREEN_BG, 3, C.GREEN_TXT, True)]
    assert C.cell_spec(m, 0, 1) == [("full", C.WHITE, 0, C.ZERO_TXT, False)]
    assert C.cell_spec(m, 0, 0) == [("full", C.BLUE_BG, 15, C.DARK_TXT, True)]
    assert C.cell_spec(m, 3, 3) == [("full", C.WHITE, 0, C.ZERO_TXT, False)]
    fig.savefig(OUT / "pixeltest.png")
    plt.close(fig)
    print("OK  Farben der geteilten Zellen (Pixelprüfung) und Zahlen")


if __name__ == "__main__":
    main()
