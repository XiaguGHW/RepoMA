"""End-to-End-Test mit der realen Ordnerstruktur R1_Auswertung (01/02/03, Modellordner, echte Dateinamensmuster):
Skript 16 (mehrere --root, --pro-modell) -> simulierte Nachläufe -> Skript 11 -> Skript 16 -> evaluate_r1 ->
validate_r1 -> evaluate_r1_ergebnisse. Nur synthetische Daten."""
import random, shutil, subprocess, sys, tempfile
from pathlib import Path
import pandas as pd
H = Path(__file__).resolve().parent
sys.path.insert(0, str(H))
import evaluate_pdf_results as E
cm = E.cm
S16 = str(H.parent / "16_incomplete_runs" / "find_incomplete_runs.py")
S11 = str(H.parent / "11_merge_nachlauf" / "merge_nachlauf.py")
GT = str(H.parents[1] / "thesis" / "R1.md")
R = Path(tempfile.mkdtemp()) / "R1_Auswertung"
MAIN = list(cm.MAIN_115); SUP = [k for k in cm.FINAL_GT if k not in cm.MAIN_129]
TC = {k: (k[3:] if k.startswith("TC:") else "AS9%07d" % i) for i, k in enumerate(cm.FINAL_GT)}
MID = {"haiku": "claude-haiku-4-5_20251001", "opus": "claude-opus-4-8", "flash": "gemini-2.5-flash", "pro": "gemini-2.5-pro",
       "gpt": "gpt-5.5-2026-04-24", "ds": "deepseek-v4-flash-2026-04-23"}
DIR = {"haiku": "Claude_Haiku", "opus": "Claude_Opus", "flash": "Gemini_Flash", "pro": "Gemini_Pro", "gpt": "GPT", "ds": "DeepSeek"}
seed = [0]


def rows(keys, drop=(), empty=()):
    seed[0] += 1; rnd = random.Random(seed[0]); out = []
    for k in keys:
        if k in drop: continue
        g, reg, al = cm.FINAL_GT[k]
        p = "" if k in empty else (g if rnd.random() < .85 else rnd.choice(cm.CLASSES))
        out.append({"prompt_engineering": "", "SAP-Nummer": "" if k.startswith("TC:") else k, "Teamcenter": TC[k],
                    "Ground Truth": g, "Register": reg, "Weitere zulässige Ground Truth": ", ".join(al),
                    "Predicted_Label": p, "Reasoning": "Analyse der Baugruppe ..." if p else "",
                    "Processing_Status": "OK" if p else "ERROR: timeout"})
    return pd.DataFrame(out)


def put(path, keys, **kw):
    path.parent.mkdir(parents=True, exist_ok=True); rows(keys, **kw).to_excel(path, sheet_name="Sheet1", index=False)


ts = iter(range(100, 400))
def t(): n = next(ts); return f"2026-11-22_{n // 60:02d}-{n % 60:02d}-00"
# 01 Prompt
for m in ("haiku", "opus", "flash", "pro"):
    for p in ("P1", "P2", "P3", "P4"):
        put(R/"01_Prompt_P1-P4"/"115BG"/DIR[m]/f"prompt_development_{p}_{MID[m]}_caching_{t()}.xlsx", MAIN,
            drop=(MAIN[3],) if (m, p) == ("haiku", "P2") else ())
    for p in ("P1", "P2", "P4") + (("P3",) if m in ("opus", "flash") else ()):
        put(R/"01_Prompt_P1-P4"/"70BG"/DIR[m]/f"prompt_development_{p}_{MID[m]}_caching_{t()}.xlsx", SUP)
