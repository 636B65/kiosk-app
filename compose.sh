#!/bin/sh
set -eu

if [ "${HIGH_TRAFFIC:-0}" = "1" ]; then
    export COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml:docker-compose.high-traffic.yml}"
else
    export COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
fi

exec docker compose "$@"
