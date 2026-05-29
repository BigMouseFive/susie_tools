"""
批量爬虫配置文件
可通过环境变量覆盖，或在此直接修改默认值
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ===================== 延迟配置 =====================
# 每个请求前的随机延迟范围（秒）
DELAY_MIN = float(os.getenv("DELAY_MIN", "2.0"))
DELAY_MAX = float(os.getenv("DELAY_MAX", "4.0"))

# 失败重试间隔（秒），每次重试递增
RETRY_BASE_DELAY = float(os.getenv("RETRY_BASE_DELAY", "2.0"))

# ===================== 超时配置 =====================
# 页面加载超时（毫秒）
PAGE_TIMEOUT = int(os.getenv("PAGE_TIMEOUT", "25000"))

# ===================== 重试配置 =====================
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))

# ===================== 并发配置 =====================
# 默认并行 worker 数量（Web 模式）
DEFAULT_WORKERS = int(os.getenv("DEFAULT_WORKERS", "5"))

# ===================== 代理配置 =====================
# 代理服务器地址，格式: http://user:pass@host:port
# 留空则不使用代理
PROXY_SERVER = os.getenv("PROXY_SERVER", "")

# ===================== 路径配置 =====================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_DIR = os.path.join(BASE_DIR, "input")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

# 默认输入文件
DEFAULT_INPUT_FILE = os.path.join(INPUT_DIR, "urls.csv")

# 默认输出文件
DEFAULT_OUTPUT_FILE = os.path.join(OUTPUT_DIR, "results.csv")

# ===================== User-Agent 列表 =====================
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]
