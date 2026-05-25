"""
诊断分析工具 —— 分析 no_seller_id 的 HTML 样本
提取页面特征，帮助优化解析策略
"""

import re
import json
import argparse
from pathlib import Path
from collections import Counter, defaultdict
from bs4 import BeautifulSoup


def analyze_single_html(filepath: Path) -> dict:
    """分析单个 HTML 文件，提取关键特征"""
    html = filepath.read_text(encoding='utf-8')
    soup = BeautifulSoup(html, 'lxml')

    features = {
        "filename": filepath.name,
        "title": "",
        "has_merchant_info": False,
        "merchant_info_id": "",
        "has_buybox": False,
        "has_tabular_buybox": False,
        "has_sold_by_text": False,
        "sold_by_matches": [],
        "has_script_merchant": False,
        "script_merchant_keys": [],
        "has_hidden_input_merchant": False,
        "hidden_input_names": [],
        "has_data_attr": False,
        "data_attr_keys": [],
        "seller_links": [],
        "page_type": "unknown",
        "is_amazon_fulfilled": False,
    }

    # 标题
    title_tag = soup.find('title')
    if title_tag:
        features["title"] = title_tag.get_text(strip=True)[:100]

    # 页面类型判断
    text = soup.get_text(separator=' ', strip=True).lower()
    if 'page not found' in features["title"].lower():
        features["page_type"] = "page_not_found"
    elif 'currently unavailable' in text or 'temporarily out of stock' in text:
        features["page_type"] = "unavailable"
    elif any(kw in text for kw in ('captcha', 'robot check', 'verify you are a human')):
        features["page_type"] = "captcha"
    elif 'cannot be shipped' in text:
        features["page_type"] = "shipping_restricted"

    # merchant-info 区域
    merchant_selectors = ['#merchant-info', '#merchantInfoFeature', '#merchant', '.merchant-info',
                          '[id*="merchant-info"]', '[id*="merchantInfo"]']
    for sel in merchant_selectors:
        try:
            el = soup.select_one(sel)
        except Exception:
            continue
        if el:
            features["has_merchant_info"] = True
            features["merchant_info_id"] = el.get('id', el.get('class', [''])[0])
            break

    # buybox
    buybox_selectors = ['#buybox', '#buyBox', '.buybox', '#desktop_buybox']
    for sel in buybox_selectors:
        try:
            if soup.select_one(sel):
                features["has_buybox"] = True
                break
        except Exception:
            continue

    # tabular buybox
    if soup.find(class_=re.compile(r'tabular-buybox', re.I)):
        features["has_tabular_buybox"] = True

    # Sold by 文本
    sold_by_pattern = re.findall(r'Sold\s+by\s+([^<\n\r]{1,80})', html, re.IGNORECASE)
    if sold_by_pattern:
        features["has_sold_by_text"] = True
        features["sold_by_matches"] = [s.strip() for s in sold_by_pattern[:5]]

    # Script 中的 merchant
    merchant_keys = set()
    for script in soup.find_all('script'):
        st = script.string or ''
        for key in ['merchantID', 'merchantId', 'merchant_id', 'sellerId', 'sellerID',
                    'winningMerchantID', 'buyBoxMerchantId', 'currentMerchant']:
            if key in st:
                merchant_keys.add(key)
                features["has_script_merchant"] = True
    features["script_merchant_keys"] = sorted(merchant_keys)

    # hidden input
    input_names = set()
    for inp in soup.find_all('input', {'type': 'hidden'}):
        name = inp.get('name', '')
        if 'merchant' in name.lower() or 'seller' in name.lower():
            input_names.add(name)
            features["has_hidden_input_merchant"] = True
    features["hidden_input_names"] = sorted(input_names)

    # data attrs
    data_keys = set()
    for el in soup.find_all(attrs=True):
        for attr in el.attrs:
            if 'merchant' in attr.lower() or 'seller' in attr.lower():
                data_keys.add(attr)
                features["has_data_attr"] = True
    features["data_attr_keys"] = sorted(data_keys)[:20]

    # seller 相关链接
    seller_links = []
    for link in soup.find_all('a', href=re.compile(r'(merchant=|seller=|/sp\?seller=|/gp/aag/main)', re.I)):
        href = link.get('href', '')[:100]
        text = link.get_text(strip=True)[:50]
        seller_links.append(f"{text} -> {href}")
    features["seller_links"] = seller_links[:10]

    # Amazon 自营
    if any(ind in soup.get_text(separator=' ', strip=True) for ind in
           ['Sold by Amazon', 'Ships from Amazon', 'Fulfilled by Amazon', 'Amazon.com']):
        features["is_amazon_fulfilled"] = True

    return features


