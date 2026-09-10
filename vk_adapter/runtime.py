"""VK runtime entrypoint with payment-receipt interception.

This wrapper keeps the established vk_adapter.app message flow intact and only
intercepts supported attachments when the linked student has a WAITING payment.
Everything else is delegated to the original handler unchanged.
"""
from __future__ import annotations

from . import app
from . import payment_receipts

_ORIGINAL_HANDLE=app.handle_message


def _waiting_payment_exists(user_id:int)->bool:
    try:return payment_receipts._waiting_payment(int(user_id)) is not None
    except Exception:return False


def handle_message(message):
    try:
        from_id=int((message or {}).get('from_id') or 0)
        attachments=(message or {}).get('attachments') or []
        command=app._extract_command(message or {})
        if from_id>0 and attachments and not command and not app.teacher_service.is_teacher(from_id):
            user=app.service.linked_user(from_id)
            if user and _waiting_payment_exists(int(user['id'])):
                result=payment_receipts.submit(int(user['id']),attachments)
                status=result.get('status')
                if status=='ok':
                    app.send(int((message or {}).get('peer_id') or from_id),f"✅ Чек получен. Платёж #{result['payment_id']} отправлен на проверку.\n\nПосле подтверждения Аделия обновит баланс автоматически.",True)
                    return
                if status=='duplicate':
                    app.send(int((message or {}).get('peer_id') or from_id),"Этот чек уже был получен 💜 Платёж уже находится на проверке.",True)
                    return
    except Exception as exc:
        print('VK RECEIPT WRAPPER ERROR:',repr(exc),flush=True)
    return _ORIGINAL_HANDLE(message)


def run_forever():
    app.handle_message=handle_message
    return app.run_forever()


if __name__=='__main__':
    run_forever()
