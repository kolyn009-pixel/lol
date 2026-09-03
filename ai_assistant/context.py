from __future__ import annotations

from datetime import datetime
import database


def find_students(term: str, limit: int = 8):
    term = (term or '').strip()
    if not term:
        return []
    c = database.connect()
    try:
        return c.execute(
            "SELECT id,name,telegram_username FROM users WHERE name LIKE ? OR telegram_username LIKE ? ORDER BY active DESC,name LIMIT ?",
            (f'%{term}%', f'%{term.lstrip("@")}%', limit),
        ).fetchall()
    finally:
        c.close()


def student_facts(uid: int) -> str:
    c = database.connect()
    try:
        u = c.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
        if not u:
            return 'Ученик не найден.'
        lines = [f"Имя: {u['name']}"]
        for field, label in [('grade','Класс'), ('telegram_username','Telegram')]:
            try:
                val = u[field]
                if val: lines.append(f'{label}: {val}')
            except Exception:
                pass
        try:
            bal = c.execute('SELECT balance_minutes FROM student_minute_balances WHERE user_id=?', (uid,)).fetchone()
            if bal: lines.append(f"Баланс минут: {int(bal[0] or 0)}")
        except Exception:
            pass
        try:
            unpaid = c.execute("SELECT COUNT(*),COALESCE(SUM(price),0) FROM lessons WHERE user_id=? AND lesson_status='CONFIRMED' AND payment_status='AWAITING_PAYMENT'", (uid,)).fetchone()
            lines.append(f"Неоплаченных подтверждённых занятий: {int(unpaid[0] or 0)}")
            lines.append(f"Сумма ожидаемой оплаты: {int(unpaid[1] or 0)} ₽")
        except Exception:
            pass
        try:
            nxt = c.execute("SELECT start_time FROM lessons WHERE user_id=? AND datetime(start_time)>=datetime('now') AND lesson_status NOT IN ('CANCELLED','COMPLETED') ORDER BY datetime(start_time) LIMIT 1", (uid,)).fetchone()
            lines.append('Следующее занятие: ' + (str(nxt[0])[:16].replace('T',' ') if nxt else 'не назначено'))
        except Exception:
            pass
        return '\n'.join(lines)
    finally:
        c.close()


def recent_messages(uid: int, limit: int = 8) -> str:
    c = database.connect()
    try:
        try:
            rows = c.execute("SELECT created_at,direction,body FROM crm_student_messages WHERE student_id=? ORDER BY datetime(created_at) DESC LIMIT ?", (uid, limit)).fetchall()
        except Exception:
            return ''
        out=[]
        for r in reversed(rows):
            who='Преподаватель' if r['direction']=='OUT' else 'Ученик'
            out.append(f"{str(r['created_at'])[:16]} · {who}: {str(r['body'])[:500]}")
        return '\n'.join(out)
    finally:
        c.close()
