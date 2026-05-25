"""
工具函数：CSV 读写、日志、ASIN 解析、断点续跑等
"""

import csv
import os
import random
import re
from pathlib import Path
from typing import List, Dict, Any, Optional

import pandas as pd
from config import (
    INPUT_DIR, OUTPUT_DIR, DEFAULT_INPUT_FILE, DEFAULT_OUTPUT_FILE,
    USER_AGENTS, ROTATE_UA
)


def ensure_dirs():
    """确保输入输出目录存在"""
    os.makedirs(INPUT_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)


def get_random_ua() -> str:
    """获取随机 User-Agent"""
    if ROTATE_UA and USER_AGENTS:
        return random.choice(USER_AGENTS)
    return USER_AGENTS[0] if USER_AGENTS else ""


def parse_asin_from_url(url: str) -> Optional[str]:
    """从亚马逊 URL 中解析 ASIN"""
    if not url:
        return None
    patterns = [
        r'/dp/([A-Z0-9]{10})',
        r'/gp/product/([A-Z0-9]{10})',
        r'/product/([A-Z0-9]{10})',
    ]
    for pat in patterns:
        m = re.search(pat, url, re.IGNORECASE)
        if m:
            return m.group(1).upper()
    return None


def load_urls(input_path: str = None) -> List[str]:
    """
    从文件加载 URL 列表
    支持 .csv（单列或多列，自动识别 url/URL 列）和 .txt（每行一个 URL）
    """
    path = Path(input_path or DEFAULT_INPUT_FILE)

    if not path.exists():
        raise FileNotFoundError(f"输入文件不存在: {path}")

    urls = []
    suffix = path.suffix.lower()

    if suffix == '.csv':
        df = pd.read_csv(path)
        # 自动识别 url 列
        url_col = None
        for col in df.columns:
            if col.lower() in ('url', 'urls', 'link', 'links', 'href'):
                url_col = col
                break
        if url_col is None:
            # 如果没有匹配的列名，取第一列
            url_col = df.columns[0]
        urls = df[url_col].dropna().astype(str).tolist()
    elif suffix == '.txt':
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    urls.append(line)
    else:
        raise ValueError(f"不支持的文件格式: {suffix}，仅支持 .csv 和 .txt")

    # 去重
    seen = set()
    unique_urls = []
    for u in urls:
        u = u.strip()
        if u and u not in seen:
            seen.add(u)
            unique_urls.append(u)

    return unique_urls


def load_existing_results(output_path: str = None) -> Dict[str, Dict[str, Any]]:
    """
    加载已处理的输出文件，用于断点续跑
    返回 dict: url -> row_data
    """
    path = Path(output_path or DEFAULT_OUTPUT_FILE)
    if not path.exists():
        return {}

    try:
        df = pd.read_csv(path, on_bad_lines='skip')
    except Exception:
        # 如果解析失败（如列数变化），跳过旧文件
        return {}

    results = {}
    for _, row in df.iterrows():
        url = str(row.get('url', '')).strip()
        # 过滤空值、NaN 字符串等无效 URL
        if url and url.lower() not in ('', 'nan', 'none', 'null'):
            # 将 pandas NaN 替换为空字符串，避免写入 CSV 时出现 nan
            row_dict = {k: '' if pd.isna(v) else v for k, v in row.to_dict().items()}
            results[url] = row_dict
    return results


def save_results(rows: List[Dict[str, Any]], output_path: str = None, mode: str = 'a'):
    """
    保存结果到 CSV
    mode: 'a' = 追加, 'w' = 覆盖
    """
    path = Path(output_path or DEFAULT_OUTPUT_FILE)
    os.makedirs(path.parent, exist_ok=True)

    if not rows:
        return

    fieldnames = ['url', 'asin', 'seller_id', 'seller_name', 'status', 'error', 'title', 'page_status']
    # 确保字段顺序，补充缺失字段
    normalized = []
    for row in rows:
        d = {k: row.get(k, '') for k in fieldnames}
        normalized.append(d)

    write_header = mode == 'w' or not path.exists() or path.stat().st_size == 0

    with open(path, mode, newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        writer.writerows(normalized)


def filter_pending_urls(urls: List[str], existing: Dict[str, Any]) -> List[str]:
    """过滤掉已处理成功的 URL，保留待处理的"""
    pending = []
    for url in urls:
        row = existing.get(url)
        if row and row.get('status') == 'success' and row.get('seller_id'):
            continue
        pending.append(url)
    return pending
