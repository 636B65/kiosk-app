#!/bin/sh
set -eu

if [ "${HIGH_TRAFFIC:-0}" = "1" ]; then
    export COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml:docker-compose.high-traffic.yml}"
else
    export COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
fi

# Footer release info for locally built frontend images (see frontend/Dockerfile).
if [ -z "${APP_VERSION:-}" ]; then
    APP_VERSION="$(git describe --tags --always 2>/dev/null | sed 's/^v//' || true)"
    export APP_VERSION="${APP_VERSION:-dev}"
fi
if [ -z "${GIT_COMMIT:-}" ]; then
    GIT_COMMIT="$(git rev-parse HEAD 2>/dev/null || true)"
    export GIT_COMMIT
fi

exec docker compose "$@"
