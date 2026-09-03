from datetime import datetime,date,timedelta
import database
from .balance_forecast import forecast
from .messaging import inbox


def today_dashboard():
    d=date.today().isoformat(); conn=database.connect(); lessons=conn.execute("SELECT l.*,u.name FROM lessons l JOIN users u ON u.id=l.user_id WHERE substr(l.start_time,1,10)=? ORDER BY datetime(l.start_time)",(d,)).fetchall(); conn.close()
    return lessons


def attention_items():
    items=[]
    for row in inbox('OPEN',100): items.append({'priority':'ACTION','title':row['subject'] or 'Организационный вопрос','details':row['body']})
    conn=database.connect(); students=conn.execute('SELECT id,name FROM users').fetchall(); conn.close()
    for s in students:
        try:
            f=forecast(s['id'])
            if f['remaining']<=120: items.append({'priority':'ATTENTION','title':f"Низкий баланс: {s['name']}",'details':f"Осталось времени: {f['remaining']} мин"})
        except Exception: pass
    return items
