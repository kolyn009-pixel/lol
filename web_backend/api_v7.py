"""Adelia web API v7: groups, Google reconnect and Telemost lifecycle."""
from __future__ import annotations

from datetime import datetime
from http.server import ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from web_backend import api as v1
from web_backend import api_v6
from web_backend import event_campaign, formula_schema_repair, google_calendar_oauth
from web_backend import group_lessons, group_lesson_access, group_portal, open_event_admin
from web_backend import lesson_join, otp_secret, public_trial_access, public_trial_channel
from web_backend import student_onboarding, student_regular_booking, student_social_profile
from web_backend import telemost_runtime, telemost_settings
from web_backend.stage12_indexes import ensure_indexes

class Handler(api_v6.Handler):
    server_version="AdeliaWeb/7.8"
    def _redirect(self,location):
        self.send_response(302);self.send_header("Location",str(location));self.send_header("Cache-Control","no-store");self.send_header("Content-Length","0");self.end_headers()
    def do_GET(self):
        parsed=urlparse(self.path);path=parsed.path;q=parse_qs(parsed.query)
        if path=="/api/teacher/groups":
            if not self._teacher():return self._json(401,{"error":"unauthorized"})
            try:return self._json(200,{"items":group_portal.teacher_groups_overview()})
            except Exception as exc:print("[web-api] teacher groups error:",type(exc).__name__,repr(exc),flush=True);return self._json(500,{"error":"server_error"})
        if path=="/api/teacher/group-lesson":
            if not self._teacher():return self._json(401,{"error":"unauthorized"})
            try:
                lid=int((q.get("id")or[""])[0]);data=open_event_admin.group_lesson_detail(lid)
                return self._json(200,data) if data else self._json(404,{"error":"group_lesson_not_found"})
            except (TypeError,ValueError) as exc:return self._json(409,{"error":str(exc)or"invalid_request"})
            except Exception as exc:print("[web-api] group lesson detail error:",type(exc).__name__,repr(exc),flush=True);return self._json(500,{"error":"server_error"})
        if path=="/api/teacher/telemost/settings":
            if not self._teacher():return self._json(401,{"error":"unauthorized"})
            try:return self._json(200,telemost_settings.snapshot())
            except Exception as exc:print("[web-api] telemost settings error:",type(exc).__name__,repr(exc),flush=True);return self._json(500,{"error":"server_error"})
        if path=="/api/teacher/google-calendar/status":
            if not self._teacher():return self._json(401,{"error":"unauthorized"})
            try:return self._json(200,google_calendar_oauth.status())
            except Exception as exc:print("[web-api] google calendar status error:",type(exc).__name__,repr(exc),flush=True);return self._json(500,{"error":"server_error"})
        if path=="/api/integrations/google/callback":
            teacher=self._teacher()
            if not teacher:return self._redirect(google_calendar_oauth.teacher_redirect("auth_required"))
            try:
                params=parse_qs(parsed.query,keep_blank_values=True);state=str((params.get("state")or[""])[0]);data=google_calendar_oauth.verify_state(state)
                if int(data["teacher_id"])!=int(teacher["admin_telegram_id"]):raise PermissionError("teacher_mismatch")
                google_calendar_oauth.complete_callback(parsed.query);return self._redirect(google_calendar_oauth.teacher_redirect("connected"))
            except PermissionError:return self._redirect(google_calendar_oauth.teacher_redirect("denied"))
            except ValueError:return self._redirect(google_calendar_oauth.teacher_redirect("invalid_state"))
            except Exception as exc:print("[web-api] google oauth error:",type(exc).__name__,repr(exc),flush=True);return self._redirect(google_calendar_oauth.teacher_redirect("failed"))
        return super().do_GET()
    def do_POST(self):
        path=urlparse(self.path).path
        if path in {"/api/teacher/lesson/open-entry","/api/teacher/lesson/mark-arrived","/api/teacher/lesson/finish"}:
            if not self._same_origin_write():return self._json(403,{"error":"cross_origin_forbidden"})
            if not self._teacher():return self._json(401,{"error":"unauthorized"})
            body=self._body()
            if body is None:return self._json(400,{"error":"invalid_json"})
            try:
                lid=int(body.get("lesson_id"))
                if path.endswith("/open-entry"):
                    result=telemost_runtime.start_individual(lid);meeting=result.get("telemost")or{}
                    return self._json(200,{**result,"status":"ok","opened_at":datetime.now().isoformat(timespec="seconds"),"meeting_url":meeting.get("join_url")})
                if path.endswith("/mark-arrived"):
                    result=lesson_join.teacher_mark_arrived(lid);return self._json(200,result) if result.get("status")=="ok" else self._json(409,{"error":result.get("status","mark_arrived_failed")})
                result=telemost_runtime.finish_individual(lid,body.get("attendance_status","PRESENT"),body.get("tutor_comment"),body.get("mode","NOW"));return self._json(200,result) if result.get("status")=="ok" else self._json(409,{"error":result.get("status","finish_failed")})
            except (TypeError,ValueError) as exc:return self._json(409,{"error":str(exc)or"invalid_request"})
            except Exception as exc:print("[web-api] lesson lifecycle error:",type(exc).__name__,repr(exc),flush=True);return self._json(500,{"error":"server_error"})
        if path in {"/api/teacher/group-lesson/start","/api/teacher/group-lesson/finish"}:
            if not self._same_origin_write():return self._json(403,{"error":"cross_origin_forbidden"})
            teacher=self._teacher()
            if not teacher:return self._json(401,{"error":"unauthorized"})
            body=self._body()
            if body is None:return self._json(400,{"error":"invalid_json"})
            try:
                lid=int(body.get("lesson_id"));result=telemost_runtime.start_group(lid,int(teacher["admin_telegram_id"])) if path.endswith("/start") else telemost_runtime.finish_group(lid);return self._json(200,result)
            except (TypeError,ValueError) as exc:return self._json(409,{"error":str(exc)or"invalid_request"})
            except Exception as exc:print("[web-api] group lifecycle error:",type(exc).__name__,repr(exc),flush=True);return self._json(500,{"error":"server_error"})
        if path in {"/api/student/group-lesson/rsvp","/api/student/lesson/rsvp"}:
            if not self._same_origin_write():return self._json(403,{"error":"cross_origin_forbidden"})
            student=self._student()
            if not student:return self._json(401,{"error":"unauthorized"})
            body=self._body()
            if body is None:return self._json(400,{"error":"invalid_json"})
            try:
                lid=int(body.get("lesson_id"));uid=int(student["id"])
                result=group_lesson_access.set_student_rsvp(lid,uid,body.get("status")) if path.endswith("group-lesson/rsvp") else lesson_join.set_attendance_intent(lid,uid,body.get("status"));return self._json(200,result)
            except PermissionError as exc:return self._json(403,{"error":str(exc)or"forbidden"})
            except (TypeError,ValueError) as exc:return self._json(409,{"error":str(exc)or"invalid_request"})
        if path=="/api/teacher/telemost/settings":
            if not self._same_origin_write():return self._json(403,{"error":"cross_origin_forbidden"})
            if not self._teacher():return self._json(401,{"error":"unauthorized"})
            body=self._body()
            if body is None:return self._json(400,{"error":"invalid_json"})
            try:return self._json(200,telemost_settings.update(body))
            except ValueError as exc:return self._json(409,{"error":str(exc)or"invalid_request"})
            except Exception as exc:print("[web-api] telemost settings save error:",type(exc).__name__,repr(exc),flush=True);return self._json(500,{"error":"server_error"})
        if path=="/api/teacher/group/create":
            if not self._same_origin_write():return self._json(403,{"error":"cross_origin_forbidden"})
            teacher=self._teacher()
            if not teacher:return self._json(401,{"error":"unauthorized"})
            body=self._body()
            if body is None:return self._json(400,{"error":"invalid_json"})
            try:
                weekday=int(body.get("weekday"));duration=int(body.get("duration_minutes")or 60);start_time=str(body.get("start_time")or"").strip();datetime.strptime(start_time,"%H:%M")
                if weekday<0 or weekday>6:raise ValueError("invalid_weekday")
                if duration<30 or duration>240:raise ValueError("invalid_duration")
                group=group_lessons.create_group(body.get("name"),body.get("subject")or"PHYSICS",body.get("study_goal")or"SCHOOL",body.get("price_per_lesson")or 0,max_members=body.get("max_members")or 8,min_attendees=body.get("min_attendees")or 2,description=body.get("description"),board_url=body.get("board_url"),recruitment_status=body.get("recruitment_status")or"OPEN",chat_mode=body.get("chat_mode")or"OPEN",created_by=int(teacher["admin_telegram_id"]))
                slot=group_lessons.add_initial_slot(int(group["id"]),weekday,start_time,duration);lesson=None;first=str(body.get("first_lesson_at")or"").strip()
                if first:lesson=group_lessons.generate_lesson(int(group["id"]),int(slot["slot_id"]),datetime.fromisoformat(first).isoformat())
                return self._json(200,{"status":"ok","group":group,"slot":slot,"lesson":lesson})
            except (TypeError,ValueError) as exc:return self._json(409,{"error":str(exc)or"invalid_request"})
            except Exception as exc:print("[web-api] group create error:",type(exc).__name__,repr(exc),flush=True);return self._json(500,{"error":"server_error"})
        if path=="/api/teacher/google-calendar/connect":
            teacher=self._teacher()
            if not teacher:return self._json(401,{"error":"unauthorized"})
            if not self._same_origin_write():return self._json(403,{"error":"cross_origin_forbidden"})
            try:return self._json(200,google_calendar_oauth.authorization_url(int(teacher["admin_telegram_id"])))
            except (FileNotFoundError,RuntimeError) as exc:return self._json(409,{"error":str(exc)})
            except Exception as exc:print("[web-api] google connect error:",type(exc).__name__,repr(exc),flush=True);return self._json(500,{"error":"server_error"})
        return super().do_POST()

def main():
    if not otp_secret.configured():raise SystemExit("ADELIA_OTP_SECRET must be set to at least 32 bytes")
    ensure_indexes();formula_schema_repair.ensure_schema();open_event_admin.choices();event_campaign.ensure_schema();student_social_profile.ensure_schema();group_portal.ensure_schema();group_lesson_access.ensure_schema();lesson_join.ensure_schema();student_onboarding.ensure_schema();public_trial_access.ensure_schema();public_trial_channel.ensure_schema();student_regular_booking.ensure_schema();print(f"Adelia web API v7.8 listening on http://{v1.HOST}:{v1.PORT}");ThreadingHTTPServer((v1.HOST,v1.PORT),Handler).serve_forever()
if __name__=="__main__":main()
