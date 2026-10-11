"""Persist files from a teacher's VK homework message before delivery."""
from __future__ import annotations

import mimetypes
import os
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

import database
import homework_attachments

from . import attachment_bridge, channel_delivery, teacher_service

MAX_FILES = 5
MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_TOTAL_BYTES = 50 * 1024 * 1024
ALLOWED_SUFFIXES = {'.pdf', '.jpg', '.jpeg', '.png', '.webp', '.doc', '.docx', '.ppt', '.pptx', '.xls', '.xlsx', '.txt', '.zip'}
VK_HOST_SUFFIXES = ('vk.com', 'vk.me', 'userapi.com', 'vk-cdn.net', 'vkuseraudio.net')


def _valid_url(url):
    parsed = urlsplit(str(url or ''))
    host = (parsed.hostname or '').lower().rstrip('.')
    if parsed.scheme != 'https' or not host or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError('file_url_invalid')
    if not any(host == suffix or host.endswith('.' + suffix) for suffix in VK_HOST_SUFFIXES):
        raise ValueError('file_host_invalid')
    return str(url)


class _SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return super().redirect_request(request, fp, code, msg, headers, _valid_url(newurl))


def _download(url):
    opener = build_opener(_SafeRedirect())
    with opener.open(Request(_valid_url(url), headers={'User-Agent': 'Adelia-VK-Homework/1.0'}), timeout=60) as response:
        if int(response.headers.get('Content-Length') or 0) > MAX_FILE_BYTES:
            raise ValueError('file_too_large')
        data = response.read(MAX_FILE_BYTES + 1)
    if not data or len(data) > MAX_FILE_BYTES:
        raise ValueError('file_empty_or_too_large')
    return data


def _stage(attachments):
    if len(attachments or []) > MAX_FILES:
        raise ValueError('too_many_files')
    staged = []
    total = 0
    for raw in attachments or []:
        item = attachment_bridge.vk_attachment_descriptor(raw)
        if not item or not item.get('url'):
            raise ValueError('unsupported_file')
        name = os.path.basename(str(item.get('filename') or 'document')).replace('\x00', '').strip()[:150]
        suffix = os.path.splitext(name)[1].lower()
        if suffix not in ALLOWED_SUFFIXES:
            raise ValueError('unsupported_file_type')
        content = _download(item['url'])
        total += len(content)
        if total > MAX_TOTAL_BYTES:
            raise ValueError('files_too_large_total')
        if suffix == '.pdf' and not content.startswith(b'%PDF-'):
            raise ValueError('invalid_pdf')
        staged.append({**item, 'filename': name, 'content': content,
                       'content_type': mimetypes.guess_type(name)[0] or item.get('content_type') or 'application/octet-stream'})
    return staged


def _create(user_id, description):
    user = database.get_user(int(user_id))
    if not user:
        raise ValueError('student_not_found')
    programs = teacher_service.student_programs(int(user_id))
    program = programs[0] if programs else None
    title = 'Дополнительное домашнее задание'
    return database.create_homework(
        user_id=int(user_id),
        study_goal=str(program['study_goal'] if program else user['study_goal'] or 'SCHOOL'),
        subject=str(program['subject'] if program else user['main_subject'] or 'PHYSICS'),
        description=description, title=title,
        program_id=int(program['id']) if program else None,
        homework_type='EXTRA',
    )


def _cancel_failed(homework_id):
    conn = database.connect()
    try:
        conn.execute('DELETE FROM homework_attachments WHERE homework_id=?', (int(homework_id),))
        conn.execute("UPDATE homework SET status='CANCELLED' WHERE id=?", (int(homework_id),))
        conn.commit()
    finally:
        conn.close()


def handle_teacher_assignment(app, peer_id, teacher_vk_id, user_id, text, attachments):
    """Return True after responding; caller keeps the pending state on failure."""
    try:
        staged = _stage(attachments)
        description = str(text or '').strip() or ('📎 ' + ', '.join(item['filename'] for item in staged))
        if not description:
            raise ValueError('empty_homework')
        homework_attachments.initialize()
        homework_id = _create(int(user_id), description)
        try:
            for item in staged:
                homework_attachments.save_reference(
                    int(homework_id), kind=item['kind'], filename=item['filename'],
                    mime_type=item['content_type'], vk_attachment_key=item.get('vk_key'),
                    vk_url=item['url'], source_channel='VK', content=item['content'],
                )
        except Exception:
            try:
                _cancel_failed(homework_id)
            except Exception as cleanup_error:
                print('VK HOMEWORK CANCEL ERROR:', type(cleanup_error).__name__, flush=True)
            raise
    except (ValueError, OSError, RuntimeError) as exc:
        app.send(peer_id, '❌ Файл не сохранён: ' + str(exc) + '. Пришлите ДЗ ещё раз или выберите другой файл.', True, 'teacher')
        return True, False
    except Exception as exc:
        print('VK HOMEWORK SAVE ERROR:', type(exc).__name__, flush=True)
        app.send(peer_id, '❌ Не удалось сохранить ДЗ. Попробуйте ещё раз; задание ученику не отправлено.', True, 'teacher')
        return True, False

    app._PENDING.pop(int(teacher_vk_id), None)
    caption = f'📝 ДЗ #{int(homework_id)}\n\n{description}'
    if staged:
        try:
            sent = homework_attachments.resend_to_student(int(homework_id), caption)
        except Exception as exc:
            print('VK HOMEWORK DELIVERY ERROR:', type(exc).__name__, flush=True)
            sent = {'count': len(staged), 'telegram': 0, 'vk': 0}
        summary = f"Файлов сохранено: {sent['count']}. Telegram: {sent['telegram']} · VK: {sent['vk']}."
    else:
        delivered = channel_delivery.send_student(int(user_id), caption)
        summary = f"Telegram: {'да' if delivered['telegram'] else 'нет'} · VK: {'да' if delivered['vk'] else 'нет'}."
    app.send(peer_id, f'✅ ДЗ #{int(homework_id)} сохранено. {summary}\nУченик сможет снова запросить файл в разделе ДЗ.', True, 'teacher')
    return True, True
