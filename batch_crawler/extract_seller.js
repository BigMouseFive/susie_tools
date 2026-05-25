/**
 * 亚马逊 Seller ID 提取脚本（增强版）
 * 由 Playwright 在页面上下文中执行
 */

function extractSellerId() {
  let sellerId = null;
  let sellerName = null;

  // ===================== 辅助函数 =====================

  function trySelectValue(selector, attr) {
    const el = document.querySelector(selector);
    if (!el) return null;
    if (attr) return el.getAttribute(attr);
    return el.value || el.textContent;
  }

  function extractFromHref(href) {
    if (!href) return null;
    const patterns = [
      /[?&](merchant|seller|merchantID)=([^&]+)/i,
      /seller=([A-Z0-9]+)/i,
      /\/gp\/aag\/main\?.*seller=([A-Z0-9]+)/i,
    ];
    for (const pat of patterns) {
      const m = href.match(pat);
      if (m) return decodeURIComponent(m[2] || m[1]);
    }
    return null;
  }

  // ===================== 1. 隐藏字段 / data 属性 =====================

  const merchantInput = document.querySelector('input[name="merchantID"], input#merchantID');
  if (merchantInput && merchantInput.value && merchantInput.value.trim()) {
    sellerId = merchantInput.value.trim();
  }

  if (!sellerId) {
    const el = document.querySelector('[data-merchant-id]:not([data-merchant-id=""])');
    if (el) sellerId = el.getAttribute('data-merchant-id');
  }

  // ===================== 2. 从链接中提取 =====================

  if (!sellerId) {
    const links = document.querySelectorAll(
      'a[href*="merchant="], a[href*="seller="], a[href*="/sp?seller="], a[href*="/gp/aag/main"]'
    );
    for (const link of links) {
      const href = link.getAttribute('href') || '';
      const id = extractFromHref(href);
      if (id) {
        sellerId = id;
        sellerName = link.textContent.trim();
        break;
      }
    }
  }

  // ===================== 3. merchant-info 区域 =====================

  if (!sellerId) {
    const merchantInfo = document.querySelector('#merchant-info, #merchantInfoFeature');
    if (merchantInfo) {
      const link = merchantInfo.querySelector('a[href*="merchant="], a[href*="seller="], a[href*="/gp/aag/main"], a[href*="/sp?seller="]');
      if (link) {
        const id = extractFromHref(link.getAttribute('href'));
        if (id) {
          sellerId = id;
          sellerName = link.textContent.trim();
        }
      }
    }
  }

  // ===================== 4. Tabular Buybox（新格式） =====================

  if (!sellerId) {
    const buyboxTexts = document.querySelectorAll('.tabular-buybox-text[href*="merchant"], .tabular-buybox-text[href*="seller"]');
    for (const txt of buyboxTexts) {
      const id = extractFromHref(txt.getAttribute('href'));
      if (id) {
        sellerId = id;
        sellerName = txt.textContent.trim();
        break;
      }
    }
  }

  // ===================== 5. Other Sellers / See All Buying Options =====================

  if (!sellerId) {
    // 有时主 buybox 是亚马逊自营，但 Other Sellers 链接中包含 seller 信息
    const otherSellerLinks = document.querySelectorAll(
      'a[href*="olp"], a[href*="offer-listing"], #olpLink a, .olp-text a'
    );
    for (const link of otherSellerLinks) {
      const href = link.getAttribute('href') || '';
      const id = extractFromHref(href);
      if (id) {
        sellerId = id;
        break;
      }
    }
  }

  // ===================== 6. 从页面 script JSON 中提取 =====================

  if (!sellerId) {
    const scripts = document.querySelectorAll('script');
    for (const script of scripts) {
      const text = script.textContent || '';
      // 匹配各种可能的字段名
      const matches = [
        text.match(/"merchantID"\s*:\s*"([A-Z0-9]+)"/i),
        text.match(/"merchantId"\s*:\s*"([A-Z0-9]+)"/i),
        text.match(/"sellerID"\s*:\s*"([A-Z0-9]+)"/i),
        text.match(/"sellerId"\s*:\s*"([A-Z0-9]+)"/i),
        text.match(/"merchant_id"\s*:\s*"([A-Z0-9]+)"/i),
        text.match(/"winningMerchantID"\s*:\s*"([A-Z0-9]+)"/i),
      ];
      for (const m of matches) {
        if (m) {
          sellerId = m[1];
          break;
        }
      }
      if (sellerId) break;
    }
  }

  // ===================== 7. window.DetailPage / AUI 数据 =====================

  if (!sellerId && window.DetailPage && window.DetailPage.StateController) {
    try {
      const state = window.DetailPage.StateController.state || {};
      // 尝试从 state 中递归搜索
      function searchObj(obj) {
        if (typeof obj !== 'object' || obj === null) return;
        for (const [k, v] of Object.entries(obj)) {
          if (typeof v === 'string' && /^[A-Z0-9]{14}$/.test(v) && /seller|merchant/i.test(k)) {
            return v;
          }
          if (typeof v === 'object') {
            const found = searchObj(v);
            if (found) return found;
          }
        }
        return null;
      }
      const fromState = searchObj(state);
      if (fromState) sellerId = fromState;
    } catch (e) {}
  }

  // ===================== 8. 从 A-Page 数据属性中提取 =====================

  if (!sellerId) {
    const aPage = document.querySelector('#a-page');
    if (aPage) {
      const data = aPage.getAttribute('data-a-page-state') || aPage.getAttribute('data-page-state');
      if (data) {
        try {
          const parsed = JSON.parse(data);
          const found = JSON.stringify(parsed).match(/"(merchantID|sellerId|merchant_id)":"([A-Z0-9]+)"/i);
          if (found) sellerId = found[2];
        } catch (e) {}
      }
    }
  }

  // ===================== 9. 变体选择后重新检测 =====================

  if (!sellerId) {
    // 如果页面有变体选择器（twister），尝试选择第一个变体触发加载
    const twisters = document.querySelectorAll(
      '#twister .a-button:not(.a-button-selected), .swatchAvailable, .dimension-value:not(.dimension-selected)'
    );
    if (twisters.length > 0) {
      // 不实际点击（避免副作用），但标记说明可能需要选择变体
      // 如果外部脚本需要，可以在 Playwright 中执行点击后再运行此脚本
    }
  }

  // ===================== 10. 提取 ASIN =====================

  let asin = null;
  const asinInput = document.querySelector('input[name="ASIN"], input#ASIN');
  if (asinInput) {
    asin = asinInput.value;
  }
  if (!asin) {
    const match = location.pathname.match(/\/(?:dp|gp\/product)\/([A-Z0-9]{10})/i);
    if (match) asin = match[1];
  }

  // ===================== 11. 检测页面异常状态 =====================

  let pageStatus = 'normal';
  const bodyText = document.body.innerText || '';
  const lowerBody = bodyText.toLowerCase();
  const title = document.title || '';

  if (lowerBody.includes('cannot be shipped to your selected delivery location')) {
    pageStatus = 'shipping_restricted';
  } else if (lowerBody.includes('currently unavailable') || lowerBody.includes('temporarily out of stock')) {
    pageStatus = 'unavailable';
  } else if (title.toLowerCase().includes('page not found') || lowerBody.includes('sorry, we just need to make sure')) {
    pageStatus = 'page_not_found';
  } else if (lowerBody.includes('verify you are a human') || lowerBody.includes('captcha')) {
    pageStatus = 'captcha';
  } else if (lowerBody.includes('robot check')) {
    pageStatus = 'robot_check';
  }

  return {
    asin: asin,
    sellerId: sellerId,
    sellerName: sellerName,
    url: location.href,
    title: document.title,
    pageStatus: pageStatus
  };
}

// 执行并返回结果
extractSellerId();
