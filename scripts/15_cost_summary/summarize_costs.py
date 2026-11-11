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
    ("opus", "Claude Opus 4.8 (PDF)", "opus"),
]

# USD je 1 Mio. Token. cache_read / cache_write als Faktor auf den Input-Preis.
# BITTE PRÜFEN (Stand der Experimente, Zugangsweg).
PRICES = {
    "haiku":      dict(inp=1.00, out=5.00, cache_read=0.10, cache_write=1.25),
    "opus":       dict(inp=5.00, out=25.00, cache_read=0.10, cache_write=1.25),
    "gemini-pro": dict(inp=1.25, out=10.00, inp_long=2.50, out_long=15.00, long_from=200_000, cache_read=0.10),
    "gpt-5.5":    dict(inp=5.00, out=30.00, cache_read=0.10),
    "deepseek":   dict(inp=0.19, out=0.51, cache_read=0.10),   # Azure AI Foundry (Global Standard); DeepSeek-API direkt: 0,14 / 0,28
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


def run_times(main_dir, max_hours=6):
    """Je Konfiguration: Startzeit (Run_Time) jedes Lauf-Files; Abstand zum nächsten Lauf / Anzahl BG."""
    out = []
    for key, cfg, _pk in CONFIGS:
        folders = [d for d in main_dir.iterdir() if d.is_dir() and key in d.name.lower()
                   and ("flash" not in d.name.lower() or key == "deepseek")]
        starts = []
        for d in folders:
            for f in d.glob("*.xlsx"):
                if f.name.startswith("~$"):
                    continue
                df = pd.read_excel(f, sheet_name=0, dtype=str)
                c_run = find_col(df.columns, "run_time")
                c_gt = find_col(df.columns, "ground truth")
                if c_run is None:
                    continue
                ts = pd.to_datetime(df[c_run], errors="coerce").dropna()
                n = int(df[c_gt].notna().sum()) if c_gt is not None else len(df)
                if len(ts):
                    starts.append((ts.min(), n, f.name))
        starts.sort()
        per_bg = []
        for (t0, n, name), (t1, _, _) in zip(starts, starts[1:]):
            h = (t1 - t0).total_seconds() / 3600
            ok = 0 < h < max_hours
            out.append({"Konfiguration": cfg, "Abstand": name, "Start": t0, "Nächster Start": t1,
                        "Stunden": round(h, 2), "BG": n, "s je BG": round(h * 3600 / n, 1) if ok else None,
                        "verwendet": "ja" if ok else f"nein (> {max_hours} h oder ≤ 0)"})
            if ok:
                per_bg.append(h * 3600 / n)
        if per_bg:
            out.append({"Konfiguration": cfg, "Abstand": "Zusammenfassung", "Start": None, "Nächster Start": None,
                        "Stunden": None, "BG": None, "s je BG": round(st.median(per_bg), 1),
                        "verwendet": f"Median aus {len(per_bg)} Läufen (von {len(starts)} Dateien)"})
    return pd.DataFrame(out)


def input_status(s):
    """Kategorie der gesendeten Eingabe aus Pages_Sent_Status / Files_Used."""
    s = "" if s is None or (isinstance(s, float) and pd.isna(s)) else str(s)
    low = s.lower()
    if not low.strip():
        return "leer"
    if "dropped" in low:
        return "Datei verworfen"
    if "error" in low or "too_large" in low or "too large" in low:
        return "Fehler (zu groß)"
    if re.search(r"first\s*\d+|erste|truncat|reduced|gekürzt|cap|pages? used|\d+\s*/\s*\d+", low):
        return "gekürzt"
    if "full" in low or "text document only" in low or "vollständig" in low:
        return "vollständig"
    return "anderes: " + s[:60]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", action="append", required=True, help="Ordner mit Ergebnisdateien (mehrfach möglich)")
    ap.add_argument("--out", default="Kosten_5_8.xlsx")
    ap.add_argument("--runs", help="Ordner mit den 10-Lauf-Ordnern (115 BG): Zeit je BG aus den Startzeiten aufeinanderfolgender Läufe")
    a = ap.parse_args()

    rows, notes, kuerz = [], [], []
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
        c_pages = find_col(df.columns, "pages_sent")
        c_files = find_col(df.columns, "files_used")
        c_gt = find_col(df.columns, "ground truth")
        for _, r in (df[df[c_gt].notna()] if c_gt is not None else df).iterrows():
            src = r[c_pages] if c_pages is not None else (r[c_files] if c_files is not None else None)
            kuerz.append({"Konfiguration": cfg, "SAP": None if c_sap is None else r[c_sap],
                          "Status": input_status(src), "Pages_Sent_Status": None if c_pages is None else r[c_pages],
                          "Files_Used": None if c_files is None else r[c_files]})
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
    zeit = run_times(Path(a.runs)) if a.runs else pd.DataFrame()
    kz = pd.DataFrame(kuerz)
    kz_sum = kz.pivot_table(index="Konfiguration", columns="Status", values="SAP", aggfunc="count", fill_value=0) \
        if len(kz) else pd.DataFrame()
    prices = pd.DataFrame([{"Preis-Schlüssel": k, **v} for k, v in PRICES.items()])
    with pd.ExcelWriter(a.out, engine="openpyxl") as xw:
        summ.to_excel(xw, sheet_name="Zusammenfassung", index=False)
        df.to_excel(xw, sheet_name="Je_Baugruppe", index=False)
        prices.to_excel(xw, sheet_name="Preise", index=False)
        pd.DataFrame(notes).to_excel(xw, sheet_name="Hinweise", index=False)
        if len(zeit):
            zeit.to_excel(xw, sheet_name="Zeit_aus_Laeufen", index=False)
        if len(kz):
            kz_sum.to_excel(xw, sheet_name="Eingabe_Kuerzung")
            kz.to_excel(xw, sheet_name="Eingabe_je_BG", index=False)
    pd.set_option("display.width", 250, "display.max_columns", 20)
    kurz = pd.DataFrame({"Konfiguration": summ["Konfiguration"], "n": summ["Anfragen"],
                         "Input-Token": summ["Input-Token Mittel"],
                         "Output-Token": summ["Output-Token Mittel (inkl. Reasoning)"],
                         "USD je BG": summ["Kosten je BG Mittel (USD)"]})
    print(kurz.to_string(index=False))
    if len(kz):
        print("\nGesendete Eingabe je Baugruppe (aus Pages_Sent_Status, sonst Files_Used):")
        print(kz_sum.to_string())
    if len(zeit):
        print("\nZeit je Baugruppe aus den Startzeiten aufeinanderfolgender Läufe (115 BG):")
        print(zeit[zeit["Abstand"] == "Zusammenfassung"][["Konfiguration", "s je BG", "verwendet"]].to_string(index=False))
    print(f"\nAusgabe: {Path(a.out).resolve()}")


if __name__ == "__main__":
    main()
