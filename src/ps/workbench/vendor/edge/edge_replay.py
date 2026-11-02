"""Same-budget historical replay with a private oracle, never new trials."""
from pathlib import Path
import sys,json,copy,time,argparse
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT/'backend'))
from edge_api import EdgeAI
from custom_ai_core import require,canonical
from custom_ai_policy import rank_cells
from boundary_rule import decide as rule_decide

def cells_from(conditions,seen,target):
    cells=[]
    for c in conditions:
        rows=seen.get(c['condition_id'],[]);success=sum(r['labels'][target] for r in rows);n=len(rows)
        state='UNMEASURED' if not n else 'MIXED' if 0<success<n else 'OBSERVED_ALL_PASS' if success else 'OBSERVED_ALL_FAIL'
        cells.append(dict(condition=c,per_target={target:dict(valid=n,success=success,failure=n-success,unknown=0,required=3,state=state)}))
    return cells

def simulate(conditions,oracle,target,model,strategy,budget):
    observed={};trace=[];used=2
    for round_index in range((budget-2)//3):
        # The selector receives only previously exposed batches. Oracle labels
        # are looked up AFTER the selected condition has been fixed.
        if round_index<2:
            phase,width=(15,1) if round_index==0 else (15,30)
            selected=next(c for c in conditions if (c['fault']['phase'],c['fault']['width'])==(phase,width));reason='DECLARED_SHARED_ANCHOR'
        elif strategy=='edge_ai':
            ranked=rank_cells(cells_from(conditions,observed,target),target,model,3,0)
            if not ranked:break
            selected=ranked[0]['condition'];reason=ranked[0]['reason']
        else:
            batches=[dict(point_id='p%d_w%d'%(t['phase'],t['width']),successes=t['successes']) for t in trace]
            result=rule_decide(batches)
            if result['action']!='SELECT':break
            selected=next(c for c in conditions if 'p%d_w%d'%(c['fault']['phase'],c['fault']['width'])==result['point_id']);reason='BOUNDARY_RULE_V02_REFERENCE'
        cid=selected['condition_id'];require(cid not in observed,'REPLAY_CANNOT_REUSE_SAME_REAL_RECORDS_AS_NEW_REPEAT')
        batch=oracle[cid];require(len(batch)==3,'EXACT_THREE_REAL_RECORDS_REQUIRED')
        observed[cid]=copy.deepcopy(batch);used+=3
        trace.append(dict(virtual_round=round_index+1,phase=selected['fault']['phase'],width=selected['fault']['width'],
            condition_id=cid,reason=reason,successes=sum(r['labels'][target] for r in batch),
            original_refs=[dict(uid=r['uid'],session=r['session'],record_id=r['record_id'],identity_hex=r['identity_hex']) for r in batch],
            used_budget_including_preparation=used))
    # Whole-grid truth below is evaluator-only, never passed to rank_cells/rule.
    truth={cid:sum(r['labels'][target] for r in rows) for cid,rows in oracle.items()}
    mixed={cid for cid,y in truth.items() if 0<y<3};boundary=set(mixed)
    by_position={(c['fault']['phase'],c['fault']['width']):c['condition_id'] for c in conditions}
    for axis in (0,1):
        for fixed in sorted({p[axis] for p in by_position}):
            line=sorted((p for p in by_position if p[axis]==fixed),key=lambda p:p[1-axis])
            for p,q in zip(line,line[1:]):
                a,b=by_position[p],by_position[q]
                if (truth[a]>=2)!=(truth[b]>=2):boundary.update((a,b))
    selected=set(observed)
    return dict(strategy=strategy,trace=trace,used_records=used,condition_coverage=len(selected)/len(conditions),
        discovered_mixed_conditions=len(selected&mixed),boundary_conditions_touched=len(selected&boundary),
        total_boundary_conditions=len(boundary),unmeasured_conditions=len(conditions)-len(selected),
        full_boundary_reconstruction_claimed=False,hardware_speedup_claimed=False)

def run(source,output,target='B_frame_correct',budget=14):
    from custom_replay import reconstruct
    require(type(budget) is int and 8<=budget<=44 and (budget-2)%3==0,'FINITE_TRIPLET_BUDGET')
    source=Path(source).resolve();out=Path(output).resolve()
    require(out!=source and source not in out.parents and out not in source.parents,'OUTPUT_OVERLAPS_SOURCE')
    out.mkdir(parents=True,exist_ok=False);raw=reconstruct(source)
    require(raw['origin']=='PYNQ_HARDWARE_CANDIDATE' and raw['raw_MMIO_transaction_binding_verified'] is True,'REAL_RAW_EVIDENCE_REQUIRED')
    plan=raw['plan'];conditions=plan['conditions']
    from learning_domain import CELLS
    require(len(conditions)==14 and {(c['fault']['phase'],c['fault']['width']) for c in conditions}=={(c['phase'],c['width']) for c in CELLS},'REPLAY_EXACT14_DOMAIN')
    oracle={c['condition_id']:[] for c in conditions}
    for r in raw['records']:
        require(r['status']=='VALID','UNKNOWN_BLOCKS_REPLAY')
        if r['kind']=='ITEM':oracle[r['condition_id']].append(r)
    require(all(len(v)==3 for v in oracle.values()),'FULL14_TRIPLETS_REQUIRED')
    model=EdgeAI().model;started=time.perf_counter()
    runs=[simulate(conditions,oracle,target,model,s,budget) for s in ('boundary_rule_v02','edge_ai')]
    import hashlib
    report=dict(schema='EDGE_AI_SAME_BUDGET_REPLAY_V1',source_session=source.name,target=target,budget=budget,
        model_sha256=model.model_sha256,strategies=runs,offline_seconds=time.perf_counter()-started,
        policy_source_sha256=hashlib.sha256((ROOT/'backend/custom_ai_policy.py').read_bytes()).hexdigest(),
        observed_labels_revealed_only_after_choice=True,replay_repeat_cap=0,
        original_record_ids_preserved=True,source_source_code_is_replayed_not_executed=True,
        training_source_overlap=source.name in model.snapshot['train_sessions'],
        retrospective_public_data=True,prospective_hardware_acceleration_verified=False,
        policy_development_has_seen_public_sessions_3a_3b=True,
        limits='Both strategies use same anchors/domain/triplet budget; oracle repeats cannot be reused. Runtime can separately permit bounded repeat confirmation; this replay sets zero extra groups.',
        new_physical_STARTs=0,hardware_access=False)
    (out/'replay.json').write_bytes(canonical(report)+b'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='strategies'},ensure_ascii=False,indent=2))
    for r in runs:print(r['strategy'],[(t['phase'],t['width']) for t in r['trace']],r['boundary_conditions_touched'],r['discovered_mixed_conditions'])
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--session',required=True);p.add_argument('--output',required=True);p.add_argument('--target',default='B_frame_correct');p.add_argument('--budget',type=int,default=14)
    a=p.parse_args();run(a.session,a.output,a.target,a.budget)
