"""
商品信息提取：标题、五点描述、主图原图 URL、类目路径与类目 ID
逻辑移植自 erp-plugin/popup/popup.js scrapeAmazonProduct
类目 ID 参考 amazon/tool/listing_fetch/fetcher.py _extract_browse_node
"""

import json
import re
from typing import List, Optional

from bs4 import BeautifulSoup

HI_RES_RE = re.compile(
    r'["\']hiRes["\']\s*:\s*["\']([^"\']+/images/I/[^"\']+)["\']',
    re.IGNORECASE,
)

MAIN_IMAGE_SELECTORS = (
    "#imgTagWrapperId img, #landingImage, #main-image, "
    "#main-image-container li img, #ivLargeImage img, "
    "#imageBlock .a-dynamic-image"
)

ALT_IMAGE_SELECTORS = (
    "#altImages img, #altImages li.imageThumbnail img, "
    "li.item.imageThumbnail img"
)

APLUS_SELECTORS = (
    "#aplus",
    "#aplus_feature_div",
    "#aplusBrandStory_feature_div",
    "#aplus3p_feature_div",
    "#dpx-aplus-product-description_feature_div",
    "#productDescription_feature_div",
    "#productDescription",
    ".aplus-v2",
    ".aplus-module",
)

MAX_GALLERY_IMAGES = 10

BREADCRUMB_CONTAINER_SELECTORS = (
    "#wayfinding-breadcrumbs_feature_div",
    "#wayfinding-breadcrumbs_container",
    ".a-breadcrumb",
    "[data-feature-name='breadcrumbs']",
)

NODE_ID_RE = re.compile(r"[?&]node=(\d+)", re.I)

BROWSE_NODE_JSON_PATTERNS = [
    re.compile(r'["\']browseNodeId["\']\s*:\s*["\'](\d+)["\']', re.I),
    re.compile(r'["\']browseNodeID["\']\s*:\s*["\'](\d+)["\']', re.I),
    re.compile(r'["\']categoryBrowseNodeId["\']\s*:\s*["\'](\d+)["\']', re.I),
    re.compile(r'["\']browseNode["\']\s*:\s*["\'](\d+)["\']', re.I),
]


def to_hi_res(url: Optional[str]) -> Optional[str]:
    """高清原图还原（对应插件 toHiRes）"""
    if not url or url.startswith("data:"):
        return None
    try:
        clean = re.sub(r"\._[A-Z0-9,_-]+_\.", ".", url).split("?")[0]
        if re.search(
            r"transparent-pixel|sprite|grey-pixel|gif-loader|play-icon|spinner",
            clean,
            re.I,
        ):
            return None
        if re.search(r"prime.*logo|marketing|badge|icon", clean, re.I):
            return None
        if not re.match(r"^https?://", clean, re.I):
            return None
        return clean
    except Exception:
        return None


def image_key(url: Optional[str]) -> Optional[str]:
    """图片去重 key（对应插件 imageKey）"""
    if not url:
        return None
    m = re.search(r"/images/I/([^./]+)", url, re.I)
    if m:
        return "I:" + m.group(1)
    return "U:" + url


class ImageCollector:
    """按 image_key 去重，保留最先出现的高清 URL"""

    def __init__(self):
        self._map: dict[str, str] = {}

    def add(self, url: Optional[str]) -> None:
        hi = to_hi_res(url)
        if not hi:
            return
        key = image_key(hi)
        if not key:
            return
        if key not in self._map:
            self._map[key] = hi

    def values(self) -> List[str]:
        return list(self._map.values())

    def keys(self) -> set[str]:
        return set(self._map.keys())


def _collect_from_img(img, collector: ImageCollector) -> None:
    collector.add(img.get("data-old-hires"))
    collector.add(img.get("src"))
    dyn = img.get("data-a-dynamic-image")
    if dyn:
        try:
            obj = json.loads(dyn)
            for u in (obj or {}).keys():
                collector.add(u)
        except (json.JSONDecodeError, TypeError):
            pass


def _extract_title(soup: BeautifulSoup) -> str:
    title_el = (
        soup.find(id="productTitle")
        or soup.find(attrs={"data-feature-name": "title"})
        or soup.find(id="title")
    )
    if title_el:
        return title_el.get_text(strip=True)
    return ""


