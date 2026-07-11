# Windows 环境安装：Anaconda、Conda、VS Code

这篇从“电脑上没有 Python”开始。所有步骤以 Windows 为例。

## 1. 先理解五个名字

| 名称 | 它是什么 | 在本计划中的用途 |
|---|---|---|
| Python | 编程语言和解释器 | 运行 `.py` 代码 |
| Anaconda Distribution | Python + conda + 常用数据科学软件的发行版 | 一次安装基本工具 |
| conda | 环境与包管理工具 | 为不同项目隔离 Python 和依赖 |
| JupyterLab/Notebook | 在浏览器/编辑器中逐段运行代码的界面 | 学习、实验和数据分析 |
| ipykernel | 让某个 Python 环境成为 Jupyter 可选内核 | 保证 Notebook 用的是正确环境 |

Anaconda 不是 Python 语法，也不是编辑器。它更像“Python 工具箱”；conda 是工具箱里的环境管理员。

## 2. Anaconda 还是 Miniconda

- **Anaconda Distribution**：体积较大，预装较多包和 Navigator，零基础更直观。
- **Miniconda**：只装 Python、conda 和少量基础组件，更轻、更适合长期工程开发。

本教程使用 Anaconda Distribution。以后熟悉环境管理后，可以改用 Miniconda；conda 命令基本相同。

> 如果在公司设备或商业组织中使用，先阅读 Anaconda 当前许可条款并咨询公司。个人学习也应从官方网站下载。

## 3. 安装 Anaconda Distribution

