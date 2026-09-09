#!/usr/bin/env python3
"""Prepare a verified desktop update bundle for adeliatutor.ru/desktop-updates.

This script does not deploy anywhere. It copies only electron-updater artifacts
from a completed build into a clean release directory and refuses incomplete
sets so the server never receives half an update.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

WIN_REQUIRED = ("latest.yml",)
MAC_REQUIRED = ("latest-mac.yml",)
ALLOWED_SUFFIXES = {".exe", ".dmg", ".zip", ".yml", ".blockmap"}


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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path, help="electron-builder dist directory")
    parser.add_argument("target", type=Path, help="clean local release bundle directory")
    parser.add_argument("--platform", choices=("win", "mac", "all"), default="all")
    args = parser.parse_args()

    source = args.source.resolve()
    target = args.target.resolve()
    if not source.is_dir():
        raise SystemExit("source directory not found")
    if args.platform in {"win", "all"}:
        find_required(source, WIN_REQUIRED)
        if not any(source.glob("*.exe")):
            raise SystemExit("Windows installer missing")
    if args.platform in {"mac", "all"}:
        find_required(source, MAC_REQUIRED)
        if not any(source.glob("*.zip")):
            raise SystemExit("macOS updater zip missing")
        if not any(source.glob("*.dmg")):
            raise SystemExit("macOS dmg missing")

    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)

    manifest = {"files": []}
    for src in collect(source):
        dst = target / src.name
        shutil.copy2(src, dst)
        manifest["files"].append({"name": dst.name, "size": dst.stat().st_size, "sha512": sha512(dst)})
    (target / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "ok", "target": str(target), "files": len(manifest["files"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