def _extract_aplus_images(soup: BeautifulSoup) -> ImageCollector:
    """A+ 区图片采集（用于从主图画廊中剔除营销图）"""
    aplus_col = ImageCollector()
    aplus_roots: set = set()
    for sel in APLUS_SELECTORS:
        for el in soup.select(sel):
            aplus_roots.add(el)

    for root in aplus_roots:
        for img in root.find_all("img"):
            aplus_col.add(img.get("src"))
            aplus_col.add(img.get("data-src"))
            aplus_col.add(img.get("data-a-hires"))
            aplus_col.add(img.get("data-a-lazy-src"))
        for el in root.select('[style*="background-image"]'):
            style = el.get("style") or ""
            m = re.search(
                r'background-image:\s*url\(["\']?([^"\')]+)["\']?\)',
                style,
                re.I,
            )
            if m and m.group(1):
                aplus_col.add(m.group(1))
    return aplus_col


def _extract_gallery_images(soup: BeautifulSoup, html: str) -> List[str]:
    """
    产品图画廊原图（hiRes + 主图 DOM + altImages，剔除 A+ 重复）
    逻辑移植自 erp-plugin/popup/popup.js scrapeAmazonProduct
    """
    main_col = ImageCollector()

    for m in HI_RES_RE.finditer(html):
        main_col.add(m.group(1))

    for img in soup.select(MAIN_IMAGE_SELECTORS):
        _collect_from_img(img, main_col)

    for img in soup.select(ALT_IMAGE_SELECTORS):
        _collect_from_img(img, main_col)

    aplus_col = _extract_aplus_images(soup)
    aplus_keys = aplus_col.keys()
    main_images = [
        u for u in main_col.values()
        if image_key(u) not in aplus_keys
    ]
    return main_images[:MAX_GALLERY_IMAGES]


def _extract_category(soup: BeautifulSoup, html: str) -> tuple[str, str]:
    """
    提取类目完整路径与叶子 Browse Node ID

    Returns:
        (category_path, category_id)
    """
    category_names: List[str] = []
    node_ids: List[str] = []

    for sel in BREADCRUMB_CONTAINER_SELECTORS:
        container = soup.select_one(sel)
        if not container:
            continue
        for a in container.find_all("a", href=True):
            text = a.get_text(strip=True)
            if text and text not in ("›", ">") and len(text) < 100:
                if text not in category_names:
                    category_names.append(text)
            href = a.get("href", "")
            m = NODE_ID_RE.search(href)
            if m:
                node_ids.append(m.group(1))
        if category_names:
            break

    category_id = node_ids[-1] if node_ids else ""

    if not category_id:
        for a in soup.select(
            "#wayfinding-breadcrumbs_feature_div a, "
            "#wayfinding-breadcrumbs_container a"
        ):
            m = NODE_ID_RE.search(a.get("href", ""))
            if m:
                category_id = m.group(1)

    if not category_id:
        for pat in BROWSE_NODE_JSON_PATTERNS:
            matches = pat.findall(html)
            if matches:
                category_id = matches[-1]
                break

    category_path = " > ".join(category_names)
    return category_path, category_id


def _extract_bullets(soup: BeautifulSoup) -> List[str]:
    bullets: List[str] = []
    for li in soup.select("#feature-bullets ul li, [data-hook='feature-bullets'] ul li"):
        text = li.get_text(strip=True)
        if not text or len(text) <= 10:
            continue
        if "model number" in text.lower():
            continue
        bullets.append(text)
        if len(bullets) >= 5:
            break
    return bullets


def extract_product_fields(soup: BeautifulSoup, html: str) -> dict:
    """
    从商品页 HTML 提取标题、五点、主图、类目路径与类目 ID

    Returns:
        productTitle, bullets (list, max 5), mainImageUrl, mainImages,
        categoryPath, categoryId
    """
    main_images = _extract_gallery_images(soup, html)
    category_path, category_id = _extract_category(soup, html)
    return {
        "productTitle": _extract_title(soup),
        "bullets": _extract_bullets(soup),
        "mainImageUrl": main_images[0] if main_images else "",
        "mainImages": main_images,
        "categoryPath": category_path,
        "categoryId": category_id,
    }
