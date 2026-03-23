# Web to Markdown

将任意网页 URL 转换为干净的 Markdown 格式正文，支持图片下载与对象存储上传。

## 背景

这个项目解决的核心问题是：**在 Claude Code 中读取网页内容并转换为 Markdown，且图片链接在任何机器上都能访问。**

典型场景：用 Claude Code 抓取一篇微信公众号文章，生成的 Markdown 需要发送给其他机器或服务使用。如果图片保存在本地，其他机器无法访问。因此需要一个对象存储服务来托管图片，Markdown 中使用公网 URL。

## 架构

项目涉及两台机器协作：

```
机器 A（工作机）                        机器 B（存储服务器）
┌─────────────────────────┐           ┌─────────────────────────┐
│  Claude Code            │           │  MinIO (Docker)         │
│    ↓ 调用 Skill         │           │    - S3 兼容 API        │
│  fetch.py               │           │    - web-images bucket  │
│    ↓ 抓取网页           │    上传    │    - 公开读，鉴权写     │
│    ↓ 下载图片到临时文件  │ ────────→ │                         │
│    ↓ 上传图片到 MinIO   │           │  Nginx 反代（HTTPS）    │
│    ↓ 返回带公网URL的 MD │           │    - 提供公网访问       │
└─────────────────────────┘           └─────────────────────────┘
```

- **机器 A**：日常工作机，运行 Claude Code，通过 `/web-to-markdown` 命令抓取网页。`fetch.py` 负责提取正文、下载图片、上传到 MinIO，最终输出的 Markdown 中图片链接为公网 URL。
- **机器 B**：存储服务器，运行 MinIO 对象存储。提供 S3 API 接收图片上传，通过域名 + HTTPS 反代提供公网图片访问。

> 如果不需要图片公网访问（例如仅本地使用），可以不部署机器 B，图片会保存到本地目录，完全向后兼容。

## 项目结构

```
web-to-markdown/
├── README.md
├── SKILL.md                      # Claude Code Skill 定义
├── requirements.txt
│
├── scripts/                      # ── 机器 A 使用 ──
│   └── fetch.py                  # 核心提取脚本（抓取 + 图片处理）
│
├── server/                       # ── 机器 B 使用 ──
│   ├── deploy.sh                 # MinIO 一键部署脚本
│   ├── docker-compose.yml        # MinIO Docker 配置
│   └── .env.example              # 环境变量模板
│
└── .claude/
    └── commands/
        └── web-to-markdown.md    # Claude Code 自定义命令
```

## 部署指南

### 机器 B：部署 MinIO 存储服务

```bash
cd server
cp .env.example .env
vim .env  # 设置 MINIO_ROOT_USER、MINIO_ROOT_PASSWORD、MINIO_DOMAIN
bash deploy.sh
```

脚本会自动：
1. 启动 MinIO Docker 容器（API 端口 9000，控制台端口 9001）
2. 创建 `web-images` bucket
3. 设置 bucket 为公开读（上传需要鉴权，下载不需要）

部署完成后，还需要自行配置 Nginx 反代 + HTTPS，将域名指向 MinIO 的 9000 端口。

### 机器 A：配置工作环境

#### 1. 安装依赖

```bash
pip install -r requirements.txt
```

#### 2. 配置 MinIO 环境变量

在 shell 配置文件（如 `~/.zshrc`）中添加：

```bash
export MINIO_ENDPOINT=http://c-machine:9000       # 机器 B 的 MinIO S3 API 地址
export MINIO_ACCESS_KEY=admin                      # 访问密钥（与机器 B 的 MINIO_ROOT_USER 一致）
export MINIO_SECRET_KEY=changeme123456             # 密钥（与机器 B 的 MINIO_ROOT_PASSWORD 一致）
export MINIO_BUCKET=web-images                     # bucket 名称（可选，默认 web-images）
export MINIO_PUBLIC_URL=https://minio.example.com  # 机器 B 的公网域名
```

#### 3. 使用

**作为 Claude Code 命令：**

```
/web-to-markdown https://mp.weixin.qq.com/s/xxx
```

**直接命令行调用：**

```bash
# 抓取网页，图片上传到 MinIO
python3 scripts/fetch.py https://example.com/article 100000 ./images

# 仅提取文本（不处理图片）
python3 scripts/fetch.py https://example.com/article
```

参数顺序灵活，脚本会自动识别数字为 `max_chars`、路径为 `image_dir`。

## 提取策略

Claude Code 调用时按以下顺序自动降级：

| 优先级 | 策略 | 工具 | 优点 | 限制 |
|--------|------|------|------|------|
| 1 | Jina Reader | `r.jina.ai` | 快（~1.5s），格式干净 | 200次/天免费配额，部分平台 403 |
| 2 | Scrapling | `fetch.py` | 无限制，支持反爬平台 | 需要安装依赖 |
| 3 | 直接抓取 | `web_fetch` | 无需额外依赖 | 仅适合静态页面 |

以下域名 Jina Reader 无法读取，会跳过直接使用 `fetch.py`：

- `mp.weixin.qq.com`（微信公众号）
- `zhuanlan.zhihu.com`（知乎专栏）
- `juejin.cn`（稀土掘金）
- `csdn.net`

## 依赖

- [Scrapling](https://github.com/D4Vinci/Scrapling) — 网页抓取
- [html2text](https://github.com/Alir3z4/html2text) — HTML 转 Markdown
- [boto3](https://github.com/boto/boto3) — S3/MinIO 上传（可选，仅配置了 MinIO 环境变量时使用）
