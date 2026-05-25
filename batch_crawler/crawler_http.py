"""
基于 curl_cffi 的 Seller ID 批量提取爬虫（HTTP 快速通道）
模拟 Chrome TLS 指纹 + HTTP/2，绕过亚马逊反爬检测
与 crawler.py（Playwright）配合，作为 Hybrid 方案的第一轮
"""

import random
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any
from urllib.parse import urlparse

from curl_cffi import requests
from tqdm import tqdm

import config
import hashlib
from extract_seller_http import extract_seller_from_html
from utils import (
    ensure_dirs, parse_asin_from_url,
    load_urls, load_existing_results, save_results, filter_pending_urls
)

# 线程本地存储，每个线程独立的 Session
_thread_local = threading.local()

# 浏览器 User-Agent 池
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]


def get_random_headers(url: str = "") -> Dict[str, str]:
    """生成随机浏览器请求头，模拟真实 Chrome 访问"""
    ua = random.choice(USER_AGENTS)
    headers = {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
    }
    if url:
        parsed = urlparse(url)
        headers["Referer"] = f"{parsed.scheme}://{parsed.netloc}/"
    return headers


def _get_session() -> requests.Session:
    """获取当前线程的 curl_cffi Session（模拟 Chrome 124）"""
    if not hasattr(_thread_local, "session"):
        _thread_local.session = requests.Session(impersonate="chrome124")
        if config.PROXY_SERVER:
            _thread_local.session.proxies = {
                "http": config.PROXY_SERVER,
                "https": config.PROXY_SERVER,
            }
    return _thread_local.session


_DIAGNOSE_DIR = None  # 诊断目录，由 --diagnose 设置


def _save_diagnose_html(url: str, html: str, status: str):
    """保存诊断 HTML（仅在 --diagnose 模式下）"""
    if not _DIAGNOSE_DIR:
        return
    try:
        from pathlib import Path
        diag_dir = Path(_DIAGNOSE_DIR)
        diag_dir.mkdir(parents=True, exist_ok=True)
        # 用 URL 的 hash 作为文件名
        url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
        asin = parse_asin_from_url(url) or url_hash
        filename = f"{status}_{asin}_{url_hash}.html"
        filepath = diag_dir / filename
        filepath.write_text(html, encoding='utf-8')
    except Exception:
        pass


def process_single_url_http(
    url: str,
    max_retries: int = config.MAX_RETRIES,
) -> Dict[str, Any]:
    """
    用 curl_cffi 处理单个 URL，返回结果字典
    每个线程使用独立的 Session（线程安全）
    """
    result = {
        "url": url,
        "asin": parse_asin_from_url(url),
        "seller_id": "",
        "seller_name": "",
        "status": "pending",
        "error": "",
        "title": "",
        "page_status": "",
    }

    # 随机延迟
    delay = random.uniform(config.DELAY_MIN, config.DELAY_MAX)
    time.sleep(delay)

    session = _get_session()

    for attempt in range(1, max_retries + 1):
        try:
            headers = get_random_headers(url)
            response = session.get(
                url,
                headers=headers,
                timeout=config.PAGE_TIMEOUT / 1000,
            )
            response.raise_for_status()

            html = response.text
            data = extract_seller_from_html(html, url)

            result["seller_id"] = (data.get("sellerId") or "").strip()
            result["seller_name"] = (data.get("sellerName") or "").strip()
            result["title"] = (data.get("title") or "").strip()
            result["asin"] = (data.get("asin") or result["asin"] or "").strip()
            result["extraction_method"] = data.get("extractionMethod", "")
            result["is_amazon"] = bool(data.get("isAmazonFulfilled"))
            page_status = data.get("pageStatus", "normal")
            result["page_status"] = page_status

            if page_status == "shipping_restricted":
                result["status"] = "shipping_restricted"
                result["error"] = "该商品无法配送到当前地区"
            elif page_status == "page_not_found":
                result["status"] = "page_not_found"
                result["error"] = "商品页面不存在"
            elif page_status == "unavailable":
                result["status"] = "unavailable"
                result["error"] = "商品当前不可用"
            elif page_status == "captcha":
                result["status"] = "captcha"
                result["error"] = "遇到验证码/机器人检测"
            elif page_status == "incomplete_page":
                # 截断页面：如果是重试机会内，尝试换 headers 重新请求
                if attempt < max_retries:
                    result["error"] = f"第 {attempt} 次尝试页面不完整，将重试..."
                    retry_delay = config.RETRY_BASE_DELAY * attempt * 2 + random.uniform(1, 3)
                    time.sleep(retry_delay)
                    continue  # 进入下一次重试
                result["status"] = "incomplete_page"
                result["error"] = "页面内容不完整，可能需要浏览器渲染"
                if _DIAGNOSE_DIR:
                    _save_diagnose_html(url, html, "incomplete_page")
            elif result["seller_id"]:
                result["status"] = "success"
                result["error"] = ""
            else:
                result["status"] = "no_seller_id"
                result["error"] = "页面中未检测到 Seller ID"
                if _DIAGNOSE_DIR:
                    _save_diagnose_html(url, html, "no_seller_id")

            return result

        except requests.exceptions.RequestException as e:
            err_msg = str(e)
            result["error"] = err_msg
            result["status"] = "error"

            if attempt < max_retries:
                retry_delay = config.RETRY_BASE_DELAY * attempt + random.uniform(0, 2)
                time.sleep(retry_delay)
            else:
                result["status"] = "failed"
                result["error"] = f"重试 {max_retries} 次后仍失败: {err_msg}"

    return result


