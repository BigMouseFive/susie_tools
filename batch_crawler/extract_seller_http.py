"""
HTTP 版 Seller ID 提取逻辑 —— 增强版
从亚马逊商品页 HTML 中解析提取 Seller ID
覆盖多种页面变体：不同站点、不同 buybox 格式、自营/FBA/FBM
"""

import re
import json
from typing import Optional, Dict, Any
from bs4 import BeautifulSoup


def extract_from_href(href: str) -> Optional[str]:
    """从链接 href 中提取 seller/merchant ID"""
    if not href:
        return None
    patterns = [
        r'[?&](merchant|seller|merchantID|merchantId)=([^&]+)',
        r'seller=([A-Z0-9]+)',
        r'/gp/aag/main\?.*seller=([A-Z0-9]+)',
    ]
    for pat in patterns:
        m = re.search(pat, href, re.IGNORECASE)
        if m:
            val = m.group(2) if m.lastindex >= 2 else m.group(1)
            return re.sub(r'%2B', '+', val)
    return None


def find_seller_in_scripts(soup: BeautifulSoup) -> Optional[str]:
    """
    从页面所有 script 标签中提取 seller/merchant ID
    支持多种 key 变体和 JSON 嵌套格式
    """
    # 要搜索的 key 变体
    key_patterns = [
        r'"merchantID"\s*:\s*"([A-Z0-9]+)"',
        r'"merchantId"\s*:\s*"([A-Z0-9]+)"',
        r'"merchant_id"\s*:\s*"([A-Z0-9]+)"',
        r'"merchant"\s*:\s*"([A-Z0-9]+)"',
        r'"sellerID"\s*:\s*"([A-Z0-9]+)"',
        r'"sellerId"\s*:\s*"([A-Z0-9]+)"',
        r'"seller_id"\s*:\s*"([A-Z0-9]+)"',
        r'"currentMerchant"\s*:\s*"([A-Z0-9]+)"',
        r'"currentSeller"\s*:\s*"([A-Z0-9]+)"',
        r'"winningMerchantID"\s*:\s*"([A-Z0-9]+)"',
        r'"winningMerchantId"\s*:\s*"([A-Z0-9]+)"',
        r'"buyBoxMerchantId"\s*:\s*"([A-Z0-9]+)"',
        r'"buyboxMerchantId"\s*:\s*"([A-Z0-9]+)"',
        r'"defaultMerchantId"\s*:\s*"([A-Z0-9]+)"',
        r"'merchantID'\s*:\s*'([A-Z0-9]+)'",
        r"'merchantId'\s*:\s*'([A-Z0-9]+)'",
        r"'sellerId'\s*:\s*'([A-Z0-9]+)'",
    ]

    for script in soup.find_all('script'):
        text = script.string or ''
        if not text.strip():
            continue

        # 先尝试正则匹配各种 key
        for pat in key_patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                return m.group(1)

        # 尝试解析 JSON 数据（a-state, a-expander 等）
        try:
            # 查找可能的 JSON 子串
            for json_match in re.finditer(r'\{[^{}]*"(?:merchant|seller)[^}]*\}', text, re.I):
                try:
                    data = json.loads(json_match.group())
                    for k, v in data.items():
                        if isinstance(v, str) and re.match(r'^[A-Z0-9]{5,}$', v):
                            if any(sk in k.lower() for sk in ('merchant', 'seller')):
                                return v
                except json.JSONDecodeError:
                    pass
        except Exception:
            pass

    return None


def find_seller_in_data_attrs(soup: BeautifulSoup) -> Optional[str]:
    """从 data-* 属性中提取 seller/merchant ID"""
    data_attrs = [
        'data-merchant-id', 'data-merchant', 'data-seller-id',
        'data-seller', 'data-merchantid', 'data-current-merchant',
        'data-merchant-name', 'data-seller-name',
    ]
    for attr in data_attrs:
        el = soup.find(attrs={attr: True})
        if el:
            val = el.get(attr, '').strip()
            if val and re.match(r'^[A-Z0-9]{5,}$', val):
                return val
    return None


