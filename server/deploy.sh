#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Load .env
if [ ! -f .env ]; then
    echo "Error: .env not found. Copy .env.example to .env and edit it first."
    exit 1
fi
source .env

echo "==> Starting MinIO..."
docker compose up -d

echo "==> Waiting for MinIO to be ready..."
for i in $(seq 1 30); do
    if curl -sf http://localhost:9000/minio/health/live >/dev/null 2>&1; then
        echo "    MinIO is ready."
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "Error: MinIO failed to start within 30 seconds."
        exit 1
    fi
    sleep 1
done

# Install mc if not present
if ! command -v mc &>/dev/null; then
    echo "==> Installing MinIO Client (mc)..."
    curl -sL https://dl.min.io/client/mc/release/linux-amd64/mc -o /usr/local/bin/mc
    chmod +x /usr/local/bin/mc
fi

echo "==> Configuring mc alias..."
mc alias set local http://localhost:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD"

echo "==> Creating bucket 'web-images'..."
mc mb --ignore-existing local/web-images

echo "==> Setting bucket to public read..."
mc anonymous set download local/web-images

echo "==> Done! MinIO is running."
echo "    API:     http://localhost:9000"
echo "    Console: http://localhost:9001"
echo "    Bucket:  web-images (public read)"
