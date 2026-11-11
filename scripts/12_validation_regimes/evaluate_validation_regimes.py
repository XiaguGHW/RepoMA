#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
evaluate_validation_regimes.py

Berechnet die Ergebnisse für Abschnitt 5.6 (offline, keine Modellaufrufe):

  Tabelle 5.6  Validierung: E1+E2 im Primärdatensatz (115 BG, Mittel über 10 Läufe)
               gegen E1+E2 im Ergänzungsdatensatz (70 BG, 1 Lauf), je Konfiguration
  Tabelle 5.7  Alle 185 BG zusammen, getrennt nach E1, E2 und M

Zusammenführung je Baugruppe: Für die 115 BG zählt der Anteil korrekter Läufe
(z. B. 9 von 10 = 0,9), für die 70 BG 1 oder 0. Mittelwerte und Bootstrap-CIs
werden über Baugruppen gebildet (jede Baugruppe gleich gewichtet).

Regime je Baugruppe (finale GT):
  M  = mehr als ein zulässiges Label (Ground Truth + Weitere zulässige Ground Truth)
  E1 / E2 = aus der Spalte "Register"; steht dort "M", gibt es aber keine
            weitere zulässige Klasse, wird E2 verwendet (Entscheidung zu 0804EN7325).

Aufruf (Windows, PowerShell):
  python evaluate_validation_regimes.py --main "C:\\...\\Downloads\\test_claude" --supp "C:\\...\\Downloads\\70BG_Ergebnisse"

