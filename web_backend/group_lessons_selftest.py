"""Consolidated non-destructive source/schema checks for Group Lessons.

Run against a disposable DB/worktree during release verification. This file
never selects production by itself.
"""
from __future__ import annotations

import inspect

from web_backend import group_lessons, group_finance, group_runtime_v2, group_trials_and_coaching, group_portal, payment_hub


def main():
    checks=[]
    def ok(name,cond):
        checks.append((name,bool(cond)))
        print(('OK ' if cond else 'FAIL ')+name)

    # Core group lifecycle.
    for name in ('create_group','request_join','approve_join','propose_additional_slot','vote_schedule','apply_proposal','generate_lesson','complete_lesson'):
        ok('group '+name, callable(getattr(group_lessons,name,None)))

    # Finance must be group-isolated and per lesson.
    for name in ('effective_price','set_personal_price','upsert_package_option','create_single_payment','create_package_payment','financial_status_for_lesson'):
        ok('finance '+name, callable(getattr(group_finance,name,None)))
    ok('per-student subscription reserve', callable(getattr(group_runtime_v2,'reserve_subscription_for_student',None)))
    ok('per-student subscription refund', callable(getattr(group_runtime_v2,'refund_subscription_for_student',None)))

    # Pause/homework bridge.
    for name in ('pause_membership','cancel_pause','refresh_pause_states','materialize_group_homework','unified_homework_for_student','teacher_group_homework_queue','reminder_targets_for_homework'):
        ok('runtime '+name, callable(getattr(group_runtime_v2,name,None)))

    # Trials and lag recommendations.
    for name in ('request_group_trial','approve_group_trial','finish_group_trial','record_risk_snapshot','maybe_recommend_individual','review_recommendation'):
        ok('trial/coaching '+name, callable(getattr(group_trials_and_coaching,name,None)))

    # Portal/open events/chat/schedule.
    for name in ('teacher_group_cabinet','student_group_summary','post_group_message','group_chat','create_open_event','open_events_for_student','register_open_event','decide_open_event_participant','start_open_event','open_event_access','save_open_event_result','teacher_schedule_cards'):
        ok('portal '+name, callable(getattr(group_portal,name,None)))

    # Payment hub must expose nearest payment before packages to every client.
    ok('payment hub student', callable(getattr(payment_hub,'student_hub',None)))
    ok('payment hub parent', callable(getattr(payment_hub,'parent_hub',None)))
    src=inspect.getsource(payment_hub.student_hub)
    ok('payment hub nearest action', 'PAY_NEAREST' in src and 'BUY_PACKAGE' in src)

    failed=[n for n,v in checks if not v]
    print(f'GROUP_LESSONS_SELFTEST {len(checks)-len(failed)}/{len(checks)}')
    if failed:
        raise SystemExit('FAILED: '+', '.join(failed))
    print('GROUP_LESSONS_SOURCE_OK')

if __name__=='__main__':
    main()
