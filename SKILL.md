---
name: web-to-markdown
description: 从指定的 URL 提取网页正文并转换成 Markdown，支持图片下载及上传到 MinIO 对象存储
---

# Web to Markdown

给一个 URL，返回干净的 Markdown 格式正文。

## 提取策略

按以下顺序尝试，失败则自动降级到下一个：

1. **Jina Reader**（首选）
   `web_fetch("https://r.jina.ai/<url>", maxChars=5000)`
   - 快（~1.5s），格式干净
   - 限制：200次/天免费配额，微信公众号等平台会 403

2. **Scrapling + html2text**（Jina 失败时）
   `python3 scripts/fetch.py <url> [max_chars] [image_dir]`
   - 无限制，能读微信公众号等反爬平台
   - max_chars 默认 100000，image_dir 可选
   - 若配置了 MinIO 环境变量，图片自动上传并使用公网 URL

3. **web_fetch 直接抓**（兜底）
   `web_fetch(url, maxChars=5000)`
   - 仅适合 GitHub README、静态博客等简单页面

## 域名快捷路由

以下域名 Jina 无法读取，跳过直接使用 fetch.py：
- `mp.weixin.qq.com`
- `zhuanlan.zhihu.com`
- `juejin.cn`
- `csdn.net`

## 防死循环规则

同一个 URL 累计失败 2 次就放弃，记录为"无法提取"，不重复重试。
