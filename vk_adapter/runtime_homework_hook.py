"""Small routing hook for durable VK teacher homework attachments."""
from __future__ import annotations

from . import homework_ingest


def intercept(app, message):
    teacher_vk_id = int((message or {}).get('from_id') or 0)
    pending = app._PENDING.get(teacher_vk_id)
    if not teacher_vk_id or not pending or pending[0] != 't_hw' or not app.teacher_service.is_teacher(teacher_vk_id):
        return False
    peer_id = int((message or {}).get('peer_id') or teacher_vk_id)
    command = app._extract_command(message)
    if command in {'cancel', 'home', 't_home'}:
        app._PENDING.pop(teacher_vk_id, None)
        app.send(peer_id, 'Хорошо, задание не создано.', True, 'teacher')
        return True
    if command:
        # A navigation button is not homework text. Let the regular router
        # select another student or screen without creating an assignment.
        app._PENDING.pop(teacher_vk_id, None)
        return False
    homework_ingest.handle_teacher_assignment(
        app, peer_id, teacher_vk_id, int(pending[1]),
        str((message or {}).get('text') or '').strip(), (message or {}).get('attachments') or [],
    )
    return True
