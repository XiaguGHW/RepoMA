"""Test: Blatt Ergebnisse unter R1 mit synthetischen Dateien (Einzelläufe, 10 runs, Ersatzquellen, fehlende Zellen)."""
import sys,tempfile,random;from pathlib import Path
sys.path.insert(0,'/home/claude/repoma/scripts/17_pdf_metrics')
import evaluate_r1_ergebnisse as X, evaluate_r1 as R, pandas as pd, numpy as np
cm=X.cm
tmp=Path(tempfile.mkdtemp()); main=list(cm.MAIN_115); sup=[k for k in cm.FINAL_GT if k not in cm.MAIN_129]
MID={"Gemini 2.5 Pro":"gemini-2.5-pro","Gemini 2.5 Flash":"gemini-2.5-flash","Claude Haiku 4.5":"claude-haiku-4-5_20251001","Claude Opus 4.8":"claude-opus-4-8","GPT-5.5":"gpt-5.5-2026-04-24","DeepSeek-V4-Flash":"deepseek-v4-flash-2026-04-23"}
INP={"pdf":"pdf_only","image":"image_only","text":"text_only"}
seed=[0]
def mk(f,keys,acc=.85):
    seed[0]+=1; rnd=random.Random(seed[0]); rows=[]
    for k in keys:
        g=cm.FINAL_GT[k][0]; p=g if rnd.random()<acc else rnd.choice(cm.CLASSES)
        rows.append({"SAP-Nummer":"" if k.startswith("TC:") else k,"Teamcenter":k[3:] if k.startswith("TC:") else "x","Predicted_Label":p})
    f.parent.mkdir(parents=True,exist_ok=True); pd.DataFrame(rows).to_excel(f,sheet_name="Sheet1",index=False)
for m in ["Gemini 2.5 Pro","Gemini 2.5 Flash","Claude Haiku 4.5","Claude Opus 4.8"]:
    for p in ["P1","P2","P3","P4"]: mk(tmp/"prompt"/f"pdf_only_115BG_{p}_{MID[m]}_caching_2026-10-01_10-00-00.xlsx",main)
    for i in ["pdf","image","text"]: mk(tmp/"input"/f"{INP[i]}_115BG_P3_{MID[m]}_caching_2026-10-02_10-00-00.xlsx",main)
mk(tmp/"input"/f"text_only_115BG_P3_{MID['GPT-5.5']}_caching_2026-11-22_10-00-00.xlsx",main)
# 70 Einzel: Haiku, Pro P3 pdf; GPT image P3; DeepSeek text P3; Opus P1 only
for m,i in [("Claude Haiku 4.5","pdf"),("Gemini 2.5 Pro","pdf"),("GPT-5.5","image"),("DeepSeek-V4-Flash","text")]:
    mk(tmp/"einzel70"/f"{INP[i]}_70BG_P3_{MID[m]}_caching_2026-10-19_10-00-00.xlsx",sup)
mk(tmp/"einzel70"/f"pdf_only_70BG_P1_{MID['Claude Opus 4.8']}_caching_2026-11-22_10-00-00.xlsx",sup)
# 10 runs 115 für 5 Modelle; 70 nur für Haiku
for m,i,fold in [("Gemini 2.5 Pro","pdf","gemini-2.5-pro_pdf_P3_10_runs"),("Gemini 2.5 Flash","pdf","gemini-2.5-flash_pdf_P3_10_runs"),("Claude Haiku 4.5","pdf","claude_haiku_pdf_P3_10_runs"),("GPT-5.5","image","gpt-5.5_image_P3_10_runs"),("DeepSeek-V4-Flash","text","deepseek-v4-flash_text_P3_10_runs")]:
    for r in range(10): mk(tmp/"stab"/fold/f"Run_{r+1:02d}.xlsx",main)
for r in range(10): mk(tmp/"stab"/"claude_haiku_pdf_P3_70BG_10_runs"/f"Run_{r+1:02d}.xlsx",sup)
T=X.main(["--gt","/home/claude/repoma/thesis/R1.md","--prompt",str(tmp/"prompt"),"--prompt",str(tmp/"einzel70"),"--input",str(tmp/"input"),"--input",str(tmp/"einzel70"),"--zehn",str(tmp/"stab"),"--out",str(tmp/"o")])
gt,pe,_=R.load_gt("/home/claude/repoma/thesis/R1.md")
# unabhängige Prüfung: Opus P2 115 = Anteil korrekt der Datei
f=tmp/"prompt"/f"pdf_only_115BG_P2_{MID['Claude Opus 4.8']}_caching_2026-10-01_10-00-00.xlsx"
run=R.read_predictions(f,"Sheet1","x",gt,pe,[]); acc=np.mean([R.correct(gt,k,run[k]) for k in run])
print("Opus P2 115:",round(acc*100,3),round(T["115"][("Claude Opus 4.8","P2")]["acc"]*100,3))
# Haiku Gesamt 185 = Mittel über 185 BG der Anteile korrekter Läufe (10 Läufe 115 + 10 Läufe 70)
import glob
runs=[R.read_predictions(Path(p),"Sheet1","x",gt,pe,[]) for p in sorted(glob.glob(str(tmp/"stab"/"claude_haiku*"/"*.xlsx")))]
keys=set().union(*runs); share=[np.mean([R.correct(gt,k,r[k]) for r in runs if k in r]) for k in keys]
print("Haiku Gesamt 185:",round(np.mean(share)*100,3),round(T["185"][("Claude Haiku 4.5","Gesamt")]["acc"]*100,3), len(keys))
print("Pro Gesamt 185 fallback:",T["185"][("Gemini 2.5 Pro","Gesamt")]["fallback"],T["185"][("Gemini 2.5 Pro","Gesamt")]["src"])
print("GPT P3 115:",T["115"][("GPT-5.5","P3")]["src"],T["115"][("GPT-5.5","P3")]["fallback"])
print(tmp)
