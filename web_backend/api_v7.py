"""Adelia web API v7: Google reconnect, groups and Telemost settings."""
from __future__ import annotations

from datetime import datetime
from http.server import ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from web_backend import api as v1
from web_backend import api_v6
from web_backend import event_campaign
from web_backend import formula_schema_repair
from web_backend import google_calendar_oauth
from web_backend import group_lessons
from web_backend import group_portal
from web_backend import open_event_admin
from web_backend import otp_secret
from web_backend import public_trial_access
from web_backend import public_trial_channel
from web_backend import student_onboarding
from web_backend import student_regular_booking
from web_backend import student_social_profile
from web_backend import telemost_settings
from web_backend.stage12_indexes import ensure_indexes


class Handler(api_v6.Handler):
    server_version = "AdeliaWeb/7.2"

    def _redirect(self, location):
        self.send_response(302)
        self.send_header("Location", str(location))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/teacher/groups":
            if not self._teacher():
                return self._json(401, {"error": "unauthorized"})
            try:
                return self._json(200, {"items": group_portal.teacher_groups_overview()})
            except Exception as exc:
                print("[web-api] teacher groups error:", type(exc).__name__, repr(exc), flush=True)
                return self._json(500, {"error": "server_error"})

        if path == "/api/teacher/telemost/settings":
            if not self._teacher():
                return self._json(401, {"error": "unauthorized"})
            try:
                return self._json(200, telemost_settings.snapshot())
            except Exception as exc:
                print("[web-api] telemost settings error:", type(exc).__name__, repr(exc), flush=True)
                return self._json(500, {"error": "server_error"})

        if path == "/api/teacher/google-calendar/status":
            teacher = self._teacher()
            if not teacher:
                return self._json(401, {"error": "unauthorized"})
            try:
                return self._json(200, google_calendar_oauth.status())
            except Exception as exc:
                print("[web-api] google calendar status error:", type(exc).__name__, repr(exc), flush=True)
                return self._json(500, {"error": "server_error"})

        if path == "/api/integrations/google/callback":
            teacher = self._teacher()
            if not teacher:
                return self._redirect(google_calendar_oauth.teacher_redirect("auth_required"))
            try:
                params = parse_qs(parsed.query, keep_blank_values=True)
                state = str((params.get("state") or [""])[0])
                state_data = google_calendar_oauth.verify_state(state)
                if int(state_data["teacher_id"]) != int(teacher["admin_telegram_id"]):
                    raise PermissionError("teacher_mismatch")
                google_calendar_oauth.complete_callback(parsed.query)
                return self._redirect(google_calendar_oauth.teacher_redirect("connected"))
            except PermissionError:
                return self._redirect(google_calendar_oauth.teacher_redirect("denied"))
            except ValueError:
                return self._redirect(google_calendar_oauth.teacher_redirect("invalid_state"))
            except Exception as exc:
                print("[web-api] google calendar oauth callback error:", type(exc).__name__, repr(exc), flush=True)
                return self._redirect(google_calendar_oauth.teacher_redirect("failed"))

        return super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path

        if path == "/api/teacher/telemost/settings":
            if not self._same_origin_write():
                return self._json(403, {"error": "cross_origin_forbidden"})
            if not self._teacher():
                return self._json(401, {"error": "unauthorized"})
            body = self._body()
            if body is None:
                return self._json(400, {"error": "invalid_json"})
            try:
                return self._json(200, telemost_settings.update(body))
            except ValueError as exc:
                return self._json(409, {"error": str(exc) or "invalid_request"})
            except Exception as exc:
                print("[web-api] telemost settings save error:", type(exc).__name__, repr(exc), flush=True)
                return self._json(500, {"error": "server_error"})

        if path == "/api/teacher/group/create":
            if not self._same_origin_write():
                return self._json(403, {"error": "cross_origin_forbidden"})
            teacher = self._teacher()
            if not teacher:
                return self._json(401, {"error": "unauthorized"})
            body = self._body()
            if body is None:
                return self._json(400, {"error": "invalid_json"})
            try:
                weekday = int(body.get("weekday"))
                duration = int(body.get("duration_minutes") or 60)
                start_time = str(body.get("start_time") or "").strip()
                datetime.strptime(start_time, "%H:%M")
                if weekday < 0 or weekday > 6:
                    raise ValueError("invalid_weekday")
                if duration < 30 or duration > 240:
                    raise ValueError("invalid_duration")

                group = group_lessons.create_group(
                    body.get("name"), body.get("subject") or "PHYSICS",
                    body.get("study_goal") or "SCHOOL", body.get("price_per_lesson") or 0,
                    max_members=body.get("max_members") or 8,
                    min_attendees=body.get("min_attendees") or 2,
                    description=body.get("description"), board_url=body.get("board_url"),
                    recruitment_status=body.get("recruitment_status") or "OPEN",
                    chat_mode=body.get("chat_mode") or "OPEN",
                    created_by=int(teacher["admin_telegram_id"]),
                )
                slot = group_lessons.add_initial_slot(int(group["id"]), weekday, start_time, duration)
                lesson = None
                first_lesson_at = str(body.get("first_lesson_at") or "").strip()
                if first_lesson_at:
                    first_dt = datetime.fromisoformat(first_lesson_at)
                    lesson = group_lessons.generate_lesson(int(group["id"]), int(slot["slot_id"]), first_dt.isoformat())
                return self._json(200, {"status": "ok", "group": group, "slot": slot, "lesson": lesson})
            except (TypeError, ValueError) as exc:
                return self._json(409, {"error": str(exc) or "invalid_request"})
            except Exception as exc:
                print("[web-api] teacher group create error:", type(exc).__name__, repr(exc), flush=True)
                return self._json(500, {"error": "server_error"})

        if path == "/api/teacher/google-calendar/connect":
            teacher = self._teacher()
            if not teacher:
                return self._json(401, {"error": "unauthorized"})
            if not self._same_origin_write():
                return self._json(403, {"error": "cross_origin_forbidden"})
            try:
                return self._json(200, google_calendar_oauth.authorization_url(int(teacher["admin_telegram_id"])))
            except (FileNotFoundError, RuntimeError) as exc:
                return self._json(409, {"error": str(exc)})
            except Exception as exc:
                print("[web-api] google calendar connect error:", type(exc).__name__, repr(exc), flush=True)
                return self._json(500, {"error": "server_error"})

        return super().do_POST()


def main():
    if not otp_secret.configured():
        raise SystemExit("ADELIA_OTP_SECRET must be set to at least 32 bytes")
    ensure_indexes()
    formula_schema_repair.ensure_schema()
    open_event_admin.choices()
    event_campaign.ensure_schema()
    student_social_profile.ensure_schema()
    group_portal.ensure_schema()
    student_onboarding.ensure_schema()
    public_trial_access.ensure_schema()
    public_trial_channel.ensure_schema()
    student_regular_booking.ensure_schema()
    print("Adelia web API v7.2 listening on " f"http://{v1.HOST}:{v1.PORT}")
    ThreadingHTTPServer((v1.HOST, v1.PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
