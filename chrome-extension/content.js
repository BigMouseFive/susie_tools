(function () {
  'use strict';

  const CONTAINER_ID = 'rmdz-toolkit-sellerid';

  // ===================== 提取 Seller ID =====================

  function extractSellerId() {
    let sellerId = null;
    let sellerName = null;

    // 1. 从隐藏的 input 字段提取
    const merchantInput = document.querySelector('input[name="merchantID"], input#merchantID, input[data-merchant-id]');
    if (merchantInput) {
      sellerId = merchantInput.value || merchantInput.getAttribute('data-merchant-id');
    }

    // 2. 从带有 data-merchant-id 属性的元素提取
    if (!sellerId) {
      const el = document.querySelector('[data-merchant-id]');
      if (el) {
        sellerId = el.getAttribute('data-merchant-id');
      }
    }

    // 3. 从 Sold by / Ships from 等链接中提取 merchant ID
    if (!sellerId) {
      const links = document.querySelectorAll('a[href*="merchant="], a[href*="seller="], a[href*="merchantID="]');
      for (const link of links) {
        const href = link.getAttribute('href') || '';
        const match = href.match(/[?&](merchant|seller|merchantID)=([^&]+)/i);
        if (match) {
          sellerId = decodeURIComponent(match[2]);
          sellerName = link.textContent.trim();
          break;
        }
      }
    }

    // 4. 从 merchant-info 区域提取
    if (!sellerId) {
      const merchantInfo = document.querySelector('#merchant-info, #merchantInfoFeature, [id*="merchant"]');
      if (merchantInfo) {
        const link = merchantInfo.querySelector('a[href*="merchant="], a[href*="seller="], a[href*="/gp/aag/main"], a[href*="/sp?seller="]');
        if (link) {
          const href = link.getAttribute('href') || '';
          let match = href.match(/[?&](merchant|seller)=([^&]+)/i);
          if (!match) match = href.match(/seller=([A-Z0-9]+)/i);
          if (!match) match = href.match(/\/gp\/aag\/main\?.*ie=UTF8&asin=[^&]+&seller=([A-Z0-9]+)/i);
          if (match) {
            sellerId = decodeURIComponent(match[2] || match[1]);
          }
          if (!sellerName) sellerName = link.textContent.trim();
        }
      }
    }

    // 5. 从页面 script 标签中的 JSON 数据提取（Amazon 有时会内嵌数据）
    if (!sellerId) {
      const scripts = document.querySelectorAll('script');
      for (const script of scripts) {
        const text = script.textContent || '';
        const match = text.match(/"merchantID"\s*:\s*"([A-Z0-9]+)"/i) ||
                      text.match(/"merchantId"\s*:\s*"([A-Z0-9]+)"/i) ||
                      text.match(/"sellerID"\s*:\s*"([A-Z0-9]+)"/i) ||
                      text.match(/"sellerId"\s*:\s*"([A-Z0-9]+)"/i);
        if (match) {
          sellerId = match[1];
          break;
        }
      }
    }

    // 6. 从任何包含 seller/merchant 的 a 标签进一步尝试
    if (!sellerId) {
      const allLinks = document.querySelectorAll('a[href*="/sp?seller="], a[href*="/gp/aag/main"]');
      for (const link of allLinks) {
        const href = link.getAttribute('href') || '';
        const match = href.match(/seller=([A-Z0-9]+)/i);
        if (match) {
          sellerId = match[1];
          if (!sellerName) sellerName = link.textContent.trim();
          break;
        }
      }
    }

    // 7. 从 Offers 列表中提取（某些页面）
    if (!sellerId) {
      const offerLink = document.querySelector('a[href*="olp"], a[href*="offers"], .tabular-buybox-text[href*="merchant"]');
      if (offerLink) {
        const href = offerLink.getAttribute('href') || '';
        const match = href.match(/[?&](merchant|seller)=([^&]+)/i);
        if (match) {
          sellerId = decodeURIComponent(match[2]);
        }
      }
    }

    return { sellerId, sellerName };
  }

  // ===================== 复制到剪贴板 =====================

  async function copyToClipboard(text) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (err) {
      // fallback
      const textarea = document.createElement('textarea');
      textarea.value = text;
      textarea.style.position = 'fixed';
      textarea.style.opacity = '0';
      document.body.appendChild(textarea);
      textarea.select();
      const success = document.execCommand('copy');
      document.body.removeChild(textarea);
      return success;
    }
  }

  // ===================== 创建 UI =====================

  function createWidget(sellerId, sellerName) {
    if (document.getElementById(CONTAINER_ID)) return;

    const container = document.createElement('div');
    container.id = CONTAINER_ID;

    // 内联样式，避免依赖外部 CSS
    const styles = {
      position: 'fixed',
      bottom: '20px',
      right: '20px',
      zIndex: '999999',
      background: '#ffffff',
      border: '1px solid #d5d9d9',
      borderRadius: '8px',
      boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
      padding: '14px 16px',
      minWidth: '220px',
      maxWidth: '320px',
      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
      fontSize: '13px',
      color: '#0f1111',
      lineHeight: '1.5',
      cursor: 'default',
      userSelect: 'none',
    };
    Object.assign(container.style, styles);

    // 头部标题栏
    const header = document.createElement('div');
    header.style.display = 'flex';
    header.style.alignItems = 'center';
    header.style.justifyContent = 'space-between';
    header.style.marginBottom = '10px';
    header.style.borderBottom = '1px solid #f0f2f2';
    header.style.paddingBottom = '8px';

    const title = document.createElement('div');
    title.textContent = '人民当家做主工具集';
    title.style.fontWeight = '700';
    title.style.fontSize = '13px';
    title.style.color = '#b12704';
    title.style.whiteSpace = 'nowrap';
    title.style.overflow = 'hidden';
    title.style.textOverflow = 'ellipsis';

    const closeBtn = document.createElement('span');
    closeBtn.textContent = '✕';
    closeBtn.style.cursor = 'pointer';
    closeBtn.style.color = '#555';
    closeBtn.style.fontSize = '14px';
    closeBtn.style.marginLeft = '10px';
    closeBtn.style.flexShrink = '0';
    closeBtn.title = '关闭';
    closeBtn.addEventListener('click', () => container.remove());

    header.appendChild(title);
    header.appendChild(closeBtn);
    container.appendChild(header);

    // 内容区
    if (sellerId) {
      // 卖家名称（如果有）
      if (sellerName) {
        const nameRow = document.createElement('div');
        nameRow.style.marginBottom = '6px';
        nameRow.innerHTML = `<span style="color:#565959">店铺：</span>${escapeHtml(sellerName)}`;
        container.appendChild(nameRow);
      }

      // Seller ID 行
      const idRow = document.createElement('div');
      idRow.style.display = 'flex';
      idRow.style.alignItems = 'center';
      idRow.style.gap = '8px';
      idRow.style.marginBottom = '10px';

      const idLabel = document.createElement('span');
      idLabel.textContent = 'Seller ID：';
      idLabel.style.color = '#565959';
      idLabel.style.flexShrink = '0';

      const idValue = document.createElement('code');
      idValue.textContent = sellerId;
      idValue.style.background = '#f3f3f3';
      idValue.style.padding = '2px 6px';
      idValue.style.borderRadius = '4px';
      idValue.style.fontFamily = 'monospace';
      idValue.style.fontSize = '12px';
      idValue.style.wordBreak = 'break-all';
      idValue.style.flex = '1';

      idRow.appendChild(idLabel);
      idRow.appendChild(idValue);
      container.appendChild(idRow);

      // 按钮行
      const btnRow = document.createElement('div');
      btnRow.style.display = 'flex';
      btnRow.style.gap = '8px';

      const copyBtn = createButton('一键复制', '#ffd814', '#0f1111', async () => {
        const ok = await copyToClipboard(sellerId);
        if (ok) {
          copyBtn.textContent = '已复制 ✓';
          copyBtn.style.background = '#1db954';
          copyBtn.style.color = '#fff';
          setTimeout(() => {
            copyBtn.textContent = '一键复制';
            copyBtn.style.background = '#ffd814';
            copyBtn.style.color = '#0f1111';
          }, 1500);
        } else {
          copyBtn.textContent = '复制失败';
          setTimeout(() => { copyBtn.textContent = '一键复制'; }, 1500);
        }
      });

      const openBtn = createButton('打开店铺', '#fff', '#0f1111', () => {
        const domain = location.hostname;
        const url = `https://${domain}/sp?seller=${encodeURIComponent(sellerId)}`;
        window.open(url, '_blank');
      });
      openBtn.style.border = '1px solid #d5d9d9';

      btnRow.appendChild(copyBtn);
      btnRow.appendChild(openBtn);
      container.appendChild(btnRow);
    } else {
      const empty = document.createElement('div');
      empty.style.color = '#565959';
      empty.style.fontSize = '12px';
      empty.textContent = '未检测到 Seller ID，请确认当前为亚马逊商品详情页。';
      container.appendChild(empty);
    }

    // 拖拽移动支持
    makeDraggable(container, header);

    document.body.appendChild(container);
  }

  function createButton(text, bg, color, onClick) {
    const btn = document.createElement('button');
    btn.textContent = text;
    btn.style.flex = '1';
    btn.style.padding = '6px 0';
    btn.style.border = 'none';
    btn.style.borderRadius = '6px';
    btn.style.background = bg;
    btn.style.color = color;
    btn.style.fontSize = '12px';
    btn.style.fontWeight = '600';
    btn.style.cursor = 'pointer';
    btn.style.transition = 'background 0.2s';
    btn.addEventListener('click', onClick);
    btn.addEventListener('mouseenter', () => { btn.style.filter = 'brightness(0.96)'; });
    btn.addEventListener('mouseleave', () => { btn.style.filter = 'none'; });
    return btn;
  }

  function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  function makeDraggable(el, handle) {
    let isDragging = false;
    let startX, startY, startLeft, startTop;

    handle.style.cursor = 'move';

    handle.addEventListener('mousedown', (e) => {
      isDragging = true;
      startX = e.clientX;
      startY = e.clientY;
      const rect = el.getBoundingClientRect();
      startLeft = rect.left;
      startTop = rect.top;
      el.style.transition = 'none';
    });

    document.addEventListener('mousemove', (e) => {
      if (!isDragging) return;
      const dx = e.clientX - startX;
      const dy = e.clientY - startY;
      el.style.left = `${startLeft + dx}px`;
      el.style.top = `${startTop + dy}px`;
      el.style.right = 'auto';
      el.style.bottom = 'auto';
    });

    document.addEventListener('mouseup', () => {
      if (isDragging) {
        isDragging = false;
        el.style.transition = '';
      }
    });
  }

  // ===================== 主逻辑 =====================

  function init() {
    // 只在商品详情页运行（URL 包含 /dp/ 或 /gp/product/）
    const path = location.pathname;
    const isProductPage = /\/(dp|gp\/product)\/[A-Z0-9]{10}/i.test(path);
    if (!isProductPage) return;

    const { sellerId, sellerName } = extractSellerId();
    createWidget(sellerId, sellerName);
  }

  // 页面加载完成后初始化
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
