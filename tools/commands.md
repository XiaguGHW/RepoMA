# 常用命令（复制用）

最新的放最上面。在公司电脑上打开 GitHub 这个页面，点代码块右上角的复制按钮即可。

---

## 2026-11-16 · Anaconda 被移除后，直接用 thesis 环境

在 VS Code 的 PowerShell 终端里"手动激活" thesis（之后直接输入 `python` 即可，只对当前终端有效）：

```
$t="C:\Users\wdu4fe\.conda\envs\thesis"; $env:Path="$t;$t\Scripts;$t\Library\bin;"+$env:Path; function prompt {"(thesis) PS $PWD> "}
```

测试 thesis 环境是否还能用（cmd 或 PowerShell）：

```
C:\Users\wdu4fe\.conda\envs\thesis\python.exe -c "import pandas; print(pandas.__version__)"
```

用 thesis 环境运行脚本（把 `脚本.py` 换成实际文件名）：

```
C:\Users\wdu4fe\.conda\envs\thesis\python.exe 脚本.py
```

VS Code：Select Python Interpreter → Enter interpreter path → 粘贴：

```
C:\Users\wdu4fe\.conda\envs\thesis\python.exe
```

给 thesis 环境装包（不需要 conda）：

```
C:\Users\wdu4fe\.conda\envs\thesis\python.exe -m pip install 包名
```

检查 Anaconda 安装目录是否还在：

```
dir "C:\Program Files\Anaconda3"
```

（诊断脚本见 `tools/env_check/`）

## 2026-11-23 · R1-Auswertung: Vollständigkeit prüfen und Nachlauf-Tabellen erzeugen

在 `R1_Auswertung\00_Skripte` 里运行。`<…>` 换成真实路径。

**115BG：**

```
python find_incomplete_runs.py `
  --root "..\01_Prompt_P1-P4\115BG" --root "..\02_Input_P3\115BG" --root "..\03_Wiederholung_10runs\115BG" `
  --reference "<完整的 115 文件>" `
  --input-dataset "<classification_experiment_dataset_v2.xlsx>" --pro-modell `
  --rerun-out "..\04_Nachlauf\115BG"
```

**70BG：**

```
python find_incomplete_runs.py `
  --root "..\01_Prompt_P1-P4\70BG" --root "..\02_Input_P3\70BG" --root "..\03_Wiederholung_10runs\70BG" `
  --reference "<完整的 70 文件>" `
  --input-dataset "<classification_experiment_dataset_v2.xlsx>" --pro-modell `
  --rerun-out "..\04_Nachlauf\70BG"
```

只检查、不生成补跑表：去掉 `--input-dataset …`、`--pro-modell` 和 `--rerun-out …` 这几行。

## 2026-11-23 · R1-Auswertung: Nachlauf zusammenführen (Merge)

在 `R1_Auswertung\00_Skripte` 里运行。补跑结果先改名为 `nachlauf_<原文件名>`，放进缺失文件所在的模型文件夹（不要放子文件夹）。

**1. 预演（不写入，只显示分配）：**

```
python merge_nachlauf.py --dry-run "<模型文件夹>" --referenz "<完整的 115 或 70 文件>"
```

例：

```
python merge_nachlauf.py --dry-run "..\01_Prompt_P1-P4\115BG\Gemini_Flash" --referenz "<完整的 115 文件>"
```

检查：每行 “ergänzt: … ← nachlauf_…” 的 P 编号/输入形式对得上；没有 “ABBRUCH”、“NICHT gefüllt”、“bitte prüfen”。

**2. 正式合并（去掉 --dry-run）：**

```
python merge_nachlauf.py "<模型文件夹>" --referenz "<完整的 115 或 70 文件>"
```

原文件和 nachlauf_ 文件会移到 `_backup_vor_merge`（第二次合并：`_backup_vor_merge_2` …），里面有 `merge_protokoll.xlsx`。

**3. 合并后复查（只检查，不生成补跑表）：**

```
python find_incomplete_runs.py `
  --root "..\01_Prompt_P1-P4\115BG" --root "..\02_Input_P3\115BG" --root "..\03_Wiederholung_10runs\115BG" `
  --reference "<完整的 115 文件>"
```

70BG 同理（把 115BG 换成 70BG，参考文件换成完整的 70 文件）。目标：`Alle Dateien vollständig.`

注意：合并前在 Excel 里关闭这些文件。

## 2026-11-23 · R1-Auswertung: alle Merges 115BG (6 Zielordner)

