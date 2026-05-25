"""
HTTP 批量爬虫入口
基于 curl_cffi 模拟 Chrome TLS 指纹 + HTTP/2，绕过亚马逊反爬检测
"""

import sys
from pathlib import Path
from typing import List, Dict, Any

import config
from crawler_http import run_crawler_http
from utils import (
    ensure_dirs, load_urls, load_existing_results, save_results
)


def run_crawler(
    urls: List[str],
    output_path: str = None,
    max_workers: int = 10,
):
    """
    批量爬虫主入口
    """
    output_path = output_path or config.DEFAULT_OUTPUT_FILE
    ensure_dirs()

    total = len(urls)
    print("=" * 50)
    print("批量爬虫启动")
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

    # 清空临时输出
    if Path(output_path).exists():
        Path(output_path).unlink()
    save_results([], output_path, mode="w")

    results = run_crawler_http(
        pending_urls,
        output_path=output_path,
        max_workers=max_workers,
    )

    # 合并已有成功记录
    result_map = {r["url"]: r for r in results}
    for url in already_success:
        if url not in result_map:
            result_map[url] = existing[url]

    # 重新写入完整结果
    if Path(output_path).exists():
        Path(output_path).unlink()
    save_results([], output_path, mode="w")
    save_results(list(result_map.values()), output_path, mode="a")

    print(f"\n结果已保存: {output_path}")
    _print_final_stats(urls, result_map)


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
    print("✅ 批量爬虫完成")
    print("=" * 50)
    print(f"   总 URL: {total}")
    print(f"   成功提取 Seller ID: {success_count}")
    print(f"   页面不完整: {incomplete_count}")
    print(f"   未检测到 Seller ID: {no_seller_count}")
    print(f"   商品不可用: {unavailable_count}")
    print(f"   地区限制: {restricted_count}")
    print(f"   验证码/反爬: {captcha_count}")
    print(f"   网络失败: {failed_count}")
    print(f"   成功率: {success_count / total * 100:.1f}%")
    print("=" * 50)


def main():
    """CLI 入口"""
    import argparse

    parser = argparse.ArgumentParser(description="亚马逊 Seller ID HTTP 批量提取工具")
    parser.add_argument("--input", "-i", help="输入文件路径", default=config.DEFAULT_INPUT_FILE)
    parser.add_argument("--output", "-o", help="输出文件路径", default=config.DEFAULT_OUTPUT_FILE)
    parser.add_argument("--workers", "-w", type=int, help="并发线程数", default=10)
    parser.add_argument("--proxy", help="代理服务器地址", default=config.PROXY_SERVER)
    args = parser.parse_args()

    if args.proxy:
        config.PROXY_SERVER = args.proxy

    if not Path(args.input).exists():
        print(f"错误: 输入文件不存在: {args.input}")
        sys.exit(1)

    urls = load_urls(args.input)
    print(f"加载到 {len(urls)} 个 URL")

    run_crawler(urls, output_path=args.output, max_workers=args.workers)


if __name__ == "__main__":
    main()
