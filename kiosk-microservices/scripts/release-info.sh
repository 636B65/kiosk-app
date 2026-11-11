#!/bin/sh
# Print the release info JSON ({"version": ..., "commit": ...}) baked into the
# images. Usage: release-info.sh <repo-dir> [APP_VERSION] [GIT_COMMIT]
#
# Explicit values (release workflow, compose.sh, build-offline.sh) win. Without
# them - e.g. a plain `docker compose up --build` - the version is the newest
# CHANGELOG.md heading and the commit is read from the checkout's .git (no git
# binary needed). Both Dockerfiles run this from the named build context "repo".
set -eu

repo="$1"
version="$(printf %s "${2:-}" | tr -cd 'A-Za-z0-9._+-')"
commit="$(printf %s "${3:-}" | tr -cd '0-9a-fA-F')"

if [ -z "$version" ] || [ "$version" = "dev" ]; then
    version="$(sed -n 's/^## \[\([0-9][0-9.]*\)\].*/\1/p' "$repo/CHANGELOG.md" 2>/dev/null | head -n 1)"
fi

if [ -z "$commit" ] && [ -f "$repo/.git/HEAD" ]; then
    head="$(cat "$repo/.git/HEAD")"
    case "$head" in
        "ref: "*)
            ref="${head#ref: }"
            if [ -f "$repo/.git/$ref" ]; then
                commit="$(cat "$repo/.git/$ref")"
            elif [ -f "$repo/.git/packed-refs" ]; then
                commit="$(grep " $ref\$" "$repo/.git/packed-refs" | cut -d ' ' -f 1 | head -n 1)"
            fi
            ;;
        *) commit="$head" ;;
    esac
    commit="$(printf %s "$commit" | tr -cd '0-9a-fA-F')"
fi

printf '{"version": "%s", "commit": "%s"}\n' "${version:-dev}" "$commit"
