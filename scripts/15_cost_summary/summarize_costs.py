#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
summarize_costs.py – Kosten je Baugruppe für Abschnitt 5.8 (offline, keine Modellaufrufe)

Liest die Spalte Token_Usage_JSON der Ergebnisdateien (Blatt Sheet1), erkennt das
Format je Anbieter (Gemini, Anthropic, OpenAI Chat/Responses, DeepSeek) und rechnet
mit der Preistabelle PRICES unten (USD je 1 Mio. Token). Bitte die Preise prüfen –
sie hängen vom Zugangsweg ab (z. B. direkte API vs. Vertex AI / Azure).

Aufruf (PowerShell):
  python summarize_costs.py --dir ..\\70BG_Ergebnisse
  python summarize_costs.py --dir ..\\70BG_Ergebnisse --dir .\\gpt-5.5_image_P3_10_runs   # mehrere Ordner

Ausgabe: Kosten_5_8.xlsx  (Blatt Zusammenfassung, Blatt Je_Baugruppe, Blatt Hinweise)
"""

import argparse
import json
import re
import statistics as st
from pathlib import Path

import pandas as pd

# Konfiguration: Schlüssel im Dateinamen -> (Name, Preis-Schlüssel)
CONFIGS = [
    ("haiku", "Claude Haiku 4.5 (PDF)", "haiku"),
    ("deepseek", "DeepSeek-V4-Flash (Text)", "deepseek"),
    ("gemini-2.5-pro", "Gemini 2.5 Pro (PDF)", "gemini-pro"),
    ("gpt-5.5", "GPT-5.5 (Image)", "gpt-5.5"),
]

# USD je 1 Mio. Token. cache_read / cache_write als Faktor auf den Input-Preis.
# BITTE PRÜFEN (Stand der Experimente, Zugangsweg).
PRICES = {
    "haiku":      dict(inp=1.00, out=5.00, cache_read=0.10, cache_write=1.25),
    "opus":       dict(inp=5.00, out=25.00, cache_read=0.10, cache_write=1.25),   # nur Schätzung (Haiku-Token)
    "gemini-pro": dict(inp=1.25, out=10.00, inp_long=2.50, out_long=15.00, long_from=200_000, cache_read=0.10),
    "gpt-5.5":    dict(inp=5.00, out=30.00, cache_read=0.10),
    "deepseek":   dict(inp=0.14, out=0.28, cache_read=0.02),   # DeepSeek-API: Cache-Hit 0,0028 USD = 2 % von 0,14
}


def parse_usage(cell):
    u = _parse_usage(cell)
    return u


def _parse_usage(cell):
    """-> dict(input, cached, cache_write, output, reasoning, fmt) oder None."""
    if cell is None or (isinstance(cell, float) and pd.isna(cell)) or not str(cell).strip():
        return None
    s = str(cell).strip()
    try:
        d = json.loads(s)
        if isinstance(d, str):
            d = json.loads(d)
    except json.JSONDecodeError:
        return None
    if not isinstance(d, dict):
        return None
    if isinstance(d.get("raw_usage"), dict) and d["raw_usage"]:  # Hülle des Connectors: Rohdaten bevorzugen
        u = _parse_usage(json.dumps(d["raw_usage"]))
        if u is not None:
            return u
    lat = d.get("latency_checkpoint") if isinstance(d.get("latency_checkpoint"), dict) else {}
    lat_s = (lat.get("service_ttlt_ms") or 0) / 1000 or None  # Azure: Zeit bis zum letzten Token
    if "usageMetadata" in d:
        d = d["usageMetadata"]
    if "usage" in d and isinstance(d["usage"], dict):
        d = d["usage"]
    g = lambda k: int(d.get(k) or 0)
    sub = lambda k, kk: int((d.get(k) or {}).get(kk) or 0) if isinstance(d.get(k), dict) else 0
    if "promptTokenCount" in d:  # Gemini: thoughts zählen als Output
        return dict(input=g("promptTokenCount"), cached=g("cachedContentTokenCount"), cache_write=0,
                    output=g("candidatesTokenCount") + g("thoughtsTokenCount"),
                    reasoning=g("thoughtsTokenCount"), fmt="Gemini", latency=lat_s)
    if "prompt_cache_hit_tokens" in d or "prompt_cache_miss_tokens" in d:  # DeepSeek
        hit = g("prompt_cache_hit_tokens")
        return dict(input=g("prompt_tokens") or hit + g("prompt_cache_miss_tokens"), cached=hit, cache_write=0,
                    output=g("completion_tokens"), reasoning=sub("completion_tokens_details", "reasoning_tokens"),
                    fmt="DeepSeek", latency=lat_s)
    if "prompt_tokens" in d:  # OpenAI Chat Completions (completion_tokens enthält Reasoning)
        return dict(input=g("prompt_tokens"), cached=sub("prompt_tokens_details", "cached_tokens"), cache_write=0,
                    output=g("completion_tokens"), reasoning=sub("completion_tokens_details", "reasoning_tokens"),
                    fmt="OpenAI-Chat", latency=lat_s)
    if "cache_creation_input_tokens" in d or "cache_read_input_tokens" in d:  # Anthropic: input ohne Cache
        cr, cw = g("cache_read_input_tokens"), g("cache_creation_input_tokens")
        return dict(input=g("input_tokens") + cr + cw, cached=cr, cache_write=cw,
                    output=g("output_tokens"), reasoning=0, fmt="Anthropic", latency=lat_s)
    if "provider" in d and "input_tokens" in d:  # Hülle ohne Rohdaten: input_tokens ohne Cache angenommen
        cr = g("cached_tokens")
        return dict(input=g("input_tokens"), cached=0, cache_write=g("cache_creation_input_tokens"),
                    output=g("output_tokens"), reasoning=g("reasoning_tokens"), fmt="Connector-Hülle", latency=lat_s)
    if "input_tokens" in d:  # OpenAI Responses (input enthält Cache) oder Anthropic ohne Cache-Felder
        return dict(input=g("input_tokens"), cached=sub("input_tokens_details", "cached_tokens"), cache_write=0,
                    output=g("output_tokens"), reasoning=sub("output_tokens_details", "reasoning_tokens"),
                    fmt="OpenAI-Responses/Anthropic", latency=lat_s)
    return None


def cost(u, p):
    long = "long_from" in p and u["input"] > p["long_from"]
    pi, po = (p["inp_long"], p["out_long"]) if long else (p["inp"], p["out"])
    plain = u["input"] - u["cached"] - u["cache_write"]
    return (plain * pi + u["cached"] * pi * p.get("cache_read", 1) + u["cache_write"] * pi * p.get("cache_write", 1)
            + u["output"] * po) / 1e6


def find_col(cols, *names):
    for c in cols:
        if any(n.lower() in str(c).lower() for n in names):
            return c
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", action="append", required=True, help="Ordner mit Ergebnisdateien (mehrfach möglich)")
    ap.add_argument("--out", default="Kosten_5_8.xlsx")
    a = ap.parse_args()

    rows, notes = [], []
    files = [f for d in a.dir for f in sorted(Path(d).rglob("*.xlsx")) if not f.name.startswith(("~$", "Kosten_", "Validation_"))]
    for f in files:
        name = f.name.lower()
        hit = [(k, n, pk) for k, n, pk in CONFIGS if k in name and ("flash" not in name or k == "deepseek")]
        if not hit:
            continue
        key, cfg, pk = hit[0]
        xl = pd.ExcelFile(f)
        sheet = "Sheet1" if "Sheet1" in xl.sheet_names else xl.sheet_names[0]
        df = pd.read_excel(f, sheet_name=sheet, dtype=str)
        c_tok = find_col(df.columns, "token_usage")
        c_sap = find_col(df.columns, "sap")
        c_time = find_col(df.columns, "latency", "duration", "dauer", "elapsed", "laufzeit", "time_s", "seconds")
        if c_tok is None:
            notes.append(dict(Datei=f.name, Hinweis="keine Spalte Token_Usage_JSON"))
            continue
        n_bad = 0
        c_run = find_col(df.columns, "run_time", "timestamp", "zeitstempel")
        gap = pd.Series([None] * len(df), index=df.index, dtype="float")
        if c_time is None and c_run is not None:
            ts = pd.to_datetime(df[c_run], errors="coerce")
            if ts.notna().sum() > 2:
                d_next = ts.shift(-1) - ts  # Abstand zur nächsten Zeile (Annahme: Anfragen nacheinander)
                gap = d_next.dt.total_seconds().where(lambda s: (s > 0) & (s < 900))
        for i, r in df.iterrows():
            u = parse_usage(r[c_tok])
            if u is None:
                n_bad += 1
                continue
            t, quelle = (u["latency"], "API-Latenz") if u.get("latency") else (
                (gap[i], "Zeitstempel-Abstand") if pd.notna(gap[i]) else (None, None))
            if c_time is not None:
                try:
                    t, quelle = float(str(r[c_time]).replace(",", ".")), "Zeitspalte"
                except ValueError:
                    pass
            row = dict(Konfiguration=cfg, Datei=f.name, SAP=None if c_sap is None else r[c_sap], Format=u["fmt"],
                       Input=u["input"], Cached=u["cached"], Cache_Write=u["cache_write"], Output=u["output"],
                       Reasoning=u["reasoning"], Kosten_USD=cost(u, PRICES[pk]), Zeit_s=t, Zeit_Quelle=quelle)
            rows.append(row)
            if pk == "haiku":  # Schätzung Opus 4.8 mit denselben Token
                rows.append({**row, "Konfiguration": "Claude Opus 4.8 (PDF) – Schätzung mit Haiku-Token",
                             "Kosten_USD": cost(u, PRICES["opus"])})
        notes.append(dict(Datei=f.name, Hinweis=f"{cfg}: Blatt {sheet}, Token-Spalte '{c_tok}', "
                          f"Zeitspalte '{c_time}', Zeitstempel '{c_run}' (Abstand zur nächsten Anfrage, nur < 15 min), nicht lesbar: {n_bad}"))

    df = pd.DataFrame(rows)
    if df.empty:
        raise SystemExit("Keine lesbaren Token-Angaben gefunden.")
    summ = []
    for cfg, g in df.groupby("Konfiguration", sort=False):
        summ.append({"Konfiguration": cfg, "Anfragen": len(g),
                     "Input-Token Mittel": round(g.Input.mean()), "Input-Token Median": round(g.Input.median()),
                     "Input-Token Max": int(g.Input.max()),
                     "Output-Token Mittel (inkl. Reasoning)": round(g.Output.mean()),
                     "davon Reasoning Mittel": round(g.Reasoning.mean()),
                     "Kosten je BG Mittel (USD)": round(g.Kosten_USD.mean(), 4),
                     "Kosten je BG Median (USD)": round(g.Kosten_USD.median(), 4),
                     "Kosten je BG Max (USD)": round(g.Kosten_USD.max(), 4),
                     "Kosten für 185 BG (USD, hochgerechnet)": round(g.Kosten_USD.mean() * 185, 2),
                     "Zeit je BG Median (s)": None if g.Zeit_s.isna().all() else round(g.Zeit_s.median(), 1),
                     "Zeit je BG Mittel (s)": None if g.Zeit_s.isna().all() else round(g.Zeit_s.mean(), 1),
                     "Zeit-Quelle": ", ".join(sorted(g.Zeit_Quelle.dropna().unique())),
                     "Format": ", ".join(sorted(g.Format.unique()))})
    summ = pd.DataFrame(summ)
    prices = pd.DataFrame([{"Preis-Schlüssel": k, **v} for k, v in PRICES.items()])
    with pd.ExcelWriter(a.out, engine="openpyxl") as xw:
        summ.to_excel(xw, sheet_name="Zusammenfassung", index=False)
        df.to_excel(xw, sheet_name="Je_Baugruppe", index=False)
        prices.to_excel(xw, sheet_name="Preise", index=False)
        pd.DataFrame(notes).to_excel(xw, sheet_name="Hinweise", index=False)
    pd.set_option("display.width", 250, "display.max_columns", 20)
    print(summ.drop(columns=["Format"]).to_string(index=False))
    print(f"\nAusgabe: {Path(a.out).resolve()}")


if __name__ == "__main__":
    main()
