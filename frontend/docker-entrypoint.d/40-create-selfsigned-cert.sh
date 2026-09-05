#!/bin/sh
#
# Create a self-signed TLS certificate on first start (docker compose --build /
# up). The certificate is written to $CERT_DIR (/etc/nginx/certs by default,
# bind-mounted from ./data/tls) and is NEVER overwritten once it exists, so
# operators can later replace it with a real certificate by dropping their own
# server.crt / server.key files into that directory.
#
set -e

CERT_DIR="${CERT_DIR:-/etc/nginx/certs}"
mkdir -p "$CERT_DIR"

if [ -f "$CERT_DIR/server.crt" ] && [ -f "$CERT_DIR/server.key" ]; then
    echo "[tls] Existing certificate found in $CERT_DIR - leaving it unchanged"
    exit 0
fi

# Incomplete/partial files would break nginx; move them aside and regenerate.
for f in server.crt server.key; do
    if [ -f "$CERT_DIR/$f" ]; then
        echo "[tls] Found incomplete $f - moving it aside" >&2
        mv "$CERT_DIR/$f" "$CERT_DIR/$f.old-$(date +%s)"
    fi
done

echo "[tls] No certificate found - generating a self-signed certificate..."
openssl req -x509 -nodes -newkey rsa:2048 -days 3650 \
    -keyout "$CERT_DIR/server.key" \
    -out "$CERT_DIR/server.crt" \
    -subj "/CN=localhost" \
    -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"
echo "[tls] Self-signed certificate generated at $CERT_DIR (valid 10 years)"