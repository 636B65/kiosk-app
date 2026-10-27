#!/bin/sh
set -eu

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
