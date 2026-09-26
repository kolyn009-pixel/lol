#!/usr/bin/env python3
"""Isolated regression test for homework files exposed in Student/Teacher web UI."""
from __future__ import annotations

import os
import tempfile

import database


def main():
    fd, path = tempfile.mkstemp(prefix="adelia-homework-file-", suffix=".db")
    os.close(fd)
    try:
        database.DB_NAME = path
        conn = database.connect()
        try:
            conn.execute(
                "CREATE TABLE homework (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL)"
            )
            conn.execute("INSERT INTO homework(id,user_id) VALUES(10,101)")
            conn.commit()
        finally:
            conn.close()

        import homework_attachments as ha

        aid = ha.save_reference(
            10,
            kind="document",
            filename="physics-homework.pdf",
            mime_type="application/pdf",
            telegram_file_id="TEST_TELEGRAM_FILE",
            source_channel="TELEGRAM",
            content=b"%PDF-db-first-homework",
        )

        items = ha.web_descriptors(10)
        assert len(items) == 1, items
        assert items[0]["id"] == aid, items
        assert items[0]["url"] == f"/api/homework/attachment?id={aid}", items
        assert items[0]["filename"] == "physics-homework.pdf", items
        forbidden_keys = {"telegram_file_id", "file_id", "vk_attachment_key", "vk_url"}
        assert not (forbidden_keys & set(items[0])), items[0]

        from vk_adapter import attachment_bridge

        def forbidden_remote(*args, **kwargs):
            raise AssertionError("homework read attempted remote transport instead of SQLite")

        old_tg = attachment_bridge.telegram_file_bytes
        old_bytes = attachment_bridge._bytes_request
        attachment_bridge.telegram_file_bytes = forbidden_remote
        attachment_bridge._bytes_request = forbidden_remote
        try:
            student = ha.read_for_web(aid, student_user_id=101)
            assert student["content"] == b"%PDF-db-first-homework"
            assert student["mime_type"] == "application/pdf"

            try:
                ha.read_for_web(aid, student_user_id=202)
            except PermissionError:
                pass
            else:
                raise AssertionError("foreign student could read homework attachment")

            teacher = ha.read_for_web(aid, teacher=True)
            assert teacher["content"] == b"%PDF-db-first-homework"
        finally:
            attachment_bridge.telegram_file_bytes = old_tg
            attachment_bridge._bytes_request = old_bytes

        conn = database.connect()
        try:
            row = conn.execute(
                "SELECT content_blob,content_size,content_sha256 FROM homework_attachments WHERE id=?",
                (aid,),
            ).fetchone()
            assert bytes(row["content_blob"]) == b"%PDF-db-first-homework", row
            assert int(row["content_size"]) == len(b"%PDF-db-first-homework"), row
            assert len(str(row["content_sha256"])) == 64, row
        finally:
            conn.close()

        print("HOMEWORK_ATTACHMENT_WEB_SELFTEST=PASS")
    finally:
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass


if __name__ == "__main__":
    main()
