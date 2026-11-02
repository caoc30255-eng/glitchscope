"""Immutable finite grids and independent measured/predicted aggregation."""
import copy
from labutil import *

TARGETS=('B_frame_correct','STM_payload_correct','STM_business_success')
def legal(phase,width):return type(phase) is int and type(width) is int and phase>=5 and width>=1 and phase+width<=45
def make_plan(payload,phases,widths,d=3,s=-1,byte=20,bit=0,repeats=3,budget=None,targets=None):
    require(isinstance(payload,bytes) and 1<=len(payload)<=256,'PAYLOAD_1_TO_256')
    require(type(d) is int and 1<=d<=4 and type(s) is int and -2<=s<=3-d,'RECEIVER_PROFILE_CURRENT_D1_TO_4_S_MINUS2_TO_3_MINUS_D')
    require(type(byte) is int and 20<=byte<20+len(payload) and type(bit) is int and 0<=bit<=7,'PAYLOAD_BIT')
    require(type(repeats) is int and 1<=repeats<=100,'REPETITIONS')
    require(phases and widths and len(set(phases))==len(phases) and len(set(widths))==len(widths),'UNIQUE_AXES')
    require(len(phases)*len(widths)<=4096 and all(type(x) is int and 0<=x<=255 for x in phases+widths),'FINITE_INTEGER_GRID')
    targets=list(targets or ('B_frame_correct','STM_business_success'));require(set(targets)<=set(TARGETS) and targets,'TARGETS')
    cells=[dict(point_id='p%d_w%d'%(p,w),phase=p,width=w,legal=legal(p,w)) for p in sorted(phases) for w in sorted(widths)]
    items=[dict(request_index=i+2,point_id=c['point_id'],phase=c['phase'],width=c['width'],repeat=r)
           for i,(c,r) in enumerate((c,r) for c in cells if c['legal'] for r in range(repeats))]
    require(items,'NO_LEGAL_MEASUREMENT_POINT');required=2+len(items)
    require(type(budget) is int and 2<=budget<=10000,'EXPLICIT_BUDGET_REQUIRED')
    require(required<=budget,'BUDGET_BELOW_DECLARED_GRID; shrink grid/repetitions explicitly')
    p=dict(schema='FINITE_SCAN_PLAN_V0_1',payload_hex=payload.hex(),payload_sha256=sha(payload),phases=sorted(phases),widths=sorted(widths),
        fixed=dict(d=d,s=s,byte=byte,bit=bit,count=1,protocol='TYPE3A'),repeats=repeats,targets=targets,cells=cells,requests=items,
        config_starts=1,control_starts=1,required_starts=required,explicit_limit=budget,
        units=dict(generator_hz=50000000,tick_nominal_ns=20,capture_hz=100000000,sample_nominal_ns=10,nominal_not_measured=True),
        stop_rules=['GRID_COMPLETE','EXPLICIT_STOP_CANCEL_UNSTARTED','UNKNOWN_BLOCKS','BUDGET_EXHAUSTED','EVIDENCE_CONFLICT'],
        hardware_budget_authorized=False,live_execution_authorized=False)
    p['plan_sha256']=digest(p);return p

def validate(plan):
    raw={k:v for k,v in plan.items() if k!='plan_sha256'};require(digest(raw)==plan.get('plan_sha256'),'IMMUTABLE_PLAN_CHANGED')
    rebuilt=make_plan(bytes.fromhex(plan['payload_hex']),plan['phases'],plan['widths'],**{k:plan['fixed'][k] for k in ('d','s','byte','bit')},
        repeats=plan['repeats'],budget=plan['explicit_limit'],targets=plan['targets'])
    require(canonical(rebuilt)==canonical(plan),'PLAN_FIELDS_OR_SCHEDULE_CHANGED');return True

def propose(plan,history):
    validate(plan);require(len(history)<=plan['required_starts'],'HISTORY_LENGTH')
    seen=set()
    for i,h in enumerate(history):
        require(h.get('request_index')==i and h.get('plan_sha256')==plan['plan_sha256'],'FEEDBACK_ORDER_OR_PLAN')
        require(isinstance(h.get('identity_hex'),str),'CANONICAL_HEX_IDENTITY_REQUIRED')
        identity=hex_identity(h['identity_hex']);require(identity not in seen,'IDENTITY_REPLAY');seen.add(identity)
        require(h.get('status') in ('VALID','UNKNOWN'),'FEEDBACK_STATUS')
        for field in ('result_sha256','diagnostic_sha256'):
            value=h.get(field)
            require(value is None or isinstance(value,str) and len(value)==64 and all(x in '0123456789abcdef' for x in value),'FEEDBACK_DIGEST')
        proof=h.get('result_sha256') if h['status']=='VALID' else h.get('diagnostic_sha256')
        require(proof is not None and h.get('origin') in ('SIMULATED_DEVELOPMENT','AUDITED_MEASUREMENT'),'FEEDBACK_PROVENANCE')
        require(h['status']!='UNKNOWN' or i==len(history)-1,'HISTORY_CONTINUES_AFTER_UNKNOWN')
    reason=None
    if len(history)>=plan['required_starts']:reason='GRID_COMPLETE'
    if len(history)>=plan['explicit_limit']:reason='BUDGET_EXHAUSTED'
    if history and history[-1]['status']=='UNKNOWN':reason='UNKNOWN_BLOCKED'
    i=len(history)
    request=None if reason else (dict(kind='CONFIG') if i==0 else dict(kind='CONTROL') if i==1 else dict(kind='ITEM',**copy.deepcopy(plan['requests'][i-2])))
    return dict(schema='SCAN_PROPOSAL_V0_1',plan_sha256=plan['plan_sha256'],after_record_id=i,
        after_identity_hex=history[-1]['identity_hex'] if history else None,
        after_result_sha256=history[-1].get('result_sha256') if history else None,
        after_diagnostic_sha256=history[-1].get('diagnostic_sha256') if history else None,
        after_diagnostic_reference=history[-1].get('diagnostic_reference') if history else None,
        action='STOP' if reason else 'CONTINUE_PREDECLARED',request=request,reason=reason or 'NEXT_PREDECLARED',
        executor_contract='NEW_MAINLINE_BOUNDED_SCAN_EXECUTOR_REQUIRED',hardware_permission=False)

