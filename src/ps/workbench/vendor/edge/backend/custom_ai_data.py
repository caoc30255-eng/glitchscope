"""Frozen audited-data snapshot loader; labels and original flags are preserved."""
from pathlib import Path
import json,hashlib
from custom_ai_core import TARGETS,CONTEXT,require,canonical,query,validate_query,digest

def read_splits(directory):
    directory=Path(directory).resolve();manifest=json.loads((directory/'data_sha256.json').read_bytes())
    result={};uids=set()
    spec=json.loads((directory/'DATA_SPEC.json').read_bytes()) if (directory/'DATA_SPEC.json').exists() else None
    if spec is not None:
        require(spec['schema']=='EDGE_AI_REVIEWED_DATASET_V1','DATA_SPEC_SCHEMA')
        proof=(directory/'TRAINING_UPDATE_APPROVAL.json').read_bytes();approval=json.loads(proof)
        require(hashlib.sha256(proof).hexdigest()==spec['training_update_approval_sha256'] and
            approval.get('reviewed_by_owner') is True and approval.get('training_approved_by_user') is True and
            approval.get('queue_file_sha256')==spec['approved_queue_sha256'],'TRAINING_UPDATE_APPROVAL_REQUIRED')
        for name,sha in spec['evaluation_sha256'].items():
            require(name in ('validation','historical_test') and hashlib.sha256((directory/(name+'.jsonl')).read_bytes()).hexdigest()==sha,'EVALUATION_SPLIT_CHANGED')
    expected=spec['counts'] if spec is not None else {'train':84,'validation':40,'historical_test':30,'controls_only':16}
    require(set(expected)=={'train','validation','historical_test','controls_only'} and all(type(v) is int and v>=0 for v in expected.values()),'SPLIT_SPEC')
    for split,total in expected.items():
        name=split+'.jsonl';raw=(directory/name).read_bytes();proof=manifest[name]
        require(len(raw)==proof['bytes'] and hashlib.sha256(raw).hexdigest()==proof['sha256'],'DATA_SNAPSHOT_CHANGED:'+split)
        rows=[json.loads(x) for x in raw.splitlines() if x.strip()];require(len(rows)==total,'SPLIT_COUNT_CHANGED')
        for r in rows:
            require(r['schema']=='B_BOUNDARY_AUDITED_ROW_V0_1' and r['split']==split and r['uid'] not in uids,'DATA_SCHEMA_SPLIT_OR_UID')
            uids.add(r['uid']);require(r['evidence_quality']=='VALID' and r['strict_retired'] is True and bool(r['evidence']),'UNCHECKED_RECORD')
            if split!='controls_only':
                require(r['eligible'] is True and r['kind']=='ITEM' and all(type(r['labels'][t]) is bool for t in TARGETS),'INVALID_LABEL_OR_KIND')
                f=r['features'];validate_query(query(**f))
                require(r['payload_sha256']==CONTEXT['payload_sha256'] and (r['byte'],r['bit'],r['count'],r['route_mode'])==(20,0,1,0),'UNSUPPORTED_TRAINING_CONTEXT')
                require(r['protocol']=='TYPE3A_SINGLE_POINT' and r['cv_group']=='p%d_w%d'%(f['phase'],f['width']),'WRONG_PROTOCOL_OR_GROUP')
                if spec is None:require(f['d'] in (3,4) and f['s']==-1,'FROZEN_TRAIN_PROFILE_CHANGED')
        result[split]=rows
    expected_train=set(spec['train_sessions']) if spec is not None else {'session_00000029','session_0000002a'}
    require({r['session'] for r in result['train']}==expected_train,'TRAIN_SESSIONS_CHANGED')
    require(not ({r['session'] for r in result['train']}&{r['session'] for r in result['validation']+result['historical_test']}),'CROSS_SESSION_SPLIT_LEAK')
    return result

def normalize(rows):
    """Only pre-trial inputs become model features; UID/context remain bookkeeping."""
    return [dict(uid=r['uid'],session=r['session'],split=r['split'],cv_group=r['cv_group'],
        features=dict(r['features']),labels={t:r['labels'][t] for t in TARGETS},
        source_row_sha256=digest(r),original_training_flag=r['source_training_authorized_flag']) for r in rows]
