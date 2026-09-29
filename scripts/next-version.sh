#!/usr/bin/env bash
# Works out the next version from the commit messages made since the last vX.Y.Z tag.
#
# Commit messages follow "type (optional module): summary" and the type decides the bump:
#   release -> first digit   (a "release (2.0.0): ..." message may also state the version)
#   feat    -> second digit
#   fix     -> third digit
#
# Prints the next version, or nothing at all when no commit asks for a bump.
set -euo pipefail

last_tag=$(git describe --tags --abbrev=0 --match 'v[0-9]*' 2>/dev/null || true)
if [[ -n "$last_tag" ]]; then
    range="${last_tag}..HEAD"
    current="${last_tag#v}"
else
    range="HEAD"
    current="0.0.0"
fi

IFS=. read -r major minor patch <<<"$current"
major=${major:-0}
minor=${minor:-0}
patch=${patch:-0}

messages=$(git log --format=%s "$range")
[[ -z "$messages" ]] && exit 0

# An explicit "release (X.Y.Z)" wins over everything else.
explicit=$(grep -iEo '^release[[:space:]]*\(([0-9]+\.[0-9]+\.[0-9]+)\)' <<<"$messages" | head -1 || true)
if [[ -n "$explicit" ]]; then
    echo "$explicit" | grep -Eo '[0-9]+\.[0-9]+\.[0-9]+'
    exit 0
fi

bump=""
while IFS= read -r message; do
    [[ -z "$message" ]] && continue
    # No ${var,,} here: macOS still ships bash 3.2.
    type=$(grep -iEo '^(release|feat|fix)[[:space:]]*(\([^)]*\))?:' <<<"$message" |
        grep -iEo '^(release|feat|fix)' | tr '[:upper:]' '[:lower:]' || true)
    case "$type" in
        release) bump="major"; break ;;
        feat) [[ "$bump" != "major" ]] && bump="minor" ;;
        fix) [[ -z "$bump" ]] && bump="patch" ;;
    esac
done <<<"$messages"

case "$bump" in
    major) echo "$((major + 1)).0.0" ;;
    minor) echo "${major}.$((minor + 1)).0" ;;
    patch) echo "${major}.${minor}.$((patch + 1))" ;;
    *) exit 0 ;;
esac
