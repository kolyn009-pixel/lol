"""Topic progress shared by the student cabinet and the parent portal."""
from __future__ import annotations

_MASTERED_SQL = "(p.status IN ('MASTERED','DONE','COMPLETED') OR COALESCE(p.mastery,0)>=80)"
_STARTED_SQL = "(p.status<>'NOT_STARTED' OR COALESCE(p.mastery,0)>0)"


def topic_stats(conn, uid):
    """Aggregate counters over student_topic_progress (same rules as the parent portal)."""
    row = conn.execute(
        "SELECT COUNT(*) total,SUM(CASE WHEN %s THEN 1 ELSE 0 END) started,"
        "SUM(CASE WHEN %s THEN 1 ELSE 0 END) mastered,AVG(COALESCE(p.mastery,0)) avg_mastery "
        "FROM student_topic_progress p WHERE p.user_id=?" % (_STARTED_SQL, _MASTERED_SQL), (uid,)).fetchone()
    return {'total': int(row['total'] or 0), 'started': int(row['started'] or 0),
            'mastered': int(row['mastered'] or 0), 'avg_mastery': round(float(row['avg_mastery'] or 0))}


def progress(conn, uid, limit=20):
    summary = {'total': 0, 'started': 0, 'mastered': 0, 'avg_mastery': 0}
    topics = []
    try:
        summary = topic_stats(conn, uid)
        rows = conn.execute(
            "SELECT p.topic_id,t.topic title,t.section,COALESCE(p.mastery,0) mastery,p.updated_at,"
            "CASE WHEN %s THEN 2 WHEN %s THEN 1 ELSE 0 END rank "
            "FROM student_topic_progress p LEFT JOIN learning_topics t ON t.id=p.topic_id "
            "WHERE p.user_id=? ORDER BY CASE WHEN %s THEN 1 WHEN %s THEN 0 ELSE 2 END,p.updated_at DESC,p.topic_id "
            "LIMIT ?" % (_MASTERED_SQL, _STARTED_SQL, _MASTERED_SQL, _STARTED_SQL), (uid, int(limit))).fetchall()
        for r in rows:
            topics.append({'topic_id': r['topic_id'], 'title': r['title'] or '', 'section': r['section'] or '',
                           'mastery': max(0, min(100, int(r['mastery'] or 0))),
                           'status': ('new', 'started', 'mastered')[r['rank']], 'updated_at': r['updated_at']})
    except Exception:
        pass
    return {'summary': summary, 'topics': topics}