put(R/"01_Prompt_P1-P4"/"70BG"/DIR["haiku"]/f"pdf_only_70BG_P3_{MID['haiku']}_caching_{t()}.xlsx", SUP)
put(R/"01_Prompt_P1-P4"/"70BG"/DIR["pro"]/f"pdf_only_70BG_P3_{MID['pro']}_caching_{t()}.xlsx", SUP)
put(R/"01_Prompt_P1-P4"/"115BG"/DIR["gpt"]/f"image_only_115BG_P3_{MID['gpt']}_caching_{t()}.xlsx", MAIN)
put(R/"01_Prompt_P1-P4"/"115BG"/DIR["ds"]/f"text_only_115BG_P3_{MID['ds']}_caching_{t()}.xlsx", MAIN)
put(R/"01_Prompt_P1-P4"/"70BG"/DIR["gpt"]/f"image_only_70BG_P3_{MID['gpt']}_caching_{t()}.xlsx", SUP)
put(R/"01_Prompt_P1-P4"/"70BG"/DIR["ds"]/f"text_only_70BG_P3_{MID['ds']}_caching_{t()}.xlsx", SUP)
# 02 Input
for m in ("haiku", "opus", "flash", "pro"):
    for i in ("image", "pdf", "text"):
        put(R/"02_Input_P3"/"115BG"/DIR[m]/f"prompt_development_P3_{MID[m]}_{i}_only_{t()}.xlsx", MAIN,
            empty=(MAIN[7],) if (m, i) == ("opus", "image") else ())
        put(R/"02_Input_P3"/"70BG"/DIR[m]/f"prompt_development_P3_{MID[m]}_{i}_only_{t()}.xlsx", SUP)
for i in ("image", "text"):
    put(R/"02_Input_P3"/"70BG"/DIR["gpt"]/f"prompt_development_P3_{MID['gpt']}_{i}_only_{t()}.xlsx", SUP)
put(R/"02_Input_P3"/"115BG"/DIR["gpt"]/f"prompt_development_P3_{MID['gpt']}_text_only_{t()}.xlsx", MAIN)
# 03 Wiederholung (Ordner ohne 70BG im Namen, erster 70BG-Lauf mit anderem Namensmuster, Pro P5, DeepSeek Run_-Präfix)
CF = {"haiku": "claude_haiku_pdf_P3_10_runs", "pro": "gemini-2.5-pro_pdf_P3_10_runs", "flash": "gemini-2.5-flash_pdf_P3_10_runs",
      "gpt": "gpt-5.5_image_P3_10_runs", "ds": "deepseek-v4-flash_text_P3_10_runs"}
FIRST = {"haiku": "pdf_only_70BG_P3", "pro": "pdf_only_70BG_P3", "gpt": "image_only_70BG_P3", "ds": "text_only_70BG_P3"}
for m, f in CF.items():
    for r in range(10):
        nm = f"prompt_development_{'P5' if m == 'pro' else 'P3'}_{MID[m]}_caching_2026-10-{10+r}_10-00-00.xlsx"
        if m == "ds": nm = f"Run_{r+1:02d}_" + nm
        put(R/"03_Wiederholung_10runs"/"115BG"/f/nm, MAIN,
            drop=(MAIN[5],) if (m == "flash" and r in (2, 6)) else (), empty=(MAIN[9],) if (m == "haiku" and r == 4) else ())
        nm70 = (f"{FIRST[m]}_{MID[m]}_caching_2026-10-19_10-00-00.xlsx" if (r == 0 and m in FIRST)
                else f"prompt_development_P3_{MID[m]}_caching_2026-11-22_{10+r}-00-00.xlsx")
        put(R/"03_Wiederholung_10runs"/"70BG"/f/nm70, SUP, drop=(SUP[0],) if (m == "gpt" and r == 3) else ())
(R/"03_Wiederholung_10runs"/"115BG"/CF["pro"]/"~$prompt_development_P5_x.xlsx").write_bytes(b"lock")
REF115 = next((R/"02_Input_P3"/"115BG"/DIR["pro"]).glob("*pdf_only*")); REF70 = next((R/"02_Input_P3"/"70BG"/DIR["pro"]).glob("*pdf_only*"))
ds = pd.concat([rows(MAIN), rows(SUP)]).drop(columns=["Predicted_Label", "Reasoning", "Processing_Status"])
ds["Weitere zulässige Ground Truth"] = ""  # andere GT-Version in der Eingabeliste
ds.to_excel(R/"dataset_v2.xlsx", sheet_name="Experiment_Dataset", index=False)
S = R/"00_Skripte"; S.mkdir()


def run(args):
    r = subprocess.run([sys.executable] + args, capture_output=True, text=True, cwd=S)
    if r.returncode: print(r.stderr[-1500:])
    return r.stdout


roots = lambda d: sum([["--root", str(R/x/d)] for x in ("01_Prompt_P1-P4", "02_Input_P3", "03_Wiederholung_10runs")], [])
for d, ref in (("115BG", REF115), ("70BG", REF70)):
    o = run([S16] + roots(d) + ["--reference", str(ref), "--input-dataset", str(R/"dataset_v2.xlsx"), "--pro-modell",
                                "--rerun-out", str(R/"04_Nachlauf"/d), "--out", str(R/"04_Nachlauf"/d/"U.xlsx")])
    print(o[o.find("unvollständig"):][:1600])
