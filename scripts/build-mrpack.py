#!/usr/bin/env python3
"""Builds a Modrinth .mrpack from the files tracked in git.

Usage: build-mrpack.py <version> [output-dir]

Every jar and zip in mods/, resourcepacks/, shaderpacks/ and datapacks/ is looked up on Modrinth
by its SHA-1. Files Modrinth knows go into modrinth.index.json as downloads from its CDN, so the
pack does not redistribute them; anything else is copied into overrides/ together with config/
and skyrecipes/.

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
LOOKUP_FOLDERS = {"mods", "resourcepacks", "shaderpacks", "datapacks"}
SKIP_NAMES = {".gitkeep", ".DS_Store"}
USER_AGENT = "soldey/Skyblock-modpack (github.com/soldey)"

# Configs that keep the player's own account state next to the settings. The listed top-level
# keys are dropped from the copy that goes into the pack; the mods recreate them empty.
STRIP_KEYS = {
    "config/skyhanni/config.json": ["storage"],
}


def tracked_files():
    out = subprocess.run(
        ["git", "ls-files", "-z", "--", *FOLDERS], check=True, capture_output=True
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


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: build-mrpack.py <version> [output-dir]")
    version = sys.argv[1]
    out_dir = Path(sys.argv[2] if len(sys.argv) > 2 else "dist")
    pack = json.loads(Path("pack.json").read_text())

    files = tracked_files()
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
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("modrinth.index.json", json.dumps(index, indent=2))
        for path in overrides:
            name = (Path("overrides") / path).as_posix()
            strip = STRIP_KEYS.get(path.as_posix())
            if strip:
                data = json.loads(path.read_text())
                for key in strip:
                    data.pop(key, None)
                archive.writestr(name, json.dumps(data, indent=2))
            else:
                archive.write(path, name)
    (out_dir / "dependencies.json").write_text(json.dumps(dependencies, indent=2))

    print(f"{target}: {len(index_files)} files from Modrinth, {len(overrides)} overrides")
    for path in overrides:
        if path.parts[0] in LOOKUP_FOLDERS:
            print(f"  not on Modrinth, shipped as override: {path}")


if __name__ == "__main__":
    main()
