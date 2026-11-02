"""Same-budget retrospective comparison; selectors never receive oracle rows."""
from pathlib import Path
import sys,json,copy,argparse,time
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'backend'),str(ROOT/'oss')]
from portable import load_default,from_condition,rank,features,canonical,entropy,require
from upstream import fit,utilities,CONFIG
from train_oss import query_row
from feedback_oss import load_splits
from edge_api import EdgeAI
from edge_replay import cells_from,simulate
from custom_replay import reconstruct

def simulate_oss(conditions,oracle,target,model,strategy,budget,clf,training):
    observed={};trace=[];used=2
    for round_index in range((budget-2)//3):
        if round_index<2:
            p,w=(15,1) if round_index==0 else (15,30)
            c=next(c for c in conditions if (c['fault']['phase'],c['fault']['width'])==(p,w));reason='DECLARED_SHARED_ANCHOR'
        elif strategy=='oss_hybrid':
            ranked=rank(cells_from(conditions,observed,target),target,model,3,0)
            if not ranked:break
            c=ranked[0]['condition'];reason=ranked[0]['reason']
        else:
            remaining=[c for c in conditions if c['condition_id'] not in observed]
            if not remaining:break
            # Actual upstream query, fixed train84 model, no unseen oracle labels.
            X=[features(query_row(r,target)) for r in training];y=[int(r['labels'][target]) for r in training]
            indices,u=utilities(clf,X,y,[features(from_condition(c,target)) for c in remaining])
            selected=indices[0];c=remaining[selected];reason='UPSTREAM_UNCERTAINTY_ENTROPY'
        key=c['condition_id'];require(key not in observed,'NO_REUSE_OF_PHYSICAL_TRIPLETS')
        batch=oracle[key];require(len(batch)==3,'EXACT_THREE_REAL_RECORDS')
        observed[key]=copy.deepcopy(batch);used+=3
        trace.append(dict(phase=c['fault']['phase'],width=c['fault']['width'],condition_id=key,reason=reason,
            successes=sum(r['labels'][target] for r in batch),used_budget_including_preparation=used,
            original_refs=[dict(uid=r['uid'],session=r['session'],record_id=r['record_id']) for r in batch]))
    truth={k:sum(r['labels'][target] for r in rows) for k,rows in oracle.items()}
    mixed={k for k,y in truth.items() if 0<y<3};boundary=set(mixed)
    pos={(c['fault']['phase'],c['fault']['width']):c['condition_id'] for c in conditions}
    for axis in (0,1):
        for fixed in sorted({p[axis] for p in pos}):
            line=sorted([p for p in pos if p[axis]==fixed],key=lambda p:p[1-axis])
            for a,b in zip(line,line[1:]):
                if (truth[pos[a]]>=2)!=(truth[pos[b]]>=2):boundary.update((pos[a],pos[b]))
    return dict(strategy=strategy,trace=trace,used_records=used,condition_coverage=len(observed)/len(conditions),
        discovered_mixed_conditions=len(set(observed)&mixed),boundary_conditions_touched=len(set(observed)&boundary),
        total_boundary_conditions=len(boundary),unmeasured_conditions=len(conditions)-len(observed),
        full_boundary_reconstruction_claimed=False,hardware_speedup_claimed=False)
def run(sessions,output):
    out=Path(output).resolve()
    for source in [ROOT,*[Path(s).resolve() for s in sessions]]:
        require(out!=source and source not in out.parents and out not in source.parents,'OUTPUT_OVERLAPS_INPUT_OR_PACKAGE')
    out.mkdir(parents=True,exist_ok=False);model=load_default();old=EdgeAI().model;training=load_splits(ROOT/'data')['train'];reports=[]
    for session in sessions:
        session=Path(session).resolve();print('RECONSTRUCT_RAW',session.name,flush=True);raw=reconstruct(session)
        require(raw['status']=='PASS' and raw['origin']=='PYNQ_HARDWARE_CANDIDATE' and raw['raw_MMIO_transaction_binding_verified'] is True,'REAL_RAW_REQUIRED')
        conditions=raw['plan']['conditions'];require(len(conditions)==14,'EXACT14_GRID_REQUIRED')
        oracle={c['condition_id']:[] for c in conditions}
        for r in raw['records']:
            require(r['status']=='VALID','UNKNOWN_BLOCKS_REPLAY')
            if r['kind']=='ITEM':oracle[r['condition_id']].append(r)
        for target in ('B_frame_correct','STM_payload_correct','STM_business_success'):
            ti=('B_frame_correct','STM_payload_correct','STM_business_success').index(target)
            clf=fit([features(query_row(r,target)) for r in training],[int(r['labels'][target]) for r in training],CONFIG['random_state']+ti*1000)
            runs=[simulate(conditions,oracle,target,old,s,14) for s in ('boundary_rule_v02','edge_ai')]
            runs.extend(simulate_oss(conditions,oracle,target,model,s,14,clf,training) for s in ('upstream_entropy','oss_hybrid'))
            report=dict(source_session=session.name,target=target,budget=14,strategies=runs)
            reports.append(report);print('REPLAY',session.name,target,[(r['strategy'],r['boundary_conditions_touched'],r['discovered_mixed_conditions']) for r in runs],flush=True)
    result=dict(schema='EDGE_AI_OSS_FOUR_STRATEGY_REPLAY_V1',reports=reports,model_sha256=model.model_sha256,
        retrospective_public_development_data=True,labels_revealed_only_after_choice=True,
        validation_sessions_not_used_for_fit=True,global_model_retrained_with_replay=False,
        fixed_model_and_hyperparameters_before_replay=True,hardware_speedup_accepted=False,
        new_STARTs=0,hardware_access=False)
    (out/'report.json').write_bytes(canonical(result)+b'\n');return result
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--session',action='append',required=True);p.add_argument('--output',required=True);a=p.parse_args();run(a.session,a.output)