def run_crawler_http(
    urls: List[str],
    output_path: str = None,
    max_workers: int = 10,
) -> List[Dict[str, Any]]:
    """
    HTTP 批量爬虫主入口
    返回所有 URL 的处理结果列表
    """
    output_path = output_path or config.DEFAULT_OUTPUT_FILE
    ensure_dirs()

    total = len(urls)
    print(f"[HTTP] 总 URL 数: {total}")

    if not urls:
        return []

    results = []
    batch_results = []
    flush_interval = 10

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_url = {
            executor.submit(process_single_url_http, url): url
            for url in urls
        }

        pbar = tqdm(total=total, desc="[HTTP] 提取 Seller ID", unit="页")
        for future in as_completed(future_to_url):
            result = future.result()
            results.append(result)
            batch_results.append(result)
            pbar.update(1)

            # 实时保存
            if len(batch_results) >= flush_interval:
                save_results(batch_results, output_path, mode="a")
                batch_results.clear()

        pbar.close()

    # 刷新剩余结果
    if batch_results:
        save_results(batch_results, output_path, mode="a")

    # 统计
    success_count = sum(1 for r in results if r.get("status") == "success" and r.get("seller_id"))
    failed_count = sum(1 for r in results if r.get("status") in ("failed", "error"))
    captcha_count = sum(1 for r in results if r.get("status") == "captcha")
    no_seller_count = sum(1 for r in results if r.get("status") == "no_seller_id")
    incomplete_count = sum(1 for r in results if r.get("status") == "incomplete_page")
    unavailable_count = sum(1 for r in results if r.get("status") == "unavailable")
    shipping_count = sum(1 for r in results if r.get("status") == "shipping_restricted")

    print(f"\n[HTTP] 完成！")
    print(f"   成功提取: {success_count}/{total} ({success_count / total * 100:.1f}%)")
    print(f"   页面不完整(需浏览器兜底): {incomplete_count}")
    print(f"   未检测到 Seller ID: {no_seller_count}")
    print(f"   商品不可用: {unavailable_count}")
    print(f"   地区限制: {shipping_count}")
    print(f"   验证码/反爬: {captcha_count}")
    print(f"   网络失败: {failed_count}")

    return results


def main():
    """CLI 入口（独立运行 HTTP 爬虫）"""
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser(description="亚马逊 Seller ID HTTP 批量提取工具")
    parser.add_argument("--input", "-i", help="输入文件路径", default=config.DEFAULT_INPUT_FILE)
    parser.add_argument("--output", "-o", help="输出文件路径", default=config.DEFAULT_OUTPUT_FILE)
    parser.add_argument("--workers", "-w", type=int, help="并发线程数", default=10)
    parser.add_argument("--proxy", help="代理服务器地址", default=config.PROXY_SERVER)
    parser.add_argument("--diagnose", "-d", help="诊断模式：保存 no_seller_id 的 HTML 到指定目录", default=None)
    args = parser.parse_args()

    global _DIAGNOSE_DIR
    _DIAGNOSE_DIR = args.diagnose

    if args.proxy:
        config.PROXY_SERVER = args.proxy

    if not Path(args.input).exists():
        print(f"错误: 输入文件不存在: {args.input}")
        return

    urls = load_urls(args.input)
    print(f"加载到 {len(urls)} 个 URL")

    # 清空输出文件并写入表头
    if Path(args.output).exists():
        Path(args.output).unlink()
    save_results([], args.output, mode="w")

    run_crawler_http(urls, output_path=args.output, max_workers=args.workers)


if __name__ == "__main__":
    main()
