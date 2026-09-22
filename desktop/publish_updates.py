#!/usr/bin/env python3
"""Prepare a verified desktop update bundle for adeliatutor.ru/desktop-updates.

This script does not deploy anywhere. It copies only electron-updater artifacts
from a completed build into a clean release directory, refuses incomplete sets,
and creates stable browser-download aliases without changing updater metadata.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

ALLOWED_SUFFIXES = {".exe", ".dmg", ".zip", ".yml", ".blockmap"}


def update_metadata_name(platform: str, channel: str) -> str:
    if platform == "win":
        return "latest.yml" if channel == "stable" else f"{channel}.yml"
    if platform == "mac":
        return "latest-mac.yml" if channel == "stable" else f"{channel}-mac.yml"
    raise ValueError(platform)


def sha512(path: Path) -> str:
    h = hashlib.sha512()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def find_required(source: Path, names: tuple[str, ...]) -> None:
    missing = [name for name in names if not (source / name).is_file()]
    if missing:
        raise SystemExit("missing update metadata: " + ", ".join(missing))


def collect(source: Path) -> list[Path]:
    files = [p for p in source.iterdir() if p.is_file() and p.suffix.lower() in ALLOWED_SUFFIXES]
    if not files:
        raise SystemExit("no updater artifacts found")
    return sorted(files)


def newest(source: Path, pattern: str) -> Path:
    matches = sorted(source.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    if not matches:
        raise SystemExit(f"artifact missing: {pattern}")
    return matches[0]


def create_download_aliases(source: Path, target: Path, platform: str, arch: str | None) -> list[Path]:
    aliases: list[Path] = []
    if platform in {"win", "all"}:
        src = newest(source, "*.exe")
        dst = target / "Adelia-latest-windows-x64.exe"
        shutil.copy2(src, dst)
        aliases.append(dst)
    if platform in {"mac", "all"}:
        if platform == "mac" and arch not in {"arm64", "x64"}:
            raise SystemExit("--arch arm64 or --arch x64 is required for mac browser alias")
        if arch in {"arm64", "x64"}:
            src = newest(source, "*.dmg")
            dst = target / f"Adelia-latest-macos-{arch}.dmg"
            shutil.copy2(src, dst)
            aliases.append(dst)
    return aliases


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path, help="electron-builder dist directory")
    parser.add_argument("target", type=Path, help="clean local release bundle directory")
    parser.add_argument("--platform", choices=("win", "mac", "all"), default="all")
    parser.add_argument("--channel", choices=("beta", "stable"), default="beta")
    parser.add_argument("--version", help="desktop semantic version recorded in the release manifest")
    parser.add_argument("--git-sha", help="source commit recorded in the release manifest")
    parser.add_argument("--arch", choices=("x64", "arm64"), help="required for a macOS browser-download alias")
    args = parser.parse_args()

    source = args.source.resolve()
    target = args.target.resolve()
    if not source.is_dir():
        raise SystemExit("source directory not found")
    if args.platform in {"win", "all"}:
        find_required(source, (update_metadata_name("win", args.channel),))
        if not any(source.glob("*.exe")):
            raise SystemExit("Windows installer missing")
    if args.platform in {"mac", "all"}:
        find_required(source, (update_metadata_name("mac", args.channel),))
        if not any(source.glob("*.zip")):
            raise SystemExit("macOS updater zip missing")
        if not any(source.glob("*.dmg")):
            raise SystemExit("macOS dmg missing")

    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)

    version = (args.version or "").strip()
    git_sha = (args.git_sha or "").strip()
    if args.channel == "beta" and version and "-beta." not in version:
        raise SystemExit("beta channel requires a beta semantic version")
    if args.channel == "stable" and version and "-" in version:
        raise SystemExit("stable channel refuses prerelease versions")
    manifest = {
        "schema": 2,
        "channel": args.channel,
        "version": version or None,
        "git_sha": git_sha or None,
        "rollback": {
            "strategy": "atomic_channel_directory",
            "instruction": "Keep the previous channel directory and atomically repoint the live channel symlink if rollback is required."
        },
        "files": [],
    }
    for src in collect(source):
        dst = target / src.name
        shutil.copy2(src, dst)
        manifest["files"].append({"name": dst.name, "size": dst.stat().st_size, "sha512": sha512(dst)})

    for alias in create_download_aliases(source, target, args.platform, args.arch):
        manifest["files"].append({"name": alias.name, "size": alias.stat().st_size, "sha512": sha512(alias), "browser_alias": True})

    (target / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (target / "release.json").write_text(json.dumps({k: manifest[k] for k in ("schema", "channel", "version", "git_sha", "rollback")}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "ok", "target": str(target), "files": len(manifest["files"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
