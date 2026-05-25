# 人民当家做主工具集 —— Windows 部署方案

## 部署方式

直接在 Windows 上安装 Python 和依赖，通过命令行运行爬虫。

---

## 详细步骤

### 1. 安装 Python（如未安装）

1. 访问 https://www.python.org/downloads/
2. 下载 Python 3.11 或 3.12
3. 安装时务必勾选 **"Add Python to PATH"**
4. 打开 CMD 或 PowerShell，验证：
   ```cmd
   python --version
   pip --version
   ```

### 2. 解压项目

将项目文件夹解压到任意目录，例如：
```
D:\tools\susie_tools\
```

### 3. 安装依赖

打开 CMD 或 PowerShell，进入项目目录：

```cmd
cd D:\tools\susie_tools\batch_crawler
```

安装 Python 依赖：

```cmd
pip install -r requirements.txt
```

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
cd D:\tools\susie_tools\batch_crawler
python hybrid_runner.py
```

**带代理运行**：

```cmd
python hybrid_runner.py --proxy http://user:pass@host:port
```

**Windows 环境变量设置方式**（PowerShell）：

```powershell
$env:DELAY_MIN = "2.0"
$env:DELAY_MAX = "4.0"
$env:PROXY_SERVER = "http://proxy.example.com:8080"
python hybrid_runner.py
```

**Windows 环境变量设置方式**（CMD）：

```cmd
set DELAY_MIN=2.0
set DELAY_MAX=4.0
set PROXY_SERVER=http://proxy.example.com:8080
python hybrid_runner.py
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

### 常见问题

**Q1：CMD 中 `set` 的环境变量重启后失效**
A：CMD 的 `set` 只对当前窗口有效。如需永久生效，通过"系统属性 → 环境变量"设置，或在 PowerShell 中使用 `$env:`。

**Q2：Excel 打开 CSV 中文乱码**
A：代码已使用 `utf-8-sig` 编码（带 BOM），直接双击打开不应乱码。如仍乱码，尝试 Excel → 数据 → 从文本/CSV 导入 → 选择 UTF-8 编码。

**Q3：PowerShell 执行策略限制**
A：如运行 `.ps1` 脚本时被阻止，以管理员身份运行 PowerShell 并执行：
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

---

## Chrome 插件（Windows 侧）

Chrome 插件的加载方式在 Windows 和 macOS 上完全相同：

1. 打开 Chrome，地址栏输入 `chrome://extensions/`
2. 右上角开启**开发者模式**
3. 点击**加载已解压的扩展程序**
4. 选择 `susie_tools\chrome-extension\` 文件夹

---

## 推荐工作流（Windows）

```
1. 安装 Python 3.11/3.12 + 勾选 Add to PATH
2. pip install -r requirements.txt
3. 准备 input\urls.csv
4. python hybrid_runner.py
5. 用 Excel 打开 output\results.csv 查看结果
```

---

## 进阶：一键运行脚本

可在 `batch_crawler\` 目录下创建 `run.bat`，内容如下：

```bat
@echo off
chcp 65001 >nul
cd /d "%~dp0"
python hybrid_runner.py -i input\urls.csv -o output\results.csv
pause
```

双击 `run.bat` 即可运行，窗口会保持打开显示结果。

如需配置代理，修改 `run.bat`：

```bat
@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PROXY_SERVER=http://your-proxy:port
python hybrid_runner.py -i input\urls.csv -o output\results.csv
pause
```
