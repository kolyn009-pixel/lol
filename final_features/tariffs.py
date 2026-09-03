from __future__ import annotations
from datetime import datetime
import database
from core import minute_balance
from . import schema

DEFAULT_DISCOUNTS={2:0,4:5,6:10,10:15}

def _now(): return datetime.now().isoformat(timespec='seconds')

def ensure_defaults():
    schema.initialize(); c=database.connect(); now=_now()
    try:
        goals=['EGE','OGE','SCHOOL','OLYMPIAD']
        for goal in goals:
            base=90 if goal in ('EGE','OGE','OLYMPIAD') else 60
            for n,p in DEFAULT_DISCOUNTS.items():
                c.execute('''INSERT OR IGNORE INTO tariff_discount_rules(study_goal,subject,base_duration_minutes,equivalent_lessons,discount_percent,active,created_at,updated_at)
                             VALUES(?,'',?,?,?,1,?,?)''',(goal,base,n,p,now,now))
        c.commit()
    finally:c.close()

def discount_for(program_id, minutes):
    ensure_defaults(); p=database.get_student_program(int(program_id)); base=minute_balance.get_program_duration(program_id)
    eq=max(1,int(minutes)//max(base,1)); c=database.connect()
    try:
        r=c.execute('''SELECT discount_percent FROM tariff_discount_rules WHERE active=1 AND study_goal=?
                     AND (subject=? OR subject='' OR subject IS NULL) AND base_duration_minutes=? AND equivalent_lessons<=?
                     ORDER BY (subject IS NOT NULL) DESC,equivalent_lessons DESC LIMIT 1''',(p['study_goal'],p['subject'],base,eq)).fetchone()
        return int(r['discount_percent'] or 0) if r else 0
    finally:c.close()

def package_quote(program_id, equivalent_lessons):
    p=database.get_student_program(int(program_id)); base=minute_balance.get_program_duration(program_id); rate=minute_balance.effective_hourly_rate(program_id)
    minutes=base*int(equivalent_lessons); subtotal=round(rate*minutes/60); disc=discount_for(program_id,minutes); total=round(subtotal*(100-disc)/100)
    return {'minutes':minutes,'equivalent_lessons':int(equivalent_lessons),'base_duration':base,'hourly_rate':rate,'subtotal':subtotal,'discount_percent':disc,'total':total}

def list_rules():
    ensure_defaults(); c=database.connect()
    try:return c.execute('SELECT * FROM tariff_discount_rules WHERE active=1 ORDER BY study_goal,base_duration_minutes,equivalent_lessons').fetchall()
    finally:c.close()
