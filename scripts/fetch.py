#!/usr/bin/env python3
"""
通用网页正文提取脚本（基于 Scrapling + html2text）
返回干净的 Markdown 格式，效果与 Jina Reader 相当。

用法：
  python3 fetch.py <url> [max_chars] [image_dir]

示例：
  python3 fetch.py https://example.com/article 12000
  python3 fetch.py https://mp.weixin.qq.com/s/xxx 100000 ./images

输出：
  Markdown 格式正文，截断至 max_chars（默认 100000）
  若指定 image_dir 或配置了 MinIO 环境变量，图片会被处理并替换链接
"""

import sys
import os
import re
import hashlib
import mimetypes
import tempfile
import urllib.request
import html2text
from scrapling.fetchers import Fetcher


# ---------------------------------------------------------------------------
# 网页抓取
# ---------------------------------------------------------------------------

def fix_lazy_images(html_raw):
    """将 data-src 懒加载属性提升为 src，确保 html2text 能正确渲染图片。"""
    return re.sub(
        r'<img([^>]*?)\sdata-src="([^"]+)"([^>]*?)>',
        lambda m: f'<img{m.group(1)} src="{m.group(2)}"{m.group(3)}>',
        html_raw
    )


def scrapling_fetch(url, max_chars=100000):
    page = Fetcher(auto_match=False).get(
        url,
        headers={"Referer": "https://www.google.com/search?q=site"}
    )

    h = html2text.HTML2Text()
    h.ignore_links = False
    h.ignore_images = False
    h.body_width = 0

    if "mp.weixin.qq.com" in url:
        selectors = ["div#js_content", "div.rich_media_content"]
    else:
        selectors = [
            'article', 'main',
            '.post-content', '.entry-content', '.article-body',
            '[class*="body"]', '[class*="content"]', '[class*="article"]',
        ]

    for selector in selectors:
        els = page.css(selector)
        if els:
            html_raw = fix_lazy_images(els[0].html_content)
            md = h.handle(html_raw)
            md = re.sub(r'\n{3,}', '\n\n', md).strip()
            if len(md) > 300:
                return md[:max_chars], selector

    html_raw = fix_lazy_images(page.html_content)
    md = h.handle(html_raw)
    md = re.sub(r'\n{3,}', '\n\n', md).strip()
    return md[:max_chars], 'body(fallback)'


# ---------------------------------------------------------------------------
# 图片处理
# ---------------------------------------------------------------------------

def _guess_ext(url):
    """从 URL 猜测图片扩展名，默认 .png"""
    path = url.split('?')[0].split('#')[0]
    for ext in ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.bmp'):
        if path.lower().endswith(ext):
            return ext
    wx_fmt = re.search(r'wx_fmt=(\w+)', url)
    if wx_fmt:
        fmt = wx_fmt.group(1)
        return '.jpg' if fmt in ('jpeg', 'jpg') else f'.{fmt}'
    return '.png'


def _download_file(url, dest_path):
    """下载 URL 到指定路径。"""
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0',
        'Referer': url,
    })
    with urllib.request.urlopen(req, timeout=15) as resp:
        with open(dest_path, 'wb') as f:
            f.write(resp.read())


# ---------------------------------------------------------------------------
# MinIO 上传
# ---------------------------------------------------------------------------

def _get_minio_config():
    """读取 MinIO 环境变量，全部存在则返回配置 dict，否则返回 None。"""
    endpoint = os.environ.get('MINIO_ENDPOINT')
    access_key = os.environ.get('MINIO_ACCESS_KEY')
    secret_key = os.environ.get('MINIO_SECRET_KEY')
    public_url = os.environ.get('MINIO_PUBLIC_URL')
    if not all([endpoint, access_key, secret_key, public_url]):
        return None
    return {
        'endpoint': endpoint,
        'access_key': access_key,
        'secret_key': secret_key,
        'bucket': os.environ.get('MINIO_BUCKET', 'web-images'),
        'public_url': public_url.rstrip('/'),
    }


def _create_s3_client(config):
    """创建 boto3 S3 客户端。"""
    import boto3
    from botocore.config import Config as BotoConfig
    return boto3.client(
        's3',
        endpoint_url=config['endpoint'],
        aws_access_key_id=config['access_key'],
        aws_secret_access_key=config['secret_key'],
        config=BotoConfig(signature_version='s3v4'),
        region_name='us-east-1',
    )


def _upload_to_minio(s3_client, file_path, file_name, config):
    """上传文件到 MinIO，返回公网 URL。"""
    content_type = mimetypes.guess_type(file_name)[0] or 'application/octet-stream'
    s3_client.upload_file(
        file_path, config['bucket'], file_name,
        ExtraArgs={'ContentType': content_type},
    )
    return f"{config['public_url']}/{config['bucket']}/{file_name}"


def download_images(md, image_dir=None):
    """
    找到 markdown 中所有图片 URL，下载并替换链接。
    - MinIO 已配置：上传到 MinIO，使用公网 URL
    - 否则：保存到 image_dir，使用本地路径
    """
    minio_config = _get_minio_config()

    if minio_config:
        s3_client = _create_s3_client(minio_config)
    elif image_dir:
        os.makedirs(image_dir, exist_ok=True)
    else:
        return md

    img_pattern = re.compile(r'!\[([^\]]*)\]\(([^)]+)\)')

    def _replace(match):
        alt, url = match.group(1), match.group(2)
        if url.startswith('data:'):
            return match.group(0)

        ext = _guess_ext(url)
        name = hashlib.md5(url.encode()).hexdigest()[:12] + ext

        try:
            if minio_config:
                with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                    tmp_path = tmp.name
                try:
                    _download_file(url, tmp_path)
                    new_url = _upload_to_minio(s3_client, tmp_path, name, minio_config)
                    print(f"  上传: {name} -> MinIO", file=sys.stderr)
                    return f'![{alt}]({new_url})'
                finally:
                    os.unlink(tmp_path)
            else:
                local_path = os.path.join(image_dir, name)
                _download_file(url, local_path)
                print(f"  下载: {name}", file=sys.stderr)
                return f'![{alt}]({local_path})'
        except Exception as e:
            print(f"  跳过: {url} ({e})", file=sys.stderr)
            return match.group(0)

    return img_pattern.sub(_replace, md)


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法: python3 fetch.py <url> [max_chars] [image_dir]", file=sys.stderr)
        print("  max_chars 和 image_dir 顺序随意，脚本会自动识别", file=sys.stderr)
        sys.exit(1)

    url = sys.argv[1]
    max_chars = 100000
    image_dir = None

    for arg in sys.argv[2:]:
        if arg.isdigit():
            max_chars = int(arg)
        else:
            image_dir = arg

    text, selector = scrapling_fetch(url, max_chars)
    text = download_images(text, image_dir)
    print(text)
