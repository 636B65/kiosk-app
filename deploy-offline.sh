#!/usr/bin/env bash
#
# deploy-offline.sh — Deploy the kiosk on an AIR-GAPPED (offline) machine.
#
# Two ways to run:
#
#   A) From the likely place — where the shipped archive is (repo checkout):
#        ./deploy-offline.sh [kiosk-app.tar.gz] [--no-verify]
#      It unpacks kiosk-app.tar.gz into ./kiosk-app (preserving any live DB),
#      then deploys. Archive defaults to ./offline/kiosk-app.tar.gz.
#
#   B) From inside an already-unpacked bundle:
#        tar -xzf kiosk-app.tar.gz && cd kiosk-app
#        ./deploy-offline.sh [--no-verify]
#
# Prerequisites: Docker Engine installed (offline) and daemon running.
#
# What it does:
#     1. unpacks the bundle (if needed), preserving your live database
#     2. verifies checksums                        (skip with --no-verify)
#     3. backs up the live database
#     4. loads the two images into Docker
#     5. starts docker compose (DB migration runs automatically on startup)
#
set -euo pipefail

cd "$(dirname "$0")"

VERIFY=1
ARCHIVE=""
for arg in "$@"; do
  case "$arg" in
    --no-verify) VERIFY=0 ;;
    *.tar.gz) ARCHIVE="$arg" ;;
    *) echo "Unknown option: $arg" >&2; exit 1 ;;
  esac
done

TARGET="kiosk-app"

# --- Unpack (mode A) if we're not already inside a bundle ---------------------
if [ -f docker-compose.yml ] && [ -f kiosk-backend.tar.gz ]; then
  echo "==> Running from inside $PWD (already unpacked)"
elif [ -n "$ARCHIVE" ] || [ -f "offline/kiosk-app.tar.gz" ] || [ -f "kiosk-app.tar.gz" ]; then
  ARCHIVE="${ARCHIVE:-$( [ -f offline/kiosk-app.tar.gz ] && echo offline/kiosk-app.tar.gz || echo kiosk-app.tar.gz )}"

  # Preserve a live DB before tar overwrites anything.
  LIVE_DB=""
  if [ -f "$TARGET/data/kiosk.db" ]; then
    LIVE_DB="$(mktemp)"
    cp "$TARGET/data/kiosk.db" "$LIVE_DB"
    echo "==> Preserving live database from previous deploy"
  fi

  echo "==> Unpacking $ARCHIVE"
  tar -xzf "$ARCHIVE"

  if [ -n "$LIVE_DB" ]; then
    mkdir -p "$TARGET/data"
    cp "$LIVE_DB" "$TARGET/data/kiosk.db"
    rm -f "$LIVE_DB"
    echo "==> Restored live database over the shipped bundle"
  fi
  cd "$TARGET"
else
  echo "Cannot find a bundle." >&2
  echo "Either run from inside kiosk-app/ or pass the archive:" >&2
  echo "  $0 path/to/kiosk-app.tar.gz" >&2
  exit 1
fi

for f in kiosk-backend.tar.gz kiosk-frontend.tar.gz docker-compose.yml; do
  [ -f "$f" ] || { echo "Missing $f in $(pwd)" >&2; exit 1; }
done

if [ "$VERIFY" = 1 ] && [ -f SHA256SUMS ]; then
  echo "==> Verifying checksums"
  sha256sum -c SHA256SUMS
fi

echo "==> Backing up database"
if [ -f data/kiosk.db ]; then
  mkdir -p data/backups
  cp data/kiosk.db "data/backups/kiosk.db.$(date +%Y%m%d-%H%M%S).bak"
  echo "    saved to data/backups/"
else
  echo "    no database yet (a fresh one is created on first start)"
fi

echo "==> Loading images"
docker load -i kiosk-backend.tar.gz
docker load -i kiosk-frontend.tar.gz

echo "==> Starting services"
docker compose up -d --force-recreate

echo "==> Status"
docker compose ps

echo
echo "Kiosk is running offline."
echo "  Customer: http://<this-machine>:8080"
echo "  Admin:    http://<this-machine>:8080/#admin"