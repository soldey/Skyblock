#!/usr/bin/env python3
"""Builds a Modrinth .mrpack from the files tracked in git.

Usage: build-mrpack.py [--dev] <version> [output-dir]

Every jar and zip in mods/, resourcepacks/, shaderpacks/ and datapacks/ is looked up on Modrinth
by its SHA-1. Files Modrinth knows go into modrinth.index.json as downloads from its CDN, so the
pack does not redistribute them; anything else goes into overrides/.

The settings (config/ and options.txt) do not go into overrides/ directly: Modrinth App deletes
every override of the old version on a pack update, so shipped configs would reset every
player's settings each time. They go into overrides/proupdater/defaults/ instead, with a
manifest.json and a resourcepacks.json, and the PRO-Updater mod lays them out: everything on a
fresh install, only missing files on an update. That layout is useless without the mod, so the
build refuses to run unless PRO-Updater is in the pack as a Modrinth download.

--dev is for trying the pack locally before PRO-Updater is on Modrinth: the untracked
mods/pro-updater-*.jar from the profile is shipped as an override and the check is skipped.
Never publish a --dev build.

Besides the pack, writes dependencies.json with the Modrinth versions the pack embeds, ready to
be sent along with the version.
"""
import hashlib
import json
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

FOLDERS = ["config", "datapacks", "mods", "resourcepacks", "skyrecipes", "shaderpacks"]
# Loose files from the profile root that ship too: video, sound, controls, keybinds.
FILES = ["options.txt"]
LOOKUP_FOLDERS = {"mods", "resourcepacks", "shaderpacks", "datapacks"}
SKIP_NAMES = {".gitkeep", ".DS_Store"}
USER_AGENT = "soldey/Skyblock-modpack (github.com/soldey)"

# What PRO-Updater lays out; everything else (skyrecipes/ data, ...) stays a plain override.
SETTINGS = ("config/", "options.txt")
DEFAULTS_DIR = "proupdater/defaults"
PRO_UPDATER_JAR = "pro-updater-*.jar"


def strip_skyhanni_storage(data):
    # SkyHanni keeps the player's own profiles next to the settings; the mod recreates it empty.
    data.pop("storage", None)


def clear_nofrills_slot_bindings(data):
    # The author's own slot bindings; a new player starts without any. The feature itself stays.
    slots = data.get("slotBinding", {}).get("data", {})
    for hotbar in slots.values():
        if isinstance(hotbar, dict):
            hotbar["last"] = 0
            hotbar["binds"] = []


# Account state or personal choices kept next to the settings, removed from the shipped copy.
JSON_SANITIZERS = {
    "config/skyhanni/config.json": strip_skyhanni_storage,
    "config/NoFrills/Configuration.json": clear_nofrills_slot_bindings,
}


def sanitize_options(text, pack):
    # The author's resource pack choice (high contrast, ...) is not the pack's: PRO-Updater turns
    # on the pack's own list, the rest is the player's business.
    lines = []
    for line in text.splitlines():
        if line.startswith("resourcePacks:"):
            line = "resourcePacks:" + json.dumps(pack["resourcePacks"], separators=(",", ":"))
        elif line.startswith("incompatibleResourcePacks:"):
            line = "incompatibleResourcePacks:[]"
        lines.append(line)
    return "\n".join(lines) + "\n"


