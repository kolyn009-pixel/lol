"""Post-trial decision lifecycle for temporary public trial users."""
from __future__ import annotations

from datetime import datetime,timedelta

import database
from core import event_center
from web_backend import public_trial

DECISIONS={'CONTINUE','THINKING','STOP'}
THINKING_TTL_DAYS=3


def _now():return datetime.now()
def _iso(v=None):return (v or _now()).isoformat(timespec='seconds')

def ensure_schema():
    public_trial.ensure_schema();c=database.connect();cols={r['name'] for r in c.execute('PRAGMA table_info(public_trial_requests)').fetchall()}
    for name,kind in {
        'followup_decision':'TEXT',
        'followup_decided_at':'TEXT',
        'followup_note':'TEXT',
        'followup_remind_at':'TEXT',
    }.items():
        if name not in cols:c.execute(f'ALTER TABLE public_trial_requests ADD COLUMN {name} {kind}')
    c.execute('CREATE INDEX IF NOT EXISTS idx_public_trial_followup ON public_trial_requests(followup_decision,followup_remind_at)');c.commit();c.close()

def status(request_id):
    ensure_schema();row=public_trial.get(int(request_id))
    if not row:raise ValueError('request_not_found')
    return {
        'request_id':int(row['id']),
        'request_status':row['status'],
        'decision':row.get('followup_decision'),
        'decided_at':row.get('followup_decided_at'),
        'remind_at':row.get('followup_remind_at'),
        'continuation_ready':bool(row.get('status')=='TRIAL_COMPLETED' and row.get('followup_decision')=='CONTINUE' and row.get('continuation_code_hash') and row.get('continuation_code_expires_at') and not row.get('continuation_code_used_at')),
    }

def decide(request_id,decision,note=None):
    ensure_schema();row=public_trial.get(int(request_id))
    if not row:raise ValueError('request_not_found')
    if row['status'] not in {'TRIAL_COMPLETED','CONVERTED'}:raise ValueError('trial_not_completed')
    choice=str(decision or '').strip().upper()
    if choice not in DECISIONS:raise ValueError('invalid_decision')
    if row['status']=='CONVERTED' and choice!='CONTINUE':raise ValueError('trial_already_converted')
    now=_now();remind=_iso(now+timedelta(days=THINKING_TTL_DAYS)) if choice=='THINKING' else None
    request_status='CLOSED' if choice=='STOP' else row['status']
    c=database.connect();c.execute('UPDATE public_trial_requests SET status=?,followup_decision=?,followup_decided_at=?,followup_note=?,followup_remind_at=?,updated_at=? WHERE id=?',(request_status,choice,_iso(now),str(note or '').strip()[:500] or None,remind,_iso(now),int(request_id)));c.commit();c.close()
    try:
        labels={'CONTINUE':'хочет продолжить','THINKING':'хочет подумать','STOP':'не планирует продолжать'}
        event_center.push('PUBLIC_TRIAL_DECISION',f"После пробного: {row.get('name') or 'Без имени'}",labels[choice],'ACTION','public_trial',int(request_id),f'public_trial_decision:{int(request_id)}:{choice}')
    except Exception:pass
    return status(request_id)

def require_continuation(request_id):
    """Allow permanent-account continuation only after an explicit CONTINUE decision."""
    state=status(request_id)
    if state['request_status']=='CONVERTED':raise ValueError('trial_already_converted')
    if state['request_status']!='TRIAL_COMPLETED':raise ValueError('trial_not_completed')
    if state['decision']!='CONTINUE':raise PermissionError('trial_continue_required')
    return state

def due_thinking(limit=100):
    ensure_schema();c=database.connect();rows=c.execute("SELECT * FROM public_trial_requests WHERE followup_decision='THINKING' AND followup_remind_at IS NOT NULL AND followup_remind_at<=? AND status='TRIAL_COMPLETED' ORDER BY followup_remind_at ASC LIMIT ?",(_iso(),max(1,min(int(limit),200)))).fetchall();c.close();return [dict(r) for r in rows]

def clear_reminder(request_id):
    ensure_schema();c=database.connect();c.execute('UPDATE public_trial_requests SET followup_remind_at=NULL,updated_at=? WHERE id=?',(_iso(),int(request_id)));c.commit();c.close();return {'status':'ok','request_id':int(request_id)}