def find_seller_in_inputs(soup: BeautifulSoup) -> Optional[str]:
    """从 hidden input 字段中提取 merchant ID"""
    # 按 name 查找
    input_names = ['merchantID', 'merchantId', 'merchant_id', 'sellerID', 'sellerId', 'seller_id']
    for name in input_names:
        inp = soup.find('input', {'name': name})
        if inp and inp.get('value', '').strip():
            return inp['value'].strip()

    # 按 id 查找
    input_ids = ['merchantID', 'merchantId', 'merchant', 'sellerID', 'sellerId']
    for inp_id in input_ids:
        inp = soup.find('input', {'id': inp_id})
        if inp and inp.get('value', '').strip():
            return inp['value'].strip()

    # 遍历所有 hidden input，找 value 像 merchant ID 的
    for inp in soup.find_all('input', {'type': 'hidden'}):
        name = (inp.get('name') or '').lower()
        if 'merchant' in name or 'seller' in name:
            val = inp.get('value', '').strip()
            if val:
                return val

    return None


def find_seller_in_merchant_info(soup: BeautifulSoup) -> tuple[Optional[str], Optional[str]]:
    """
    从 merchant-info 区域提取 seller ID 和名称
    支持多种 ID/Class 变体
    """
    selectors = [
        '#merchant-info',
        '#merchantInfoFeature',
        '#merchant',
        '#merchant-info-container',
        '.merchant-info',
        '[id*="merchant-info"]',
        '[id*="merchantInfo"]',
        '[id*="bylineInfo"]',
    ]

    for sel in selectors:
        try:
            container = soup.select_one(sel)
        except Exception:
            continue
        if not container:
            continue

        # 先找区域内的链接
        for link in container.find_all('a', href=re.compile(r'(merchant=|seller=|/gp/aag/main|/sp\?seller=)', re.I)):
            sid = extract_from_href(link.get('href', ''))
            if sid:
                name = link.get_text(strip=True)
                return sid, name

        # 再找区域内任何含 seller/merchant 的链接
        for link in container.find_all('a', href=True):
            sid = extract_from_href(link.get('href', ''))
            if sid:
                return sid, link.get_text(strip=True)

    return None, None


def find_seller_in_buybox(soup: BeautifulSoup) -> tuple[Optional[str], Optional[str]]:
    """
    从 buybox 购买框区域提取 seller
    支持多种 buybox 格式变体
    """
    # Tabular buybox（新格式）
    for txt in soup.find_all(class_=re.compile(r'tabular-buybox-text', re.I)):
        href = txt.get('href', '')
        if href and ('merchant' in href or 'seller' in href):
            sid = extract_from_href(href)
            if sid:
                return sid, txt.get_text(strip=True)
        # tabular buybox 内可能嵌套链接
        for link in txt.find_all('a', href=True):
            sid = extract_from_href(link.get('href', ''))
            if sid:
                return sid, link.get_text(strip=True)

    # 普通 buybox
    buybox_selectors = ['#buybox', '#buyBox', '.buybox', '#addToCart', '#desktop_buybox']
    for sel in buybox_selectors:
        try:
            buybox = soup.select_one(sel)
        except Exception:
            continue
        if not buybox:
            continue
        for link in buybox.find_all('a', href=re.compile(r'(merchant=|seller=|/gp/aag/main|/sp\?seller=)', re.I)):
            sid = extract_from_href(link.get('href', ''))
            if sid:
                return sid, link.get_text(strip=True)

    return None, None


def find_seller_in_links(soup: BeautifulSoup) -> tuple[Optional[str], Optional[str]]:
    """
    全页面搜索 seller/merchant 相关链接
    按优先级排序
    """
    # 高优先级：Sold by / Ships from 等明确标识 seller 的链接
    for link in soup.find_all('a', href=re.compile(r'(merchant=|seller=|merchantID=)', re.I)):
        sid = extract_from_href(link.get('href', ''))
        if sid:
            return sid, link.get_text(strip=True)

    # 次优先级：/sp?seller= 或 /gp/aag/main 链接
    for link in soup.find_all('a', href=re.compile(r'/sp\?seller=|/gp/aag/main')):
        href = link.get('href', '')
        m = re.search(r'seller=([A-Z0-9]+)', href, re.I)
        if m:
            return m.group(1), link.get_text(strip=True)

    # 再次：offer-listing / olp 链接
    for link in soup.find_all('a', href=re.compile(r'(olp|offer-listing)', re.I)):
        sid = extract_from_href(link.get('href', ''))
        if sid:
            return sid, None

    return None, None