def shipped_bytes(path, pack):
    """The bytes of a tracked file as they go into the pack."""
    key = path.as_posix()
    sanitize = JSON_SANITIZERS.get(key)
    if sanitize:
        data = json.loads(path.read_text())
        sanitize(data)
        return (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode()
    if key == "options.txt" and "resourcePacks" in pack:
        return sanitize_options(path.read_text(), pack).encode()
    return path.read_bytes()


def tracked_files():
    out = subprocess.run(
        ["git", "ls-files", "-z", "--", *FOLDERS, *FILES], check=True, capture_output=True
    ).stdout
    return sorted(Path(p) for p in out.decode().split("\0") if p and Path(p).name not in SKIP_NAMES)


def lookup(sha1s):
    if not sha1s:
        return {}
    request = urllib.request.Request(
        "https://api.modrinth.com/v2/version_files",
        data=json.dumps({"hashes": sha1s, "algorithm": "sha1"}).encode(),
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def is_setting(path):
    key = path.as_posix()
    return any(key == s or (s.endswith("/") and key.startswith(s)) for s in SETTINGS)


def main():
    args = [a for a in sys.argv[1:] if a != "--dev"]
    dev = "--dev" in sys.argv[1:]
    if not args:
        sys.exit("usage: build-mrpack.py [--dev] <version> [output-dir]")
    version = args[0]
    out_dir = Path(args[1] if len(args) > 1 else "dist")
    pack = json.loads(Path("pack.json").read_text())

    files = tracked_files()
    if dev:
        files += sorted(Path("mods").glob(PRO_UPDATER_JAR))
    candidates = {}
    for path in files:
        if path.parts[0] in LOOKUP_FOLDERS and path.suffix in {".jar", ".zip"}:
            candidates[hashlib.sha1(path.read_bytes()).hexdigest()] = path
    known = lookup(list(candidates))

    index_files, dependencies, overrides = [], [], []
    for path in files:
        sha1 = next((h for h, p in candidates.items() if p == path), None)
        version_info = known.get(sha1) if sha1 else None
        if version_info is None:
            overrides.append(path)
            continue
        remote = next(f for f in version_info["files"] if f["hashes"]["sha1"] == sha1)
        data = path.read_bytes()
        index_files.append({
            "path": path.as_posix(),
            "hashes": {"sha1": sha1, "sha512": hashlib.sha512(data).hexdigest()},
            "env": {"client": "required", "server": "unsupported"},
            "downloads": [remote["url"]],
            "fileSize": len(data),
        })
        dependencies.append({
            "project_id": version_info["project_id"],
            "version_id": version_info["id"],
            "dependency_type": "embedded",
        })

    if not dev:
        if not any(Path(f["path"]).match(f"mods/{PRO_UPDATER_JAR}") for f in index_files):
            sys.exit(
                "PRO-Updater is not in the pack as a Modrinth download. Without it nobody lays out "
                "proupdater/defaults/ and players get no settings at all. Once it is on Modrinth, take "
                "mods/pro-updater-* out of .gitignore and commit the jar. To try the pack locally "
                "before that, build with --dev."
            )

    index = {
        "formatVersion": 1,
        "game": "minecraft",
        "versionId": version,
        "name": pack["name"],
        "summary": pack["summary"],
        "files": index_files,
        "dependencies": {
            "minecraft": pack["minecraft"],
            "fabric-loader": pack["fabric-loader"],
        },
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{pack['name'].replace(' ', '-')}-{version}.mrpack"
    manifest_files = {}
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("modrinth.index.json", json.dumps(index, indent=2))
        for path in overrides:
            data = shipped_bytes(path, pack)
            if is_setting(path):
                archive.writestr(f"overrides/{DEFAULTS_DIR}/{path.as_posix()}", data)
                manifest_files[path.as_posix()] = hashlib.sha1(data).hexdigest()
            else:
                archive.writestr(f"overrides/{path.as_posix()}", data)
        manifest = {"version": version, "files": dict(sorted(manifest_files.items()))}
        archive.writestr(f"overrides/{DEFAULTS_DIR}/manifest.json", json.dumps(manifest, indent=2) + "\n")
        archive.writestr(
            f"overrides/{DEFAULTS_DIR}/resourcepacks.json",
            json.dumps(pack["resourcePacks"], indent=2) + "\n",
        )
    (out_dir / "dependencies.json").write_text(json.dumps(dependencies, indent=2))

    plain = len(overrides) - len(manifest_files)
    print(f"{target}: {len(index_files)} files from Modrinth, {plain} overrides, "
          f"{len(manifest_files)} settings in {DEFAULTS_DIR}/")
    for path in overrides:
        if path.parts[0] in LOOKUP_FOLDERS:
            print(f"  not on Modrinth, shipped as override: {path}")
    if dev:
        print("  --dev build: for local testing only, do not publish")


if __name__ == "__main__":
    main()
