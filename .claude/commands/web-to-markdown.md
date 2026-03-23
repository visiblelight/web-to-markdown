---
description: 从指定的URL读取网页内容，并转换成markdown
argument-hint: [url]
allowed-tools: WebFetch, Bash
---

# Web to Markdown — 提取网页内容转换成markdown

给一个 URL，返回干净的 Markdown 格式正文。

## 提取策略

限制网页最大内容
MAX_CHARS=5000

按以下顺序尝试读取 $1：

1. **Jina Reader（首选）**
   web_fetch("https://r.jina.ai/$1", maxChars=MAX_CHARS)
   优点：快（~1.5s），格式干净
   限制：200次/天免费配额
   失败场景：微信公众号（403）、部分国内平台

2. **Scrapling + html2text（Jina 超限或失败时）**
   exec: python3 /Users/vision/NAS/hub/work/projects/web-to-markdown/scripts/fetch.py $1 100000 [image_dir]
   优点：无限制，效果和 Jina 相当，能读微信公众号
   适合：mp.weixin.qq.com、Substack、Medium 等反爬平台
   若设置了 MINIO_* 环境变量，图片自动上传到 MinIO，markdown 使用公网 URL

3. **web_fetch 直接抓（静态页面兜底）**
   web_fetch($1, maxChars=MAX_CHARS)
   适合：GitHub README、普通静态博客、技术文档

## 域名快捷路由

以下域名 Jina 无法读取，不要浪费时间，直接使用 fetch 脚本尝试：
- `mp.weixin.qq.com`
- `zhuanlan.zhihu.com`
- `juejin.cn`
- `csdn.net`

## 防死循环规则

同一个 URL 累计失败 2 次就放弃，记录为"无法提取"，不重复重试。