在 `R1_Auswertung\00_Skripte` 里运行。一个文件夹一条命令，文件夹里的多个配置（P1–P4、pdf/image/text）会自动分开配对。

先设参考文件：

```
$ref = "..\02_Input_P3\115BG\Gemini_Pro\prompt_development_P3_gemini-2.5-pro_text_only_2026-09-23_12-31-24.xlsx"
```

**预演：**

```
python merge_nachlauf.py --dry-run "..\01_Prompt_P1-P4\115BG\Claude_Opus"  --referenz $ref
python merge_nachlauf.py --dry-run "..\01_Prompt_P1-P4\115BG\Claude_Haiku" --referenz $ref
python merge_nachlauf.py --dry-run "..\01_Prompt_P1-P4\115BG\Gemini_Flash" --referenz $ref
python merge_nachlauf.py --dry-run "..\01_Prompt_P1-P4\115BG\Gemini_Pro"   --referenz $ref
python merge_nachlauf.py --dry-run "..\02_Input_P3\115BG\Gemini_Flash"     --referenz $ref
python merge_nachlauf.py --dry-run "..\02_Input_P3\115BG\Gemini_Pro"       --referenz $ref
```

**正式合并：**

```
python merge_nachlauf.py "..\01_Prompt_P1-P4\115BG\Claude_Opus"  --referenz $ref
python merge_nachlauf.py "..\01_Prompt_P1-P4\115BG\Claude_Haiku" --referenz $ref
python merge_nachlauf.py "..\01_Prompt_P1-P4\115BG\Gemini_Flash" --referenz $ref
python merge_nachlauf.py "..\01_Prompt_P1-P4\115BG\Gemini_Pro"   --referenz $ref
python merge_nachlauf.py "..\02_Input_P3\115BG\Gemini_Flash"     --referenz $ref
python merge_nachlauf.py "..\02_Input_P3\115BG\Gemini_Pro"       --referenz $ref
```

**复查：**

```
python find_incomplete_runs.py --root "..\01_Prompt_P1-P4\115BG" --root "..\02_Input_P3\115BG" --root "..\03_Wiederholung_10runs\115BG" --reference $ref
```

注意（P3 = pdf 是同一次运行）：
- Gemini Pro DN9616：补跑一次，结果复制到 `01\115BG\Gemini_Pro\` 和 `02\115BG\Gemini_Pro\` 各一份。
- Flash P3 / Haiku P3：不补跑，用 `02\115BG\<模型>\` 里已完整的 `…_pdf_only_…` 文件替换 `01\115BG\<模型>\` 里的 P3 文件（旧文件移走，不要两个 P3 同时在文件夹里）。
- `$ref` 只在当前 PowerShell 窗口有效，新开窗口要重新设置。

## 2026-11-23 · R1-Auswertung: 70BG prüfen

在 `R1_Auswertung\00_Skripte` 里运行。

```
$ref70 = "..\02_Input_P3\70BG\Gemini_Pro\pdf_only_70BG_P3_gemini-2.5-pro_caching_2026-10-19_20-24-45.xlsx"
Test-Path $ref70
python find_incomplete_runs.py --root "..\01_Prompt_P1-P4\70BG" --root "..\02_Input_P3\70BG" --root "..\03_Wiederholung_10runs\70BG" --reference $ref70
```

`Test-Path` 应为 True；输出里 “Referenz” 应为 70 BG；目标：`Alle Dateien vollständig.`

有缺失时生成补跑表：

```
python find_incomplete_runs.py --root "..\01_Prompt_P1-P4\70BG" --root "..\02_Input_P3\70BG" --root "..\03_Wiederholung_10runs\70BG" --reference $ref70 `
  --input-dataset "<classification_experiment_dataset_v2.xlsx>" --pro-modell --rerun-out "..\04_Nachlauf\70BG"
```

合并：同 115BG（`merge_nachlauf.py "<模型文件夹>" --referenz $ref70`，先 `--dry-run`）。

## 2026-11-23 · R1-Auswertung: Kennzahlen berechnen

```
python evaluate_r1.py --dir "..\03_Wiederholung_10runs" --gt R1.md --out "..\05_Ergebnisse"
python validate_r1.py --zehn "..\03_Wiederholung_10runs" --gt R1.md --werte "..\05_Ergebnisse\Wiederhollaeufe_R1.xlsx"
python evaluate_r1_ergebnisse.py --gt R1.md --prompt "..\01_Prompt_P1-P4" --input "..\02_Input_P3" --zehn "..\03_Wiederholung_10runs" --out "..\05_Ergebnisse"
```