def point_matches(plan,record):
    c=record.get('condition') or {};f=plan['fixed']
    return c.get('block_sha256')==plan['payload_sha256'] and all(c.get(k)==f[src] for k,src in
        [('d','d'),('s','s'),('first_byte','byte'),('bit','bit'),('count','count'),('protocol','protocol')])

def aggregate(plan,records,predictions=None):
    validate(plan);out=copy.deepcopy(plan['cells']);byid={c['point_id']:c for c in out};unmatched=[];seen={};identities=set()
    for c in out:c.update(measurements=[],targets={t:dict(valid=0,success=0,failure=0,unknown=0,fraction=None) for t in TARGETS})
    for r in records:
        if r.get('kind')!='ITEM':continue
        uid=r['uid'];require(uid not in seen or canonical(r)==seen[uid],'RECORD_CONFLICT')
        if uid in seen:continue
        seen[uid]=canonical(r)
        if not point_matches(plan,r):unmatched.append(uid);continue
        c=r['condition'];point=byid.get('p%d_w%d'%(c['phase'],c['width']))
        if not point or not point['legal']:unmatched.append(uid);continue
        require(r.get('origin') in ('SIMULATED_DEVELOPMENT','AUDITED_MEASUREMENT'),'UNVERIFIED_RECORD')
        if r.get('identity_hex') is not None:
            require(isinstance(r['identity_hex'],str),'CANONICAL_HEX_IDENTITY_REQUIRED')
            identity=hex_identity(r['identity_hex']);require(identity not in identities,'MEASUREMENT_IDENTITY_REPLAY');identities.add(identity)
        point['measurements'].append(copy.deepcopy(r))
        for t in TARGETS:
            value=None if r['status']=='UNKNOWN' else r['labels'].get(t)
            require(value is None or type(value) is bool,'LABEL_MUST_BE_BOOLEAN_OR_UNKNOWN')
            stats=point['targets'][t]
            if value is None:stats['unknown']+=1
            else:stats['valid']+=1;stats['success' if value else 'failure']+=1
    for c in out:
        for t,s in c['targets'].items():s['fraction']=s['success']/s['valid'] if s['valid'] else None
        c['status']='ILLEGAL' if not c['legal'] else 'UNKNOWN' if any(s['unknown'] for s in c['targets'].values()) else 'MEASURED' if c['measurements'] else 'UNMEASURED'
        count=len(c['measurements']);bound=all(isinstance(r.get('identity_hex'),str) for r in c['measurements'])
        c['completion']=dict(required_repeats=plan['repeats'],occupied_ITEMs=count,identities_bound=bound,
            missing_repeats=max(0,plan['repeats']-count),excess_repeats=max(0,count-plan['repeats']),
            execution_coverage_complete=c['legal'] and bound and count==plan['repeats'],
            valid_measurements_sufficient=c['legal'] and bound and count==plan['repeats'] and all(c['targets'][t]['valid']==plan['repeats'] and not c['targets'][t]['unknown'] for t in plan['targets']))
    legal_cells=[c for c in out if c['legal']]
    execution_complete=all(c['completion']['execution_coverage_complete'] for c in legal_cells)
    valid_sufficient=all(c['completion']['valid_measurements_sufficient'] for c in legal_cells)
    return dict(plan_sha256=plan['plan_sha256'],fixed=plan['fixed'],cells=out,unmatched_uids=unmatched,
        coverage=dict(legal=sum(c['legal'] for c in out),measured=sum(c['status']=='MEASURED' for c in out),unknown=sum(c['status']=='UNKNOWN' for c in out)),
        predictions=copy.deepcopy(predictions or []),execution_coverage_complete=execution_complete,valid_measurements_sufficient=valid_sufficient,
        completion_scope='DECLARED_GRID_ITEM_REPETITIONS_ONLY; CONFIG/control and new execution authorization are not inferred',
        real_hardware_complete=execution_complete and valid_sufficient and all(all(r['origin']=='AUDITED_MEASUREMENT' for r in c['measurements']) for c in legal_cells),
        note='Finite declared grid only; predicted values never create measured records')

def default_plan(d=3):return make_plan(bytes(range(256)),[5,15,25,35],[1,10,20,30,40],d=d,repeats=3,budget=44)
