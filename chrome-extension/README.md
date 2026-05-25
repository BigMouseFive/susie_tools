# 人民当家做主工具集 —— 亚马逊 Seller ID 提取器

Chrome 浏览器插件，在亚马逊（Amazon）产品详情页自动提取并展示 **Seller ID（卖家ID）**。

## 功能特性

- ✅ **自动识别**：打开亚马逊商品详情页即自动提取 Seller ID
- ✅ **多站点支持**：支持 Amazon 美国、英国、德国、日本、中国等 19 个站点
- ✅ **一键复制**：点击即可复制 Seller ID 到剪贴板
- ✅ **快捷跳转**：一键跳转到卖家店铺页面
- ✅ **拖拽移动**：浮层支持拖拽，不遮挡关键内容
- ✅ **轻量无感**：零权限依赖，仅读取页面内容

## 安装方法

### 方式一：开发者模式加载（推荐）

1. 打开 Chrome 浏览器，地址栏输入 `chrome://extensions/`
2. 右上角开启 **开发者模式**
3. 点击 **加载已解压的扩展程序**
4. 选择本项目文件夹（包含 `manifest.json` 的目录）
5. 安装完成，打开任意亚马逊商品详情页即可看到浮层

### 方式二：打包安装（可选）

1. 在 `chrome://extensions/` 页面点击 **打包扩展程序**
2. 选择本项目文件夹，生成 `.crx` 文件
3. 将 `.crx` 文件拖拽到 Chrome 扩展页面安装

## 使用说明

1. 访问任意亚马逊商品详情页，例如：
   ```
   https://www.amazon.com/dp/B08N5WRWNW
   ```
2. 页面右下角会自动出现 **人民当家做主工具集** 浮层
3. 浮层中显示当前商品的 **Seller ID** 及店铺名称
4. 点击 **一键复制** 按钮即可复制 Seller ID
5. 点击 **打开店铺** 按钮可跳转至卖家店铺主页
6. 浮层支持鼠标拖拽移动位置，点击 ✕ 可关闭

## 文件结构

```
scrapy_seller_id/
├── manifest.json       # Chrome 插件配置
├── content.js          # 内容脚本：提取 Seller ID 并渲染浮层
├── icons/
│   ├── icon16.png      # 插件图标（16px）
│   ├── icon48.png      # 插件图标（48px）
│   └── icon128.png     # 插件图标（128px）
└── README.md           # 使用说明
```

## Seller ID 提取原理

插件采用多种策略提取 Seller ID，优先级如下：

1. 从页面隐藏 `input[name="merchantID"]` 字段读取
2. 从 `data-merchant-id` 数据属性读取
3. 从 "Sold by" / "Ships from" 链接的 `href` 中解析 `merchant=` / `seller=` 参数
4. 从 `#merchant-info` 区域的卖家主页链接中提取
5. 从页面内嵌 JSON 数据中的 `merchantID` / `sellerId` 字段提取
6. 从 `/sp?seller=` 或 `/gp/aag/main` 链接中提取

## 支持的亚马逊站点

- 北美：`amazon.com`, `amazon.ca`, `amazon.com.mx`, `amazon.com.br`
- 欧洲：`amazon.co.uk`, `amazon.de`, `amazon.fr`, `amazon.it`, `amazon.es`, `amazon.nl`, `amazon.pl`, `amazon.se`, `amazon.tr`
- 亚太：`amazon.co.jp`, `amazon.in`, `amazon.com.au`, `amazon.cn`, `amazon.sg`
- 中东：`amazon.ae`

## 注意事项

- 插件仅在亚马逊 **商品详情页**（URL 包含 `/dp/` 或 `/gp/product/`）生效
- 若页面未显示 Seller ID，可能是因为该商品为亚马逊自营（Amazon）或页面结构特殊
- 浮层位置可自由拖拽，关闭后刷新页面会重新出现

## 更新日志

### v1.0.0
- 初始版本发布
- 支持自动提取 Seller ID
- 支持一键复制与店铺跳转