检查：每个模型 “10 Läufe 115 BG, 10 Läufe 70 BG”；validate 最后一行 “OK – alle Werte unabhängig bestätigt.”；ergebnisse 没有 “Einzelläufe gefunden”。

## 2026-11-23 · R1-Auswertung: alle Merges 70BG (4 Zielordner)

在 `R1_Auswertung\00_Skripte` 里运行。补跑结果改名 `nachlauf_<原文件名>`，放进对应文件夹（Pro、GPT 各需 2 个补跑结果）。

```
$ref70 = "..\02_Input_P3\70BG\Gemini_Pro\pdf_only_70BG_P3_gemini-2.5-pro_caching_2026-10-19_20-24-45.xlsx"
Test-Path $ref70
```

**预演：**

```
python merge_nachlauf.py --dry-run "..\01_Prompt_P1-P4\70BG\Claude_Haiku"                         --referenz $ref70
python merge_nachlauf.py --dry-run "..\03_Wiederholung_10runs\70BG\claude_haiku_pdf_P3_10_runs"    --referenz $ref70
python merge_nachlauf.py --dry-run "..\03_Wiederholung_10runs\70BG\gemini-2.5-pro_pdf_P3_10_runs"  --referenz $ref70
python merge_nachlauf.py --dry-run "..\03_Wiederholung_10runs\70BG\gpt-5.5_image_P3_10_runs"       --referenz $ref70
```

**正式合并：**

```
python merge_nachlauf.py "..\01_Prompt_P1-P4\70BG\Claude_Haiku"                         --referenz $ref70
python merge_nachlauf.py "..\03_Wiederholung_10runs\70BG\claude_haiku_pdf_P3_10_runs"    --referenz $ref70
python merge_nachlauf.py "..\03_Wiederholung_10runs\70BG\gemini-2.5-pro_pdf_P3_10_runs"  --referenz $ref70
python merge_nachlauf.py "..\03_Wiederholung_10runs\70BG\gpt-5.5_image_P3_10_runs"       --referenz $ref70
```

**复查：**

```
python find_incomplete_runs.py --root "..\01_Prompt_P1-P4\70BG" --root "..\02_Input_P3\70BG" --root "..\03_Wiederholung_10runs\70BG" --reference $ref70
```

目标：`Alle Dateien vollständig.`（Pro 第 2 个补跑结果里的 MB8153 用不上，会被忽略，正常。）

## 2026-11-23 · R1-Auswertung: Diagramme Wiederholungsläufe

```
python plot_wiederholung_r1.py --dir "..\03_Wiederholung_10runs" --gt R1.md --out "..\05_Ergebnisse\Diagramme"
```

Ausgabe: `Diagramme_Wiederholung_R1.xlsx` (alle Diagramme, Blätter 185 BG / 115 BG / Werte je Lauf) – zum Versenden; dazu die einzelnen PNGs und `Accuracy_je_Lauf_R1.xlsx`.

## 2026-11-23 · R1: Einzelnachweis je Baugruppe

```
python detail_bg_r1.py --dir "..\03_Wiederholung_10runs" --gt R1.md --out "..\05_Ergebnisse\Detail_BG_R1.xlsx"
```

## 2026-11-23 · R1: Input-Vergleich (02_Input_P3) nach Teilmengen

```
python eval_input_regime_r1.py --input "..\02_Input_P3" --gt R1.md --nur pdf --out "..\05_Ergebnisse\Input_P3_pdf_Teilmengen_R1.xlsx"
python eval_input_regime_r1.py --input "..\02_Input_P3" --gt R1.md --out "..\05_Ergebnisse\Input_P3_Teilmengen_R1.xlsx"
```

Allowed und Strict Accuracy für alle / eindeutig / mehrdeutig / E1 / E2 / M (R1-Register), 115 und 185 BG, Einzelläufe.

## 2026-11-23 · R1: Prompt-Vergleich P3 (01_Prompt_P1-P4) nach Teilmengen

```
python eval_prompt_p3_regime_r1.py --prompt "..\01_Prompt_P1-P4" --gt R1.md --out "..\05_Ergebnisse\Prompt_P3_Teilmengen_R1.xlsx"
```

Andere Prompts: `--p P1` (bzw. P2, P4), z. B.
```
python eval_prompt_p3_regime_r1.py --prompt "..\01_Prompt_P1-P4" --gt R1.md --p P1 --out "..\05_Ergebnisse\Prompt_P1_Teilmengen_R1.xlsx"
```

