#!/usr/bin/env python3
"""Git filter that keeps SkyHanni's account storage out of the repository.

config/skyhanni/config.json holds the settings and, under "storage", the player's own profile
data. Git sees the file without that section, while the copy in the profile keeps it:

  clean  - on `git add`: drops "storage" from what gets committed.
  smudge - on checkout: puts back the "storage" of the file that is already on disk, so git never
           wipes it from the profile.

Registered once per clone (scripts/setup-git.sh does it):
  git config filter.strip-storage.clean  "python3 scripts/strip-storage-filter.py clean"
  git config filter.strip-storage.smudge "python3 scripts/strip-storage-filter.py smudge %f"
"""
import json
import sys
from pathlib import Path

KEY = "storage"


def main():
    mode = sys.argv[1]
    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
    except ValueError:
        # Not JSON (half-written by the game, say): pass it through untouched.
        sys.stdout.write(raw)
        return
    if not isinstance(data, dict):
        sys.stdout.write(raw)
        return

    if mode == "clean":
        data.pop(KEY, None)
    elif mode == "smudge":
        on_disk = Path(sys.argv[2])
        try:
            kept = json.loads(on_disk.read_text()).get(KEY)
        except (OSError, ValueError, AttributeError):
            kept = None
        if kept is not None:
            data[KEY] = kept
    sys.stdout.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