1. 打开 [Anaconda Windows 图形安装说明](https://www.anaconda.com/docs/getting-started/anaconda/install/windows-gui-install)。
2. 从官方页面下载 Windows 64-bit Graphical Installer。
3. 双击安装包，选择 `Just Me (Recommended)`。
4. 安装目录尽量不包含空格和特殊字符，例如：

   ```text
   C:\Users\你的用户名\anaconda3
   ```

5. `Create shortcuts` 保持勾选。
6. **不要勾选** `Add Anaconda3 to my PATH environment variable`。官方不推荐永久加入 PATH，它容易与其他 Python 冲突。
7. 可以保留“注册为默认 Python”的选项；若电脑已有重要 Python 开发环境，可取消。
8. 完成安装后，从 Windows 开始菜单打开 **Anaconda Prompt**。

## 4. 验证安装

下面的命令全部在 **Anaconda Prompt** 中逐行执行。不要输入提示符前的 `(base)`。

```powershell
conda --version
python --version
where conda
where python
```

成功时会看到 conda/Python 版本和安装路径，例如：

```text
conda 25.x.x
Python 3.x.x
C:\Users\...\anaconda3\...
```

如果提示“不是内部或外部命令”，先确认打开的是 Anaconda Prompt，而不是普通命令提示符。

## 5. 为学习仓库创建独立环境

不要把所有包都装进 `base`。创建名为 `llm-learning` 的环境：

```powershell
conda create -n llm-learning python=3.12 -y
conda activate llm-learning
python --version
where python
```

激活成功后，命令行左侧应从 `(base)` 变为：

```text
(llm-learning) C:\Users\...
```

`where python` 的第一条路径应含有 `envs\llm-learning`。这是判断环境是否正确的最可靠方法之一。

常用命令：

```powershell
conda env list                 # 查看环境
conda activate llm-learning   # 进入环境
conda deactivate              # 退出当前环境
conda list                    # 查看当前环境的包
conda remove -n 环境名 --all  # 删除环境；确认名称后再执行
```

## 6. 安装 Jupyter 与 ipykernel

先确认左侧显示 `(llm-learning)`，再执行：

```powershell
conda install -c conda-forge jupyterlab notebook ipykernel pydantic -y
python -m ipykernel install --user --name llm-learning --display-name "Python (llm-learning)"
jupyter kernelspec list
```

成功时，最后一条命令应列出 `llm-learning`。`--name` 是内部名称，`--display-name` 是 VS Code/Jupyter 里看到的名字。

启动 JupyterLab：

```powershell
cd /d D:\workspace\llm-learning
jupyter lab
```

如果 Anaconda Prompt 不接受 `cd /d`，使用：

```powershell
D:
cd \workspace\llm-learning
jupyter lab
```

浏览器通常会自动打开 `http://localhost:8888/lab`。不要关闭运行 Jupyter 的终端；关闭终端会停止服务。结束时在终端按 `Ctrl+C`，再输入 `y`。

## 7. 安装 VS Code 与扩展

1. 从 [VS Code 官网](https://code.visualstudio.com/) 安装。
2. 打开扩展页面（左侧方块图标），安装 Microsoft 发布的：
   - Python
   - Jupyter
   - Pylance
3. 用 `File → Open Folder` 打开：

   ```text
   D:\workspace\llm-learning
   ```

4. 按 `Ctrl+Shift+P`，输入 `Python: Select Interpreter`。
5. 选择路径包含 `envs\llm-learning` 的解释器。
6. 打开 `.ipynb` 后，点击右上角 `Select Kernel`，选择 `Python (llm-learning)`。

VS Code 的“解释器”和 Notebook 的“Kernel”可能需要分别选择。编辑 `.py` 时看解释器，运行 `.ipynb` 时看 Kernel。

## 8. 最终自检

在 VS Code 终端中执行：

```powershell
python -c "import sys; print(sys.executable)"
python -c "import IPython, ipykernel; print('Jupyter kernel OK')"
jupyter kernelspec list
```

然后打开 `python入门实验.ipynb`，选择 `Python (llm-learning)`，运行第一个代码单元格。只要显示的 `sys.executable` 路径含 `envs\llm-learning`，环境就正确。

## 9. 常见问题

### `conda` 命令找不到

优先打开 Anaconda Prompt。若希望 PowerShell 识别 conda，在 Anaconda Prompt 执行：

```powershell
conda init powershell
```

关闭并重新打开 PowerShell。不要手工把大量 Anaconda 路径塞入 PATH。

### VS Code 找不到环境

1. 确认 `conda env list` 中存在 `llm-learning`。
2. `Ctrl+Shift+P → Python: Select Interpreter → Enter interpreter path`。
3. 选择类似：

   ```text
   C:\Users\你的用户名\anaconda3\envs\llm-learning\python.exe
   ```

4. 执行 `Developer: Reload Window` 后重试。

### Notebook 能打开但 `import` 报错

最常见原因是选错 Kernel。先在单元格运行：

```python
import sys
print(sys.executable)
```

如果路径不是 `llm-learning`，点击右上角重新选择 Kernel。安装包时也应先激活同一环境。

### `ModuleNotFoundError`

在已激活的环境中安装，并用 `python -m pip` 保证 pip 属于当前 Python：

```powershell
conda activate llm-learning
python -m pip install 包名
```

Notebook 中不推荐盲目使用 `!pip install`，因为它可能指向另一个环境。确需安装时可使用 `%pip install 包名`，安装后重启 Kernel。

### conda 下载很慢或失败

先区分网络、代理、证书和 channel 问题，不要随便复制未知镜像配置。可以重试并查看：

```powershell
conda info
conda config --show channels
```

公司网络下应联系 IT 配置代理/白名单。不要关闭 SSL 校验来“解决”证书错误。

## 官方资料

- [Anaconda Windows 安装](https://www.anaconda.com/docs/getting-started/anaconda/install/windows-gui-install)
- [Jupyter 安装](https://jupyter.org/install)
- [IPython/ipykernel 安装](https://ipython.readthedocs.io/en/stable/install/)
- [VS Code 管理 Jupyter Kernel](https://code.visualstudio.com/docs/datascience/jupyter-kernel-management)
