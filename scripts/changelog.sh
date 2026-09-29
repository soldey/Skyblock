#!/usr/bin/env bash
# Prints release notes built from the conventional commits made since the last vX.Y.Z tag.
#
# Usage: changelog.sh [tag-being-released]
# The tag is only used for the compare link at the bottom; it defaults to HEAD.
set -euo pipefail

new_ref="${1:-HEAD}"

last_tag=$(git describe --tags --abbrev=0 --match 'v[0-9]*' 2>/dev/null || true)
range="HEAD"
[[ -n "$last_tag" ]] && range="${last_tag}..HEAD"

section() {
    local type="$1" title="$2"
    local lines
    lines=$(git log --format=%s "$range" |
        grep -iE "^${type}[[:space:]]*(\([^)]*\))?:" |
        sed -E "s/^[a-zA-Z]+[[:space:]]*(\(([^)]*)\))?:[[:space:]]*/\2|/" |
        awk -F'|' '{ if ($1 != "") printf "- **%s**: %s\n", $1, $2; else printf "- %s\n", $2 }' || true)
    if [[ -n "$lines" ]]; then
        echo "### $title"
        echo "$lines"
        echo
    fi
}

section "feat" "Features"
section "fix" "Fixes"
section "release" "Release"

if [[ -n "$last_tag" ]]; then
    echo "**Full changelog**: https://github.com/${GITHUB_REPOSITORY:-soldey/Skyblock}/compare/${last_tag}...${new_ref}"
fi
