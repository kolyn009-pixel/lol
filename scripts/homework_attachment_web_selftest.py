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
        )

        items = ha.web_descriptors(10)
        assert len(items) == 1, items
        assert items[0]["id"] == aid, items
        assert items[0]["url"] == f"/api/homework/attachment?id={aid}", items
        assert items[0]["filename"] == "physics-homework.pdf", items
        forbidden_keys = {"telegram_file_id", "file_id", "vk_attachment_key", "vk_url"}
        assert not (forbidden_keys & set(items[0])), items[0]

        from vk_adapter import attachment_bridge

        old = attachment_bridge.telegram_file_bytes
        attachment_bridge.telegram_file_bytes = lambda file_id: b"%PDF-test-homework"
        try:
            student = ha.read_for_web(aid, student_user_id=101)
            assert student["content"] == b"%PDF-test-homework"
            assert student["mime_type"] == "application/pdf"

            try:
                ha.read_for_web(aid, student_user_id=202)
            except PermissionError:
                pass
            else:
                raise AssertionError("foreign student could read homework attachment")

            teacher = ha.read_for_web(aid, teacher=True)
            assert teacher["content"] == b"%PDF-test-homework"
        finally:
            attachment_bridge.telegram_file_bytes = old

        print("HOMEWORK_ATTACHMENT_WEB_SELFTEST=PASS")
    finally:
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass


if __name__ == "__main__":
    main()
