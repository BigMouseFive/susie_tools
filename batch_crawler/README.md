# Amazon Seller ID 批量提取工具

基于 `curl_cffi` 模拟 Chrome 浏览器指纹，批量抓取亚马逊商品页面并提取 Seller ID 的本地可视化工具。

---

## 功能特性

- **Web 可视化操作**：单页应用，上传文件 → 实时监控 → 下载结果
- **全局串行队列**：所有 URL 进入同一队列，单线程严格逐个执行，最大程度避免触发反爬
- **实时进度推送**：SSE 实时将处理进度推送到浏览器，无需刷新页面
- **状态持久化**：队列状态自动保存到本地 JSON，程序崩溃或重启后可恢复未完成任务
- **断点续跑**：任务结果自动写入 CSV，已成功的 URL 不会重复处理
- **多策略解析**：针对亚马逊页面结构，内置 7 种 Seller ID 提取策略，覆盖各种页面类型

---

## 安装

```bash
pip install -r requirements.txt
```

主要依赖：
- `curl-cffi` — 模拟 Chrome TLS/HTTP2 指纹
- `beautifulsoup4` + `lxml` — HTML 解析
- `pandas` — CSV 读写
- `flask` — Web 服务

---

## 启动

### 方式一：双击启动（推荐，无需命令行）

**macOS**
1. 确保已安装依赖（首次使用前执行一次 `pip install -r requirements.txt`）
2. 双击项目目录中的 **`Start.command`**
3. 首次运行时 macOS 可能会提示安全警告，前往「系统设置 → 隐私与安全性」允许即可
4. 脚本会自动启动服务并打开浏览器

**Windows**
1. 确保已安装依赖
2. 双击 **`start.py`**（需系统已关联 Python 打开方式）

### 方式二：命令行启动

```bash
python web_app.py
```

浏览器打开 **http://127.0.0.1:5000**

> 本工具为本地个人使用设计，仅监听 `127.0.0.1`，不会暴露到公网。

---

## 使用说明

### 1. 准备 URL 文件

支持两种格式：

**CSV 文件**
```csv
url
https://www.amazon.ae/dp/B00TSTZQEY?psc=1
https://www.amazon.ae/dp/B07MWHDHT5?psc=1
```

- 自动识别 `url` / `URL` / `link` / `links` / `href` 列名
- 若无匹配列名，默认取第一列

**TXT 文件**
```
https://www.amazon.ae/dp/B00TSTZQEY?psc=1
https://www.amazon.ae/dp/B07MWHDHT5?psc=1
```

- 每行一个 URL
- `#` 开头的行为注释，自动跳过

### 2. 上传并启动

在 Web 界面点击上传区域，选择 CSV 或 TXT 文件，点击「开始提取」。

### 3. 监控进度

- **实时状态面板**：显示队列中 / 运行中 / 已完成任务数
- **任务列表**：展示每个任务的总数、成功数、失败数、进度条、状态
- **当前处理**：显示正在抓取的 ASIN 和 URL

### 4. 下载结果

任务完成后（或已取消），点击「下载」按钮获取结果 CSV。

结果 CSV 字段：

| 字段 | 说明 |
|---|---|
| `url` | 原始商品链接 |
| `asin` | 商品 ASIN |
| `seller_id` | 卖家/商家 ID |
| `seller_name` | 卖家名称 |
| `status` | 处理状态：`success` / `no_seller_id` / `captcha` / `incomplete_page` / `unavailable` / `failed` |
| `error` | 错误信息（如有） |
| `title` | 商品标题（`#productTitle`，非浏览器标签页标题） |
| `bullet_1` ~ `bullet_5` | 五点描述（`#feature-bullets`，最多 5 条） |
| `main_image_url` | 主图原图 URL（画廊第 1 张，优先 `hiRes` 高清源，去尺寸后缀） |
| `image_2` ~ `image_10` | 产品图画廊其余原图（hiRes + 主图区 + 缩略图合并去重，最多共 10 张） |
| `category_path` | 产品类目完整路径（面包屑，如 `Fashion > Men > Watches`） |
| `category_id` | 叶子类目 Browse Node ID（面包屑最后一级 `node=` 参数） |
| `page_status` | 页面状态：`normal` / `captcha` / `unavailable` 等 |

### 5. 取消任务

对于运行中或等待中的任务，可点击「取消」，该任务剩余 URL 将从队列中移除。

---

## 持久化与恢复

- 队列状态保存在 `data/queue_state.json`
- 每个任务的结果保存在 `output/<job_id>_seller_id.csv`
- **程序重启后自动恢复**：未完成的队列会自动加载，后台 worker 继续执行
- 已完成的历史任务可在任务列表中查看和下载

---

## 项目结构

```
├── web_app.py              # Flask Web 应用主入口
├── task_queue.py           # 任务队列引擎（串行执行 + 持久化）
├── crawler_http.py         # HTTP 爬虫核心（curl_cffi）
├── extract_seller_http.py  # HTML 解析引擎（Seller ID + 商品字段）
├── extract_product_http.py # 商品标题、五点、主图提取
├── utils.py                # 工具函数（CSV 读写、ASIN 解析等）
├── config.py               # 配置文件（延迟、超时、代理等）
├── requirements.txt
├── templates/
│   └── index.html          # Web 前端页面
├── static/
│   ├── style.css           # 前端样式
│   └── app.js              # 前端交互逻辑
├── input/                  # 上传文件目录
├── output/                 # 结果 CSV 输出目录
└── data/                   # 队列状态持久化目录
```

---

## 配置说明

编辑 `config.py` 或在项目根目录创建 `.env` 文件：

```env
# 请求延迟（秒）
DELAY_MIN=2.0
DELAY_MAX=4.0

# 单个 URL 最大重试次数
MAX_RETRIES=3

# 页面加载超时（毫秒）
PAGE_TIMEOUT=25000

# 代理服务器（可选）
PROXY_SERVER=http://user:pass@host:port
```

---

## 注意事项

1. **本地使用**：Flask 开发服务器仅监听 `127.0.0.1`，如需对外提供服务请使用生产级 WSGI 服务器（如 `waitress`、`gunicorn`）
2. **反爬策略**：串行执行 + 随机延迟 + Session 定期刷新 + 自动重试，已针对亚马逊反爬做了优化，但仍建议根据实际网络环境调整 `DELAY_MIN` / `DELAY_MAX`
3. **大文件上传**：Web 端限制上传 16MB，如有更大文件建议拆分为多个 CSV 分批上传
4. **网络稳定性**：单个 URL 处理期间（含重试）最长可能耗时数十秒，如遇验证码会额外增加 10~25 秒重试延迟

---

## CLI 模式（可选）

若仍需命令行模式，可直接运行原有入口：

```bash
# 带断点续跑
python hybrid_runner.py --input input/urls.csv --output output/results.csv

# 纯 HTTP 爬虫
python crawler_http.py --input input/urls.csv --workers 10 --retries 3
```
