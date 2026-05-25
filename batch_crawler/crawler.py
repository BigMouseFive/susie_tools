"""
亚马逊 Seller ID 批量提取爬虫（优化版）
使用 Playwright 浏览器自动化，每个 worker 独立 browser 实例
"""

import asyncio
import random
import sys
from pathlib import Path

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout
from playwright_stealth import Stealth
from tqdm.asyncio import tqdm

import config
from utils import (
    ensure_dirs, get_random_ua, parse_asin_from_url,
    load_urls, load_existing_results, save_results, filter_pending_urls
)

# 全局信号量控制并发
_semaphore = None


async def load_extract_script() -> str:
    """加载页面内执行的 JS 提取脚本"""
    script_path = Path(__file__).parent / "extract_seller.js"
    with open(script_path, "r", encoding="utf-8") as f:
        return f.read()


def should_block_route(route) -> bool:
    """判断是否应该拦截该资源请求"""
    if not config.BLOCK_UNNECESSARY_RESOURCES:
        return False
    resource_type = route.request.resource_type
    url = route.request.url.lower()
    blocked_types = {"image", "media", "font", "stylesheet"}
    blocked_exts = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".woff", ".woff2", ".ttf", ".css", ".mp4", ".webp")
    if resource_type in blocked_types:
        return True
    if any(url.endswith(ext) for ext in blocked_exts):
        return True
    # 拦截一些亚马逊的追踪/分析请求
    if "analytics" in url or "metrics" in url or "telemetry" in url:
        return True
    return False


async def setup_page(page):
    """设置页面：资源拦截、viewport"""
    await page.set_viewport_size(
        {"width": config.VIEWPORT_WIDTH, "height": config.VIEWPORT_HEIGHT}
    )
    if config.BLOCK_UNNECESSARY_RESOURCES:
        await page.route("**/*", lambda route: route.abort() if should_block_route(route) else route.continue_())


async def smart_wait_for_seller(page, timeout_ms: int = None, interval_ms: int = None) -> bool:
    """
    智能等待：轮询检测页面中是否出现了 seller 相关信息
    返回 True 表示检测到，False 表示超时
    """
    timeout = timeout_ms or config.SMART_WAIT_TIMEOUT
    interval = interval_ms or config.SMART_WAIT_INTERVAL
    elapsed = 0
    seller_selectors = [
        'input[name="merchantID"][value]:not([value=""])',
        '#merchant-info:not(:empty)',
        '#merchantInfoFeature',
        '[data-merchant-id]:not([data-merchant-id=""])',
        'a[href*="merchant="]',
        'a[href*="seller="]',
        'a[href*="/sp?seller="]',
        'a[href*="/gp/aag/main"]',
        '#buybox',
        '.tabular-buybox-text[href*="merchant"]',
        '#olpLink',
        'a[href*="offer-listing"]',
    ]
    while elapsed < timeout:
        # 检查是否有任一关键元素存在且有内容
        found = await page.evaluate(
            """
            (selectors) => {
                for (const sel of selectors) {
                    const el = document.querySelector(sel);
                    if (el) {
                        // 对于链接，检查 href 是否有内容
                        if (el.tagName === 'A') {
                            if (el.getAttribute('href') && el.getAttribute('href').length > 5) return true;
                        }
                        // 对于有文本的元素，检查非空
                        if (el.textContent && el.textContent.trim().length > 0) return true;
                        // 对于 input，检查 value
                        if (el.value && el.value.trim().length > 0) return true;
                        // 对于 data 属性
                        const dm = el.getAttribute('data-merchant-id');
                        if (dm && dm.trim().length > 0) return true;
                    }
                }
                return false;
            }
            """,
            seller_selectors,
        )
        if found:
            return True
        await asyncio.sleep(interval / 1000)
        elapsed += interval
    return False


async def dismiss_interference(page):
    """自动清理干扰元素：cookie 横幅、地区弹窗等"""
    try:
        # Cookie 横幅（多种可能的选择器）
        cookie_selectors = [
            '#sp-cc-accept',
            '[data-cel-widget="gdpr-consent-banner"] input[type="submit"]',
            '#a-autoid-0-announce',
            'input[name="accept"]',
            'button:has-text("Accept")',
        ]
        for sel in cookie_selectors:
            try:
                btn = await page.query_selector(sel)
                if btn and await btn.is_visible():
                    # 使用短 timeout 避免点击操作卡住
                    await btn.click(timeout=3000)
                    await asyncio.sleep(0.3)
            except Exception:
                pass

        # 地区选择弹窗
        location_selectors = [
            '[data-action="a-popover-close"]',
            '.a-popover-header .a-button-close',
            '#glow-ingress-block',
        ]
        for sel in location_selectors:
            try:
                btn = await page.query_selector(sel)
                if btn and await btn.is_visible():
                    await btn.click(timeout=3000)
                    await asyncio.sleep(0.3)
            except Exception:
                pass
    except Exception:
        pass


