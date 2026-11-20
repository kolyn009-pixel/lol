"""POST /api/teacher/lesson/payment: «ждём оплату» или «оплачено» по одному занятию."""
from __future__ import annotations
import database
from web_backend import teacher_lesson_actions, push_events

ERRORS = {
    'invalid_lessons_count': 'Количество занятий — целое число от 1 до 100',
    'amount_required': 'Укажите сумму',
    'invalid_amount': 'Сумма должна быть целым положительным числом',
    'amount_must_divide_by_lessons': 'Сумма должна делиться на количество занятий без остатка',
    'positive_payment_required': 'Сумма должна быть больше нуля',
    'lesson_not_found': 'Занятие не найдено',
    'lesson_not_payable': 'Отменённое занятие нельзя отметить оплаченным',
    'lesson_not_awaiting_payment': 'Занятие не ожидает оплаты',
    'payment_not_awaiting': 'Занятие не ожидает оплаты',
    'invalid_action': 'Неизвестное действие',
    'invalid_lesson_id': 'Не указано занятие',
}
INVOICE_CONFLICT = 'По этому занятию уже выставлен счёт — подтвердите его в разделе «Оплаты»'


class PaymentError(Exception):
    def __init__(self, code, error, message=None):
        super().__init__(error)
        self.code, self.error, self.message = code, error, message or ERRORS.get(error, error)

    def body(self):
        return {'error': self.error, 'message': self.message}


def _int(value, error):
    if isinstance(value, bool) or value is None:
        raise PaymentError(400, error)
    try:
        if isinstance(value, float) and not value.is_integer():
            raise ValueError
        return int(str(value).strip()) if not isinstance(value, (int, float)) else int(value)
    except (TypeError, ValueError):
        raise PaymentError(400, error)


def lessons_count(value):
    count = 1 if value in (None, '') else _int(value, 'invalid_lessons_count')
    if not 1 <= count <= 100:
        raise PaymentError(400, 'invalid_lessons_count')
    return count


def balance_lessons(user_id):
    conn = database.connect()
    try:
        row = conn.execute("SELECT COALESCE(SUM(MAX(0,lessons_total-lessons_used)),0) FROM lesson_packages WHERE user_id=? AND status='ACTIVE'", (int(user_id),)).fetchone()
        return int(row[0] or 0)
    finally:
        conn.close()


def _notify_paid(user_id, payment_id, balance):
    try:
        push_events.student_and_parents(
            int(user_id), 'Оплата получена', f'Оплата получена 💜 На балансе занятий: {int(balance)}.',
            '/app/', '/app/parent/', f'pay-ok-{int(payment_id)}',
            {'type': 'payment_confirmed', 'payment_id': int(payment_id)}, mirror_messengers=True)
    except Exception as exc:
        print('[web-api] lesson payment notify error:', type(exc).__name__, flush=True)


def mark_paid(lesson_id, amount, actor_id, count, source='WEB'):
    lesson = database.get_lesson(int(lesson_id))
    if not lesson:
        raise PaymentError(404, 'lesson_not_found')
    already = lesson['payment_status'] == 'PAID' and bool(lesson['payment_id']) and bool(lesson['package_id'])
    if already:
        amount = None
    elif amount in (None, ''):
        amount = None
        if not int(lesson['price'] or 0):
            raise PaymentError(400, 'amount_required')
    else:
        amount = _int(amount, 'invalid_amount')
        if amount <= 0:
            raise PaymentError(400, 'invalid_amount')
        if amount % count:
            raise PaymentError(400, 'amount_must_divide_by_lessons')
    try:
        payment_id, package_id = database.confirm_manual_lesson_payment(int(lesson_id), amount, actor_id=actor_id, source=source, lessons_count=count)
    except ValueError as exc:
        if str(exc) == 'linked_invoice_requires_review':
            raise PaymentError(409, 'linked_invoice_requires_review', INVOICE_CONFLICT)
        raise PaymentError(409 if str(exc) in {'lesson_not_payable', 'lesson_not_awaiting_payment'} else 400, str(exc))
    conn = database.connect()
    try:
        pay = conn.execute('SELECT lessons_count,total_amount FROM payments WHERE id=?', (int(payment_id),)).fetchone()
    finally:
        conn.close()
    balance = balance_lessons(lesson['user_id'])
    if not already:
        _notify_paid(lesson['user_id'], payment_id, balance)
    return {'status': 'ok', 'action': 'paid', 'lesson_id': int(lesson_id), 'payment_id': int(payment_id), 'package_id': int(package_id),
            'lessons_count': int(pay['lessons_count'] or count) if pay else count, 'amount': int(pay['total_amount'] or 0) if pay else amount,
            'balance_lessons_after': balance, 'already_paid': already}


def handle(body, actor_id):
    """Возвращает (http_code, json)."""
    try:
        action = str(body.get('action') or '').strip().lower()
        if action not in {'await', 'paid'}:
            raise PaymentError(400, 'invalid_action')
        lesson_id = _int(body.get('lesson_id'), 'invalid_lesson_id')
        if action == 'await':
            try:
                result = teacher_lesson_actions.confirm_payment_wait(lesson_id, actor_id, notify=False)
            except ValueError as exc:
                raise PaymentError(404 if str(exc) == 'lesson_not_found' else 409, str(exc))
            return 200, {'status': 'ok', 'action': 'await', 'lesson_id': lesson_id, 'already_confirmed': bool(result.get('already_confirmed'))}
        return 200, mark_paid(lesson_id, body.get('amount'), actor_id, lessons_count(body.get('lessons_count')))
    except PaymentError as exc:
        return exc.code, exc.body()
