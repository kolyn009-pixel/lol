from datetime import date, datetime
import calendar
import database


def bounds(month=None):
    if not month: month=date.today().strftime('%Y-%m')
    y,m=map(int,month.split('-')); last=calendar.monthrange(y,m)[1]
    return month,f'{y:04d}-{m:02d}-01',f'{y:04d}-{m:02d}-{last:02d}'


def build(student_id, month=None):
    month,start,end=bounds(month); conn=database.connect(); u=conn.execute('SELECT * FROM users WHERE id=?',(student_id,)).fetchone()
    lessons=conn.execute("SELECT COUNT(*) c, COALESCE(SUM(CASE WHEN actual_duration_minutes>0 THEN actual_duration_minutes ELSE duration_minutes END),0) mins FROM lessons WHERE user_id=? AND lesson_status='COMPLETED' AND substr(start_time,1,10) BETWEEN ? AND ?",(student_id,start,end)).fetchone()
    hw=conn.execute("SELECT COUNT(*) total, SUM(CASE WHEN status IN ('COMPLETED','REVIEWED','ACCEPTED') THEN 1 ELSE 0 END) done, SUM(CASE WHEN deadline<? AND status IN ('ASSIGNED','REVISION') THEN 1 ELSE 0 END) overdue FROM homework WHERE user_id=? AND substr(assigned_at,1,10) BETWEEN ? AND ?",(end,student_id,start,end)).fetchone()
    conn.close()
    return (f"📊 <b>Отчёт за {month}</b>\n👤 {u['name'] if u else student_id}\n\n"
            f"🎓 Проведено занятий: <b>{lessons['c'] or 0}</b>\n⏱ Учебное время: <b>{lessons['mins'] or 0} мин</b>\n"
            f"📝 ДЗ назначено: <b>{hw['total'] or 0}</b>\n✅ Выполнено/принято: <b>{hw['done'] or 0}</b>\n⚠️ Просрочено на конец периода: <b>{hw['overdue'] or 0}</b>")


def save_draft(student_id,text,month,actor):
    conn=database.connect(); cur=conn.cursor(); cur.execute("INSERT INTO monthly_reports_log(student_id,month,report_text,status,created_by,created_at) VALUES(?,?,?,'DRAFT',?,?)",(student_id,month,text,actor,datetime.now().isoformat(timespec='seconds'))); conn.commit(); rid=cur.lastrowid; conn.close(); return rid
