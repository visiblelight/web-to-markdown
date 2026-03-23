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

# Validate required vars
: "${MINIO_ROOT_USER:?MINIO_ROOT_USER must be set in .env}"
: "${MINIO_ROOT_PASSWORD:?MINIO_ROOT_PASSWORD must be set in .env}"

# Check jvs certbot webroot volume exists
if ! docker volume ls --format '{{.Name}}' | grep -q "^jvs_certbot_webroot$"; then
    echo "Error: Docker volume 'jvs_certbot_webroot' not found."
    echo "       Make sure the jvs project is running first."
    exit 1
fi

echo "==> Issuing SSL certificate for minio.ke.run..."
docker compose run --rm --entrypoint certbot certbot certonly \
    --webroot -w /var/www/certbot \
    -d minio.ke.run \
    --register-unsafely-without-email \
    --agree-tos \
    --keep-until-expiring

echo "==> Copying certificates to MinIO certs volume..."
docker compose run --rm --entrypoint sh certbot -c \
    "cp /etc/letsencrypt/live/minio.ke.run/fullchain.pem /certs/public.crt && \
     cp /etc/letsencrypt/live/minio.ke.run/privkey.pem /certs/private.key"

echo "==> Starting MinIO and certbot..."
docker compose up -d

echo "==> Waiting for MinIO to be ready..."
for i in $(seq 1 30); do
    if curl -sk https://localhost:9443/minio/health/live >/dev/null 2>&1; then
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
mc alias set local https://minio.ke.run:9443 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD"

echo "==> Creating bucket 'web-images'..."
mc mb --ignore-existing local/web-images

echo "==> Setting bucket to public read..."
mc anonymous set download local/web-images

echo "==> Setting up daily cron to restart MinIO (ensures renewed certs take effect)..."
(crontab -l 2>/dev/null | grep -v "web-images-minio"; echo "0 3 * * * docker restart web-images-minio") | crontab -

echo ""
echo "==> Done!"
echo "    MinIO API:     https://minio.ke.run:9443"
echo "    MinIO Console: https://localhost:9001"
echo ""
echo "    Machine A 环境变量配置："
echo "      MINIO_ENDPOINT=https://minio.ke.run:9443"
echo "      MINIO_ACCESS_KEY=$MINIO_ROOT_USER"
echo "      MINIO_SECRET_KEY=<your password>"
echo "      MINIO_BUCKET=web-images"
echo "      MINIO_PUBLIC_URL=https://minio.ke.run:9443"
