"""Test: Ordner mit mehreren Konfigurationen (Prompt-Vergleich) und falsches Modell als Nachlauf. Nur synthetische Daten."""
import sys,tempfile,subprocess,random;from pathlib import Path
sys.path.insert(0,'/home/claude/repoma/scripts/17_pdf_metrics')
import evaluate_pdf_results as E, pandas as pd
cm=E.cm
S16="/home/claude/repoma/scripts/16_incomplete_runs/find_incomplete_runs.py"
S11="/home/claude/repoma/scripts/11_merge_nachlauf/merge_nachlauf.py"
tmp=Path(tempfile.mkdtemp()); main=list(cm.MAIN_115)
TC={k:"AS9%07d"%i for i,k in enumerate(main)}
def mk(f,seed,drop=()):
    rnd=random.Random(seed); rows=[]
    for k in main:
        if k in drop: continue
        g,reg,al=cm.FINAL_GT[k]; rows.append({"prompt_engineering":"","SAP-Nummer":k,"Teamcenter":TC[k],"Ground Truth":g,"Register":reg,"Weitere zulässige Ground Truth":", ".join(al),"Predicted_Label":g,"Allowed_Set_Status":"CORRECT","Data_Folder_Path":"x"})
    pd.DataFrame(rows).to_excel(f,sheet_name="Sheet1",index=False)
d=tmp/"prompt_vergleich"; d.mkdir()
i=0
for m in ["claude-haiku-4-5","gemini-2.5-flash"]:
    for p in ["P1","P2"]:
        mk(d/f"pdf_only_115BG_{p}_{m}_caching_2026-10-1{i}_10-00-00.xlsx",i,drop=(main[i],)); i+=1
mk(tmp/"ref.xlsx",99)
ds=pd.read_excel(tmp/"ref.xlsx").drop(columns=["Predicted_Label","Allowed_Set_Status"])
with pd.ExcelWriter(tmp/"dataset.xlsx") as xw: ds.to_excel(xw,sheet_name="Experiment_Dataset",index=False)
r=subprocess.run([sys.executable,S16,"--root",str(d),"--reference",str(tmp/"ref.xlsx"),"--input-dataset",str(tmp/"dataset.xlsx"),"--pro-modell","--rerun-out",str(tmp/"NL"),"--out",str(tmp/"U.xlsx")],capture_output=True,text=True,cwd=tmp)
o=r.stdout; print(o[o.find("Hinweis"):][:1200], r.stderr[-400:])
print(sorted(p.name for p in (tmp/"NL").iterdir()))
# falsches Modell als Nachlauf in Haiku-Stabilitätsordner
h=tmp/"claude_haiku_pdf_P3_10_runs"; h.mkdir()
mk(h/"pdf_only_115BG_P3_claude-haiku-4-5_caching_2026-10-01_10-00-00.xlsx",1,drop=(main[3],))
mk(h/"nachlauf_pdf_only_115BG_P3_gemini-2.5-flash_caching_2026-11-21_10-00-00.xlsx",2)
print(subprocess.run([sys.executable,S11,str(h)],capture_output=True,text=True).stdout)
# Nachläufe für den gemischten Prompt-Ordner: je Konfiguration ein Ergebnis aus der jeweiligen Eingabe
for sub in (tmp/"NL").iterdir():
    if not sub.is_dir(): continue
    x=pd.read_excel(sub/"nachlauf_dataset.xlsx",dtype=str); x["Predicted_Label"]="Roboter"; x["Allowed_Set_Status"]=""
    tok=sub.name.split("__")[1].split("_")   # haiku_P1_pdf
    m={"haiku":"claude-haiku-4-5","gemini-flash":"gemini-2.5-flash"}[tok[0]]
    x.to_excel(d/f"nachlauf_pdf_only_115BG_{tok[1]}_{m}_caching_2026-11-22_1{len(list(d.glob('nachlauf_*')))}-00-00.xlsx",sheet_name="Sheet1",index=False)
print(subprocess.run([sys.executable,S11,str(d),"--referenz",str(tmp/"ref.xlsx")],capture_output=True,text=True).stdout)
print(subprocess.run([sys.executable,S16,"--root",str(d),"--reference",str(tmp/"ref.xlsx"),"--out",str(tmp/"U3.xlsx")],capture_output=True,text=True,cwd=tmp).stdout[:150])
for f in sorted(d.glob("*.xlsx")):
    df=pd.read_excel(f); print(f.name[:50],len(df),(df["Predicted_Label"]=="Roboter").sum())