def find_seller_in_text(html: str) -> tuple[Optional[str], Optional[str]]:
    """
    从页面纯文本中搜索 Sold by / Ships from 信息
    作为最后的兜底策略
    """
    # 尝试多种文本模式
    patterns = [
        # Sold by <a>Seller</a> (HTML 已被 strip)
        (r'Sold\s+by\s+([^\n\r<]+)', 'sold_by'),
        (r'Ships\s+from\s+([^\n\r<]+)', 'ships_from'),
        (r'Fulfilled\s+by\s+([^\n\r<]+)', 'fulfilled_by'),
    ]

    for pat, _ in patterns:
        m = re.search(pat, html, re.IGNORECASE)
        if m:
            name = m.group(1).strip()
            # 清理 HTML 标签残留
            name = re.sub(r'<[^>]+>', '', name).strip()
            if name and name.lower() not in ('amazon', 'amazon.com'):
                # 文本模式只能返回名称，无法直接拿到 ID
                # 但如果是 Amazon 自营，我们单独处理
                return None, name

    return None, None


def is_amazon_fulfilled(soup: BeautifulSoup) -> bool:
    """检测是否为亚马逊自营/FBA"""
    text = soup.get_text(separator=' ', strip=True)
    amazon_indicators = [
        'Sold by Amazon',
        'Ships from Amazon',
        'Fulfilled by Amazon',
        'Dispatched from and sold by Amazon',
        'Ships from and sold by Amazon',
    ]
    for ind in amazon_indicators:
        if ind in text:
            return True

    # 检查 bylineInfo 链接是否指向 Amazon
    byline = soup.find(id='bylineInfo')
    if byline:
        byline_text = byline.get_text(strip=True).lower()
        if 'amazon' in byline_text:
            return True

    return False


def is_incomplete_page(soup: BeautifulSoup) -> bool:
    """
    检测页面是否被截断/不完整（反爬返回的假页面）
    正常商品页应包含标题、价格等核心元素
    """
    # 检查是否有商品标题
    has_title = bool(
        soup.find(id='productTitle') or
        soup.find(id='title') or
        soup.find('h1', class_=re.compile(r'product|title', re.I)) or
        soup.find(id='btAsinTitle')
    )

    # 检查是否有价格相关元素
    has_price = bool(
        soup.find(id='corePrice_feature_div') or
        soup.find(id='priceblock_ourprice') or
        soup.find(id='priceblock_dealprice') or
        soup.find(class_=re.compile(r'a-price|a-offscreen', re.I)) or
        soup.find(id='newBuyBoxPrice')
    )

    # 检查是否有购买按钮/表单
    has_buy_button = bool(
        soup.find(id='add-to-cart-button') or
        soup.find(id='submit.add-to-cart') or
        soup.find(id='buy-now-button') or
        soup.find('input', {'name': 'submit.add-to-cart'}) or
        soup.find('span', {'id': re.compile(r'submit\.add-to-cart', re.I)})
    )

    # 如果同时缺少标题、价格、购买按钮，认为页面不完整
    # 但要有一定的容错：某些页面可能价格放在 JS 中动态加载
    missing_count = sum(not x for x in [has_title, has_price, has_buy_button])
    return missing_count >= 2


