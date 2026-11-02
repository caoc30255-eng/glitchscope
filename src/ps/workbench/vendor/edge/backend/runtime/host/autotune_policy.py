"""Pure finite-feedback screening; no learning, hardware IO, retries or new quota."""
from scan_plan import make_schedule

def decide(history,operator_stop=False):
    n=len(history);schedule=make_schedule();ids=set()
    if n>12:raise ValueError('Policy limit exceeded')
    for rid,r in enumerate(history,1):
        if r['record_id']!=rid or r['identity_hex'] in ids:raise ValueError('Policy history order/identity')
        ids.add(r['identity_hex'])
        if not r['strict_retirement_verified'] or r.get('source_review')!='PENDING_SOURCE_REVIEW':raise ValueError('Only rechecked retired feedback')
        if type(r['labels']['B_frame_correct']) is not bool:raise ValueError('Missing feedback is not failure')
        entry=None if rid==1 else schedule['items'][rid-2]
        if (r['point_id'],r['repeat'])!=(None if entry is None else entry['point_id'],None if entry is None else entry['repeat']):raise ValueError('Policy stage differs')
    def score(stage):return sum(r['labels']['B_frame_correct'] for r in history if r['point_id']==stage)
    ref=score('reference_d3');candidate=score('candidate_d4');validation=score('validation_d4')
    out=dict(schema='FINITE_B_DECISION_V0_1',after_record_id=n,
        after_identity_hex=history[-1]['identity_hex'] if history else None,
        action='CONTINUE_PREDECLARED_NEXT',next_request=None,reason='',selected_B=None,
        reference_successes=ref,candidate_successes=candidate,validation_successes=validation,
        threshold_successes=2,records_per_stage=3,policy_kind='DETERMINISTIC_FEEDBACK_RULE',
        AI_training_run=False,reliability_certified=False)
    def stop(reason,selected=None):out.update(action='STOP',reason=reason,selected_B=selected);return out
    if operator_stop:return stop('OPERATOR_STOP_CANCEL_UNSTARTED')
    if n>=6 and ref>=2:
        if n!=6:raise ValueError('Candidate executed after reference already sufficient')
        return stop('REFERENCE_SUFFICIENT_NO_TUNE_NEEDED',dict(d=3,s=-1))
    if n>=9 and (candidate<2 or candidate<=ref):
        if n!=9:raise ValueError('Validation executed after failed candidate screen')
        return stop('CANDIDATE_NOT_PROVISIONALLY_BETTER')
    if n==12:
        return stop('D4_NEW_RECORD_VALIDATION_PASSED' if validation>=2 else 'D4_NEW_RECORD_VALIDATION_FAILED',dict(d=4,s=-1) if validation>=2 else None)
    if n<3:out['reason']='BOOTSTRAP_CONFIG_AND_TWO_CONTROLS'
    elif n<6:out['reason']='EVALUATE_D3_REFERENCE'
    elif n<9:out['reason']='D3_BELOW_THRESHOLD_TEST_D4'
    else:out['reason']='D4_PROVISIONALLY_BETTER_VALIDATE_NEW_RECORDS'
    out['next_request']=dict(client_request_id='CONFIG',receiver_B=dict(d=3,s=-1),fault=None) if n==0 else dict(
        client_request_id=schedule['items'][n-1]['client_request_id'],receiver_B=schedule['items'][n-1]['receiver_B'],fault=schedule['items'][n-1]['profile'])
    return out
