# 人民当家做主工具集

亚马逊 Seller ID 提取工具集，包含两个子项目：

1. **Chrome 插件** —— 单页实时提取，浏览器内一键查看
2. **批量爬虫** —— Python + curl_cffi 自动化，支持几百到几千个链接批量处理

---

## 项目结构

```
susie_tools/
├── chrome-extension/          # Chrome 浏览器插件
│   ├── manifest.json
│   ├── content.js
│   ├── icons/
│   └── README.md
├── batch_crawler/             # Python 批量爬虫
│   ├── requirements.txt
│   ├── config.py              # 配置文件
│   ├── crawler_http.py        # HTTP 批量爬虫核心
│   ├── hybrid_runner.py       # 批量爬虫入口（推荐）
│   ├── extract_seller_http.py # HTTP 版提取逻辑
│   ├── diagnose_analyzer.py   # 诊断分析工具
│   ├── utils.py               # 工具函数
│   ├── input/                 # 放置 URL 列表
│   └── output/                # 输出结果
└── README.md                  # 本文件
```

---

## 一、Chrome 插件（单页模式）

适合场景：日常浏览时快速查看当前商品页的 Seller ID

### 安装

1. 打开 Chrome，地址栏输入 `chrome://extensions/`
2. 右上角开启 **开发者模式**
3. 点击 **加载已解压的扩展程序**
4. 选择 `chrome-extension/` 文件夹

### 使用

- 打开任意亚马逊商品详情页（URL 包含 `/dp/` 或 `/gp/product/`）
- 页面右下角自动出现浮层，显示 Seller ID
- 支持**一键复制**和**打开店铺**
- 浮层可拖拽移动

详见 [`chrome-extension/README.md`](chrome-extension/README.md)

---

## 二、批量爬虫（批量模式）

适合场景：已有成百上千个产品链接，需要批量提取对应的 Seller ID

### 环境准备

```bash
cd batch_crawler

# 安装 Python 依赖
pip install -r requirements.txt
```

### 准备 URL 列表

将产品链接放入 `batch_crawler/input/urls.csv`：

```csv
url
https://www.amazon.com/dp/B08N5WRWNW
https://www.amazon.com/dp/B09V3KXJPB
https://www.amazon.co.uk/dp/B08N5M7S6K
```

也支持 `.txt` 格式（每行一个 URL）：

```txt
https://www.amazon.com/dp/B08N5WRWNW
https://www.amazon.com/dp/B09V3KXJPB
```

### 运行爬虫

```bash
cd batch_crawler

# 默认配置
python hybrid_runner.py

# 指定参数
python hybrid_runner.py -i input/urls.csv -o output/results.csv -w 10

# 使用代理
python hybrid_runner.py --proxy http://user:pass@host:port
```

### 输出结果

结果保存为 CSV，字段说明：

| 字段 | 说明 |
|------|------|
| `url` | 产品链接 |
| `asin` | 自动解析的商品 ASIN |
| `seller_id` | 提取到的 Seller ID |
| `seller_name` | 卖家店铺名称（如有） |
| `status` | `success` / `no_seller_id` / `incomplete_page` / `failed` / `error` |
| `error` | 错误信息（失败时） |
| `title` | 页面标题 |

### 断点续跑

爬虫支持**断点续跑**：
- 如果中途停止，再次运行时会自动跳过已处理成功的 URL
- 只重新处理失败的记录
- 适合长时间运行的批量任务

### 反爬策略

- 随机延迟 2-4 秒（可配置）
- 完整浏览器请求头（User-Agent、Sec-Fetch、Referer 等）
- curl_cffi 模拟 Chrome TLS 指纹 + HTTP/2
- 失败自动重试 3 次
- 支持代理服务器
- 并发数可控（默认 10 线程）

### 配置文件

修改 `batch_crawler/config.py` 中的参数，或通过环境变量覆盖：

```bash
export DELAY_MIN=1.0
export DELAY_MAX=3.0
export PROXY_SERVER=http://proxy.example.com:8080
python hybrid_runner.py
```

---

## 技术说明

### Seller ID 提取逻辑

插件和爬虫共用同一套提取策略（按优先级）：

1. 隐藏字段 `input[name="merchantID"]` 及其变体
2. `data-merchant-id` / `data-seller-id` 等 data 属性
3. "Sold by" 链接中的 `merchant=` / `seller=` 参数
4. `#merchant-info` 区域的卖家主页链接
5. 页面内嵌 JSON 数据中的 `merchantID` / `sellerId` / `winningMerchantID` 等
6. `/sp?seller=` 或 `/gp/aag/main` 链接
7. Offers 列表链接
8. 纯文本搜索兜底（`Sold by` / `Ships from`）

---

## 支持的亚马逊站点

- 北美：`amazon.com`, `amazon.ca`, `amazon.com.mx`, `amazon.com.br`
- 欧洲：`amazon.co.uk`, `amazon.de`, `amazon.fr`, `amazon.it`, `amazon.es`, `amazon.nl`, `amazon.pl`, `amazon.se`, `amazon.tr`
- 亚太：`amazon.co.jp`, `amazon.in`, `amazon.com.au`, `amazon.cn`, `amazon.sg`
- 中东：`amazon.ae`

---

## 注意事项

1. **地区限制（重要）**：如果你不在目标亚马逊站点所在国家/地区（例如在中国访问 amazon.com），亚马逊可能会返回"无法配送到您的地址"的简化页面，导致无法获取 Seller ID。**强烈建议配置对应地区的代理服务器**：
   ```bash
   python hybrid_runner.py --proxy http://user:pass@us-proxy:port
   ```
2. **亚马逊反爬严格**：大量请求可能触发验证码或 IP 封禁，建议：
   - 控制并发数（5-10 为宜）
   - 使用代理池轮换 IP
   - 适当增大延迟间隔
3. **断点续跑**：长时间任务建议分批次执行，利用断点续跑机制
4. **合法合规**：请确保使用本工具符合亚马逊服务条款及当地法律法规
