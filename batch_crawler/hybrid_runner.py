"""
Hybrid 混合调度入口
第一轮：requests HTTP 快速通道
第二轮：Playwright 浏览器兜底
"""

import asyncio
import sys
from pathlib import Path
from typing import List, Dict, Any

import config
from crawler import run_crawler as run_crawler_playwright
from crawler_http import run_crawler_http
from utils import (
    ensure_dirs, load_urls, load_existing_results, save_results
)


def collect_failed_urls(results: List[Dict[str, Any]]) -> List[str]:
    """收集 HTTP 轮中失败的 URL，用于第二轮 Playwright 兜底"""
    failed = []
    for r in results:
        status = r.get("status", "")
        seller_id = r.get("seller_id", "")
        # 以下情况需要 fallback 到 Playwright：
        # - 未成功提取 seller_id（no_seller_id, captcha, error, failed）
        # - 地区限制（shipping_restricted）换浏览器也没用，但保留在结果中不重复处理
        if status not in ("success", "shipping_restricted") or not seller_id:
            failed.append(r["url"])
    return failed


def merge_results(
    http_results: List[Dict[str, Any]],
    playwright_results: List[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """
    合并 HTTP 和 Playwright 的结果
    Playwright 结果优先覆盖 HTTP 结果（因为 Playwright 更准确）
    """
    merged = {}
    for r in http_results:
        merged[r["url"]] = r
    for r in playwright_results:
        # Playwright 结果覆盖 HTTP 结果（只要 Playwright 有结果）
        merged[r["url"]] = r
    return merged


async def run_hybrid(
    urls: List[str],
    output_path: str = None,
    http_workers: int = 10,
    http_output_path: str = None,
    playwright_output_path: str = None,
):
    """
    Hybrid 主入口
    """
    output_path = output_path or config.DEFAULT_OUTPUT_FILE
    http_output_path = http_output_path or str(Path(output_path).with_suffix('.http.csv'))
    playwright_output_path = playwright_output_path or str(Path(output_path).with_suffix('.playwright.csv'))
    ensure_dirs()

    total = len(urls)
    print("=" * 50)
    print("Hybrid 混合爬虫启动")
    print(f"总 URL 数: {total}")
    print("=" * 50)

    # 检查已有结果（断点续跑）
    existing = load_existing_results(output_path)
    already_success = [
        url for url in urls
        if (r := existing.get(url))
        and r.get("status") == "success"
        and r.get("seller_id")
    ]
    pending_urls = [url for url in urls if url not in already_success]

    if already_success:
        print(f"\n已处理成功（跳过）: {len(already_success)}")
    print(f"待处理: {len(pending_urls)}\n")

    if not pending_urls:
        print("所有 URL 已处理完成！")
        _print_final_stats(urls, existing)
        return

    # ========== 第一轮：HTTP 快速通道 ==========
    print("\n>>> 第一轮：HTTP 快速通道")
    print(f"并发线程: {http_workers}")

    # 清空 HTTP 临时输出
    if Path(http_output_path).exists():
        Path(http_output_path).unlink()
    save_results([], http_output_path, mode="w")

    http_results = run_crawler_http(
        pending_urls,
        output_path=http_output_path,
        max_workers=http_workers,
    )

    # 收集需要 fallback 的 URL
    fallback_urls = collect_failed_urls(http_results)
    http_success = [r for r in http_results if r.get("status") == "success" and r.get("seller_id")]

    print(f"\n[HTTP 汇总] 成功: {len(http_success)}, 需兜底: {len(fallback_urls)}")

    # ========== 第二轮：Playwright 兜底 ==========
    playwright_results = []
    if fallback_urls:
        print("\n>>> 第二轮：Playwright 浏览器兜底")
        print(f"兜底 URL 数: {len(fallback_urls)}")

        # 清空 Playwright 临时输出
        if Path(playwright_output_path).exists():
            Path(playwright_output_path).unlink()
        save_results([], playwright_output_path, mode="w")

        playwright_results = await run_crawler_playwright(
            fallback_urls,
            output_path=playwright_output_path,
        )

    # ========== 合并结果 ==========
    print("\n>>> 合并结果")
    merged = merge_results(http_results, playwright_results)

    # 合并已有成功记录
    for url in already_success:
        if url not in merged:
            merged[url] = existing[url]

    # 写入最终输出
    if Path(output_path).exists():
        Path(output_path).unlink()
    save_results([], output_path, mode="w")
    save_results(list(merged.values()), output_path, mode="a")

    print(f"最终结果已保存: {output_path}")

    # 最终统计
    _print_final_stats(urls, merged)


def _print_final_stats(urls: List[str], results: Dict[str, Dict[str, Any]]):
    """打印最终统计"""
    total = len(urls)

    success_count = sum(
        1 for url in urls
        if (r := results.get(url))
        and r.get("status") == "success"
        and r.get("seller_id")
    )
    failed_count = sum(
        1 for url in urls
        if (r := results.get(url))
        and r.get("status") in ("failed", "error")
    )
    restricted_count = sum(
        1 for url in urls
        if (r := results.get(url))
        and r.get("status") == "shipping_restricted"
    )
    no_seller_count = sum(
        1 for url in urls
        if (r := results.get(url))
        and r.get("status") == "no_seller_id"
    )
    incomplete_count = sum(
        1 for url in urls
        if (r := results.get(url))
        and r.get("status") == "incomplete_page"
    )
    unavailable_count = sum(
        1 for url in urls
        if (r := results.get(url))
        and r.get("status") == "unavailable"
    )
    captcha_count = sum(
        1 for url in urls
        if (r := results.get(url))
        and r.get("status") == "captcha"
    )

    if success_count > total:
        success_count = min(success_count, total)

    print("\n" + "=" * 50)
    print("✅ Hybrid 混合爬虫完成")
    print("=" * 50)
    print(f"   总 URL: {total}")
    print(f"   成功提取 Seller ID: {success_count}")
    print(f"   页面不完整(浏览器兜底): {incomplete_count}")
    print(f"   未检测到 Seller ID: {no_seller_count}")
    print(f"   商品不可用: {unavailable_count}")
    print(f"   地区限制: {restricted_count}")
    print(f"   验证码/反爬: {captcha_count}")
    print(f"   网络/页面失败: {failed_count}")
    print(f"   成功率: {success_count / total * 100:.1f}%")
    print("=" * 50)


def main():
    """CLI 入口"""
    import argparse

    parser = argparse.ArgumentParser(description="亚马逊 Seller ID Hybrid 混合提取工具")
    parser.add_argument("--input", "-i", help="输入文件路径", default=config.DEFAULT_INPUT_FILE)
    parser.add_argument("--output", "-o", help="输出文件路径", default=config.DEFAULT_OUTPUT_FILE)
    parser.add_argument("--http-workers", "-w", type=int, help="HTTP 并发线程数", default=10)
    parser.add_argument("--proxy", help="代理服务器地址", default=config.PROXY_SERVER)
    parser.add_argument("--playwright-only", action="store_true", help="仅使用 Playwright（跳过 HTTP 轮）")
    args = parser.parse_args()

    if args.proxy:
        config.PROXY_SERVER = args.proxy

    if not Path(args.input).exists():
        print(f"错误: 输入文件不存在: {args.input}")
        sys.exit(1)

    urls = load_urls(args.input)
    print(f"加载到 {len(urls)} 个 URL")

    if args.playwright_only:
        # 仅使用 Playwright（回退到原有行为）
        asyncio.run(run_crawler_playwright(urls, output_path=args.output))
    else:
        asyncio.run(run_hybrid(urls, output_path=args.output, http_workers=args.http_workers))


if __name__ == "__main__":
    main()
