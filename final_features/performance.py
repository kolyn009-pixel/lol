from __future__ import annotations
from learning import exam_results

def projection(user_id,target=None):
    rows=list(exam_results.history(user_id))
    scores=[float(r['test_score']) for r in rows if r['test_score'] is not None]
    if not scores:return {'current':None,'change':None,'forecast_low':None,'forecast_high':None,'target':target}
    current=scores[-1]; change=(scores[-1]-scores[0]) if len(scores)>1 else 0
    recent=scores[-4:]
    avg_gain=sum(recent[i]-recent[i-1] for i in range(1,len(recent)))/max(1,len(recent)-1) if len(recent)>1 else 0
    # Deliberately conservative, transparent short-horizon projection, not an ML claim.
    center=max(0,min(100,current+avg_gain*2)); low=max(0,round(center-4)); high=min(100,round(center+4))
    return {'current':round(current,1),'change':round(change,1),'forecast_low':low,'forecast_high':high,'target':target,'tests':len(scores)}
