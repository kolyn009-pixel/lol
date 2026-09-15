"""Teacher-facing orchestration for standalone events and attendance."""
from __future__ import annotations
import database
from web_backend import attendance_tracking,group_portal,open_event_policy,telemost_runtime,group_lesson_access
PAID_STATUSES={'PAID','WAIVED'}
def _now():return database.now_iso()
def choices():
 open_event_policy.ensure_schema();c=database.connect();students=[dict(r) for r in c.execute("SELECT id,name,grade,main_subject FROM users WHERE active=1 ORDER BY name COLLATE NOCASE").fetchall()];groups=[dict(r) for r in c.execute("SELECT id,name,subject,study_goal FROM study_groups WHERE active=1 ORDER BY name COLLATE NOCASE").fetchall()];c.close();return {'students':students,'groups':groups}
def create(payload,teacher_id):
 r=open_event_policy.create_event(payload.get('title'),payload.get('starts_at'),int(payload.get('duration_minutes') or 60),event_type