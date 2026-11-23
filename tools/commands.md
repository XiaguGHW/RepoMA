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