# Nachläufe simulieren: Ordner aus dem Nachlauf-Ordnernamen + Übersicht
for d in ("115BG", "70BG"):
    ov = pd.read_excel(R/"04_Nachlauf"/d/"Nachlauf_Uebersicht.xlsx")
    assert ov["Gefunden"].all()
    print(d, "Nachlauf-Ordner:", sorted(p.name for p in (R/"04_Nachlauf"/d).iterdir() if p.is_dir()))
    for sub in (R/"04_Nachlauf"/d).iterdir():
        if not sub.is_dir(): continue
        target = Path(ov[ov["Nachlauf-Ordner"].astype(str) == str(sub)]["Ergebnisdatei"].iloc[0]) if False else None
        x = pd.read_excel(sub/"nachlauf_dataset.xlsx", dtype=str)
        assert (x["prompt_engineering"] == "yes").all()
        # Zielordner aus dem Nachlauf-Ordnernamen: <Top>__<Ordner>[__modell_P_eingabe]
        parts = sub.name.split("__")
        top, base, tok = parts[0], parts[1], (parts[2] if len(parts) > 2 else "")
        cand = [p for p in R.rglob("*.xlsx") if p.parent.name == base and p.parent.parent.parent.name == top
                and p.parent.parent.name == d and not p.name.startswith("nachlauf_")]
        if tok:
            mt, pt, it = tok.split("_")
            cand = [p for p in cand if pt in p.name or pt == "x"]
            cand = [p for p in cand if it == "x" or it in p.name.lower()] or cand
        src = sorted(cand)[0]
        x["Predicted_Label"] = "Roboter"; x["Reasoning"] = "Nachlauf-Analyse ..."; x["Processing_Status"] = "OK"
        n_need = 2 if "flash" in base else 1
        for k in range(n_need):
            x.to_excel(src.parent / f"nachlauf_{src.stem}_n{k}.xlsx".replace("2026-", f"2026-12-0{k+1}-"), sheet_name="Sheet1", index=False)
for d, ref in (("115BG", REF115), ("70BG", REF70)):
    for folder in sorted({p.parent for p in R.rglob("nachlauf_*.xlsx") if d in p.parts and "04_Nachlauf" not in p.parts}):
        o = run([S11, str(folder), "--referenz", str(ref)])
        bad = [l for l in o.splitlines() if "ABBRUCH" in l or "NICHT gefüllt" in l]
        print(f"merge {d}/{folder.name}:", "FEHLER " + " | ".join(bad) if bad else "ok")
for d, ref in (("115BG", REF115), ("70BG", REF70)):
    o = run([S16] + roots(d) + ["--reference", str(ref), "--out", str(R/"04_Nachlauf"/d/"U2.xlsx")])
    print(d, "Kontrolle:", [l for l in o.splitlines() if "vollständig" in l])
# GT der Originale nicht durch dataset_v2 überschrieben?
f = next((R/"03_Wiederholung_10runs"/"115BG"/CF["flash"]).glob("prompt_development_P3_*2026-10-12*.xlsx"))
x = pd.read_excel(f); assert len(x) == 115
assert (x["Weitere zulässige Ground Truth"].fillna("") != "").sum() > 20, "GT überschrieben!"
assert (x["prompt_engineering"].fillna("") == "yes").sum() == 0
print(run([str(H/"evaluate_r1.py"), "--dir", str(R/"03_Wiederholung_10runs"), "--gt", GT, "--out", str(R/"05_Ergebnisse")])[-1300:])
print(run([str(H/"validate_r1.py"), "--zehn", str(R/"03_Wiederholung_10runs"), "--gt", GT, "--werte",
           str(R/"05_Ergebnisse"/"Wiederhollaeufe_R1.xlsx")])[-200:])
o = run([str(H/"evaluate_r1_ergebnisse.py"), "--gt", GT, "--prompt", str(R/"01_Prompt_P1-P4"), "--input", str(R/"02_Input_P3"),
         "--zehn", str(R/"03_Wiederholung_10runs"), "--out", str(R/"05_Ergebnisse")])
print(o[o.find("185 BG"):][:2600])
