#!/usr/bin/env bash
# Run once after cloning: registers the filter that keeps SkyHanni's account storage out of git.
# Without it `git add` would commit config/skyhanni/config.json as it is, profile data included.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

git config filter.strip-storage.clean "python3 scripts/strip-storage-filter.py clean"
git config filter.strip-storage.smudge "python3 scripts/strip-storage-filter.py smudge %f"
git config filter.strip-storage.required true

echo "strip-storage filter registered."
