#!/bin/sh
# Print the release notes for a tag: its "## [x.y.z]" section of CHANGELOG.md
# plus a "Full Changelog" link to the previous v* tag.
# Usage: release-notes.sh <tag> <compare-url-base>
#   GitHub: release-notes.sh v1.4.0 https://github.com/owner/repo/compare
#   GitLab: release-notes.sh v1.4.0 https://gitlab.com/group/repo/-/compare
# Used by .github/workflows/publish-images.yml and .gitlab-ci.yml.
set -eu

tag="$1"
compare="$2"
version="${tag#v}"

# The section for this version, up to the next version heading.
notes="$(awk -v head="## [$version]" '
  /^## \[/ { if (found) exit; if (index($0, head) == 1) { found = 1; next } }
  found { print }
' CHANGELOG.md)"
if ! printf '%s' "$notes" | grep -q '[^[:space:]]'; then
    echo "CHANGELOG.md has no [$version] section" >&2
    exit 1
fi
printf '%s\n' "$notes"

prev="$(git describe --tags --abbrev=0 --match 'v*' "$tag^" 2>/dev/null || true)"
if [ -n "$prev" ]; then
    printf '\n**Full Changelog**: %s/%s...%s\n' "$compare" "$prev" "$tag"
fi
