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