def extract_seller_from_html(html: str, url: str = "") -> Dict[str, Any]:
    """
    从亚马逊商品页 HTML 中提取 Seller ID
    返回与 extract_seller.js 一致的字典格式
    """
    result = {
        "asin": None,
        "sellerId": None,
        "sellerName": None,
        "url": url,
        "title": None,
        "pageStatus": "normal",
        "isAmazonFulfilled": False,
        "extractionMethod": None,
    }

    if not html or len(html) < 500:
        result["pageStatus"] = "page_not_found"
        return result

    soup = BeautifulSoup(html, 'lxml')

    # 提取标题
    title_tag = soup.find('title')
    if title_tag:
        result["title"] = title_tag.get_text(strip=True)

    # 检测页面是否不完整（反爬返回的假页面）
    if is_incomplete_page(soup):
        result["pageStatus"] = "incomplete_page"
        return result

    # 检测页面异常状态
    body_text = soup.get_text(separator=' ', strip=True).lower()
    if 'cannot be shipped to your selected delivery location' in body_text:
        result["pageStatus"] = "shipping_restricted"
        return result

    # 检测商品是否不可用 —— 只在 availability 区域和标题附近检测
    # 避免把推荐商品/页脚中的 "currently unavailable" 误判
    availability_el = soup.find(id='availability') or soup.find(id='availability_feature_div')
    availability_text = availability_el.get_text(separator=' ', strip=True).lower() if availability_el else ''
    title_text = (result["title"] or '').lower()

    unavailable_indicators = ['currently unavailable', 'temporarily out of stock']
    if any(ind in availability_text for ind in unavailable_indicators):
        result["pageStatus"] = "unavailable"
        return result
    # 如果 availability 区域找不到，退而检查标题（某些下架商品标题会变）
    if 'currently unavailable' in title_text:
        result["pageStatus"] = "unavailable"
        return result

    if 'page not found' in title_text or 'sorry, we just need to make sure' in body_text:
        result["pageStatus"] = "page_not_found"
        return result
    if any(kw in body_text for kw in ('verify you are a human', 'captcha', 'robot check', 'type the characters', 'security check')):
        result["pageStatus"] = "captcha"
        return result

    # 提取 ASIN
    asin_input = soup.find('input', {'name': 'ASIN'}) or soup.find('input', {'id': 'ASIN'})
    if asin_input and asin_input.get('value'):
        result["asin"] = asin_input['value'].strip()
    if not result["asin"] and url:
        m = re.search(r'/(?:dp|gp/product)/([A-Z0-9]{10})', url, re.IGNORECASE)
        if m:
            result["asin"] = m.group(1).upper()

    # 检测亚马逊自营
    if is_amazon_fulfilled(soup):
        result["isAmazonFulfilled"] = True
        result["sellerName"] = "Amazon"
        # 某些站点自营商品的 merchant ID 是固定值
        if not result["sellerId"]:
            # 尝试从页面中找到自营的 merchant ID
            sid = find_seller_in_scripts(soup)
            if sid:
                result["sellerId"] = sid
                result["extractionMethod"] = "script_json"
                return result
            sid = find_seller_in_inputs(soup)
            if sid:
                result["sellerId"] = sid
                result["extractionMethod"] = "hidden_input"
                return result

    # ===== 提取策略（按优先级） =====

    # 策略 1: hidden input 字段
    seller_id = find_seller_in_inputs(soup)
    if seller_id:
        result["sellerId"] = seller_id
        result["extractionMethod"] = "hidden_input"
        return result

    # 策略 2: data-* 属性
    seller_id = find_seller_in_data_attrs(soup)
    if seller_id:
        result["sellerId"] = seller_id
        result["extractionMethod"] = "data_attr"
        return result

    # 策略 3: script 标签内 JSON
    seller_id = find_seller_in_scripts(soup)
    if seller_id:
        result["sellerId"] = seller_id
        result["extractionMethod"] = "script_json"
        return result

    # 策略 4: merchant-info 区域
    sid, sname = find_seller_in_merchant_info(soup)
    if sid:
        result["sellerId"] = sid
        result["sellerName"] = sname or result["sellerName"]
        result["extractionMethod"] = "merchant_info"
        return result

    # 策略 5: buybox 区域
    sid, sname = find_seller_in_buybox(soup)
    if sid:
        result["sellerId"] = sid
        result["sellerName"] = sname or result["sellerName"]
        result["extractionMethod"] = "buybox"
        return result

    # 策略 6: 全页面链接搜索
    sid, sname = find_seller_in_links(soup)
    if sid:
        result["sellerId"] = sid
        result["sellerName"] = sname or result["sellerName"]
        result["extractionMethod"] = "page_link"
        return result

    # 策略 7: 文本搜索兜底
    sid, sname = find_seller_in_text(html)
    if sname and not result["sellerName"]:
        result["sellerName"] = sname
        result["extractionMethod"] = "text_fallback"

    return result