def analyze_directory(diagnose_dir: str):
    """分析诊断目录中的所有 HTML 文件"""
    diag_path = Path(diagnose_dir)
    if not diag_path.exists():
        print(f"目录不存在: {diagnose_dir}")
        return

    files = list(diag_path.glob("*.html"))
    print(f"发现 {len(files)} 个诊断 HTML 文件\n")

    all_features = []
    for f in files:
        try:
            feat = analyze_single_html(f)
            all_features.append(feat)
        except Exception as e:
            print(f"  分析失败 {f.name}: {e}")

    if not all_features:
        print("没有可分析的文件")
        return

    # 汇总统计
    print("=" * 60)
    print("汇总统计")
    print("=" * 60)

    page_types = Counter(f["page_type"] for f in all_features)
    print(f"\n页面类型分布:")
    for pt, cnt in page_types.most_common():
        print(f"  {pt}: {cnt}")

    print(f"\n有 merchant-info 区域: {sum(1 for f in all_features if f['has_merchant_info'])}/{len(all_features)}")
    print(f"有 buybox: {sum(1 for f in all_features if f['has_buybox'])}/{len(all_features)}")
    print(f"有 tabular buybox: {sum(1 for f in all_features if f['has_tabular_buybox'])}/{len(all_features)}")
    print(f"有 Sold by 文本: {sum(1 for f in all_features if f['has_sold_by_text'])}/{len(all_features)}")
    print(f"Script 含 merchant key: {sum(1 for f in all_features if f['has_script_merchant'])}/{len(all_features)}")
    print(f"Hidden input 含 merchant: {sum(1 for f in all_features if f['has_hidden_input_merchant'])}/{len(all_features)}")
    print(f"有 data-* 属性: {sum(1 for f in all_features if f['has_data_attr'])}/{len(all_features)}")
    print(f"Amazon 自营: {sum(1 for f in all_features if f['is_amazon_fulfilled'])}/{len(all_features)}")

    # Script 中的 key 分布
    all_script_keys = []
    for f in all_features:
        all_script_keys.extend(f["script_merchant_keys"])
    if all_script_keys:
        print(f"\nScript 中出现的 merchant/seller key:")
        for key, cnt in Counter(all_script_keys).most_common():
            print(f"  {key}: {cnt}")

    # Hidden input name 分布
    all_input_names = []
    for f in all_features:
        all_input_names.extend(f["hidden_input_names"])
    if all_input_names:
        print(f"\nHidden input name 分布:")
        for name, cnt in Counter(all_input_names).most_common():
            print(f"  {name}: {cnt}")

    # Data attr 分布
    all_data_attrs = []
    for f in all_features:
        all_data_attrs.extend(f["data_attr_keys"])
    if all_data_attrs:
        print(f"\nData 属性分布 (top 20):")
        for attr, cnt in Counter(all_data_attrs).most_common(20):
            print(f"  {attr}: {cnt}")

    # 没有 merchant-info 的样本
    no_merchant = [f for f in all_features if not f["has_merchant_info"]]
    if no_merchant:
        print(f"\n--- 没有 merchant-info 区域的 {len(no_merchant)} 个样本 ---")
        for f in no_merchant[:5]:
            print(f"  {f['filename']}: {f['title'][:60]}...")

    # 有 Sold by 文本但无 ID 的样本
    sold_by_no_id = [f for f in all_features if f["has_sold_by_text"] and not f["is_amazon_fulfilled"]]
    if sold_by_no_id:
        print(f"\n--- 有 Sold by 文本但可能无 ID 的 {len(sold_by_no_id)} 个样本 (展示前 5 个) ---")
        for f in sold_by_no_id[:5]:
            print(f"  {f['filename']}:")
            for m in f["sold_by_matches"]:
                print(f"    Sold by: {m}")

    print("\n" + "=" * 60)
    print("分析完成。根据以上特征，可针对性补充 extract_seller_http.py 的解析策略。")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="分析 no_seller_id 的诊断 HTML 样本")
    parser.add_argument("directory", help="诊断 HTML 保存目录")
    args = parser.parse_args()
    analyze_directory(args.directory)


if __name__ == "__main__":
    main()
