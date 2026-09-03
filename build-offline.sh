#!/usr/bin/env bash
#
# build-offline.sh — Build the kiosk images on an INTERNET-CONNECTED machine and
# bundle everything needed to deploy into ONE archive for an air-gapped target.
#
# Run:  ./build-offline.sh [amd64|arm64] [--include-data]
#   arch        defaults to the local machine's architecture.
#   --include-data  also bundle your current data/kiosk.db (first deploy ONLY —
#                   it WILL overwrite any existing DB on the target).
#
# Output: ./offline/kiosk-app.tar.gz
#   Contains (under kiosk-app/):
#     docker-compose.yml        deploy-offline.sh
#     kiosk-backend.tar.gz      kiosk-frontend.tar.gz
#     SHA256SUMS                [data/kiosk.db  only with --include-data]
#
#   On the target:
#     Copy kiosk-app.tar.gz to the target, then run (from this repo checkout):
#       ./deploy-offline.sh kiosk-app.tar.gz
#     ...or unpack manually and run from inside:
#       tar -xzf kiosk-app.tar.gz && cd kiosk-app && ./deploy-offline.sh
#
# NOTE on cross-arch builds (arm64 on an amd64 machine, etc.):
#   buildx needs QEMU emulation enabled on this machine, e.g.:
#     docker run --rm --privileged tonistiigi/binfmt --install all
#
set -euo pipefail

cd "$(dirname "$0")"

OUT="$(uname -m)"
INCLUDE_DATA=0
for arg in "$@"; do
  case "$arg" in
    --include-data) INCLUDE_DATA=1 ;;
    amd64|x86_64)   OUT="amd64" ;;
    arm64|aarch64)  OUT="arm64" ;;
    *) echo "Unknown option/arch: $arg" >&2; exit 1 ;;
  esac
done

case "$OUT" in
  amd64) PLATFORM="linux/amd64" ;;
  arm64) PLATFORM="linux/arm64" ;;
  *)
    echo "Unknown platform: $OUT" >&2
    echo "Usage: $0 [amd64|arm64] [--include-data]" >&2
    exit 1
    ;;
esac

WORK="offline/.work"
BUNDLE="$WORK/kiosk-app"
rm -rf offline
mkdir -p "$BUNDLE"

echo "==> Building for $PLATFORM (target arch: $OUT)"

# Output straight to a loadable tarball so cross-arch builds also work.
docker buildx build \
  --platform "$PLATFORM" \
  --output type=docker,dest="$BUNDLE/kiosk-backend.tar" \
  ./backend
gzip -f "$BUNDLE/kiosk-backend.tar"

docker buildx build \
  --platform "$PLATFORM" \
  --output type=docker,dest="$BUNDLE/kiosk-frontend.tar" \
  ./frontend
gzip -f "$BUNDLE/kiosk-frontend.tar"

echo "==> Bundling docker-compose.yml + deploy-offline.sh"
cp docker-compose.yml "$BUNDLE/"
cp deploy-offline.sh "$BUNDLE/"

FILES="kiosk-backend.tar.gz kiosk-frontend.tar.gz docker-compose.yml deploy-offline.sh"

if [ "$INCLUDE_DATA" = 1 ]; then
  if [ -f data/kiosk.db ]; then
    echo "==> Bundling data/kiosk.db (WARNING: overwrites any DB on target)"
    mkdir -p "$BUNDLE/data"
    cp data/kiosk.db "$BUNDLE/data/kiosk.db"
    FILES="$FILES data/kiosk.db"
  else
    echo "!! --include-data set but data/kiosk.db not found; continuing without it" >&2
  fi
fi

echo "==> Checksums"
( cd "$BUNDLE" && sha256sum $FILES > SHA256SUMS )

echo "==> Creating archive"
tar -C "$WORK" -czf "offline/kiosk-app.tar.gz" kiosk-app
rm -rf "$WORK"

echo
echo "Done: offline/kiosk-app.tar.gz"
echo
echo "Ship this single file to the target, then on the target:"
echo "    ./deploy-offline.sh kiosk-app.tar.gz"
echo "  or manually:"
echo "    tar -xzf kiosk-app.tar.gz && cd kiosk-app && ./deploy-offline.sh"