"""Teacher-facing server health and safe storage maintenance.

Only explicitly whitelisted, regeneratable files are ever eligible for cleanup.
The preview token is short lived and apply_cleanup revalidates every candidate
before deletion. Databases, receipts, materials and backups are never candidates.
"""
from __future__ import annotations

import json
import os
import secrets
import shutil
import time
from pathlib import Path
from threading import Lock

import database
from web_backend import receipt_cloud_archive

ROOT = Path(database.BASE_DIR).resolve()
DB = Path(database.DB_NAME).resolve()
RECEIPTS = Path(os.getenv("ADELIA_WEB_RECEIPT_DIR", "/opt/tutorbot/data/web_receipts")).resolve()
BACKUPS = Path(os.getenv("ADELIA_BACKUP_DIR", str(ROOT / "backups"))).resolve()
PUBLIC = Path(os.getenv("ADELIA_PUBLIC_ROOT", "/var/www/adeliatutor.ru")).resolve()
TMP_ROOT = Path("/tmp").resolve()
_PREVIEWS = {}
_LOCK = Lock()
PREVIEW_TTL = 600


def _bytes(path: Path):
    try:
        if path.is_file():
            return int(path.stat().st_size)
        if not path.is_dir():
            return 0
        total = 0
        for base, dirs, files in os.walk(path, followlinks=False):
            dirs[:] = [d for d in dirs if not Path(base, d).is_symlink()]
            for name in files:
                p = Path(base, name)
                try:
                    if not p.is_symlink():
                        total += p.stat().st_size
                except OSError:
                    pass
        return total
    except OSError:
        return 0


def _disk():
    usage = shutil.disk_usage(ROOT)
    return {"total": usage.total, "used": usage.used, "free": usage.free, "percent": round(usage.used * 100 / usage.total, 1) if usage.total else 0}


def _memory():
    result = {"total": None, "available": None, "used": None, "percent": None}
    try:
        values = {}
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, raw = line.split(":", 1)
            values[key] = int(raw.strip().split()[0]) * 1024
        total = values.get("MemTotal", 0)
        available = values.get("MemAvailable", 0)
        result = {"total": total, "available": available, "used": max(0, total - available), "percent": round((total - available) * 100 / total, 1) if total else None}
    except Exception:
        pass
    return result


def _load():
    try:
        one, five, fifteen = os.getloadavg()
        return {"one": round(one, 2), "five": round(five, 2), "fifteen": round(fifteen, 2), "cpu_count": os.cpu_count() or 1}
    except OSError:
        return {"one": None, "five": None, "fifteen": None, "cpu_count": os.cpu_count() or 1}


def _file_group(path: Path):
    return {"path": str(path), "exists": path.exists(), "bytes": _bytes(path)}


def snapshot():
    disk = _disk()
    memory = _memory()
    load = _load()
    archive = receipt_cloud_archive.queue_stats()
    warnings = []
    if disk["percent"] >= 90:
        warnings.append({"level": "critical", "code": "disk_90", "text": "Диск заполнен более чем на 90%."})
    elif disk["percent"] >= 80:
        warnings.append({"level": "warning", "code": "disk_80", "text": "Диск заполнен более чем на 80%."})
    if memory.get("percent") is not None and memory["percent"] >= 90:
        warnings.append({"level": "warning", "code": "memory_90", "text": "Используется более 90% оперативной памяти."})
    if archive.get("failed"):
        warnings.append({"level": "warning", "code": "receipt_archive_failed", "text": f"Не удалось архивировать чеков: {archive['failed']}."})
    if not receipt_cloud_archive.configured():
        warnings.append({"level": "warning", "code": "yandex_disk_not_configured", "text": "Яндекс Диск для чеков не подключён."})
    return {
        "generated_at": database.now_iso(),
        "disk": disk,
        "memory": memory,
        "load": load,
        "storage": {
            "database": _file_group(DB),
            "receipts": _file_group(RECEIPTS),
            "backups": _file_group(BACKUPS),
            "public_site": _file_group(PUBLIC),
            "repository": _file_group(ROOT),
        },
        "receipt_archive": {**archive, "configured": receipt_cloud_archive.configured()},
        "warnings": warnings,
    }


def _safe_candidate(path: Path):
    try:
        resolved = path.resolve()
    except OSError:
        return False
    # Python bytecode/caches inside the application tree are always regeneratable.
    if ROOT == resolved or ROOT in resolved.parents:
        if "__pycache__" in resolved.parts:
            return True
        if resolved.is_file() and resolved.suffix in {".pyc", ".pyo"}:
            return True
        return False
    # /tmp cleanup is intentionally narrow: only our own named temp files.
    if TMP_ROOT in resolved.parents and resolved.name.startswith(("adelia_", "tutorbot_")):
        return True
    return False


def _candidates():
    now = time.time()
    found = {}
    for p in ROOT.rglob("__pycache__"):
        if p.is_dir() and _safe_candidate(p):
            found[str(p.resolve())] = p
    for pattern in ("adelia_*", "tutorbot_*"):
        for p in TMP_ROOT.glob(pattern):
            try:
                if _safe_candidate(p) and now - p.stat().st_mtime >= 24 * 3600:
                    found[str(p.resolve())] = p
            except OSError:
                pass
    items = []
    for key, path in sorted(found.items()):
        items.append({"path": key, "bytes": _bytes(path), "kind": "directory" if path.is_dir() else "file", "mtime": int(path.stat().st_mtime) if path.exists() else 0})
    return items


def preview_cleanup():
    items = _candidates()
    token = secrets.token_urlsafe(24)
    expires = time.time() + PREVIEW_TTL
    with _LOCK:
        _PREVIEWS.clear()
        _PREVIEWS[token] = {"expires": expires, "items": items}
    return {"token": token, "expires_in": PREVIEW_TTL, "items": items, "bytes": sum(x["bytes"] for x in items), "count": len(items), "protected": [str(DB), str(RECEIPTS), str(BACKUPS)]}


def apply_cleanup(token):
    token = str(token or "")
    with _LOCK:
        preview = _PREVIEWS.pop(token, None)
    if not preview or preview["expires"] < time.time():
        raise ValueError("cleanup_preview_expired")
    removed = []
    skipped = []
    freed = 0
    for item in preview["items"]:
        path = Path(item["path"])
        try:
            if not path.exists() or not _safe_candidate(path):
                skipped.append({"path": str(path), "reason": "not_eligible"})
                continue
            stat = path.stat()
            # Revalidate that the target was not replaced since preview.
            if int(stat.st_mtime) != int(item.get("mtime") or 0):
                skipped.append({"path": str(path), "reason": "changed_since_preview"})
                continue
            size = _bytes(path)
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            removed.append({"path": str(path), "bytes": size})
            freed += size
        except OSError as exc:
            skipped.append({"path": str(path), "reason": type(exc).__name__})
    log_dir = ROOT / "logs"
    try:
        log_dir.mkdir(exist_ok=True)
        with (log_dir / "storage_cleanup.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"at": database.now_iso(), "freed": freed, "removed": removed, "skipped": skipped}, ensure_ascii=False) + "\n")
    except OSError:
        pass
    return {"status": "ok", "freed_bytes": freed, "removed": removed, "skipped": skipped, "health": snapshot()}
