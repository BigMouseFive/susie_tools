"""
基于 curl_cffi 的 Seller ID 批量提取爬虫
模拟 Chrome TLS 指纹 + HTTP/2 + 完整浏览器请求头，绕过亚马逊反爬检测
支持多轮重试：失败 URL 自动进入下一轮重新处理
"""

import random
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Tuple
from urllib.parse import urlparse
from pathlib import Path

from curl_cffi import requests
from tqdm import tqdm

import config
import hashlib
from extract_seller_http import extract_seller_from_html
from utils import (
    ensure_dirs, parse_asin_from_url,
    load_urls, load_existing_results, save_results
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


def _get_session(force_refresh: bool = False) -> requests.Session:
    """获取当前线程的 curl_cffi Session（模拟 Chrome 124）"""
    if force_refresh and hasattr(_thread_local, "session"):
        try:
            _thread_local.session.close()
        except Exception:
            pass
        delattr(_thread_local, "session")

    if not hasattr(_thread_local, "session"):
        _thread_local.session = requests.Session(impersonate="chrome124")
        if config.PROXY_SERVER:
            _thread_local.session.proxies = {
                "http": config.PROXY_SERVER,
                "https": config.PROXY_SERVER,
            }
    return _thread_local.session


def _refresh_session():
    """强制刷新当前线程的 Session（用于 captcha 后或定期轮换）"""
    _get_session(force_refresh=True)


def _maybe_refresh_session(urls_processed: int, refresh_every: int = 15):
    """每处理 N 个 URL 后自动刷新 Session"""
    if urls_processed > 0 and urls_processed % refresh_every == 0:
        _refresh_session()


_DIAGNOSE_DIR = None  # 诊断目录


def _save_diagnose_html(url: str, html: str, status: str):
    """保存诊断 HTML"""
    if not _DIAGNOSE_DIR:
        return
    try:
        diag_dir = Path(_DIAGNOSE_DIR)
        diag_dir.mkdir(parents=True, exist_ok=True)
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
    html = ""  # 用于 diagnose 保存

    for attempt in range(1, max_retries + 1):
        try:
            headers = get_random_headers(url)
            # captcha 后的重试使用更长超时
            is_captcha_retry = attempt > 1 and html and 'security check' in html.lower()
            timeout = 40 if is_captcha_retry else config.PAGE_TIMEOUT / 1000
            response = session.get(
                url,
                headers=headers,
                timeout=timeout,
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
                # captcha：刷新 Session + 超长延迟后重试
                if attempt < max_retries:
                    result["error"] = f"第 {attempt} 次遇到验证码，刷新 Session 后重试..."
                    _refresh_session()
                    retry_delay = 10 + random.uniform(5, 15)
                    time.sleep(retry_delay)
                    continue
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
            elif result["seller_id"]:
                result["status"] = "success"
                result["error"] = ""
            else:
                result["status"] = "no_seller_id"
                result["error"] = "页面中未检测到 Seller ID"

            # 保存 diagnose（所有非 success 状态）
            if _DIAGNOSE_DIR and result["status"] != "success" and html:
                _save_diagnose_html(url, html, result["status"])

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

    # 循环结束后（所有重试耗尽），保存 diagnose
    if _DIAGNOSE_DIR and result["status"] != "success" and html:
        _save_diagnose_html(url, html, result["status"])

    return result


def _run_single_round(
    urls: List[str],
    max_workers: int,
    round_num: int,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    处理单轮 URL
    返回: (成功结果列表, 失败结果列表)
    """
    total = len(urls)
    success_results = []
    failed_results = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_url = {
            executor.submit(process_single_url_http, url): url
            for url in urls
        }

        pbar = tqdm(
            total=total,
            desc=f"[HTTP 第{round_num + 1}轮]",
            unit="页",
        )
        fail_count = 0
        processed_count = 0

        for future in as_completed(future_to_url):
            result = future.result()
            processed_count += 1
            if result.get("status") == "success" and result.get("seller_id"):
                success_results.append(result)
            else:
                failed_results.append(result)
                fail_count += 1
            pbar.set_postfix(failed=fail_count)
            pbar.update(1)

            # Session 定期刷新（线程安全：每个线程独立计数）
            _maybe_refresh_session(processed_count, refresh_every=15)

        pbar.close()

    return success_results, failed_results


def _print_failed_results(results: List[Dict[str, Any]]):
    """命令行输出失败详情"""
    failed = [r for r in results if r.get("status") != "success" or not r.get("seller_id")]
    if not failed:
        return

    print("\n" + "=" * 80)
    print("❌ 失败详情（未写入 CSV）")
    print("=" * 80)
    print(f"{'URL':<50} | {'状态':<18} | 错误信息")
    print("-" * 80)
    for r in failed:
        url = r.get("url", "")[:48]
        status = r.get("status", "")[:16]
        error = r.get("error", "")[:40]
        print(f"{url:<50} | {status:<18} | {error}")
    print("=" * 80)


def run_crawler_http(
    urls: List[str],
    output_path: str = None,
    max_workers: int = 10,
    max_rounds: int = 1,
) -> List[Dict[str, Any]]:
    """
    HTTP 批量爬虫主入口（支持多轮重试）

    Args:
        urls: URL 列表
        output_path: 输出 CSV 路径（只写入成功结果）
        max_workers: 并发线程数
        max_rounds: 轮次重试次数（默认 1，即不重试）

    Returns:
        所有 URL 的最新结果列表
    """
    output_path = output_path or config.DEFAULT_OUTPUT_FILE
    ensure_dirs()

    total_initial = len(urls)
    print(f"[HTTP] 总 URL 数: {total_initial}，轮次: {max_rounds}")

    if not urls:
        return []

    # 清空输出文件并写入表头
    out_path = Path(output_path)
    if out_path.exists():
        out_path.unlink()
    save_results([], output_path, mode="w")

    all_results: Dict[str, Dict[str, Any]] = {}  # url -> 最新结果
    pending = urls[:]

    for round_num in range(max_rounds):
        if not pending:
            break

        success_results, failed_results = _run_single_round(
            pending, max_workers, round_num
        )

        # 成功结果写入 CSV
        if success_results:
            save_results(success_results, output_path, mode="a")

        # 更新所有结果（成功和失败都保留最新）
        for r in success_results + failed_results:
            all_results[r["url"]] = r

        # 准备下一轮：收集失败的 URL
        failed_urls = [r["url"] for r in failed_results]

        if round_num < max_rounds - 1 and failed_urls:
            print(f"\n>>> 第 {round_num + 2} 轮重试: {len(failed_urls)} 个 URL")
            pending = failed_urls[:]
            time.sleep(3)  # 轮次间冷却
        else:
            break

    results_list = list(all_results.values())

    # 最终统计
    success_count = sum(
        1 for r in results_list
        if r.get("status") == "success" and r.get("seller_id")
    )
    failed_count = sum(
        1 for r in results_list
        if r.get("status") in ("failed", "error")
    )
    captcha_count = sum(1 for r in results_list if r.get("status") == "captcha")
    no_seller_count = sum(1 for r in results_list if r.get("status") == "no_seller_id")
    incomplete_count = sum(1 for r in results_list if r.get("status") == "incomplete_page")
    unavailable_count = sum(1 for r in results_list if r.get("status") == "unavailable")
    shipping_count = sum(1 for r in results_list if r.get("status") == "shipping_restricted")

    print(f"\n[HTTP] 完成！")
    print(f"   成功提取: {success_count}/{total_initial} ({success_count / total_initial * 100:.1f}%)")
    if max_rounds > 1:
        print(f"   最终失败: {total_initial - success_count}")
    print(f"   页面不完整: {incomplete_count}")
    print(f"   未检测到 Seller ID: {no_seller_count}")
    print(f"   商品不可用: {unavailable_count}")
    print(f"   地区限制: {shipping_count}")
    print(f"   验证码/反爬: {captcha_count}")
    print(f"   网络失败: {failed_count}")

    # 命令行输出失败详情
    _print_failed_results(results_list)

    return results_list


def main():
    """CLI 入口（独立运行 HTTP 爬虫）"""
    import argparse

    parser = argparse.ArgumentParser(description="亚马逊 Seller ID HTTP 批量提取工具")
    parser.add_argument("--input", "-i", help="输入文件路径", default=config.DEFAULT_INPUT_FILE)
    parser.add_argument("--output", "-o", help="输出文件路径", default=config.DEFAULT_OUTPUT_FILE)
    parser.add_argument("--workers", "-w", type=int, help="并发线程数", default=10)
    parser.add_argument("--proxy", help="代理服务器地址", default=config.PROXY_SERVER)
    parser.add_argument("--retries", "-r", type=int, help="轮次重试次数（默认 3）", default=3)
    parser.add_argument("--diagnose", "-d", help="诊断模式目录（默认 diagnose）", default="diagnose")
    parser.add_argument("--no-diagnose", action="store_true", help="禁用诊断模式")
    args = parser.parse_args()

    global _DIAGNOSE_DIR
    _DIAGNOSE_DIR = None if args.no_diagnose else args.diagnose

    if args.proxy:
        config.PROXY_SERVER = args.proxy

    if not Path(args.input).exists():
        print(f"错误: 输入文件不存在: {args.input}")
        return

    urls = load_urls(args.input)
    print(f"加载到 {len(urls)} 个 URL")

    run_crawler_http(
        urls,
        output_path=args.output,
        max_workers=args.workers,
        max_rounds=args.retries + 1,  # retries=3 表示最多 4 轮（初始 + 3 次重试）
    )


if __name__ == "__main__":
    main()
