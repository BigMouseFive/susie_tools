# 人民当家做主工具集 —— Windows 部署方案

## 方案概述

将现有的 Python + Playwright 批量爬虫工具部署到 Windows 环境使用。代码本身已具备跨平台兼容性（路径使用 `pathlib`/`os.path.join`，环境变量使用 `os.getenv`），主要差异在于安装步骤和命令行语法。

## 部署方式

### 方式 A：原生 Python 部署（推荐）
直接在 Windows 上安装 Python 和依赖，通过命令行运行爬虫。

**优点**：最轻量，无需额外虚拟化层，资源占用最小  
**缺点**：需要手动管理 Python 环境  
**适用**：有基本技术能力的用户，单台 Windows 机器长期运行

### 方式 B：WSL2 / Docker 部署（可选）
在 Windows 的 WSL2 子系统或 Docker 容器中运行 Linux 环境，再执行爬虫。

**优点**：环境隔离，与 macOS/Linux 开发环境完全一致  
**缺点**：额外安装 WSL2/Docker，启动稍慢，资源占用增加  
**适用**：已有 WSL2/Docker 环境的团队，或需要统一多平台环境的场景

---

## 方式 A：原生 Python 部署详细步骤

### 1. 安装 Python（如未安装）

1. 访问 https://www.python.org/downloads/
2. 下载 Python 3.11 或 3.12（**不要选 3.13**，Playwright 兼容性待验证）
3. 安装时务必勾选 **"Add Python to PATH"**
4. 打开 CMD 或 PowerShell，验证：
   ```cmd
   python --version
   pip --version
   ```

### 2. 解压项目

将 `scrapy_seller_id` 文件夹解压到任意目录，例如：
```
D:\tools\scrapy_seller_id\
```

### 3. 安装依赖

打开 CMD 或 PowerShell，进入项目目录：

```cmd
cd D:\tools\scrapy_seller_id\batch_crawler
```

安装 Python 依赖：

```cmd
pip install -r requirements.txt
```

安装 Playwright 浏览器：

```cmd
playwright install chromium
```

> **注意**：如果 `playwright install chromium` 报错网络问题，可尝试设置代理后重试，或手动下载浏览器二进制文件。

### 4. 准备 URL 列表

在 `batch_crawler\input\` 目录下创建 `urls.csv`：

```csv
url
https://www.amazon.com/dp/B08N5WRWNW
https://www.amazon.com/dp/B09V3KXJPB
```

或创建 `urls.txt`（每行一个 URL）。

### 5. 运行爬虫

**基础运行**：

```cmd
cd D:\tools\scrapy_seller_id\batch_crawler
python crawler.py
```

**带代理运行**：

```cmd
python crawler.py --proxy http://user:pass@host:port
```

**Windows 环境变量设置方式**（PowerShell）：

```powershell
$env:CONCURRENCY = "2"
$env:BATCH_SIZE_PER_BROWSER = "1"
$env:DELAY_MIN = "2.0"
$env:DELAY_MAX = "4.0"
$env:PROXY_SERVER = "http://proxy.example.com:8080"
python crawler.py
```

**Windows 环境变量设置方式**（CMD）：

```cmd
set CONCURRENCY=2
set BATCH_SIZE_PER_BROWSER=1
set DELAY_MIN=2.0
set DELAY_MAX=4.0
set PROXY_SERVER=http://proxy.example.com:8080
python crawler.py
```

### 6. 查看结果

结果保存在 `batch_crawler\output\results.csv`，直接用 Excel 双击打开即可（已带 UTF-8 BOM，中文不乱码）。

---

## Windows 特有注意事项

| 项目 | macOS/Linux | Windows |
|------|------------|---------|
| Python 命令 | `python3` | `python` |
| 环境变量设置 | `export KEY=value` | `set KEY=value` (CMD) / `$env:KEY="value"` (PowerShell) |
| 路径分隔符 | `/` | `\`（代码已自动处理） |
| CSV 打开方式 | 文本编辑器/Numbers | **直接双击用 Excel 打开**（utf-8-sig 编码，中文正常） |
| 终端推荐 | Terminal / iTerm | **PowerShell**（比 CMD 功能更强，推荐） |
| Playwright 浏览器缓存 | `~/Library/Caches/ms-playwright` | `%USERPROFILE%\AppData\Local\ms-playwright` |

### 常见问题

**Q1：运行时报错 `"playwright" 不是内部或外部命令`**  
A：Python 的 Scripts 目录未加入 PATH。尝试用 `python -m playwright install chromium` 替代。

**Q2：CMD 中 `set` 的环境变量重启后失效**  
A：CMD 的 `set` 只对当前窗口有效。如需永久生效，通过"系统属性 → 环境变量"设置，或在 PowerShell 中使用 `$env:`。

**Q3：Excel 打开 CSV 中文乱码**  
A：代码已使用 `utf-8-sig` 编码（带 BOM），直接双击打开不应乱码。如仍乱码，尝试 Excel → 数据 → 从文本/CSV 导入 → 选择 UTF-8 编码。

**Q4：PowerShell 执行策略限制**  
A：如运行 `.ps1` 脚本时被阻止，以管理员身份运行 PowerShell 并执行：
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

**Q5：杀毒软件拦截 Chromium 浏览器**  
A：Playwright 下载的 Chromium 可能被 Windows Defender 误报。将 `%USERPROFILE%\AppData\Local\ms-playwright` 加入杀毒软件白名单。

---

## 方式 B：WSL2 部署（简要）

如更习惯 Linux 命令行，可在 Windows 上安装 WSL2 + Ubuntu：

```powershell
wsl --install -d Ubuntu
```

然后在 WSL2 的 Ubuntu 中按 macOS/Linux 步骤执行即可（`python3`、`export` 等命令完全一致）。WSL2 下 Playwright 的浏览器安装到 Linux 子系统中，与 Windows 宿主隔离。

---

## Chrome 插件（Windows 侧）

Chrome 插件的加载方式在 Windows 和 macOS 上完全相同：

1. 打开 Chrome，地址栏输入 `chrome://extensions/`
2. 右上角开启**开发者模式**
3. 点击**加载已解压的扩展程序**
4. 选择 `scrapy_seller_id\chrome-extension\` 文件夹

---

## 推荐工作流（Windows）

```
1. 安装 Python 3.11/3.12 + 勾选 Add to PATH
2. pip install -r requirements.txt
3. playwright install chromium
4. 准备 input\urls.csv
5. python crawler.py
6. 用 Excel 打开 output\results.csv 查看结果
```

---

## 进阶：一键运行脚本

可在 `batch_crawler\` 目录下创建 `run.bat`，内容如下：

```bat
@echo off
chcp 65001 >nul
cd /d "%~dp0"
python crawler.py -i input\urls.csv -o output\results.csv
pause
```

双击 `run.bat` 即可运行，窗口会保持打开显示结果。

如需配置代理，修改 `run.bat`：

```bat
@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PROXY_SERVER=http://your-proxy:port
python crawler.py -i input\urls.csv -o output\results.csv
pause
```