Ausgabe: Validation_Regimes.xlsx im aktuellen Ordner (oder --out).
Benötigt: pandas, numpy, openpyxl
"""

import argparse
import re
import sys
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

N_BOOT = 2000
SEED = 42
CI = (2.5, 97.5)

CLASSES = [
    "Greifer",
    "Lineareinheit",
    "Rotationseinheit",
    "Roboter",
    "Multi-Achs-System (Gantry)",
    "Kombinierte Einheit",
    "Keine der verfügbaren Klassen",
]
SYNONYMS = {
    "gantry": "Multi-Achs-System (Gantry)",
    "umsetzeinheit": "Kombinierte Einheit",
    "keine der verfgbaren klassen": "Keine der verfügbaren Klassen",
}
# Zuordnung Ordner-/Dateiname -> Konfiguration (Reihenfolge = Tabellenreihenfolge)
CONFIGS = [
    ("Claude Haiku 4.5 (PDF)", "haiku"),
    ("DeepSeek-V4-Flash (Text)", "deepseek"),
    ("Gemini 2.5 Pro (PDF)", "gemini-2.5-pro"),
    ("GPT-5.5 (Image)", "gpt-5.5"),
]

# Finale Ground Truth (Stufe C, nach dem Review nach den LLM-Experimenten) aus
# thesis/classification_data_and_revision_statistics.md: SAP -> [GT, Register, weitere zulässige].
# Ohne SAP-Nummer: Schlüssel "TC:<Teamcenter>". Diese Werte haben Vorrang vor den Ergebnisdateien;
# Abweichungen werden im Blatt "Pruefungen" protokolliert.
FINAL_GT = {
"0804FC1588": [
"Multi-Achs-System (Gantry)",
"M",
[
"Kombinierte Einheit"
]
],
"0804FA3834": [
"Rotationseinheit",
"E1",
[]
],
"0804BR4641": [
"Roboter",
"E1",
[]
],
"0804KM9320": [
"Greifer",
"E1",
[]
],
"0804FZ8322": [
"Lineareinheit",
"E1",
[]
],
"0804FM8785": [
"Roboter",
"E1",
[]
],
"0804KZ9027": [
"Kombinierte Einheit",
"M",
[
"Lineareinheit"
]
],
"0804KK0664": [
"Greifer",
"E1",
[]
],
"0804CW9430": [
"Roboter",
"E1",
[]
],
"0804KZ1155": [
"Greifer",
"E1",
[]
],
"0804HZ8350": [
"Multi-Achs-System (Gantry)",
"E1",
[]
],
"0804KZ8712": [
"Lineareinheit",
"E1",
[]
],
"0804KE7723": [
"Multi-Achs-System (Gantry)",
"E1",
[]
],
"0804JL8049": [
"Greifer",
"E1",
[]
],
"0804JU4254": [
"Rotationseinheit",
"E1",
[]
],
"0804KW6842": [
"Greifer",
"E1",
[]
],
"0804KT1289": [
"Lineareinheit",
"E1",
[]
],
"0804KW1502": [
"Lineareinheit",
"E1",
[]
],
"0804KY7179": [
"Lineareinheit",
"E1",
[]
],
"0804FF2025": [
"Roboter",
"E1",
[]
],
"0804KM8175": [
"Lineareinheit",
"E1",
[]
],
"0804KR0143": [
"Multi-Achs-System (Gantry)",
"E1",
[]
],
"0804KY3585": [
"Multi-Achs-System (Gantry)",
"E1",
[]
],
"0804DT6452": [
"Multi-Achs-System (Gantry)",
"M",
[
"Keine der verfügbaren Klassen"
]
],
"0804FR1463": [
"Rotationseinheit",
"E1",
[]
],
"0804EC1049": [
"Roboter",
"E1",
[]
],
"0804LG8766": [
"Greifer",
"E1",
[]
],
"0804GD6171": [
"Roboter",
"E1",
[]
],
"0804JD0275": [
"Greifer",
"E2",
[]
],
"0804FK2694": [
"Multi-Achs-System (Gantry)",
"E2",
[]
],
"0804JL8434": [
"Roboter",
"M",
[
"Kombinierte Einheit"
]
],
"0804KB2225": [
"Rotationseinheit",
"M",
[
"Keine der verfügbaren Klassen"
]
],
"0804KY5559": [
"Greifer",
"E2",
[]
],
"0804HK5576": [
"Roboter",
"M",
[
"Kombinierte Einheit"
]
],
"0804KR6993": [
"Lineareinheit",
"E2",
[]
],
"0804LH5422": [
"Kombinierte Einheit",
"E2",
[]
],
"0804KZ5637": [
"Greifer",
"E2",
[]
],
"0804KR9668": [
"Greifer",
"M",
[
"Keine der verfügbaren Klassen"
]
],
"0804JU56371": [
"Roboter",
"M",
[
"Kombinierte Einheit"
]
],
"0804AY8008": [
"Kombinierte Einheit",
"E2",
[]
],
"0804EU0861": [
"Roboter",
"M",
[
"Kombinierte Einheit"
]
],
"0804GE7738": [
"Rotationseinheit",
"M",
[
"Kombinierte Einheit"
]
],
"0804DU5323": [
"Multi-Achs-System (Gantry)",
"E2",
[]
],
"0804GV7647": [
"Kombinierte Einheit",
"E2",
[]
],
"0804EB6690": [
"Kombinierte Einheit",
"E2",
[]
],
"0804306221": [
"Kombinierte Einheit",
"E2",
[]
],
"0804KZ9209": [
"Lineareinheit",
"E2",
[]
],
"0804DN9616": [
"Multi-Achs-System (Gantry)",
"E2",
[]
],
"0804LB1151": [
"Lineareinheit",
"M",
[
"Multi-Achs-System (Gantry)",
"Kombinierte Einheit"
]
],
"0804CE5532": [
"Kombinierte Einheit",
"E2",
[]
],
"0804FU6515": [
"Kombinierte Einheit",
"E2",
[]
],
"0804GY2576": [
"Kombinierte Einheit",
"M",
[
"Multi-Achs-System (Gantry)"
]
],
"0804KM9359": [
"Rotationseinheit",
"E2",
[]
],
"0804CH8012": [
"Kombinierte Einheit",
"E2",
[]
],
"0804KB7256": [
"Rotationseinheit",
"E2",
[]
],
"0804AR3766": [
"Rotationseinheit",
"M",
[
"Greifer"
]
],
"0804HX0679": [
"Rotationseinheit",
"E2",
[]
],
"0804KZ9488": [
"Kombinierte Einheit",
"E2",
[]
],
"0804DU5389": [
"Multi-Achs-System (Gantry)",
"M",
[
"Kombinierte Einheit"
]
],
"0804GY2577": [
"Kombinierte Einheit",
"E2",
[]
],
"0804LG6553": [
"Multi-Achs-System (Gantry)",
"E1",
[]
],
"0804KY6491": [
"Lineareinheit",
"E1",
[]
],
"0804FH4760": [
"Roboter",
"E1",
[]
],
"0804KS8037": [
"Multi-Achs-System (Gantry)",
"E1",
[]
],
"0804KR9943": [
"Kombinierte Einheit",
"E1",
[]
],
"0804EK1683": [
"Roboter",
"E1",
[]
],
"0804LU7362": [
"Keine der verfügbaren Klassen",
"E1",
[]
],
"0804KT2332": [
"Greifer",
"E1",
[]
],
"0804EV7706": [
"Roboter",
"E1",
[]
],
"0804KY9594": [
"Lineareinheit",
"E1",
[]
],
"0804KU2401": [
"Lineareinheit",
"E1",
[]
],
"0804LH9239": [
"Keine der verfügbaren Klassen",
"E1",
[]
],
"0804LB3626": [
"Lineareinheit",
"E1",
[]
],
"0804KW6429": [
"Multi-Achs-System (Gantry)",
"E1",
[]
],
"0804KB9919": [
"Greifer",
"E1",
[]
],
"0804KU7061": [
"Keine der verfügbaren Klassen",
"E1",
[]
],
"0804JT7787": [
"Keine der verfügbaren Klassen",
"E1",
[]
],
"0804EA6409": [
"Roboter",
"E1",
[]
],
"0804FR8437": [
"Roboter",
"E1",
[]
],
"0804CC3075": [
"Roboter",
"E1",
[]
],
"0804KU9472": [
"Greifer",
"E1",
[]
],
"0804LY4947": [
"Lineareinheit",
"E1",
[]
],
"0804KT8575": [
"Roboter",
"E1",
[]
],
"0804MA9380": [
"Lineareinheit",
"E2",
[]
],
"0804LY8514": [
"Rotationseinheit",
"E2",
[]
],
"0804MA7037": [
"Keine der verfügbaren Klassen",
"E2",
[]
],
"0804KV4964": [
"Greifer",
"M",
[
"Keine der verfügbaren Klassen"
]
],
"0804JK8878": [
"Greifer",
"M",
[
"Lineareinheit"
]
],
"0804LZ1241": [
"Rotationseinheit",
"E1",
[]
],
"3843CE1617": [
"Multi-Achs-System (Gantry)",
"E1",
[]
],
"0804GZ3046": [
"Rotationseinheit",
"E1",
[]
],
"0804DY2146": [
"Rotationseinheit",
"E1",
[]
],
"0804JX5741": [
"Multi-Achs-System (Gantry)",
"E1",
[]
],
"0804LC3026": [
"Greifer",
"E1",
[]
],
"0804FL5283": [
"Roboter",
"E1",
[]
],
"0804FT6844": [
"Kombinierte Einheit",
"E2",
[]
],
"0804EZ0597": [
"Kombinierte Einheit",
"E2",
[]
],
"0804KX4663": [
"Roboter",
"M",
[
"Kombinierte Einheit"
]
],
"0804JX5476": [
"Rotationseinheit",
"M",
[
"Keine der verfügbaren Klassen"
]
],
"0804KV0861": [
"Greifer",
"M",
[
"Rotationseinheit"
]
],
"0804HL3088": [
"Rotationseinheit",
"E2",
[]
],
"0804HH8872": [
"Kombinierte Einheit",
"E2",
[]
],
"0804JX8777": [
"Keine der verfügbaren Klassen",
"E2",
[]
],
"0804LM2565": [
"Keine der verfügbaren Klassen",
"E2",
[]
],
"0804LW3879": [
"Lineareinheit",
"M",
[
"Kombinierte Einheit"
]
],
"0804HK2005": [
"Greifer",
"M",
[
"Rotationseinheit"
]
],
"0804LM8093": [
"Rotationseinheit",
"E2",
[]
],
"0804KY7178": [
"Lineareinheit",
"M",
[
"Kombinierte Einheit"
]
],
"0804LA7293": [
"Kombinierte Einheit",
"E2",
[]
],
"0804CM8667": [
"Rotationseinheit",
"M",
[
"Kombinierte Einheit"
]
],
"0804EN7325": [
"Kombinierte Einheit",
"E2",
[]
],
"0804LK3617": [
"Rotationseinheit",
"M",
[
"Kombinierte Einheit"
]
],
"0804GT0312": [
"Kombinierte Einheit",
"E2",
[]
],
"0804MB2849": [
"Lineareinheit",
"M",
[
"Kombinierte Einheit"
]
],
"0804KU1528": [
"Greifer",
"M",
[
"Lineareinheit"
]
],
"3842998383": [
"Keine der verfügbaren Klassen",
"E2",
[]
],
"0804KV2157": [
"Kombinierte Einheit",
"E2",
[]
],
"0804GT5112": [
"Kombinierte Einheit",
"E1",
[]
],
"0804GA4441": [
"Keine der verfügbaren Klassen",
"E1",
[]
],
"0804LR0554": [
"Lineareinheit",
"M",
[
"Kombinierte Einheit"
]
],
"0804JL5526": [
"Lineareinheit",
"M",
[
"Keine der verfügbaren Klassen"
]
],
"0804LE2661": [
"Greifer",
"M",
[
"Kombinierte Einheit"
]
],
"0804AF9667": [
"Multi-Achs-System (Gantry)",
"M",
[
"Kombinierte Einheit"
]
],
"0804LV8630": [
"Rotationseinheit",
"M",
[
"Kombinierte Einheit"
]
],
"0804BD5654": [
"Kombinierte Einheit",
"E2",
[]
],
"0804CC2134": [
"Roboter",
"M",
[
"Kombinierte Einheit"
]
],
"0804JX6656": [
"Multi-Achs-System (Gantry)",
"M",
[
"Kombinierte Einheit",
"Keine der verfügbaren Klassen"
]
],
"0804KW8391": [
"Multi-Achs-System (Gantry)",
"M",
[
"Kombinierte Einheit",
"Keine der verfügbaren Klassen"
]
],
"0804FT0436": [
"Lineareinheit",
"E1",
[]
],
"0804JK3979": [
"Lineareinheit",
"E1",
[]
],
"0804AG8297": [
"Lineareinheit",
"E1",
[]
],
"0804LM7661": [
"Multi-Achs-System (Gantry)",
"E1",
[]
],
"0804KE6397": [
"Roboter",
"E1",
[]
],
"0804KV5835": [
"Lineareinheit",
"E2",
[]
],
"0804LC5647": [
"Kombinierte Einheit",
"E2",
[]
],
"0804LW4010": [
"Rotationseinheit",
"E1",
[]
],
"TC:AS00235507": [
"Keine der verfügbaren Klassen",
"E1",
[]
],
"0804358312": [
"Keine der verfügbaren Klassen",
"E2",
[]
],
"0804LR7381": [
"Greifer",
"E1",
[]
],
"0804LW5713": [
"Keine der verfügbaren Klassen",
"E1",
[]
],
"0804KC4801": [
"Keine der verfügbaren Klassen",
"E1",
[]
],
"0804LD6387": [
"Keine der verfügbaren Klassen",
"E1",
[]
],
"0804LS4641": [
"Rotationseinheit",
"E1",
[]
],
"0804KL2297": [
"Keine der verfügbaren Klassen",
"E1",
[]
],
"0804MA1736": [
"Roboter",
"E1",
[]
],
"0804MA6689": [
"Roboter",
"E1",
[]
],
"0804LN1286": [
"Greifer",
"E1",
[]
],
"0804LN1294": [
"Greifer",
"E1",
[]
],
"0804LN1297": [
"Greifer",
"E1",
[]
],
"0804FE3750": [
"Lineareinheit",
"E2",
[]
],
"TC:AS00215660": [
"Keine der verfügbaren Klassen",
"E1",
[]
],
"1800257228": [
"Keine der verfügbaren Klassen",
"E1",
[]
],
"0804LK4678": [
"Kombinierte Einheit",
"E1",
[]
],
"0804MB2648": [
"Roboter",
"E1",
[]
],
"0804LG2192": [
"Roboter",
"E1",
[]
],
"1800257479": [
"Keine der verfügbaren Klassen",
"E1",
[]
],
"3843AV9602": [
"Keine der verfügbaren Klassen",
"E1",
[]
],
"3843AB4237": [
"Roboter",
"E1",
[]
],
"1800257202": [
"Keine der verfügbaren Klassen",
"E1",
[]
],
"0804JS9252": [
"Keine der verfügbaren Klassen",
"E1",
[]
],
"1800257521": [
"Keine der verfügbaren Klassen",
"E1",
[]
],
"0804LE7880": [
"Multi-Achs-System (Gantry)",
"E2",
[]
],
"0804KU1103": [
"Greifer",
"E2",
[]
],
"0804AT5037": [
"Kombinierte Einheit",
"E1",
[]
],
"0804LB4468": [
"Rotationseinheit",
"E1",
[]
],
"0804LU7693": [
"Lineareinheit",
"M",
[
"Kombinierte Einheit"
]
],
"0804BN2123": [
"Lineareinheit",
"E1",
[]
],
"3843106114": [
"Keine der verfügbaren Klassen",
"E1",
[]
],
"0804LL3638": [
"Multi-Achs-System (Gantry)",
"E1",
[]
],
"0804EM7937": [
"Lineareinheit",
"E1",
[]
],
"3843CD1070": [
"Keine der verfügbaren Klassen",
"E1",
[]
],
"0804LZ1881": [
"Rotationseinheit",
"E1",
[]
],
"0804LL8077": [
"Roboter",
"E1",
[]
],
"0804KA8953": [
"Rotationseinheit",
"E2",
[]
],
"0804KF8538": [
"Roboter",
"E1",
[]
],
"0804LF6209": [
"Greifer",
"E1",
[]
],
"0804MB8153": [
"Greifer",
"E2",
[]
],
"0804LX7355": [
"Multi-Achs-System (Gantry)",
"E1",
[]
],
"3843AZ5880": [
"Keine der verfügbaren Klassen",
"E1",
[]
],
"0804GR4842": [
"Greifer",
"E2",
[]
],
"0804KB9727": [
"Rotationseinheit",
"E1",
[]
],
"0804MC3545": [
"Lineareinheit",
"E1",
[]
],
"0804JF2622": [
"Lineareinheit",
"E1",
[]
],
"0804LS3667": [
"Rotationseinheit",
"E1",
[]
],
"0804LN1289": [
"Greifer",
"E1",
[]
],
"0804KD4277": [
"Rotationseinheit",
"E1",
[]
],
"0804LN1287": [
"Greifer",
"E1",
[]
],
"0804AF6207": [
"Kombinierte Einheit",
"E1",
[]
],
"0804JC9184": [
"Roboter",
"E1",
[]
],
"0804LM0799": [
"Lineareinheit",
"E1",
[]
],
"0804LH2249": [
"Keine der verfügbaren Klassen",
"E1",
[]
],
"0804LK3474": [
"Rotationseinheit",
"E1",
[]
],
"0804HD4595": [
"Rotationseinheit",
"E1",
[]
],
"0804JR9924": [
"Keine der verfügbaren Klassen",
"E1",
[]
],
"TC:AX01253877": [
"Keine der verfügbaren Klassen",
"E1",
[]
],
"1800257200": [
"Keine der verfügbaren Klassen",
"E1",
[]
],
"0804KX6885": [
"Multi-Achs-System (Gantry)",
"E1",
[]
],
"0804JW4969": [
"Roboter",
"E1",
[]
],
"0804AH9298": [
"Kombinierte Einheit",
"E2",
[]
]
}

# 57 Baugruppen der bisherigen Fehleranalyse (Blatt "Korrigierte GT&ZGT", Input-Vergleich, 12 Läufe)
FEHLERANALYSE_57 = ['0804EN7325', '0804FC1588', '0804LV8630', '804306221', '0804GE7738', '0804GT0312', '0804MB2849', '0804DN9616', '0804EB6690', '0804GT5112', '0804JX6656', '0804KM9359', '0804KW8391', '0804LK3617', '0804HZ8350', '0804KY3585', '0804CC2134', '0804EK1683', '0804FT0436', '0804GD6171', '0804FH4760', '0804HH8872', '0804HX0679', '0804KE7723', '0804KY7178', '0804KZ9027', '0804AR3766', '0804DT6452', '0804KB7256', '0804KU2401', '0804KY7179', '0804KZ9488', '0804LA7293', '0804LH9239', '0804AF9667', '0804AY8008', '0804CE5532', '0804EV7706', '0804FK2694', '0804FT6844', '0804FU6515', '0804GA4441', '0804GY2577', '0804GZ3046', '0804JL5526', '0804JU56371', '0804KK0664', '0804KM8175', '0804KS8037', '0804KT1289', '0804KV2157', '0804KZ8712', '0804LB3626', '0804LE2661', '0804LZ1241', '3842998383', '3843CE1617']

SKIP_PREFIX = ("~$", "PPT_", "Evaluation_", "Validation_", "nachlauf_")


# ---------------------------------------------------------------- Labels
def _norm(s):
    s = unicodedata.normalize("NFC", str(s)).replace("\u00a0", " ")
    return re.sub(r"\s+", " ", s).strip().lower()


LOOKUP = {_norm(c): c for c in CLASSES}
LOOKUP.update({_norm(k): v for k, v in SYNONYMS.items()})


def is_empty(x):
    if x is None:
        return True
    if isinstance(x, float) and np.isnan(x):
        return True
    s = str(x).strip()
    return s == "" or s.lower() in {"nan", "none", "—", "-"}


def canon(x):
    """Kanonischer Klassenname, None bei leer, 'UNGÜLTIG:<text>' sonst."""
    if is_empty(x):
        return None
    s = re.sub(r"^\[[A-Ga-g]\]\s*", "", str(x).strip())
    n = _norm(s)
    if n in LOOKUP:
        return LOOKUP[n]
    if n.startswith("keine der"):
        return "Keine der verfügbaren Klassen"
    return f"UNGÜLTIG:{s}"


# ---------------------------------------------------------------- Einlesen
def find_col(cols, exact=None, contains=None):
    if exact:
        for c in cols:
            if str(c).strip().lower() == exact.lower():
                return c
    if contains:
        for c in cols:
            if all(t.lower() in str(c).lower() for t in contains):
                return c
    return None


def read_result_file(path, issues, cfg, source, run):
    xl = pd.ExcelFile(path)
    sheet = "Sheet1" if "Sheet1" in xl.sheet_names else xl.sheet_names[0]
    df = pd.read_excel(path, sheet_name=sheet, dtype=str)
    cols = list(df.columns)
    c_sap = find_col(cols, contains=["sap"])
    c_tc = find_col(cols, contains=["teamcenter"])
    c_gt = find_col(cols, exact="Ground Truth")
    c_alt = find_col(cols, contains=["weitere"])
    c_pred = find_col(cols, contains=["predicted"])
    c_stat = find_col(cols, contains=["allowed", "status"])
    c_reg = find_col(cols, exact="Register")
    c_pe = find_col(cols, contains=["prompt", "engineering"])
    c_name = find_col(cols, contains=["benennung", "(e)"]) or find_col(cols, contains=["benennung"])
    if not (c_sap and c_gt and c_pred):
        sys.exit(f"Spalten nicht gefunden in {path.name} (Blatt {sheet}): {cols}")
    if c_reg is None:
        issues.append(dict(Typ="Spalte Register fehlt (Regime aus finaler GT)", Konfiguration=cfg, Quelle=source, Datei=path.name))

    recs = []
    seen = set()
    for i, row in df.iterrows():
        if is_empty(row[c_gt]):
            continue
        if c_pe is not None and not is_empty(row[c_pe]) and str(row[c_pe]).strip().lower() == "yes":
            continue
        sap = "" if is_empty(row[c_sap]) else str(row[c_sap]).strip()
        if not sap and c_tc is not None and not is_empty(row[c_tc]):
            sap = "TC:" + str(row[c_tc]).strip()
        if not sap:
            sap = f"ROW{i+2}"
        gt = canon(row[c_gt])
        alts = [canon(a) for a in ("" if c_alt is None or is_empty(row[c_alt]) else str(row[c_alt])).split(",") if a.strip()]
        alts = [a for a in alts if a]
        pred = canon(row[c_pred])
        stat = "" if c_stat is None or is_empty(row[c_stat]) else str(row[c_stat]).strip().upper()
        reg = "" if c_reg is None or is_empty(row[c_reg]) else str(row[c_reg]).strip().upper()
        for lab in [gt] + alts:
            if lab and lab.startswith("UNGÜLTIG"):
                issues.append(dict(Typ="Ungültiges GT-Label", Konfiguration=cfg, Quelle=source, Datei=path.name, SAP=sap, Detail=lab))
        if pred and pred.startswith("UNGÜLTIG"):
            issues.append(dict(Typ="Ungültige Vorhersage (als falsch gewertet)", Konfiguration=cfg, Quelle=source,
                               Datei=path.name, SAP=sap, Detail=pred))
        key = sap if sap in FINAL_GT else (sap.lstrip("0") and next((k for k in FINAL_GT if k.lstrip("0") == sap.lstrip("0")), None))
        if key and key in FINAL_GT:
            fgt, freg, falts = FINAL_GT[key]
            fgt = canon(fgt)
            falts = [canon(x) for x in falts]
            if gt != fgt or set(alts) != set(falts) or (reg and reg != freg and freg != "M"):
                issues.append(dict(Typ="GT aus Datei durch finale GT ersetzt", Konfiguration=cfg, Quelle=source,
                                   Datei=path.name, SAP=sap,
                                   Detail=f"Datei: {gt} | {', '.join(alts) or '—'} | {reg}  ->  final: {fgt} | {', '.join(falts) or '—'} | {freg}"))
            gt, alts, reg = fgt, falts, freg
            sap = key  # einheitliche SAP-Schreibweise (z. B. fehlende führende Null)
        else:
            issues.append(dict(Typ="SAP nicht in finaler GT gefunden (Datei-GT verwendet)", Konfiguration=cfg,
                               Quelle=source, Datei=path.name, SAP=sap))
        if sap in seen:
            issues.append(dict(Typ="Doppelte Baugruppe in einer Datei (zweite Zeile ignoriert)", Konfiguration=cfg,
                               Quelle=source, Datei=path.name, SAP=sap))
            continue
        seen.add(sap)
        excluded = pred is None or stat == "EXCLUDED"
        name = "" if c_name is None or is_empty(row[c_name]) else str(row[c_name]).strip()
        recs.append(dict(cfg=cfg, source=source, run=run, sap=sap, gt=gt, name=name,
                         allowed=frozenset([gt] + alts), register=reg, pred=pred, excluded=excluded))
    return recs


def list_xlsx(folder):
    return sorted(f for f in folder.glob("*.xlsx") if not f.name.startswith(SKIP_PREFIX))


def run_key(f):
    m = re.search(r"Run_(\d+)", f.name, re.I)
    t = re.search(r"(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})", f.name)
    return (int(m.group(1)) if m else 10**6, t.group(1) if t else "", f.name)


def load(main_dir, supp_dir):
    recs, issues = [], []
    for cfg, key in CONFIGS:
        # Primärdatensatz: Unterordner mit 10 Läufen
        folders = [d for d in main_dir.iterdir() if d.is_dir() and key in d.name.lower()]
        folders = [d for d in folders if "flash" not in d.name.lower() or key == "deepseek"]
        if len(folders) != 1:
            sys.exit(f"Primärdatensatz: für '{cfg}' {len(folders)} Ordner gefunden: {[d.name for d in folders]}")
        files = sorted(list_xlsx(folders[0]), key=run_key)
        if len(files) != 10:
            issues.append(dict(Typ="Anzahl Läufe", Konfiguration=cfg, Quelle="115", Detail=f"{len(files)} Dateien"))
        for r, f in enumerate(files, 1):
            recs += read_result_file(f, issues, cfg, "115", r)
        # Ergänzungsdatensatz: eine Datei je Konfiguration
        sfiles = [f for f in list_xlsx(supp_dir) if key in f.name.lower()]
        sfiles = [f for f in sfiles if "flash" not in f.name.lower() or key == "deepseek"]
        if len(sfiles) != 1:
            sys.exit(f"Ergänzungsdatensatz: für '{cfg}' {len(sfiles)} Dateien gefunden: {[f.name for f in sfiles]}")
        recs += read_result_file(sfiles[0], issues, cfg, "70", 1)
    return pd.DataFrame(recs), issues


# ---------------------------------------------------------------- Auswertung
def regime(allowed, register):
    if len(allowed) > 1:
        return "M"
    if register in ("E1", "E2"):
        return register
    return "E2" if register == "M" else "?"


def per_assembly(df):
    """Je Konfiguration und Baugruppe: Anteil korrekter (allowed/strict) gültiger Läufe."""
    v = df[~df.excluded].copy()
    v["hit"] = [p in a for p, a in zip(v.pred, v.allowed)]
    v["strict"] = v["pred"] == v["gt"]
    v["alt"] = v.hit & ~v.strict
    g = v.groupby(["cfg", "source", "sap"])
    out = g.agg(hit=("hit", "mean"), strict=("strict", "mean"), alt=("alt", "mean"), n_runs=("run", "nunique")).reset_index()
    first = df.drop_duplicates(["cfg", "source", "sap"]).set_index(["cfg", "source", "sap"])
    out["gt"] = [first.loc[(c, s, a), "gt"] for c, s, a in zip(out.cfg, out.source, out.sap)]
    out["regime"] = [regime(first.loc[(c, s, a), "allowed"], first.loc[(c, s, a), "register"])
                     for c, s, a in zip(out.cfg, out.source, out.sap)]
    return out


def boot_mean(x, rng):
    x = np.asarray(x, float)
    if len(x) == 0:
        return np.nan, np.nan, np.nan
    idx = rng.integers(0, len(x), size=(N_BOOT, len(x)))
    b = x[idx].mean(axis=1)
    lo, hi = np.percentile(b, CI)
    return x.mean(), lo, hi


def boot_diff(x, y, rng):
    x, y = np.asarray(x, float), np.asarray(y, float)
    bx = x[rng.integers(0, len(x), size=(N_BOOT, len(x)))].mean(axis=1)
    by = y[rng.integers(0, len(y), size=(N_BOOT, len(y)))].mean(axis=1)
    d = bx - by
    lo, hi = np.percentile(d, CI)
    return x.mean() - y.mean(), lo, hi


def pct(v, d=1):
    return "–" if v is None or np.isnan(v) else f"{v*100:.{d}f}".replace(".", ",")


def fmt(m, lo, hi):
    return "–" if np.isnan(m) else f"{pct(m)} [{pct(lo)}–{pct(hi)}]"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--main", required=True, help="Ordner mit den 10-Lauf-Ordnern (115 BG)")
    ap.add_argument("--supp", required=True, help="Ordner mit den Ergebnisdateien der 70 BG")
    ap.add_argument("--out", default="Validation_Regimes.xlsx")
    a = ap.parse_args()

    df, issues = load(Path(a.main), Path(a.supp))
    pa = per_assembly(df)
    rng = np.random.default_rng(SEED)
    cfgs = [c for c, _ in CONFIGS]

    # Prüfungen: Regime-Verteilung und GT-Konsistenz
    chk = []
    for c in cfgs:
        for src in ["115", "70"]:
            sub = pa[(pa.cfg == c) & (pa.source == src)]
            vc = sub.regime.value_counts()
            chk.append({"Konfiguration": c, "Datensatz": src, "Baugruppen": len(sub),
                        **{r: int(vc.get(r, 0)) for r in ["E1", "E2", "M", "?"]}})
    expected = {"115": (115, 51, 34, 30), "70": (70, 59, 10, 1)}
    for row in chk:
        e = expected[row["Datensatz"]]
        row["Erwartet (n/E1/E2/M)"] = "/".join(map(str, e))
        row["OK"] = "ja" if (row["Baugruppen"], row["E1"], row["E2"], row["M"]) == e else "NEIN"
    gt_sets = df.groupby(["source", "sap"]).agg(n=("allowed", lambda s: len(set(s))), g=("gt", lambda s: len(set(s))))
    for (src, sap), r in gt_sets.iterrows():
        if r.n > 1 or r.g > 1:
            issues.append(dict(Typ="GT/ZGT unterscheidet sich zwischen Dateien", Quelle=src, SAP=sap))
    excl = df[df.excluded].groupby(["cfg", "source"]).size()
    for (c, s), n in excl.items():
        issues.append(dict(Typ="EXCLUDED/leer (nicht gewertet)", Konfiguration=c, Quelle=s, Detail=str(n)))

    # Tabelle 5.6
    t56 = []
    for c in cfgs:
        m = pa[(pa.cfg == c) & (pa.source == "115") & pa.regime.isin(["E1", "E2"])].hit
        s = pa[(pa.cfg == c) & (pa.source == "70") & pa.regime.isin(["E1", "E2"])].hit
        t56.append({"Konfiguration": c,
                    "115 BG, E1+E2 (n)": len(m), "115 BG, E1+E2 (10 Läufe)": fmt(*boot_mean(m, rng)),
                    "70 BG, E1+E2 (n)": len(s), "70 BG, E1+E2 (1 Lauf)": fmt(*boot_mean(s, rng)),
                    "Δ (70 − 115)": fmt(*boot_diff(s, m, rng))})
    t56 = pd.DataFrame(t56)

    # Einzelfall M im Ergänzungsdatensatz
    mrows = []
    for c in cfgs:
        sub = df[(df.cfg == c) & (df.source == "70")]
        for r in sub.itertuples():
            if len(r.allowed) > 1:
                mrows.append({"Konfiguration": c, "SAP": r.sap, "Ground Truth": r.gt,
                              "Zulässig": ", ".join(sorted(r.allowed)), "Vorhersage": r.pred,
                              "Korrekt (allowed)": "ja" if r.pred in r.allowed else "nein"})
    mcase = pd.DataFrame(mrows)

    # Klassenweise E1+E2, 115 vs 70
    kl = []
    for c in cfgs:
        for k in CLASSES:
            row = {"Konfiguration": c, "Klasse (Primärlabel)": k}
            for src in ["115", "70"]:
                x = pa[(pa.cfg == c) & (pa.source == src) & pa.regime.isin(["E1", "E2"]) & (pa["gt"] == k)].hit
                row[f"{src} BG n"] = len(x)
                row[f"{src} BG Accuracy"] = pct(x.mean()) if len(x) else "–"
            kl.append(row)
    kl = pd.DataFrame(kl)

    # Tabelle 5.7: 185 BG nach Regime
    t57 = []
    for c in cfgs:
        sub = pa[pa.cfg == c]
        row = {"Konfiguration": c}
        for r in ["E1", "E2", "M"]:
            x = sub[sub.regime == r]
            row[f"{r} (n)"] = len(x)
            row[f"{r} Allowed Accuracy"] = fmt(*boot_mean(x.hit, rng))
        x = sub[sub.regime == "M"]
        row["M: Anteil Primärlabel"] = fmt(*boot_mean(x.strict, rng))
        row["M: Anteil weiteres zulässiges Label"] = fmt(*boot_mean(x.alt, rng))
        row["Gesamt 185 Allowed Accuracy"] = fmt(*boot_mean(sub.hit, rng))
        row["Gesamt 185 Strict Accuracy"] = fmt(*boot_mean(sub.strict, rng))
        t57.append(row)
    t57 = pd.DataFrame(t57)


    # Fehlerliste je Baugruppe und Konfusionsmatrix der Fehler
    in57 = {s.lstrip("0") for s in FEHLERANALYSE_57}
    v = df[~df.excluded].copy()
    v["hit"] = [p in a for p, a in zip(v["pred"], v["allowed"])]
    wrong = v[~v["hit"]]
    err_rows = []
    for (src, sap), g in wrong.groupby(["source", "sap"]):
        first = df[(df.source == src) & (df.sap == sap)].iloc[0]
        row = {"Datensatz": src, "SAP": sap, "Benennung": first["name"],
               "Regime": regime(first["allowed"], first["register"]),
               "Ground Truth": first["gt"],
               "Weitere zulässige": ", ".join(sorted(a for a in first["allowed"] if a != first["gt"])) or "—",
               "In Fehleranalyse (57)": "ja" if sap.lstrip("0") in in57 else "NEU"}
        n_cfg = 0
        for c in cfgs:
            gc = g[g.cfg == c]
            total = int(((v.cfg == c) & (v.source == src) & (v.sap == sap)).sum())
            if len(gc):
                n_cfg += 1
                preds = gc["pred"].fillna("—").value_counts()
                row[c] = f"{len(gc)}/{total}: " + ", ".join(f"{k} ×{n}" for k, n in preds.items())
            else:
                row[c] = "–"
        row["Konfigurationen mit Fehler"] = n_cfg
        err_rows.append(row)
    errs = pd.DataFrame(err_rows)
    if len(errs):
        errs = errs.sort_values(["Konfigurationen mit Fehler", "Datensatz", "SAP"], ascending=[False, True, True])
    gd = [c for c in cfgs if c.startswith(("GPT", "DeepSeek"))]
    errs_gd = errs[(errs[gd] != "–").any(axis=1)] if len(errs) else errs

    labels = CLASSES + ["(ungültig)"]
    def confusion(sub):
        m = pd.DataFrame(0, index=CLASSES, columns=labels)
        for gt_, pr in zip(sub["gt"], sub["pred"]):
            col = pr if pr in CLASSES else "(ungültig)"
            if gt_ in CLASSES:
                m.loc[gt_, col] += 1
        m.index.name = "Primärlabel \\ Vorhersage (nur Fehler)"
        return m
    conf_blocks = [("Alle Konfigurationen", confusion(wrong))] + [(c, confusion(wrong[wrong.cfg == c])) for c in cfgs]

    notes = pd.DataFrame({"Hinweis": [
        "Werte in %, in Klammern 95%-Bootstrap-CI (B=2000, Seed 42, Ziehen von Baugruppen mit Zurücklegen).",
        "115 BG: je Baugruppe Anteil korrekter Läufe über 10 Läufe; 70 BG: 1 Lauf (0 oder 1).",
        "Tabelle 5.7: alle 185 BG, je Baugruppe gleich gewichtet; CI je Regime getrennt gezogen.",
        "Regime: M = mehr als ein zulässiges Label; sonst Spalte Register (M ohne weitere Klasse -> E2).",
        "Δ (70 − 115): Differenz der Mittelwerte, CI aus unabhängigen Bootstrap-Ziehungen beider Datensätze.",
        "EXCLUDED/leere Vorhersagen werden nicht gewertet (siehe Prüfungen).",
        "Fehler_BG: je Baugruppe mit mindestens einem Fehler 'k/n: Vorhersage ×Anzahl' je Konfiguration (k Fehlläufe von n).",
        "Fehler: Vorhersage außerhalb der zulässigen Labels. 'NEU' = nicht unter den 57 BG der bisherigen Fehleranalyse.",
        "Konfusion_Fehler: nur fehlerhafte Vorhersagen, Zeilen = Primärlabel, Spalten = Vorhersage; gezählt über Läufe.",
    ]})

    with pd.ExcelWriter(a.out, engine="openpyxl") as xw:
        t56.to_excel(xw, sheet_name="Tabelle_5_6", index=False)
        t57.to_excel(xw, sheet_name="Tabelle_5_7", index=False)
        (mcase if len(mcase) else pd.DataFrame({"Hinweis": ["keine M-Baugruppe im Ergänzungsdatensatz"]})).to_excel(xw, sheet_name="M_im_70er_Satz", index=False)
        kl.to_excel(xw, sheet_name="Klassen_E1E2_115_vs_70", index=False)
        pd.DataFrame(chk).to_excel(xw, sheet_name="Pruefung_Regime", index=False)
        (pd.DataFrame(issues) if issues else pd.DataFrame({"Hinweis": ["keine Auffälligkeiten"]})).to_excel(xw, sheet_name="Pruefungen", index=False)
        errs.to_excel(xw, sheet_name="Fehler_BG", index=False)
        errs_gd.to_excel(xw, sheet_name="Fehler_GPT_DeepSeek", index=False)
        r0 = 0
        for title, m in conf_blocks:
            pd.DataFrame({title: []}).to_excel(xw, sheet_name="Konfusion_Fehler", startrow=r0, index=False)
            m.to_excel(xw, sheet_name="Konfusion_Fehler", startrow=r0 + 1)
            r0 += len(m) + 4
        notes.to_excel(xw, sheet_name="Hinweise", index=False)
        for ws in xw.book.worksheets:
            for col in ws.columns:
                w = max(len(str(c.value)) if c.value is not None else 0 for c in col)
                ws.column_dimensions[col[0].column_letter].width = min(max(10, w + 2), 70)

    pd.set_option("display.width", 200, "display.max_columns", 20)
    print("\nPrüfung Regime-Verteilung:\n", pd.DataFrame(chk).to_string(index=False))
    print("\nTabelle 5.6:\n", t56.to_string(index=False))
    print("\nTabelle 5.7:\n", t57.to_string(index=False))
    if len(errs):
        print("\nBaugruppen mit Fehlern:")
        for src in ["115", "70"]:
            e = errs[errs["Datensatz"] == src]
            print(f"  {src} BG: {len(e)} Baugruppen, davon NEU (nicht in 57): {(e['In Fehleranalyse (57)'] == 'NEU').sum()}")
        print(f"  mit Fehlern bei GPT-5.5 oder DeepSeek: {len(errs_gd)}, davon NEU: {(errs_gd['In Fehleranalyse (57)'] == 'NEU').sum()}")
    print(f"\n{len(issues)} Hinweise in 'Pruefungen'. Ausgabe: {Path(a.out).resolve()}")


if __name__ == "__main__":
    main()
