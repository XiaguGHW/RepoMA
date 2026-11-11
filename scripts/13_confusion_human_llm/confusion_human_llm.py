"""Konfusionsmatrizen Mensch (Workshop) vs. LLM (vier finale Konfigurationen), 115 BG.

Abschnitt 5.7 (Error Analysis). Offline, keine Modellaufrufe.

- Mensch: Blatt "Klassifikation_Übersicht_Gesamt" der Workshop-Auswertung, jede Klassifikation
  (eine Zelle in einer Spalte "TN_...") zählt einmal.
- LLM: je Konfiguration eine Ergebnisdatei (ein Lauf, P3, 115 BG), Pfad per Kommandozeile.
- Zeilen = Primärlabel der finalen GT (FINAL_GT aus Skript 12), Spalten = vergebene Klasse.
- Darstellung Variante A1: Diagonale blau; Nicht-Diagonale geteilt, links rot = nicht zulässig,
  rechts grün = weiteres zulässiges Label (nur M); leere Hälfte graue 0; ganze Zelle 0 = graue 0.

Aufruf (Beispiel, PowerShell):
    python confusion_human_llm.py --workshop "...\\Workshop_Auswertung.xlsx" `
        --haiku "...\\haiku.xlsx" --gemini "...\\gemini.xlsx" `
        --gpt "...\\Run_1.xlsx" --deepseek "...\\Run_1.xlsx" --out Konfusion_Mensch_LLM
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "12_validation_regimes"))
import evaluate_validation_regimes as ev  # noqa: E402  (FINAL_GT, canon, read_result_file)

FINAL_GT = ev.FINAL_GT
is_empty = ev.is_empty
find_col = ev.find_col

# ---------------------------------------------------------------- Klassen, Codes A–G
GANTRY = "Multi-Achs-System (Gantry)"
NONE_CLS = "Keine der verfügbaren Klassen"
ORDER = [
    ("A", GANTRY),
    ("B", "Rotationseinheit"),
    ("C", "Roboter"),
    ("D", "Greifer"),
    ("E", "Lineareinheit"),
    ("F", "Kombinierte Einheit"),
    ("G", NONE_CLS),
]
CODES = [c for c, _ in ORDER]
CLASSES = [k for _, k in ORDER]
IDX = {k: i for i, k in enumerate(CLASSES)}
assert set(CLASSES) == set(ev.CLASSES), "Klassennamen weichen von Skript 12 ab"

LEGEND_NAMES = {
    "de": ["Gantry", "Rotationseinheit", "Roboter", "Greifer", "Lineareinheit",
           "Kombinierte Einheit", "Keine der verfügbaren Klassen"],
    "en": ["Multi-Axis System (Gantry)", "Rotary Unit", "Robot", "Gripper", "Linear Unit",
           "Combined Unit", "None of the Available Classes"],
}

# Zusätzliche Schreibweisen (Ergänzung zu ev.SYNONYMS)
EXTRA_SYNONYMS = {
    "multi-achs-system": GANTRY,
    "multi-achs system": GANTRY,
    "multi-achs-system gantry": GANTRY,
    "multi-axis system (gantry)": GANTRY,
    "multi-axis system": GANTRY,
    "portal": GANTRY,
    "kombinierte einheit (umsetzeinheit)": "Kombinierte Einheit",
    "umsetzeinheit (kombinierte einheit)": "Kombinierte Einheit",
    "combined unit": "Kombinierte Einheit",
    "rotary unit": "Rotationseinheit",
    "robot": "Roboter",
    "gripper": "Greifer",
    "linear unit": "Lineareinheit",
    "none of the available classes": NONE_CLS,
}
ev.LOOKUP.update({ev._norm(k): v for k, v in EXTRA_SYNONYMS.items()})
_ORIG_CANON = ev.canon


def _collapse(s):
    return re.sub(r"[^a-z]", "", s)


_COLLAPSED = {_collapse(k): v for k, v in ev.LOOKUP.items()}


def canon(x):
    """Kanonischer Klassenname; None bei leer; 'UNGÜLTIG:<text>' wenn nicht erkannt.

    Zusätzlich zu Skript 12: Vergleich nur über Buchstaben a–z (fängt fehlende Leerzeichen,
    Bindestriche und Kodierungsfehler wie 'verfÃ¼gbaren' ab)."""
    c = _ORIG_CANON(x)
    if c is None or not c.startswith("UNGÜLTIG:"):
        return c
    n = _collapse(ev._norm(c[len("UNGÜLTIG:"):]))
    if n in _COLLAPSED:
        return _COLLAPSED[n]
    if n.startswith("keineder"):
        return NONE_CLS
    return c


ev.canon = canon  # read_result_file aus Skript 12 nutzt damit dieselbe Normalisierung

# ---------------------------------------------------------------- Datensatz (115 BG)
PRE_EXPERIMENT = [
    "0804KM9320", "0804HK5576", "0804KR9668", "0804DU5389", "0804KR9943", "0804LU7362", "0804KY9594",
    "0804KW6429", "0804LY8514", "0804MA7037", "0804DY2146", "0804FL5283", "0804EZ0597", "0804LW3879",
]
# Primärdatensatz (129 BG) in der Reihenfolge von thesis/classification_data_and_revision_statistics.md
MAIN_129 = [
    "0804FC1588", "0804FA3834", "0804BR4641", "0804KM9320", "0804FZ8322", "0804FM8785", "0804KZ9027",
    "0804KK0664", "0804CW9430", "0804KZ1155", "0804HZ8350", "0804KZ8712", "0804KE7723", "0804JL8049",
    "0804JU4254", "0804KW6842", "0804KT1289", "0804KW1502", "0804KY7179", "0804FF2025", "0804KM8175",
    "0804KR0143", "0804KY3585", "0804DT6452", "0804FR1463", "0804EC1049", "0804LG8766", "0804GD6171",
    "0804JD0275", "0804FK2694", "0804JL8434", "0804KB2225", "0804KY5559", "0804HK5576", "0804KR6993",
    "0804LH5422", "0804KZ5637", "0804KR9668", "0804JU56371", "0804AY8008", "0804EU0861", "0804GE7738",
    "0804DU5323", "0804GV7647", "0804EB6690", "0804306221", "0804KZ9209", "0804DN9616", "0804LB1151",
    "0804CE5532", "0804FU6515", "0804GY2576", "0804KM9359", "0804CH8012", "0804KB7256", "0804AR3766",
    "0804HX0679", "0804KZ9488", "0804DU5389", "0804GY2577", "0804LG6553", "0804KY6491", "0804FH4760",
    "0804KS8037", "0804KR9943", "0804EK1683", "0804LU7362", "0804KT2332", "0804EV7706", "0804KY9594",
    "0804KU2401", "0804LH9239", "0804LB3626", "0804KW6429", "0804KB9919", "0804KU7061", "0804JT7787",
    "0804EA6409", "0804FR8437", "0804CC3075", "0804KU9472", "0804LY4947", "0804KT8575", "0804MA9380",
    "0804LY8514", "0804MA7037", "0804KV4964", "0804JK8878", "0804LZ1241", "3843CE1617", "0804GZ3046",
    "0804DY2146", "0804JX5741", "0804LC3026", "0804FL5283", "0804FT6844", "0804EZ0597", "0804KX4663",
    "0804JX5476", "0804KV0861", "0804HL3088", "0804HH8872", "0804JX8777", "0804LM2565", "0804LW3879",
    "0804HK2005", "0804LM8093", "0804KY7178", "0804LA7293", "0804CM8667", "0804EN7325", "0804LK3617",
    "0804GT0312", "0804MB2849", "0804KU1528", "3842998383", "0804KV2157", "0804GT5112", "0804GA4441",
    "0804LR0554", "0804JL5526", "0804LE2661", "0804AF9667", "0804LV8630", "0804BD5654", "0804CC2134",
    "0804JX6656", "0804KW8391", "0804FT0436",
]
MAIN_115 = [s for s in MAIN_129 if s not in PRE_EXPERIMENT]
assert len(MAIN_129) == 129 and len(MAIN_115) == 115 and all(s in FINAL_GT for s in MAIN_129)
SET_115 = set(MAIN_115)

# Konfigurationen: (Argument, Anzeigename, erwarteter Teil des Dateipfads)
CONFIGS = [
    ("haiku", "Claude Haiku 4.5 (PDF)", "haiku"),
    ("gemini", "Gemini 2.5 Pro (PDF)", "gemini-2.5-pro"),
    ("gpt", "GPT-5.5 (Image)", "gpt-5.5"),
    ("deepseek", "DeepSeek-V4-Flash (Text)", "deepseek"),
]

# ---------------------------------------------------------------- Farben (Variante A1)
NAVY = "#173F65"        # Titelzeile
HEAD = "#2E6DA4"        # Kopfzeile
ROWLAB_BG = "#EEF3F8"   # Zeilenbeschriftung
BLUE_BG = "#D6E8F5"     # Diagonale
RED_BG = "#FBE3E3"
RED_TXT = "#C62828"
GREEN_BG = "#E3F1DD"
GREEN_TXT = "#2E7D32"
ZERO_TXT = "#9E9E9E"
WHITE = "#FFFFFF"
GRID = "#D9D9D9"
DARK_TXT = "#173F65"


# ---------------------------------------------------------------- GT
def gt_info(key):
    """(Primärlabel, Menge zulässiger Labels, Regime) aus FINAL_GT."""
    g, reg, alts = FINAL_GT[key]
    g = canon(g)
    allowed = frozenset([g] + [canon(a) for a in alts])
    return g, allowed, ev.regime(allowed, reg)


_STRIPPED = {k.lstrip("0"): k for k in FINAL_GT if not k.startswith("TC:")}


def match_key(sap_raw, tc_raw=None):
    """SAP-Nummer der finalen GT (führende Nullen, '.0' von Excel, Leerzeichen); sonst Teamcenter."""
    if not is_empty(sap_raw):
        s = re.sub(r"\s+", "", str(sap_raw))
        if re.fullmatch(r"\d+\.0+", s):
            s = s.split(".")[0]
        if s in FINAL_GT:
            return s
        if s.lstrip("0") in _STRIPPED:
            return _STRIPPED[s.lstrip("0")]
    if tc_raw is not None and not is_empty(tc_raw):
        k = "TC:" + str(tc_raw).strip()
        if k in FINAL_GT:
            return k
    return None


# ---------------------------------------------------------------- Einlesen Mensch
def pick_sheet(path, wanted):
    names = pd.ExcelFile(path).sheet_names
    if wanted in names:
        return wanted
    cand = [n for n in names if "bersicht" in n.lower() and "gesamt" in n.lower()]
    if len(cand) == 1:
        return cand[0]
    sys.exit(f"Blatt '{wanted}' nicht gefunden in {Path(path).name}. Vorhandene Blätter: {names}")


def read_workshop(path, sheet, issues):
    sh = pick_sheet(path, sheet)
    df = pd.read_excel(path, sheet_name=sh, dtype=str)
    cols = list(df.columns)
    c_sap = find_col(cols, contains=["sap"])
    c_tc = find_col(cols, contains=["teamcenter"])
    c_gt = find_col(cols, exact="Ground Truth")
    c_ws = find_col(cols, contains=["work"]) or cols[0]
    tn_cols = [c for c in cols if str(c).strip().upper().startswith("TN_")]
    if c_sap is None or not tn_cols:
        sys.exit(f"Spalten nicht gefunden (SAP / TN_...) in Blatt '{sh}': {cols}")

    ann = []            # Annotationen der 115 BG
    other = []          # Annotationen außerhalb der 115 BG (Vorversuch, Ergänzung), nur gezählt
    seen = {}           # (key, Teilnehmer) -> Excel-Zeile
    rows_per_key = defaultdict(list)
    for i, row in df.iterrows():
        xrow = i + 2
        vals = {c: row[c] for c in tn_cols if not is_empty(row[c])}
        if is_empty(row[c_sap]) and (c_tc is None or is_empty(row[c_tc])) and not vals:
            continue  # Leerzeile
        key = match_key(row[c_sap], row[c_tc] if c_tc else None)
        ws = "" if is_empty(row[c_ws]) else str(row[c_ws]).strip()
        if key is None:
            issues.append(dict(Typ="Mensch: Zeile keiner Baugruppe der finalen GT zugeordnet (ignoriert)",
                               Quelle="Workshop", ExcelZeile=xrow, SAP=row[c_sap],
                               Detail=f"{len(vals)} Klassifikationen"))
            continue
        rows_per_key[key].append(xrow)
        if key not in SET_115:
            subset = "Vorversuch (14)" if key in PRE_EXPERIMENT else ("Primär" if key in MAIN_129 else "Ergänzung (70)")
            for c, v in vals.items():
                other.append(dict(sap=key, participant=str(c).strip(), subset=subset, label=canon(v)))
            continue
        g, allowed, reg = gt_info(key)
        if c_gt is not None and not is_empty(row[c_gt]):
            old = canon(row[c_gt])
            if old != g:
                issues.append(dict(Typ="Mensch: Spalte 'Ground Truth' der Workshop-Tabelle ≠ finale GT (finale GT verwendet)",
                                   Quelle="Workshop", ExcelZeile=xrow, SAP=key, Detail=f"Tabelle: {old}  ->  final: {g}"))
        for c, v in vals.items():
            p = str(c).strip()
            lab = canon(v)
            if (key, p) in seen:
                issues.append(dict(Typ="Mensch: doppelte Klassifikation derselben Person (zweite ignoriert)",
                                   Quelle="Workshop", ExcelZeile=xrow, SAP=key, Teilnehmer=p,
                                   Detail=f"erste in Zeile {seen[(key, p)]}; Wert: {v}"))
                continue
            seen[(key, p)] = xrow
            if lab.startswith("UNGÜLTIG:"):
                issues.append(dict(Typ="Mensch: Klassenname nicht erkannt (nicht in Matrix)", Quelle="Workshop",
                                   ExcelZeile=xrow, SAP=key, Teilnehmer=p, Detail=str(v)))
                continue
            ann.append(dict(sap=key, participant=p, workshop=ws, excel_row=xrow,
                            gt=g, allowed=allowed, regime=reg, pred=lab, raw=str(v).strip()))
    for key, rows in rows_per_key.items():
        if len(rows) > 1:
            issues.append(dict(Typ="Mensch: Baugruppe in mehreren Zeilen (Klassifikationen zusammengeführt)",
                               Quelle="Workshop", SAP=key, Detail=f"Excel-Zeilen {rows}"))
    return ann, other, dict(sheet=sh, tn_cols=[str(c).strip() for c in tn_cols])


# ---------------------------------------------------------------- Einlesen LLM
def read_llm(path, cfg_name, expect, issues):
    path = Path(path)
    if not path.is_file():
        sys.exit(f"Datei nicht gefunden: {path}")
    if expect not in str(path).lower():
        issues.append(dict(Typ="LLM: Dateipfad enthält nicht die erwartete Kennung (Konfiguration prüfen)",
                           Quelle=cfg_name, Datei=str(path), Detail=f"erwartet: '{expect}'"))
    tmp = []
    recs = ev.read_result_file(path, tmp, cfg_name, "115", 1)
    for it in tmp:
        it = dict(it)
        it["Typ"] = "LLM: " + it.pop("Typ")
        it["Quelle"] = cfg_name
        it.pop("Konfiguration", None)
        issues.append(it)
    out = []
    for r in recs:
        # SAP-Schreibweise selbst vereinheitlichen (ältere Versionen von Skript 12 behalten z. B. '804306221')
        r["sap"] = match_key(r["sap"]) or r["sap"]
        if r["sap"] not in SET_115:
            issues.append(dict(Typ="LLM: Baugruppe nicht im 115er-Satz (ignoriert)", Quelle=cfg_name,
                               Datei=path.name, SAP=r["sap"]))
            continue
        if r["excluded"] or r["pred"] is None:
            issues.append(dict(Typ="LLM: keine gültige Vorhersage (EXCLUDED/leer, nicht in Matrix)",
                               Quelle=cfg_name, Datei=path.name, SAP=r["sap"]))
            continue
        if r["pred"].startswith("UNGÜLTIG:"):
            continue  # bereits von read_result_file protokolliert
        g, allowed, reg = gt_info(r["sap"])
        out.append(dict(sap=r["sap"], gt=g, allowed=allowed, regime=reg, pred=r["pred"]))
    return out


# ---------------------------------------------------------------- Matrix
def build_matrix(records):
    """diag[i]: Primärlabel getroffen; red[i,j]: nicht zulässig; green[i,j]: weiteres zulässiges Label."""
    K = len(CLASSES)
    diag = np.zeros(K, int)
    red = np.zeros((K, K), int)
    green = np.zeros((K, K), int)
    for r in records:
        i, j = IDX[r["gt"]], IDX[r["pred"]]
        if r["pred"] == r["gt"]:
            diag[i] += 1
        elif r["pred"] in r["allowed"]:
            green[i, j] += 1
        else:
            red[i, j] += 1
    total = red + green
    total[np.diag_indices(K)] = diag
    return dict(diag=diag, red=red, green=green, total=total, n=int(total.sum()))


def cell_spec(m, i, j):
    """Liste der Zellteile: (Teil, Hintergrund, Zahl, Textfarbe, fett)."""
    if i == j:
        n = int(m["diag"][i])
        return [("full", BLUE_BG, n, DARK_TXT, True)] if n else [("full", WHITE, 0, ZERO_TXT, False)]
    r, g = int(m["red"][i, j]), int(m["green"][i, j])
    if r == 0 and g == 0:
        return [("full", WHITE, 0, ZERO_TXT, False)]
    return [("left", RED_BG if r else WHITE, r, RED_TXT if r else ZERO_TXT, bool(r)),
            ("right", GREEN_BG if g else WHITE, g, GREEN_TXT if g else ZERO_TXT, bool(g))]


# ---------------------------------------------------------------- Zeichnen
TXT = {
    "de": dict(head="GT \\ Pred", diag="Primärlabel getroffen", red="Fehlklassifikation (links)",
               green="zulässiges Alternativlabel (rechts)",
               rows="Zeilen: Primärlabel (finale GT), Spalten: vergebene Klasse. Klassencode: ",
               human="Manuelle Klassifikation (Workshop)", n_h="Klassifikationen", n_l="Baugruppen",
               note="LLM: je Konfiguration ein Lauf (Prompt P3, 115 Baugruppen). Mensch: jede Klassifikation "
                    "im Workshop zählt einmal ({lo}–{hi} Personen je Baugruppe). Absolute Anzahlen."),
    "en": dict(head="GT \\ Pred", diag="Primary label predicted", red="Misclassification (left)",
               green="Other allowed label (right)",
               rows="Rows: primary label (final ground truth), columns: assigned class. Class codes: ",
               human="Human classification (workshop)", n_h="annotations", n_l="assemblies",
               note="LLM: one run per configuration (prompt P3, 115 assemblies). Human: each workshop "
                    "annotation counted once ({lo}–{hi} annotators per assembly). Absolute counts."),
}


def title_for(name, m, lang, human=False):
    t = TXT[lang]
    return f"{name}, n = {m['n']} {t['n_h']}" if human else f"{name}, n = {m['n']}"


def fit_text(ax, t, x0, x1, frac=0.94):
    """Verkleinert die Schrift von t, bis der Text zwischen x0 und x1 (Datenkoordinaten) passt.

    Nötig, weil die Schriftbreite je nach installierter Schrift (Windows: Arial/DejaVu Sans) variiert."""
    r = ax.figure.canvas.get_renderer()
    avail = abs(ax.transData.transform((x1, 0))[0] - ax.transData.transform((x0, 0))[0]) * frac
    w = t.get_window_extent(r).width
    if w > avail > 0:
        t.set_fontsize(t.get_fontsize() * avail / w)


def draw_matrix(ax, m, title, fs=1.0, title_fs=None):
    """Zeichnet eine Matrix im Stil A1 in ax (Koordinaten: x 0..8.3, y 0..8.35, y nach unten)."""
    from matplotlib.patches import Rectangle
    K = len(CLASSES)
    lw, cw = 1.3, 1.0           # Breite Zeilenbeschriftung, Zellbreite
    th, hh, rh = 0.75, 0.6, 0.5 * 1.4  # Titel-, Kopf-, Zeilenhöhe
    W = lw + K * cw
    H = th + hh + K * rh
    ax.set_xlim(0, W)
    ax.set_ylim(H, 0)
    ax.axis("off")

    def box(x, y, w, h, fc, ec=GRID, lw_=0.6, z=1):
        ax.add_patch(Rectangle((x, y), w, h, facecolor=fc, edgecolor=ec, linewidth=lw_, zorder=z))

    box(0, 0, W, th, NAVY, NAVY)
    t = ax.text(W / 2, th / 2, title, ha="center", va="center", color="white", fontsize=12.5 * (title_fs or fs),
                fontweight="bold")
    fit_text(ax, t, 0, W)
    box(0, th, lw, hh, HEAD, HEAD)
    t = ax.text(lw / 2, th + hh / 2, TXT_HEAD, ha="center", va="center", color="white", fontsize=7.9 * fs,
                fontweight="bold")
    fit_text(ax, t, 0, lw, frac=0.9)
    for j, c in enumerate(CODES):
        box(lw + j * cw, th, cw, hh, HEAD, HEAD)
        ax.text(lw + (j + 0.5) * cw, th + hh / 2, c, ha="center", va="center", color="white",
                fontsize=11 * fs, fontweight="bold")
    for i, c in enumerate(CODES):
        y = th + hh + i * rh
        box(0, y, lw, rh, ROWLAB_BG)
        ax.text(lw / 2, y + rh / 2, c, ha="center", va="center", color=DARK_TXT, fontsize=11 * fs, fontweight="bold")
        for j in range(K):
            x = lw + j * cw
            box(x, y, cw, rh, WHITE)
            for part, bg, n, col, bold in cell_spec(m, i, j):
                if part == "full":
                    px, pw = x, cw
                elif part == "left":
                    px, pw = x, cw / 2
                else:
                    px, pw = x + cw / 2, cw / 2
                if bg != WHITE:
                    box(px + 0.02, y + 0.02, pw - 0.04, rh - 0.04, bg, bg, 0, z=2)
                ax.text(px + pw / 2, y + rh / 2, str(n), ha="center", va="center", color=col,
                        fontsize=11 * fs, fontweight="bold" if bold else "normal", zorder=3)


TXT_HEAD = "GT \\ Pred"


def codes_line(lang):
    """Eine Zeile mit den Klassencodes A–G."""
    t = TXT[lang]
    prefix = t["rows"].split(". ", 1)[1].strip()          # "Class codes:" / "Klassencode:"
    return prefix + " " + " | ".join(f"{c} = {n}" for c, n in zip(CODES, LEGEND_NAMES[lang]))


def draw_legend(ax, lang, fs=1.0, codes_max=None):
    """Legende wie A1: Farbfelder, darunter die Klassencodes in einer Zeile.

    Die Schriftgröße der Codezeile wird verkleinert, bis die Zeile in die Breite passt
    (höchstens codes_max pt)."""
    from matplotlib.patches import Patch
    t = TXT[lang]
    ax.axis("off")
    handles = [Patch(facecolor=bg, edgecolor="#BBBBBB", linewidth=0.8, label=lab)
               for bg, lab in [(BLUE_BG, t["diag"]), (RED_BG, t["red"]), (GREEN_BG, t["green"])]]
    leg = ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(0, 1.0), ncol=3, frameon=False,
                    fontsize=11 * fs, handlelength=1.5, handleheight=1.1, columnspacing=2.2,
                    borderaxespad=0, borderpad=0, handletextpad=0.6)
    leg._legend_box.align = "left"
    size = codes_max or 9.5 * fs
    txt = ax.annotate(codes_line(lang), xy=(0, 1), xycoords="axes fraction", xytext=(0, -2.3 * 11 * fs),
                      textcoords="offset points", va="top", ha="left", fontsize=size)
    fig = ax.figure
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    avail = ax.get_window_extent(r).width
    width = txt.get_window_extent(r).width
    if width > avail:
        txt.set_fontsize(size * avail / width * 0.98)


def save_single(m, title, path, lang, hf=1.0):
    """hf: Höhenfaktor der Matrix (1.0 = ursprüngliche Zeilenhöhe)."""
    import matplotlib.pyplot as plt
    fig = plt.figure(figsize=(8.6, 4.7 * hf + 0.8))
    gs = fig.add_gridspec(2, 1, height_ratios=[4.7 * hf, 0.8], hspace=0.05 / hf)
    draw_matrix(fig.add_subplot(gs[0]), m, title)
    draw_legend(fig.add_subplot(gs[1]), lang, fs=1.05)
    fig.savefig(path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def save_overview(llm_mats, human_mat, path, lang, hf=1.0):
    """hf: Höhenfaktor der Matrizen (1.0 = ursprüngliche Zeilenhöhe)."""
    import matplotlib.pyplot as plt
    fig = plt.figure(figsize=(16, 8.4 * hf + 1.1))
    gs = fig.add_gridspec(3, 3, height_ratios=[4.2 * hf, 4.2 * hf, 1.1], width_ratios=[1, 1, 2.08],
                          hspace=0.08, wspace=0.05)
    pos = [(0, 0), (0, 1), (1, 0), (1, 1)]
    for (r, c), (name, m) in zip(pos, llm_mats):
        draw_matrix(fig.add_subplot(gs[r, c]), m, title_for(name, m, lang), fs=0.92)
    draw_matrix(fig.add_subplot(gs[0:2, 2]), human_mat, title_for(TXT[lang]["human"], human_mat, lang, True),
                fs=1.55, title_fs=1.2)
    draw_legend(fig.add_subplot(gs[2, :]), lang, fs=1.75)
    fig.savefig(path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)


# ---------------------------------------------------------------- Excel
def matrix_frames(m):
    idx = [f"{c} {k}" for c, k in ORDER]
    tot = pd.DataFrame(m["total"], index=idx, columns=CODES)
    tot["Summe"] = tot.sum(axis=1)
    tot.loc["Summe"] = tot.sum(axis=0)
    red = pd.DataFrame(m["red"], index=idx, columns=CODES)
    green = pd.DataFrame(m["green"], index=idx, columns=CODES)
    return tot, red, green


def summary_row(name, m, n_bg):
    n = m["n"]
    d, g, r = int(m["diag"].sum()), int(m["green"].sum()), int(m["red"].sum())
    return {"Matrix": name, "n (Einträge)": n, "Baugruppen": n_bg, "Diagonale (Primärlabel)": d,
            "grün (weiteres zulässiges Label)": g, "rot (nicht zulässig)": r,
            "Allowed Accuracy %": round(100 * (d + g) / n, 1) if n else None,
            "Strict Accuracy %": round(100 * d / n, 1) if n else None}


def autosize(ws):
    from openpyxl.styles import Font
    for c in ws[1]:
        c.font = Font(bold=True)
    for col in ws.columns:
        width = max(len(str(c.value)) if c.value is not None else 0 for c in col)
        ws.column_dimensions[col[0].column_letter].width = min(max(8, width + 2), 70)


def write_excel(path, mats, summ, checks):
    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        pd.DataFrame(summ).to_excel(xw, sheet_name="Uebersicht", index=False)
        long = []
        for sheet, name, m in mats:
            tot, red, green = matrix_frames(m)
            r0 = 0
            for lab, frame in [("Gesamt (Diagonale = Primärlabel)", tot), ("rot: nicht zulässig", red),
                               ("grün: weiteres zulässiges Label", green)]:
                pd.DataFrame([[f"{name} – {lab}"]]).to_excel(xw, sheet_name=sheet, startrow=r0, index=False, header=False)
                frame.to_excel(xw, sheet_name=sheet, startrow=r0 + 1)
                r0 += len(frame) + 4
            for i, (ci, ki) in enumerate(ORDER):
                for j, (cj, kj) in enumerate(ORDER):
                    long.append({"Matrix": name, "GT-Code": ci, "GT (Primärlabel)": ki, "Pred-Code": cj,
                                 "Vorhersage": kj, "Anzahl": int(m["total"][i, j]),
                                 "Diagonale": int(m["diag"][i]) if i == j else 0,
                                 "rot": int(m["red"][i, j]), "grün": int(m["green"][i, j])})
        pd.DataFrame(long).to_excel(xw, sheet_name="Lang", index=False)
        for sheet, frame in checks:
            frame.to_excel(xw, sheet_name=sheet, index=False)
        pd.DataFrame({"Code": CODES, "Klasse (GT-Schreibweise)": CLASSES,
                      "Kurzname de": LEGEND_NAMES["de"], "Name en": LEGEND_NAMES["en"]}).to_excel(
            xw, sheet_name="Legende", index=False)
        for ws in xw.book.worksheets:
            if ws.title in {"Uebersicht", "Lang", "Legende"} or ws.title.startswith("Pruefung"):
                autosize(ws)


# ---------------------------------------------------------------- Hauptprogramm
def run(args):
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    issues = []

    ann, other, meta = read_workshop(args.workshop, args.sheet, issues)
    llm = []
    for arg, name, expect in CONFIGS:
        llm.append((name, read_llm(getattr(args, arg), name, expect, issues)))

    human_m = build_matrix(ann)
    llm_m = [(name, build_matrix(recs)) for name, recs in llm]

    # ---------------- Prüfungen
    per_bg = defaultdict(list)
    for a in ann:
        per_bg[a["sap"]].append(a["participant"])
    llm_pred = {name: {r["sap"]: r["pred"] for r in recs} for name, recs in llm}
    bg_rows = []
    for k in MAIN_115:
        g, allowed, reg = gt_info(k)
        n = len(per_bg.get(k, []))
        row = {"SAP": k, "Primärlabel": g, "Code": CODES[IDX[g]], "Regime": reg,
               "zulässige Labels": ", ".join(sorted(allowed - {g})) or "—",
               "Anzahl Personen": n, "Personen": ", ".join(per_bg.get(k, [])),
               "5–10 Personen": "ok" if 5 <= n <= 10 else "PRÜFEN"}
        for name, _ in llm:
            row[name] = llm_pred[name].get(k, "FEHLT")
        bg_rows.append(row)
        if n == 0:
            issues.append(dict(Typ="Mensch: keine Klassifikation für Baugruppe", Quelle="Workshop", SAP=k))
        elif not 5 <= n <= 10:
            issues.append(dict(Typ="Mensch: Anzahl Personen außerhalb 5–10", Quelle="Workshop", SAP=k, Detail=str(n)))
        for name, _ in llm:
            if k not in llm_pred[name]:
                issues.append(dict(Typ="LLM: keine Vorhersage für Baugruppe", Quelle=name, SAP=k))

    part = Counter(a["participant"] for a in ann)
    part_other = Counter((o["participant"], o["subset"]) for o in other)
    tn_rows = []
    for p in meta["tn_cols"]:
        tn_rows.append({"Teilnehmer (Spalte)": p, "Klassifikationen 115 BG": part.get(p, 0),
                        "Vorversuch (14)": part_other.get((p, "Vorversuch (14)"), 0),
                        "Ergänzung (70)": part_other.get((p, "Ergänzung (70)"), 0)})

    n_pre = sum(1 for o in other if o["subset"] == "Vorversuch (14)")
    n_supp = sum(1 for o in other if o["subset"] == "Ergänzung (70)")
    n_counts = Counter(len(per_bg.get(k, [])) for k in MAIN_115)
    regimes = Counter(gt_info(k)[2] for k in MAIN_115)
    typ_counts = Counter(i["Typ"] for i in issues)
    summary = [
        ("Workshop-Datei", str(args.workshop)), ("Blatt", meta["sheet"]),
        ("Teilnehmerspalten (TN_…)", len(meta["tn_cols"])),
        ("Klassifikationen in der Mensch-Matrix (115 BG)", human_m["n"]),
        ("Klassifikationen Vorversuch (14 BG, nicht verwendet)", n_pre),
        ("Klassifikationen 129 BG gesamt (zum Vergleich mit früheren 895)", human_m["n"] + n_pre),
        ("Klassifikationen Ergänzungsdatensatz (nicht verwendet)", n_supp),
        ("Baugruppen mit ≥1 Klassifikation", sum(1 for k in MAIN_115 if per_bg.get(k))),
        ("Personen je Baugruppe: min / max", f"{min(n_counts)} / {max(n_counts)}"),
        ("Verteilung Personen je BG", ", ".join(f"{k}: {v}" for k, v in sorted(n_counts.items()))),
        ("Regime 115 BG (erwartet 51/34/30)", f"E1 {regimes['E1']} / E2 {regimes['E2']} / M {regimes['M']}"),
    ]
    for name, recs in llm:
        p = Path(getattr(args, [c[0] for c in CONFIGS if c[1] == name][0]))
        summary.append((f"{name}: Datei", str(p)))
        summary.append((f"{name}: Vorhersagen in Matrix", f"{len(recs)} von 115"))
    for t, c in sorted(typ_counts.items()):
        summary.append((f"Hinweis: {t}", c))
    summ_df = pd.DataFrame(summary, columns=["Prüfung", "Wert"])

    issue_cols = ["Typ", "Quelle", "Datei", "ExcelZeile", "SAP", "Teilnehmer", "Detail"]
    iss_df = pd.DataFrame(issues)
    for c in issue_cols:
        if c not in iss_df.columns:
            iss_df[c] = ""
    iss_df = iss_df[issue_cols]
    gt_repl = iss_df[iss_df["Typ"].str.contains("finale GT", na=False)]
    unknown = iss_df[iss_df["Typ"].str.contains("nicht erkannt|Ungültig", case=False, na=False)]

    # ---------------- Ausgaben
    lang = args.lang
    summ = [summary_row(TXT[lang]["human"], human_m, sum(1 for k in MAIN_115 if per_bg.get(k)))]
    summ += [summary_row(name, m, len({r["sap"] for r in recs})) for (name, m), (_, recs) in zip(llm_m, llm)]
    sheets = [("M_Mensch", TXT[lang]["human"], human_m)]
    short = {"Claude Haiku 4.5 (PDF)": "M_Haiku", "Gemini 2.5 Pro (PDF)": "M_Gemini",
             "GPT-5.5 (Image)": "M_GPT", "DeepSeek-V4-Flash (Text)": "M_DeepSeek"}
    sheets += [(short[name], name, m) for name, m in llm_m]
    checks = [("Pruefung_Zusammenfassung", summ_df), ("Pruefung_BG", pd.DataFrame(bg_rows)),
              ("Pruefung_Teilnehmer", pd.DataFrame(tn_rows)), ("Pruefung_GT_ersetzt", gt_repl),
              ("Pruefung_Labels_unbekannt", unknown), ("Pruefung_Hinweise", iss_df)]
    xlsx = out / "Konfusion_Mensch_LLM.xlsx"
    write_excel(xlsx, sheets, summ, checks)

    pngs = []
    try:
        import matplotlib
        matplotlib.use("Agg")
        matplotlib.rcParams["font.family"] = "sans-serif"
        matplotlib.rcParams["font.sans-serif"] = ["Arial", "Liberation Sans", "Helvetica", "DejaVu Sans"]
        files = {"M_Mensch": "konfusion_mensch.png", "M_Haiku": "konfusion_haiku.png",
                 "M_Gemini": "konfusion_gemini.png", "M_GPT": "konfusion_gpt.png",
                 "M_DeepSeek": "konfusion_deepseek.png"}
        for sheet, name, m in sheets:
            p = out / files[sheet]
            save_single(m, title_for(name, m, lang, human=(sheet == "M_Mensch")), p, lang, args.height)
            pngs.append(p)
        p = out / "konfusion_gesamt.png"
        save_overview(llm_m, human_m, p, lang, args.height)
        pngs.append(p)
    except ImportError:
        print("matplotlib nicht installiert: keine PNGs erzeugt.")

    print(f"Mensch: {human_m['n']} Klassifikationen auf {sum(1 for k in MAIN_115 if per_bg.get(k))} BG "
          f"(Personen je BG {min(n_counts)}–{max(n_counts)}); Vorversuch {n_pre}, Ergänzung {n_supp}.")
    for name, m in llm_m:
        print(f"{name}: n = {m['n']}")
    print(f"{len(issues)} Hinweise (Blatt 'Pruefung_Hinweise').")
    for t, c in sorted(typ_counts.items()):
        print(f"  {c:4d}  {t}")
    print(f"Ausgabe: {out.resolve()}")
    return dict(human=human_m, llm=dict(llm_m), issues=issues, bg=bg_rows, xlsx=xlsx, pngs=pngs,
                n_pre=n_pre, n_supp=n_supp)


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workshop", required=True, help="Excel-Datei der Workshop-Auswertung")
    ap.add_argument("--sheet", default="Klassifikation_Übersicht_Gesamt", help="Blattname (Standard: %(default)s)")
    ap.add_argument("--haiku", required=True, help="Ergebnisdatei Claude Haiku 4.5, PDF (Input-Vergleich, P3)")
    ap.add_argument("--gemini", required=True, help="Ergebnisdatei Gemini 2.5 Pro, PDF (Input-Vergleich, P3)")
    ap.add_argument("--gpt", required=True, help="Ergebnisdatei GPT-5.5, Bild (Stabilität, Lauf 1)")
    ap.add_argument("--deepseek", required=True, help="Ergebnisdatei DeepSeek-V4-Flash, Text (Stabilität, Lauf 1)")
    ap.add_argument("--out", default="Konfusion_Mensch_LLM", help="Ausgabeordner (Standard: %(default)s)")
    ap.add_argument("--lang", choices=["en", "de"], default="en", help="Sprache der Abbildungen (Standard: en)")
    ap.add_argument("--height", type=float, default=0.7,
                    help="Höhenfaktor der Matrizen (1.0 = höhere Zeilen; Standard: %(default)s)")
    return ap.parse_args(argv)


if __name__ == "__main__":
    run(parse_args())
