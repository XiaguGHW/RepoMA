"""End-to-End-Test: Skript 16 (--pro-modell) -> simulierte Nachläufe -> Skript 11 -> Skript 16/17. Nur synthetische Daten."""
import sys,tempfile,subprocess,random;from pathlib import Path
sys.path.insert(0,'/home/claude/repoma/scripts/17_pdf_metrics')
import evaluate_pdf_results as E, pandas as pd
cm=E.cm
S16="/home/claude/repoma/scripts/16_incomplete_runs/find_incomplete_runs.py"
S11="/home/claude/repoma/scripts/11_merge_nachlauf/merge_nachlauf.py"
S17="/home/claude/repoma/scripts/17_pdf_metrics/evaluate_stability_results.py"
tmp=Path(tempfile.mkdtemp())
allk=list(cm.FINAL_GT); TC={k:(k[3:] if k.startswith("TC:") else "AS9%07d"%i) for i,k in enumerate(allk)}
def rows_for(keys, seed, status=True):
    rnd=random.Random(seed); out=[]
    for k in keys:
        gt,reg,alts=cm.FINAL_GT[k]; p=gt if rnd.random()<.85 else rnd.choice(cm.CLASSES)
        r={"prompt_engineering":"","SAP-Nummer":"" if k.startswith("TC:") else k,"Teamcenter":TC[k],"Ground Truth":gt,"Register":reg,"Weitere zulässige Ground Truth":", ".join(alts),"Predicted_Label":p,"Data_Folder_Path":"x"}
        if status: r["Allowed_Set_Status"]="CORRECT" if p==gt or p in alts else "INCORRECT"
        out.append(r)
    return pd.DataFrame(out)
def write(df,f): df.to_excel(f,sheet_name="Sheet1",index=False)
sup=[k for k in allk if k not in cm.MAIN_129]; tck=[k for k in sup if k.startswith("TC:")][0]; sapk=[k for k in sup if not k.startswith("TC:")][3]
main=list(cm.MAIN_115); m1,mall=main[2],main[9]
A=tmp/"r115"/"claude_haiku_pdf_P3_10_runs"; A.mkdir(parents=True)
for r in range(3):
    df=rows_for(main,r)
    df=df[df["SAP-Nummer"]!=mall]                       # mall fehlt in ALLEN Läufen
    if r==0: df=df[df["SAP-Nummer"]!=m1]                # m1 fehlt in Lauf 1
    if r==2: df.loc[df["SAP-Nummer"]==m1,"Predicted_Label"]="[EMPTY]"   # und ist leer in Lauf 3
    write(df,A/f"pdf_only_P3_haiku_caching_2026-10-0{r+1}_10-00-00.xlsx")
B=tmp/"r70"/"gemini-2.5-flash_pdf_P3_70BG_10_runs"; B.mkdir(parents=True)
for r in range(3):
    df=rows_for(sup,10+r,status=False)
    if r==1: df=df[df["Teamcenter"]!=TC[tck]]
    if r==2: df.loc[df["SAP-Nummer"]==sapk,"Predicted_Label"]=None
    write(df,B/f"pdf_only_70BG_P3_flash_caching_2026-11-0{r+1}_10-00-00.xlsx")
write(rows_for(main,99),tmp/"ref115.xlsx"); write(rows_for(sup,99,False),tmp/"ref70.xlsx")
ds=pd.concat([rows_for(main,0),rows_for(sup,0,False)]).drop(columns=["Predicted_Label","Allowed_Set_Status"])
ds["SAP-Nummer"]=ds["SAP-Nummer"].str.replace("0804","0804.",regex=False)   # andere Schreibweise in der Eingabeliste
with pd.ExcelWriter(tmp/"dataset.xlsx") as xw: ds.to_excel(xw,sheet_name="Experiment_Dataset",index=False)
def run16(root,ref,extra=[]):
    r=subprocess.run([sys.executable,S16,"--root",str(root),"--reference",str(ref),"--out",str(tmp/"U.xlsx")]+extra,capture_output=True,text=True,cwd=tmp); return r.stdout+r.stderr[-300:]
for root,ref,nl in [(tmp/"r115",tmp/"ref115.xlsx",tmp/"NL115"),(tmp/"r70",tmp/"ref70.xlsx",tmp/"NL70")]:
    o=run16(root,ref,["--input-dataset",str(tmp/"dataset.xlsx"),"--pro-modell","--rerun-out",str(nl)]); print(o[o.find("Nachlauf je"):][:400])
    x=pd.read_excel(next(nl.rglob("nachlauf_dataset.xlsx")),dtype=str); print("  Nachlauf-Eingabe:",x[["SAP-Nummer","Teamcenter","prompt_engineering"]].values.tolist())
def rerun(nl,folder,tag,n,start=1):
    for i in range(n):
        x=pd.read_excel(next(nl.rglob("nachlauf_dataset.xlsx")),dtype=str); x["SAP-Nummer"]=x["SAP-Nummer"].str.replace(".","",regex=False)
        x["Predicted_Label"]=["Roboter","Greifer","Lineareinheit"][i%3]; x["Allowed_Set_Status"]=""
        write(x,folder/f"nachlauf_{tag}_2026-11-{20+start+i}_10-00-00.xlsx")
print("== Merge 1 (ohne --referenz), je 1 Nachlauf")
rerun(tmp/"NL115",A,"haiku",1); rerun(tmp/"NL70",B,"flash",1)
for folder in (A,B): r=subprocess.run([sys.executable,S11,str(folder)],capture_output=True,text=True); print(r.stdout[r.stdout.find("Nachlauf-Dateien")+16:][:900],r.stderr[-500:])
print("== Merge 2 (115 mit --referenz, 3 weitere Nachläufe)")
rerun(tmp/"NL115",A,"haiku",3,start=5)
r=subprocess.run([sys.executable,S11,str(A),"--referenz",str(tmp/"ref115.xlsx")],capture_output=True,text=True); print(r.stdout[-900:],r.stderr[-500:])
for root,ref in [(tmp/"r115",tmp/"ref115.xlsx"),(tmp/"r70",tmp/"ref70.xlsx")]: print(run16(root,ref)[:200])
for f in sorted(A.glob("*.xlsx"))+sorted(B.glob("*.xlsx")):
    df=pd.read_excel(f,dtype=str); sel=df[df["SAP-Nummer"].isin([m1,mall,sapk])|(df["Teamcenter"]==TC[tck])]
    print(f.name[-28:],len(df),"pe-yes:",(df["prompt_engineering"].fillna("")=="yes").sum(),sel[["SAP-Nummer","Teamcenter","Predicted_Label"]].fillna("").values.tolist())
for root in (tmp/"r115",tmp/"r70"):
    o=subprocess.run([sys.executable,S17,"--dir",str(root),"--out",str(tmp/"o")],capture_output=True,text=True).stdout; print(o[:330])
