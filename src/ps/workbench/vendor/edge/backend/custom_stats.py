"""Separate full-condition statistics, preserving per-target and source identity."""
import copy
from custom_plan import validate_plan,require,TARGETS
from learning_domain import digest

def aggregate(plan,records,session):
    validate_plan(plan);require(type(records) is list and len(records)<=plan['max_records'],'RECORD_BUDGET')
    lookup={c['condition_id']:c for c in plan['conditions']};groups={k:[] for k in lookup};uids=set();identities=set();ids=set();epochs=set()
    for ordinal,r in enumerate(records,1):
        require(r['record_id']==ordinal and r['kind']==('CONFIG' if ordinal==1 else 'CONTROL' if ordinal==2 else 'ITEM'),'COMPLETE_ORDERED_ATTEMPT_PREFIX_REQUIRED')
        require(r['status']!='UNKNOWN' or ordinal==len(records),'UNKNOWN_MUST_BLOCK_FOLLOWING_RECORDS')
        require(r['session']==session,'CROSS_SESSION');require(type(r['record_id']) is int and r['record_id']>0 and r['record_id'] not in ids,'RECORD_REPLAY')
        require(type(r['epoch']) is int,'EPOCH');epochs.add(r['epoch']);require(len(epochs)==1,'CROSS_EPOCH')
        require(type(r['uid']) is str and len(r['uid'])==64 and r['uid'] not in uids,'UID_REPLAY')
        require(r['status'] in ('VALID','UNKNOWN') and r['evidence'],'UNCHECKED_RESULT')
        if r['identity_hex'] is not None:
            require(type(r['identity_hex']) is str and len(r['identity_hex'])==64 and r['identity_hex'] not in identities,'IDENTITY_REPLAY')
            identities.add(r['identity_hex'])
        else:require(r['status']=='UNKNOWN','MISSING_VALID_IDENTITY')
        ids.add(r['record_id']);uids.add(r['uid'])
        if r['status']=='VALID':require(r['strict_retired'] is True and r['actual_READY_saved'] is True,'STRICT_RETIREMENT_READY')
        if r['status']=='UNKNOWN':require(all(r['labels'][t] is None for t in TARGETS),'UNKNOWN_NOT_FAILURE')
        if r['kind']!='ITEM':
            expected=plan['preparation'][ordinal-1]['receiver_B']
            require(r['requested_receiver_B']==expected,'PREPARATION_REQUEST_PROFILE')
            if r['status']=='VALID':require(all(type(r['actual_receiver_B'][k]) is int and r['actual_receiver_B'][k]==expected[k] for k in ('d','s')) and r['actual_receiver_B']['RX_profile_verified'] is True,'PREPARATION_READBACK_PROFILE')
            continue
        c=lookup.get(r['condition_id']);require(c is not None and r['condition_sha256']==c['condition_sha256'],'UNKNOWN_FULL_CONDITION')
        require(r['requested_receiver_B']==c['receiver_B'] and r['fault']==c['fault'] and r['payload_sha256']==c['payload_sha256'] and r['route_mode']==c['route_mode'] and r['mode']==c['mode'],'REQUEST_CONDITION_MISMATCH')
        if r['status']=='VALID':
            require(all(type(r['actual_receiver_B'][k]) is int and r['actual_receiver_B'][k]==c['receiver_B'][k] for k in ('d','s')) and r['actual_receiver_B']['RX_profile_verified'] is True,'ACTUAL_READBACK_MISMATCH')
        require(all(type(r['labels'][t]) is bool if r['status']=='VALID' else r['labels'][t] is None for t in TARGETS),'UNKNOWN_NOT_FAILURE')
        groups[c['condition_id']].append(r)
        coarse_limit=plan['repeats'] if c['condition_id'] in plan['coarse_condition_ids'] else 0
        if len(groups[c['condition_id']])>coarse_limit:
            require(plan['refinement']['enabled'] and type(r.get('selection_sha256')) is str and len(r['selection_sha256'])==64,'EXCESS_UNPERMITTED_REPEATS')
    cells=[]
    for cid,c in lookup.items():
        rows=groups[cid];required=plan['repeats'] if cid in plan['coarse_condition_ids'] else plan['refinement']['confirmation_repeats']
        targets={}
        for t in TARGETS:
            y=sum(r['labels'][t] is True for r in rows);n=sum(r['labels'][t] is False for r in rows);u=sum(r['status']=='UNKNOWN' for r in rows);valid=y+n
            state='UNKNOWN' if u else 'UNMEASURED' if not rows else 'PARTIAL' if valid<required else 'MIXED' if y and n else 'OBSERVED_ALL_PASS' if y else 'OBSERVED_ALL_FAIL'
            targets[t]=dict(success=y,failure=n,unknown=u,valid=valid,required=required,state=state)
        cells.append(dict(condition=copy.deepcopy(c),per_target=targets,record_refs=copy.deepcopy(rows)))
    unknown=any(r['status']=='UNKNOWN' for r in records)
    return dict(schema='CUSTOM_SCAN_STATS_V0_1',session=session,plan_sha256=plan['sha256'],source_scope='CURRENT_SESSION_CHECKED_RAW_ONLY',
        state='BLOCKED_UNKNOWN' if unknown else 'OBSERVATIONS',conditions=cells,valid_records=sum(r['status']=='VALID' for r in records),
        unknown_records=sum(r['status']=='UNKNOWN' for r in records),full_condition_grouping=True,training_model_used=False,
        input_sha256=digest(records),confirmed_domain_complete=not unknown and all(c['per_target'][plan['target']]['valid']>=c['per_target'][plan['target']]['required'] for c in cells),
        coarse_domain_complete=not unknown and all(next(x for x in cells if x['condition']['condition_id']==cid)['per_target'][plan['target']]['valid']>=plan['repeats'] for cid in plan['coarse_condition_ids']))

def group_external(observations):
    """Cross-session descriptive view only; never usable as an execution grant."""
    groups={};seen=set()
    for stats in observations:
        for cell in stats['conditions']:
            key=cell['condition']['condition_sha256']
            entry=groups.setdefault(key,dict(condition=cell['condition'],sources=[],per_target={t:dict(success=0,failure=0,unknown=0,valid=0) for t in TARGETS}))
            for record in cell['record_refs']:
                require(record['uid'] not in seen,'DUPLICATE_EXTERNAL_SOURCE_UID');seen.add(record['uid'])
            entry['sources'].append(dict(session=stats['session'],plan_sha256=stats['plan_sha256'],record_refs=cell['record_refs'],per_target=copy.deepcopy(cell['per_target'])))
            for t in TARGETS:
                for k in entry['per_target'][t]:entry['per_target'][t][k]+=cell['per_target'][t][k]
    return dict(view='EXTERNAL_DESCRIPTIVE_GROUPS_NOT_EXECUTION_INPUT',groups=list(groups.values()),hardware_permission=False)
