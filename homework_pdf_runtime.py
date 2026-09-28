from __future__ import annotations

import fcntl
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import database


# ============================================================
# STORAGE POLICY
# ============================================================

CACHE_DIR = Path(
    "/opt/tutorbot/storage/homework_files"
)

# Hard limit.
CACHE_MAX_BYTES = 2 * 1024 * 1024 * 1024

# Once cleanup starts, shrink below the hard limit.
CACHE_TARGET_BYTES = int(
    1.55 * 1024 * 1024 * 1024
)

# Emergency disk guard.
MIN_FREE_DISK_BYTES = 3 * 1024 * 1024 * 1024

# Emergency cleanup target.
EMERGENCY_TARGET_BYTES = int(
    1.20 * 1024 * 1024 * 1024
)

# Individual PDF guard.
MAX_PDF_BYTES = 80 * 1024 * 1024

PREVIEW_WIDTH = 1450
MAX_PAGES = 500


FINISHED_HOMEWORK_STATUSES = {
    "DONE",
    "APPROVED",
    "REVIEWED",
    "COMPLETED",
    "CHECKED",
}

ACTIVE_HOMEWORK_STATUSES = {
    "ASSIGNED",
    "ACTIVE",
    "PENDING",
    "REVISION",
}


# ============================================================
# INITIALIZATION
# ============================================================

