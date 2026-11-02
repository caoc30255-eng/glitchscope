"""Immutable12 maximum; grouped evaluation and fresh-record candidate validation."""
import copy,hashlib,json
TARGETS=('B_frame_correct','STM_payload_correct','STM_business_success')
def make_schedule():
    items=[dict(client_request_id='baseline_d%d'%d,point_id=None,repeat=None,receiver_B=dict(d=d,s=-1),profile=None) for d in (3,4)]
    for stage,d in (('reference_d3',3),('candidate_d4',4),('validation_d4',4)):
        for repeat in (1,2,3):
            items.append(dict(client_request_id=stage+'_r%d'%repeat,point_id=stage,repeat=repeat,
                receiver_B=dict(d=d,s=-1),profile=dict(byte=20,bit=0,phase=15,width=20)))
    return dict(schema='BOUNDED_AUTOTUNE_SCHEDULE_V0_1',items=items,phase=15,width=20,byte=20,bit=0,s=-1,
        repeats=3,threshold_successes=2,policy='FINITE_B_FEEDBACK_RULE_V0_1',
        source_sha256=hashlib.sha256(bytes(range(256))*11).hexdigest(),max_records_including_CONFIG=12,
        automatic_retry=False,training_authorized=False,production_billing_finalized=False)
def validate_schedule(value):
    if json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)!=json.dumps(make_schedule(),sort_keys=True,separators=(',',':')):
        raise ValueError('EXACT12_FEEDBACK_PLAN_REQUIRED')
    return True
def aggregate(state):
    schedule=make_schedule();results=state.get('results',[]);ids=set();cells=[]
    if len(results)>12:raise ValueError('LIMIT12')
    for rid,r in enumerate(results,1):
        entry=None if rid==1 else schedule['items'][rid-2];identity=r['identity_hex']
        if r['record_id']!=rid or len(identity)!=64 or any(c not in '0123456789abcdef' for c in identity) or identity in ids:raise ValueError('ORDER_OR_IDENTITY')
        ids.add(identity)
        if (r['point_id'],r['repeat'])!=(None if entry is None else entry['point_id'],None if entry is None else entry['repeat']):raise ValueError('WRONG_STAGE_SLOT')
        expected=dict(d=3,s=-1) if entry is None else entry['receiver_B']
        if {k:r['actual_receiver_B'][k] for k in ('d','s')}!=expected or r['actual_receiver_B']['RX_profile_verified'] is not True:raise ValueError('ACTUAL_PROFILE')
    for stage,d in (('reference_d3',3),('candidate_d4',4),('validation_d4',4)):
        rows=[copy.deepcopy(r) for r in results if r['point_id']==stage];rounds=[r['repeat'] for r in rows]
        if rounds!=list(range(1,len(rows)+1)) or len(rows)>3:raise ValueError('STAGE_REPEAT')
        unknown=state.get('unresolved_record');u=int(bool(unknown and unknown.get('point_id')==stage));targets={}
        for t in TARGETS:
            values=[r['labels'][t] for r in rows]
            if any(type(v) is not bool for v in values):raise ValueError('UNKNOWN_NOT_BOOLEAN')
            targets[t]=dict(success=sum(values),failure=len(values)-sum(values),valid=len(values),unknown=u,fraction=sum(values)/len(values) if values else None)
        terminal=state['state'] not in ('READY','RUNNING','STOPPING')
        status='UNKNOWN' if u else 'COMPLETE' if len(rows)==3 else 'PARTIAL' if rows else 'CANCELLED_UNSTARTED' if terminal else 'UNMEASURED'
        cells.append(dict(point_id=stage,phase=15,width=20,d=d,s=-1,legal=True,measurements=rows,status=status,
            targets=targets,required_repeats=3,missing_repeats=max(0,3-len(rows)-u)))
    return dict(schema='BOUNDED_AUTOTUNE_RESULTS_V0_1',session=state['session'],state=state['state'],
        origin='LIVE_RAW_RECHECKED_PENDING_REVIEW',cells=cells,legal_cells=3,measured_cells=sum(bool(c['measurements']) for c in cells),
        attempts=state['attempts'],completed_records=state['completed_records'],max_records=12,
        phase=15,width=20,byte=20,bit=0,s=-1,summary=state.get('summary'),
        training_authorized=False,production_billing_finalized=False,real_hardware_test_accepted=False)