async def scroll_page(page):
    """滚动页面触发懒加载"""
    try:
        await page.evaluate("""
            () => {
                window.scrollBy(0, 400);
                setTimeout(() => window.scrollBy(0, 400), 300);
                setTimeout(() => window.scrollBy(0, -200), 600);
            }
        """)
        await asyncio.sleep(0.8)
    except Exception:
        pass


async def process_single_url(
    page,
    url: str,
    extract_script: str,
    max_retries: int = config.MAX_RETRIES,
) -> dict:
    """
    处理单个 URL，返回结果字典
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
    await asyncio.sleep(delay)

    for attempt in range(1, max_retries + 1):
        try:
            # 导航到页面
            response = await page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=config.PAGE_TIMEOUT,
            )

            # 清理干扰元素
            await dismiss_interference(page)

            # 智能等待 seller 相关元素出现
            seller_appeared = await smart_wait_for_seller(page)

            # 如果智能等待超时，再滚动一下页面触发懒加载
            if not seller_appeared:
                await scroll_page(page)
                seller_appeared = await smart_wait_for_seller(page, timeout_ms=5000)

            # 额外等待 JS 渲染
            await asyncio.sleep(random.uniform(0.5, 1.0))

            # 执行提取脚本
            data = await page.evaluate(extract_script)

            if not isinstance(data, dict):
                raise ValueError(f"提取脚本返回异常: {type(data)}")

            result["seller_id"] = (data.get("sellerId") or data.get("seller_id") or "").strip()
            result["seller_name"] = (data.get("sellerName") or data.get("seller_name") or "").strip()
            result["title"] = (data.get("title") or "").strip()
            result["asin"] = (data.get("asin") or result["asin"] or "").strip()
            page_status = data.get("pageStatus", "normal")
            result["page_status"] = page_status

            if page_status == "shipping_restricted":
                result["status"] = "shipping_restricted"
                result["error"] = "该商品无法配送到当前地区，亚马逊未显示 Seller 信息。建议配置对应国家/地区的代理后重试。"
            elif page_status == "page_not_found":
                result["status"] = "page_not_found"
                result["error"] = "商品页面不存在（ASIN 可能已下架或无效）"
            elif page_status == "unavailable":
                result["status"] = "unavailable"
                result["error"] = "商品当前不可用"
            elif result["seller_id"]:
                result["status"] = "success"
                result["error"] = ""
            else:
                result["status"] = "no_seller_id"
                result["error"] = "页面中未检测到 Seller ID（可能为亚马逊自营、页面结构异常或需要代理）"

            return result

        except Exception as e:
            err_msg = str(e)
            result["error"] = err_msg
            result["status"] = "error"

            if attempt < max_retries:
                retry_delay = config.RETRY_BASE_DELAY * attempt + random.uniform(0, 2)
                await asyncio.sleep(retry_delay)
                # 重试前刷新页面，清理可能的状态污染
                try:
                    await page.reload(wait_until="domcontentloaded", timeout=config.PAGE_TIMEOUT)
                except Exception:
                    pass
            else:
                result["status"] = "failed"
                result["error"] = f"重试 {max_retries} 次后仍失败: {err_msg}"

    return result


async def worker_task(
    worker_id: int,
    queue: asyncio.Queue,
    extract_script: str,
    pbar: tqdm,
    output_path: str,
):
    """
    工作协程：每个 worker 拥有独立的 browser 实例
    处理 BATCH_SIZE_PER_BROWSER 个 URL 后重启 browser
    """
    stealth = Stealth()
    batch_count = 0
    browser = None
    context = None
    page = None

    async def init_browser():
        nonlocal browser, context, page
        p = await async_playwright().start()
        b = await p.chromium.launch(
            headless=config.HEADLESS,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-web-security",
                "--disable-features=IsolateOrigins,site-per-process",
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ],
        )
        ctx = await b.new_context(
            viewport={"width": config.VIEWPORT_WIDTH, "height": config.VIEWPORT_HEIGHT},
            user_agent=get_random_ua(),
            locale="en-US",
            timezone_id="America/New_York",
        )
        if config.PROXY_SERVER:
            # 注意：proxy 需要在 new_context 时传入，这里已在上层处理
            pass
        await stealth.apply_stealth_async(ctx)
        pg = await ctx.new_page()
        await setup_page(pg)
        browser = b
        context = ctx
        page = pg
        return p

    playwright = await init_browser()
    batch_results = []
    flush_interval = 5

    try:
        while True:
            try:
                url = queue.get_nowait()
            except asyncio.QueueEmpty:
                break

            async with _semaphore:
                # 如果达到批次上限，重启 browser
                if batch_count >= config.BATCH_SIZE_PER_BROWSER:
                    try:
                        await page.close()
                        await context.close()
                        await browser.close()
                        await playwright.stop()
                    except Exception:
                        pass
                    playwright = await init_browser()
                    batch_count = 0

                try:
                    result = await process_single_url(page, url, extract_script)
                except Exception as e:
                    result = {
                        "url": url,
                        "asin": parse_asin_from_url(url),
                        "seller_id": "",
                        "seller_name": "",
                        "status": "error",
                        "error": f"未捕获异常: {str(e)}",
                        "title": "",
                        "page_status": "",
                    }

                batch_results.append(result)
                batch_count += 1
                pbar.update(1)

                # 实时保存
                if len(batch_results) >= flush_interval:
                    save_results(batch_results, output_path, mode="a")
                    batch_results.clear()

    finally:
        # 刷新剩余结果
        if batch_results:
            save_results(batch_results, output_path, mode="a")

        # 清理资源
        try:
            await page.close()
            await context.close()
            await browser.close()
            await playwright.stop()
        except Exception:
            pass


async def run_crawler(
    urls: list,
    output_path: str = None,
    input_path: str = None,
):
    """
    主入口：批量爬取 Seller ID
    """
    output_path = output_path or config.DEFAULT_OUTPUT_FILE
    ensure_dirs()

    # 断点续跑：加载已处理结果
    existing = load_existing_results(output_path)
    pending_urls = filter_pending_urls(urls, existing)

    total = len(urls)
    already_done = total - len(pending_urls)

    print(f"总 URL 数: {total}")
    print(f"已处理成功: {already_done}")
    print(f"待处理: {len(pending_urls)}")

    if not pending_urls:
        print("所有 URL 已处理完成，无需继续。")
        return

    # 如果输出文件不存在，先写入表头
    if not Path(output_path).exists() or Path(output_path).stat().st_size == 0:
        save_results([], output_path, mode="w")

    # 加载提取脚本
    extract_script = await load_extract_script()

    # 初始化并发信号量
    global _semaphore
    _semaphore = asyncio.Semaphore(config.CONCURRENCY)

    # 创建任务队列
    queue = asyncio.Queue()
    for url in pending_urls:
        queue.put_nowait(url)

    pbar = tqdm(total=len(pending_urls), desc="提取 Seller ID", unit="页")

    # 启动 worker（每个 worker 独立 browser 实例）
    workers = [
        asyncio.create_task(
            worker_task(i, queue, extract_script, pbar, output_path)
        )
        for i in range(config.CONCURRENCY)
    ]

    await asyncio.gather(*workers)
    pbar.close()

    # 最终统计：只统计当前输入 URL 列表中的结果，避免历史残留数据干扰
    final_results = load_existing_results(output_path)

    success_count = sum(
        1 for url in urls
        if (r := final_results.get(url))
        and r.get("status") == "success"
        and r.get("seller_id")
    )
    failed_count = sum(
        1 for url in urls
        if (r := final_results.get(url))
        and r.get("status") in ("failed", "error")
    )
    restricted_count = sum(
        1 for url in urls
        if (r := final_results.get(url))
        and r.get("status") == "shipping_restricted"
    )
    no_seller_count = sum(
        1 for url in urls
        if (r := final_results.get(url))
        and r.get("status") == "no_seller_id"
    )

    # 防御性检查：成功数不应超过总数
    if success_count > total:
        print(f"\n⚠️ 警告：成功数({success_count})超过总URL数({total})，可能存在历史残留数据")
        success_count = min(success_count, total)

    print(f"\n✅ 完成！结果已保存到: {output_path}")
    print(f"   总 URL: {total}")
    print(f"   成功提取 Seller ID: {success_count}")
    print(f"   未检测到 Seller ID: {no_seller_count}")
    print(f"   地区限制: {restricted_count}")
    print(f"   网络/页面失败: {failed_count}")
    print(f"   成功率: {success_count / total * 100:.1f}%")

    # 返回当前输入 URLs 对应的结果列表，供 Hybrid 调用方使用
    return [final_results.get(url, {"url": url, "status": "unknown"}) for url in urls]


def main():
    """CLI 入口"""
    import argparse

    parser = argparse.ArgumentParser(description="亚马逊 Seller ID 批量提取工具")
    parser.add_argument("--input", "-i", help="输入文件路径 (.csv 或 .txt)", default=config.DEFAULT_INPUT_FILE)
    parser.add_argument("--output", "-o", help="输出文件路径 (.csv)", default=config.DEFAULT_OUTPUT_FILE)
    parser.add_argument("--concurrency", "-c", type=int, help="并发数", default=config.CONCURRENCY)
    parser.add_argument("--headless", action="store_true", help="无头模式", default=config.HEADLESS)
    parser.add_argument("--proxy", help="代理服务器地址", default=config.PROXY_SERVER)
    parser.add_argument("--no-block", action="store_true", help="禁用资源拦截（用于调试）")
    args = parser.parse_args()

    # 命令行参数覆盖配置
    if args.concurrency:
        config.CONCURRENCY = args.concurrency
    if args.headless is not None:
        config.HEADLESS = args.headless
    if args.proxy:
        config.PROXY_SERVER = args.proxy
    if args.no_block:
        config.BLOCK_UNNECESSARY_RESOURCES = False

    # 检查输入文件
    if not Path(args.input).exists():
        print(f"错误: 输入文件不存在: {args.input}")
        print(f"请将 URL 列表放入该路径，或指定 --input 参数")
        sys.exit(1)

    urls = load_urls(args.input)
    print(f"加载到 {len(urls)} 个 URL")

    asyncio.run(run_crawler(urls, output_path=args.output, input_path=args.input))


if __name__ == "__main__":
    main()
