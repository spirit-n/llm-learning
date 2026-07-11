# Jupyter、Notebook 与 ipykernel 详解

## 1. Notebook 是什么

`.ipynb` 是包含 Markdown、代码和输出的 JSON 文档。界面叫 JupyterLab、Jupyter Notebook 或 VS Code Notebook；真正执行 Python 的后台进程叫 **Kernel**。

```text
Notebook 界面 → 发送代码 → Python Kernel → 返回输出
```

所以“Jupyter 已安装”不代表“当前 Notebook 用对了 Python 环境”。

## 2. ipykernel 做什么

`ipykernel` 让某个 Python 环境能作为 Jupyter Kernel 启动。注册命令：

```powershell
conda activate llm-learning
python -m ipykernel install --user --name llm-learning --display-name "Python (llm-learning)"
```

- `python -m ...`：明确使用当前 `python` 运行模块。
- `--user`：为当前 Windows 用户注册，不要求管理员权限。
- `--name`：机器识别的唯一名称。
- `--display-name`：Notebook 菜单中显示的名称。

查看和删除：

```powershell
jupyter kernelspec list
jupyter kernelspec remove llm-learning
```

删除 kernelspec 不会删除 conda 环境；删除 conda 环境也可能留下失效 kernelspec。

## 3. Cell 的两种主要类型

- **Code**：发送给 Kernel 运行。
- **Markdown**：写标题、解释、公式、链接和结论。

常用快捷键（先按 `Esc` 进入命令模式）：

| 快捷键 | 功能 |
|---|---|
| `Shift+Enter` | 运行并移动到下一格 |
| `Ctrl+Enter` | 运行当前格 |
| `A` / `B` | 在上方/下方插入 Cell |
| `M` | 改为 Markdown |
| `Y` | 改为 Code |
| `D D` | 删除当前 Cell |

VS Code 中快捷键可能略有差异，可用界面按钮完成同样操作。

## 4. 为什么运行顺序会骗人

Notebook 保留内存状态。下面先运行第二格再运行第一格，可能得到与文件从上到下运行不同的结果：

```python
# Cell 1
x = 1
```

```python
# Cell 2
x += 1
print(x)
```

提交实验前执行 `Restart Kernel and Run All`。如果从头运行失败，说明 Notebook 不可复现。

## 5. `%pip`、`!pip` 和终端 pip

- 推荐：在激活环境的终端使用 `python -m pip install 包名`。
- Notebook 内临时安装：`%pip install 包名`，它更了解当前 Kernel。
- 不推荐盲用：`!pip install 包名`，它可能调用 PATH 中另一个 pip。

安装后若仍 import 失败，重启 Kernel。

## 6. 查看当前 Kernel

在任何 Notebook 第一格放入：

```python
import sys
from pathlib import Path

print("Python:", sys.version)
print("解释器:", sys.executable)
print("工作目录:", Path.cwd())
```

路径应包含 `envs\llm-learning`。工作目录决定相对路径从哪里开始，这是“明明有文件却找不到”的常见原因。

## 7. Notebook 适合与不适合什么

适合：探索、可视化、分步理解 API、评测分析、教程。

不适合：大型业务逻辑、复杂模块、生产服务、只在某个运行顺序下才能工作。成熟代码应移入 `.py` 包并由 pytest 测试，Notebook 只调用它。

## 8. 常见故障顺序

1. 运行 `sys.executable`，确认 Kernel。
2. 运行 `python -m pip show 包名` 或 Notebook 中 `%pip show 包名`。
3. Restart Kernel。
4. 检查工作目录和文件路径。
5. 查看完整 traceback 的最后一行与第一处自己的代码。
6. 仍无法解决时，记录环境名、Python 版本、安装命令和完整错误，而不是只说“运行不了”。

资料：[Jupyter 官方安装](https://jupyter.org/install)、[ipykernel 安装](https://ipython.readthedocs.io/en/stable/install/)、[VS Code Notebook](https://code.visualstudio.com/docs/datascience/jupyter-notebooks)。
