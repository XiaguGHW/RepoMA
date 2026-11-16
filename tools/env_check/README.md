# env_check — conda / Git 找不到时的排查

背景：2026-11-16 起，公司电脑上 `conda activate thesis` 报 "CommandNotFound"，Anaconda Prompt 提示 "Das System kann den angegebenen Pfad nicht finden"，VS Code 也找不到 Git。

## 用法

把 `check_conda_git.bat` 放到桌面等非 Downloads 目录（Bosch AppLocker 会拦截 Downloads 里的 .bat），然后双击（或在 cmd 里运行）。结果会显示在窗口里，同时保存到同目录下的 `env_check_log.txt`。

## 怎么看结果

| 结果 | 说明 | 下一步 |
|---|---|---|
| `dir` 找到了 conda.exe / git.exe，但 `where` 找不到 | 程序还在，只是 PATH 被重置了 | 把路径加回 PATH，再运行 `<安装目录>\Scripts\conda.exe init powershell` 和 `init cmd.exe`，然后重启 VS Code |
| `dir` 全都 "Datei nicht gefunden" | 程序被卸载或挪走了 | 通过公司软件中心重装 Git 和 Anaconda/Miniconda，然后重建 `thesis` 环境（参考仓库根目录的 `requirements.txt`） |
| envs 下面还有 `thesis` | 环境还在 | conda 恢复后直接 `conda activate thesis` |

VS Code 里 "Default environment manager 'ms-python.python:conda' ..." 的提示先点 Close，不要点 Reset setting。conda 恢复后它会自动正常。