Einzelnachweis für einen Prompt/ein Modell aus 01 (z. B. Haiku, P1):
```
python detail_bg_r1.py --dir "..\01_Prompt_P1-P4" --gt R1.md --p P1 --modell Haiku --out "..\05_Ergebnisse\Detail_Haiku_P1.xlsx"
```

## 2026-11-24 · R2-Auswertung (gleiche Ergebnisse wie R1, nur mit R2 als Ground Truth)

在 `R1_Auswertung\00_Skripte` 里运行。先把 `thesis/R2.md` 放进 00_Skripte，并新建文件夹 `05_Ergebnisse_R2`。
GT 名称自动从文件名取（R2.md → R2），输出文件名和表头都会是 R2。

```
python evaluate_r1.py --dir "..\03_Wiederholung_10runs" --gt R2.md --out "..\05_Ergebnisse_R2"
python validate_r1.py --zehn "..\03_Wiederholung_10runs" --gt R2.md --werte "..\05_Ergebnisse_R2\Wiederhollaeufe_R2.xlsx"
python evaluate_r1_ergebnisse.py --gt R2.md --prompt "..\01_Prompt_P1-P4" --input "..\02_Input_P3" --zehn "..\03_Wiederholung_10runs" --out "..\05_Ergebnisse_R2"
python plot_wiederholung_r1.py --dir "..\03_Wiederholung_10runs" --gt R2.md --out "..\05_Ergebnisse_R2\Diagramme"
```

Ausgabe: `Wiederhollaeufe_R2.xlsx`, `Ergebnisse_unter_R2.xlsx`, `Diagramme\Diagramme_Wiederholung_R2.xlsx`.

## 2026-11-24 · Konfusionsmatrizen: Mittel oder Summe über alle Läufe

`evaluate_r1.py` hat die Option `--km`:
- `--km mittel` (Standard): Blätter `KM_…`, Zelle = mittlere Anzahl je Lauf (Dezimalzahlen)
- `--km summe`: Blätter `KMS_…`, Zelle = Gesamtanzahl über alle 10 Läufe (ganze Zahlen, n = BG × Läufe)
- `--km beide`: beide Varianten

```
python evaluate_r1.py --dir "..\03_Wiederholung_10runs" --gt R2.md --out "..\05_Ergebnisse_R2" --km summe
```

Accuracy und Precision/Recall/F1 sind in beiden Varianten gleich; nur die Zellwerte sind ×10.

### Konfusionsmatrizen auswählen (GT, 115/185 BG, Modell)

| Option | Werte | Bedeutung |
|---|---|---|
| `--gt` | `R1.md` / `R2.md` | Ground Truth (Ausgabe heißt dann `…_R1` bzw. `…_R2`) |
| `--km` | `mittel` (Standard) / `summe` / `beide` / `keine` | Mittel je Lauf (`KM_…`), Summe über 10 Läufe (`KMS_…`) |
| `--km-bg` | `beide` (Standard) / `115` / `185` | nur für 115 BG, nur für 185 BG oder beide |
| `--km-modell` | z. B. `Haiku` (mehrfach möglich) | nur diese Modelle; ohne Angabe alle |

Beispiele:
```
python evaluate_r1.py --dir "..\03_Wiederholung_10runs" --gt R2.md --out "..\05_Ergebnisse_R2" --km summe --km-bg 185
python evaluate_r1.py --dir "..\03_Wiederholung_10runs" --gt R1.md --out "..\05_Ergebnisse" --km summe --km-bg 115 --km-modell Haiku --km-modell GPT
python evaluate_r1.py --dir "..\03_Wiederholung_10runs" --gt R2.md --out "..\05_Ergebnisse_R2" --km keine
```

### Konfusionsmatrizen für Einzelläufe (01_Prompt_P1-P4, 02_Input_P3)

Mit `--p` und/oder `--input` wertet `evaluate_r1.py` Einzelläufe aus (je Modell und Datensatz eine Datei, auch Opus).
Ausgabe: `Einzellauf_<P>_<Eingabe>_<GT>.xlsx` (Blatt „Einzellauf“, „Werte“, `KM_…` mit ganzen Zahlen). Die Wiederholungs-Ergebnisse werden nicht überschrieben.

- `--p P1|P2|P3|P4`: nur dieser Prompt (Dateien ohne P-Angabe gelten als P3)
- `--input pdf|image|text|bevorzugt`: nur diese Eingabe (bevorzugt = pdf, GPT-5.5 Bild, DeepSeek text; Dateien ohne Angabe = bevorzugte Eingabe)
- `--km-bg`, `--km-modell` wie oben

