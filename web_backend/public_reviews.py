"""Public review storage for the tutor landing page."""

from database import connect, now_iso


def ensure_public_reviews_table():
    conn=connect()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS public_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            author TEXT,
            text TEXT NOT NULL,
            source TEXT DEFAULT 'Профи.ру',
            source_url TEXT,
            rating INTEGER DEFAULT 5,
            active INTEGER DEFAULT 1,
            sort_order INTEGER DEFAULT 100,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit();conn.close()


def list_public_reviews(limit=12):
    ensure_public_reviews_table()
    conn=connect()
    rows=conn.execute("""
        SELECT author,text,source,source_url,rating
        FROM public_reviews
        WHERE active=1
        ORDER BY sort_order,id DESC
        LIMIT ?
    """,(int(limit),)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_public_review(author,text,source='Профи.ру',source_url=None,rating=5,sort_order=100):
    ensure_public_reviews_table()
    conn=connect()
    cur=conn.execute("""
        INSERT INTO public_reviews(author,text,source,source_url,rating,active,sort_order,created_at)
        VALUES(?,?,?,?,?,1,?,?)
    """,(author,text,source,source_url,int(rating),int(sort_order),now_iso()))
    conn.commit();rid=cur.lastrowid;conn.close();return int(rid)