def initialize():
    CACHE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    c = database.connect()

    try:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS homework_pdf_pages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                homework_id INTEGER NOT NULL,
                attachment_id INTEGER NOT NULL,
                page_number INTEGER NOT NULL,
                page_count INTEGER NOT NULL,

                telegram_file_id TEXT,
                vk_attachment_key TEXT,

                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,

                UNIQUE(
                    attachment_id,
                    page_number
                )
            );

            CREATE INDEX IF NOT EXISTS
                idx_hw_pdf_pages_homework
            ON homework_pdf_pages(
                homework_id,
                attachment_id,
                page_number
            );

            CREATE TABLE IF NOT EXISTS homework_pdf_sources (
                attachment_id INTEGER PRIMARY KEY,
                homework_id INTEGER NOT NULL,

                local_path TEXT NOT NULL,
                size_bytes INTEGER NOT NULL DEFAULT 0,

                last_accessed_at TEXT NOT NULL,
                cached_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS
                idx_hw_pdf_sources_homework
            ON homework_pdf_sources(
                homework_id
            );

            CREATE INDEX IF NOT EXISTS
                idx_hw_pdf_sources_access
            ON homework_pdf_sources(
                last_accessed_at
            );
            """
        )

        c.commit()

    finally:
        c.close()


def _now():
    return database.now_iso()


# ============================================================
# GENERIC ATTACHMENT HELPERS
# ============================================================

def _value(row, key, default=None):
    try:
        return row[key]
    except Exception:
        return default


def attachment_filename(row):
    return str(
        _value(row, "file_name")
        or _value(row, "filename")
        or "homework.pdf"
    )


def telegram_file_id(row):
    return (
        _value(row, "telegram_file_id")
        or _value(row, "file_id")
    )


def is_pdf(row):
    if not row:
        return False

    filename = (
        attachment_filename(row)
        .lower()
    )

    mime = str(
        _value(
            row,
            "mime_type",
            "",
        )
        or ""
    ).lower()

    return (
        filename.endswith(".pdf")
        or mime == "application/pdf"
    )


def attachments(homework_id):
    c = database.connect()

    try:
        return list(
            c.execute(
                """
                SELECT *
                FROM homework_attachments
                WHERE homework_id=?
                ORDER BY id
                """,
                (int(homework_id),),
            ).fetchall()
        )

    finally:
        c.close()


def attachment(
    homework_id,
    attachment_id,
):
    c = database.connect()

    try:
        return c.execute(
            """
            SELECT *
            FROM homework_attachments
            WHERE homework_id=?
              AND id=?
            """,
            (
                int(homework_id),
                int(attachment_id),
            ),
        ).fetchone()

    finally:
        c.close()


# ============================================================
# PAGE PLATFORM CACHE
# ============================================================

def cached_page(
    attachment_id,
    page_number,
):
    initialize()

    c = database.connect()

    try:
        return c.execute(
            """
            SELECT *
            FROM homework_pdf_pages
            WHERE attachment_id=?
              AND page_number=?
            """,
            (
                int(attachment_id),
                int(page_number),
            ),
        ).fetchone()

    finally:
        c.close()


def save_page(
    homework_id,
    attachment_id,
    page_number,
    page_count,
    telegram_id=None,
    vk_key=None,
):
    initialize()

    now = _now()

    c = database.connect()

    try:
        c.execute(
            """
            INSERT INTO homework_pdf_pages(
                homework_id,
                attachment_id,
                page_number,
                page_count,
                telegram_file_id,
                vk_attachment_key,
                created_at,
                updated_at
            )
            VALUES(?,?,?,?,?,?,?,?)

            ON CONFLICT(
                attachment_id,
                page_number
            )
            DO UPDATE SET
                homework_id=excluded.homework_id,
                page_count=excluded.page_count,

                telegram_file_id=COALESCE(
                    excluded.telegram_file_id,
                    homework_pdf_pages.telegram_file_id
                ),

                vk_attachment_key=COALESCE(
                    excluded.vk_attachment_key,
                    homework_pdf_pages.vk_attachment_key
                ),

                updated_at=excluded.updated_at
            """,
            (
                int(homework_id),
                int(attachment_id),
                int(page_number),
                int(page_count),
                (
                    str(telegram_id)
                    if telegram_id
                    else None
                ),
                (
                    str(vk_key)
                    if vk_key
                    else None
                ),
                now,
                now,
            ),
        )

        c.commit()

    finally:
        c.close()


# ============================================================
# SOURCE PDF CACHE
# ============================================================

def _source_path(attachment_id):
    return (
        CACHE_DIR
        / f"source_{int(attachment_id)}.pdf"
    )


def _lock_path(attachment_id):
    return (
        CACHE_DIR
        / f"source_{int(attachment_id)}.lock"
    )


def _record_source(
    attachment_id,
    homework_id,
    path,
):
    now = _now()

    size = 0

    try:
        size = int(
            Path(path).stat().st_size
        )
    except Exception:
        pass

    c = database.connect()

    try:
        c.execute(
            """
            INSERT INTO homework_pdf_sources(
                attachment_id,
                homework_id,
                local_path,
                size_bytes,
                last_accessed_at,
                cached_at
            )
            VALUES(?,?,?,?,?,?)

            ON CONFLICT(
                attachment_id
            )
            DO UPDATE SET
                homework_id=excluded.homework_id,
                local_path=excluded.local_path,
                size_bytes=excluded.size_bytes,
                last_accessed_at=excluded.last_accessed_at
            """,
            (
                int(attachment_id),
                int(homework_id),
                str(path),
                size,
                now,
                now,
            ),
        )

        c.commit()

    finally:
        c.close()


def _touch_source(
    attachment_id,
):
    c = database.connect()

    try:
        c.execute(
            """
            UPDATE homework_pdf_sources
            SET last_accessed_at=?
            WHERE attachment_id=?
            """,
            (
                _now(),
                int(attachment_id),
            ),
        )

        c.commit()

    finally:
        c.close()


def _remove_source(
    attachment_id,
    path=None,
):
    if path is None:
        path = _source_path(
            attachment_id
        )

    try:
        Path(path).unlink(
            missing_ok=True
        )
    except Exception:
        pass

    c = database.connect()

    try:
        c.execute(
            """
            DELETE FROM homework_pdf_sources
            WHERE attachment_id=?
            """,
            (int(attachment_id),),
        )

        c.commit()

    finally:
        c.close()


def _download_source(row):
    # The persisted attachment is the source of truth for repeat requests.
    stored = row["content_blob"] if "content_blob" in row.keys() else None
    if stored:
        data = bytes(stored)
        if len(data) > MAX_PDF_BYTES:
            raise RuntimeError("PDF слишком большой для локального просмотра.")
        return data

    from vk_adapter import (
        attachment_bridge as bridge
    )

    fid = telegram_file_id(
        row
    )

    if fid:
        data = (
            bridge.telegram_file_bytes(
                fid
            )
        )

    else:
        url = _value(
            row,
            "vk_url",
        )

        if not url:
            raise RuntimeError(
                "У PDF нет Telegram file_id "
                "или VK URL."
            )

        data = bridge._bytes_request(
            str(url),
            timeout=90,
        )

    if len(data) > MAX_PDF_BYTES:
        raise RuntimeError(
            "PDF слишком большой "
            "для локального просмотра."
        )

    return data


def _cache_disk_usage():
    total = 0

    for path in CACHE_DIR.glob(
        "source_*.pdf"
    ):
        try:
            total += int(
                path.stat().st_size
            )
        except Exception:
            pass

    return total


def _free_disk_bytes():
    try:
        return int(
            shutil.disk_usage(
                CACHE_DIR
            ).free
        )
    except Exception:
        return 999 * 1024 * 1024 * 1024


def _homework_priority(
    status,
):
    """
    Lower number = delete first.
    """

    normalized = str(
        status or ""
    ).upper()

    if normalized in FINISHED_HOMEWORK_STATUSES:
        return 0

    if normalized == "CANCELLED":
        return 0

    if normalized == "EXPIRED":
        return 1

    if normalized == "REVISION":
        return 3

    if normalized in ACTIVE_HOMEWORK_STATUSES:
        return 5

    return 2


def cleanup(
    force=False,
):
    """
    Smart LRU cleanup.

    Delete first:
      1. completed/checked homework PDFs
      2. old unknown/inactive PDFs
      3. active homework only as last resort

    Never stores image/page binaries in SQLite.
    """

    initialize()

    current_size = (
        _cache_disk_usage()
    )

    free_disk = (
        _free_disk_bytes()
    )

    emergency = (
        free_disk
        < MIN_FREE_DISK_BYTES
    )

    if (
        not force
        and not emergency
        and current_size
        <= CACHE_MAX_BYTES
    ):
        return {
            "before": current_size,
            "after": current_size,
            "deleted": 0,
            "emergency": False,
        }

    target = (
        EMERGENCY_TARGET_BYTES
        if emergency
        else CACHE_TARGET_BYTES
    )

    c = database.connect()

    try:
        rows = list(
            c.execute(
                """
                SELECT
                    s.attachment_id,
                    s.homework_id,
                    s.local_path,
                    s.size_bytes,
                    s.last_accessed_at,
                    h.status AS homework_status
                FROM homework_pdf_sources s
                LEFT JOIN homework h
                  ON h.id=s.homework_id
                ORDER BY
                    s.last_accessed_at ASC
                """
            ).fetchall()
        )

    finally:
        c.close()

    candidates = []

    for row in rows:
        path = Path(
            row["local_path"]
        )

        if not path.exists():
            _remove_source(
                row["attachment_id"],
                path,
            )
            continue

        try:
            size = int(
                path.stat().st_size
            )
        except Exception:
            size = int(
                row["size_bytes"]
                or 0
            )

        priority = (
            _homework_priority(
                row[
                    "homework_status"
                ]
            )
        )

        candidates.append(
            (
                priority,
                str(
                    row[
                        "last_accessed_at"
                    ]
                    or ""
                ),
                int(
                    row["attachment_id"]
                ),
                path,
                size,
            )
        )

    # Completed first.
    # Within same class: least recently used first.
    candidates.sort(
        key=lambda item: (
            item[0],
            item[1],
        )
    )

    deleted = 0

    for (
        _priority,
        _last_access,
        attachment_id,
        path,
        size,
    ) in candidates:

        if current_size <= target:
            break

        _remove_source(
            attachment_id,
            path,
        )

        current_size = max(
            0,
            current_size - size,
        )

        deleted += 1

    # Remove orphan files that do not have DB metadata.
    known = {
        int(item[2])
        for item in candidates
    }

    for path in CACHE_DIR.glob(
        "source_*.pdf"
    ):
        try:
            aid = int(
                path.stem.split(
                    "_",
                    1,
                )[1]
            )
        except Exception:
            continue

        if aid in known:
            continue

        try:
            size = int(
                path.stat().st_size
            )

            path.unlink(
                missing_ok=True
            )

            current_size = max(
                0,
                current_size - size,
            )

            deleted += 1

        except Exception:
            pass

    return {
        "before": (
            _cache_disk_usage()
            if deleted == 0
            else None
        ),
        "after": current_size,
        "deleted": deleted,
        "emergency": emergency,
    }


def ensure_source(row):
    """
    Persistent original-PDF cache.

    No TTL.
    File stays until smart 2 GB eviction removes it.
    """

    initialize()

    attachment_id = int(
        row["id"]
    )

    homework_id = int(
        row["homework_id"]
    )

    target = _source_path(
        attachment_id
    )

    lock_path = _lock_path(
        attachment_id
    )

    with open(
        lock_path,
        "a+b",
    ) as lock:

        fcntl.flock(
            lock.fileno(),
            fcntl.LOCK_EX,
        )

        try:
            if (
                target.exists()
                and target.stat().st_size > 0
            ):
                os.utime(
                    target,
                    None,
                )

                _record_source(
                    attachment_id,
                    homework_id,
                    target,
                )

                _touch_source(
                    attachment_id
                )

                return target

            # Before adding another PDF,
            # make sure disk pressure is safe.
            cleanup()

            data = _download_source(
                row
            )

            tmp = (
                CACHE_DIR
                / (
                    f".source_"
                    f"{attachment_id}_"
                    f"{os.getpid()}.tmp"
                )
            )

            tmp.write_bytes(
                data
            )

            os.replace(
                tmp,
                target,
            )

            _record_source(
                attachment_id,
                homework_id,
                target,
            )

            # New PDF may push us over the 2 GB limit.
            cleanup()

            # cleanup() may theoretically remove this PDF
            # only in an emergency situation where disk is full.
            if not target.exists():
                data = _download_source(
                    row
                )

                target.write_bytes(
                    data
                )

                _record_source(
                    attachment_id,
                    homework_id,
                    target,
                )

            return target

        finally:
            fcntl.flock(
                lock.fileno(),
                fcntl.LOCK_UN,
            )


# ============================================================
# PDF RENDER
# ============================================================

def _pdf_page_count(source):
    result = subprocess.run(
        [
            "pdfinfo",
            str(source),
        ],
        capture_output=True,
        text=True,
        timeout=15,
        check=True,
    )

    pages = None

    for line in (
        result.stdout
        .splitlines()
    ):
        if line.lower().startswith(
            "pages:"
        ):
            pages = int(
                line.split(
                    ":",
                    1,
                )[1].strip()
            )

            break

    if not pages:
        raise RuntimeError(
            "Не удалось определить "
            "количество страниц PDF."
        )

    if pages > MAX_PAGES:
        raise RuntimeError(
            f"PDF содержит {pages} страниц. "
            f"Лимит просмотра — {MAX_PAGES}."
        )

    return pages


def render_page(
    homework_id,
    attachment_id,
    requested_page,
):
    row = attachment(
        homework_id,
        attachment_id,
    )

    if not row:
        raise RuntimeError(
            "Вложение не найдено."
        )

    if not is_pdf(row):
        raise RuntimeError(
            "Вложение не является PDF."
        )

    source = ensure_source(
        row
    )

    _touch_source(
        attachment_id
    )

    cached = cached_page(
        attachment_id,
        requested_page,
    )

    if cached:
        pages = int(
            cached["page_count"]
        )
    else:
        pages = _pdf_page_count(
            source
        )

    page = max(
        1,
        min(
            int(requested_page),
            pages,
        ),
    )

    with tempfile.TemporaryDirectory(
        prefix="tutorbot_hw_page_"
    ) as td:

        output = (
            Path(td)
            / "page"
        )

        subprocess.run(
            [
                "pdftoppm",

                "-f",
                str(page),

                "-l",
                str(page),

                "-singlefile",

                "-jpeg",

                "-jpegopt",
                "quality=82",

                "-scale-to-x",
                str(PREVIEW_WIDTH),

                "-scale-to-y",
                "-1",

                str(source),
                str(output),
            ],
            capture_output=True,
            timeout=30,
            check=True,
        )

        image = (
            Path(td)
            / "page.jpg"
        )

        if not image.exists():
            raise RuntimeError(
                "Preview страницы "
                "не был создан."
            )

        data = image.read_bytes()

    save_page(
        homework_id,
        attachment_id,
        page,
        pages,
    )

    return {
        "bytes": data,
        "page": page,
        "pages": pages,
    }


# ============================================================
# DIAGNOSTICS
# ============================================================

def cache_stats():
    initialize()

    size = _cache_disk_usage()

    c = database.connect()

    try:
        row = c.execute(
            """
            SELECT
                COUNT(*) AS files,
                COALESCE(
                    SUM(size_bytes),
                    0
                ) AS db_bytes
            FROM homework_pdf_sources
            """
        ).fetchone()

    finally:
        c.close()

    return {
        "files": int(
            row["files"]
            or 0
        ),
        "bytes": size,
        "limit_bytes": CACHE_MAX_BYTES,
        "free_disk_bytes": _free_disk_bytes(),
    }


initialize()