Prompt-Vergleich nur mit 01, Input-Vergleich nur mit 02 – sonst gibt es für P3 zwei passende Dateien (Warnung, die letzte nach Dateiname wird genommen):
```
python evaluate_r1.py --dir "..\01_Prompt_P1-P4" --p P1 --gt R2.md --out "..\05_Ergebnisse_R2\KM_Einzellauf"
python evaluate_r1.py --dir "..\01_Prompt_P1-P4" --p P3 --input bevorzugt --gt R2.md --out "..\05_Ergebnisse_R2\KM_Einzellauf"
python evaluate_r1.py --dir "..\02_Input_P3" --input image --gt R2.md --out "..\05_Ergebnisse_R2\KM_Einzellauf"
```

## 2026-11-24 · R2: Schnellstart (nach dem Austausch der Skripte)

```
python evaluate_r1.py --dir "..\03_Wiederholung_10runs" --gt R2.md --out "..\05_Ergebnisse_R2"
python validate_r1.py --zehn "..\03_Wiederholung_10runs" --gt R2.md --werte "..\05_Ergebnisse_R2\Wiederhollaeufe_R2.xlsx"
```

Erwartet am Ende: „OK – alle Werte unabhängig bestätigt“.

Danach Ergebnistabelle und Diagramme:
```
python evaluate_r1_ergebnisse.py --gt R2.md --prompt "..\01_Prompt_P1-P4" --input "..\02_Input_P3" --zehn "..\03_Wiederholung_10runs" --out "..\05_Ergebnisse_R2"
python plot_wiederholung_r1.py --dir "..\03_Wiederholung_10runs" --gt R2.md --out "..\05_Ergebnisse_R2\Diagramme"
```

Zum Versenden: `Wiederhollaeufe_R2.xlsx` (ohne KM_-Blätter), `Ergebnisse_unter_R2.xlsx`, `Diagramme\Diagramme_Wiederholung_R2.xlsx`.

## 2026-11-25 · Liste mehrdeutige Baugruppen (R2) aus LLM-Ergebnissen vorbefüllen

Vorlage `thesis/Mehrdeutige_Baugruppen_R2_Begruendung.xlsx` nach 00_Skripte kopieren, dann:
```
python fill_mehrdeutig_llm.py --dir "..\01_Prompt_P1-P4" --dir "..\02_Input_P3" --dir "..\03_Wiederholung_10runs" --vorlage Mehrdeutige_Baugruppen_R2_Begruendung.xlsx --out "..\05_Ergebnisse_R2\Mehrdeutige_Baugruppen_R2_LLM.xlsx"
```
Füllt „von LLM markiert“ (ja/nein + Kommentar mit Häufigkeit je Modell), Entwürfe für „Grund Label n“ (hellblau) und das Blatt „LLM-Reasoning“.

Vorlage neu erzeugen (z. B. nach Änderung der GT):
```
python make_vorlage_mehrdeutig.py --gt R2.md --out Mehrdeutige_Baugruppen_R2_Begruendung.xlsx
```
„von LLM markiert“ steht jetzt direkt in der Zelle als „ja (n/N)“ / „nein (0/N)“, dazu Spalte „andere Klassen“ (z. B. „GR × 2, RO × 1“); keine Kommentare mehr. Aufschlüsselung je Modell im Blatt „LLM-Häufigkeiten“.

## 2026-11-25 · CAD-Screenshots in die Liste der mehrdeutigen BG übernehmen

Stammdaten-Tabelle (SAP-Nummer, Teamcenter, Benennung, Abbildung) nach `R1_Auswertung\06_Stammdaten\` legen.
Als letzten Schritt (nach `fill_mehrdeutig_llm.py`):
```
python add_screenshots.py --quelle "..\06_Stammdaten\<Tabelle>.xlsx" --ziel "..\05_Ergebnisse_R2\Mehrdeutige_Baugruppen_R2_LLM.xlsx" --out "..\05_Ergebnisse_R2\Mehrdeutige_Baugruppen_R2_LLM_Bilder.xlsx"
```
Optional größere Bilder: `--zeilenhoehe 110` (Zeilenhöhe in pt). Bilder werden mit Seitenverhältnis in die Zelle „Screenshot“ eingepasst und zentriert; erkannt werden normal eingefügte Bilder und „in Zelle platzierte“ Bilder.
