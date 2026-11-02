"""All legal scan contexts -> reviewed queue, never silent training updates."""
from pathlib import Path
import json,hashlib,copy
from portable import canonical,digest,from_condition,validate,TARGETS,require
def read(p):return json.loads(Path(p).read_bytes())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def collect(source,output):
    source=Path(source).resolve();out=Path(output).resolve()
    require(out!=source and source not in out.parents,'OUTPUT_OVERLAPS_SOURCE')
    from custom_replay import reconstruct
    rebuilt=reconstruct(source)
    require(rebuilt['status']=='PASS' and rebuilt['origin']=='PYNQ_HARDWARE_CANDIDATE' and rebuilt['raw_MMIO_transaction_binding_verified'] is True,'REAL_RAW_RECONSTRUCTION_REQUIRED')
    cleanup=read(source/'CUSTOM_SCAN/cleanup/state.json')
    require(cleanup['after']['lock_closed'] is True and cleanup['after']['receiver_close_called'] is True and not cleanup['errors'],'CLOSED_SCAN_REQUIRED')
    lookup={c['condition_id']:c for c in rebuilt['plan']['conditions']};rows=[]
    unknown=any(r['status']=='UNKNOWN' for r in rebuilt['records'])
    for r in rebuilt['records']:
        if r['kind']!='ITEM':continue
        q=from_condition(lookup[r['condition_id']],TARGETS[0]);validate(q)
        eligible=r['status']=='VALID' and not unknown and r['strict_retired'] is True and r['actual_READY_saved'] is True
        rows.append(dict(uid=r['uid'],session=r['session'],identity_hex=r['identity_hex'],record_id=r['record_id'],
            status=r['status'],query=q,labels=copy.deepcopy(r['labels']),
            training_candidate=eligible,training_approved=False,evidence=copy.deepcopy(r['evidence']),
            exclusion='SESSION_HAS_UNKNOWN' if unknown else None,source_inventory_sha256=digest(rebuilt['original_inventory'])))
    for name,proof in rebuilt['original_inventory'].items():
        p=(source/name).resolve();require(source in p.parents,'SOURCE_PATH_ESCAPE')
        require(p.stat().st_size==proof['bytes'] and sha(p)==proof['sha256'],'SOURCE_CHANGED_DURING_IMPORT')
    result=dict(schema='EDGE_AI_ALL_CONTEXT_FEEDBACK_QUEUE_V1',rows=rows,rows_sha256=digest(rows),
        source_session=rebuilt['records'][0]['session'],source_inventory=rebuilt['original_inventory'],
        source_root=str(source),unknown_records=sum(r['status']=='UNKNOWN' for r in rebuilt['records']),
        reviewed_for_training=False,training_performed=False,hardware_access=False,new_STARTs=0)
    with out.open('xb') as f:f.write(canonical(result)+b'\n')
    return dict(status='RAW_ALL_CONTEXT_QUEUE_CREATED',records=len(rows),eligible=sum(r['training_candidate'] for r in rows),
        reviewed_for_training=False,training_performed=False,hardware_access=False,new_STARTs=0)
def prepare_snapshot(base,queue,approval,output):
    """Only after explicit review and user training authorization; no fit here."""
    from custom_ai_data import read_splits
    base=Path(base).resolve();out=Path(output).resolve();queue=Path(queue);approval=Path(approval)
    require(out!=base and base not in out.parents and out not in base.parents,'OUTPUT_OVERLAPS_DATASET')
    q=read(queue);a=read(approval)
    require(a.get('reviewed_by_owner') is True and a.get('training_approved_by_user') is True and a.get('queue_file_sha256')==sha(queue),'REVIEWED_UPDATE_AUTHORIZATION_REQUIRED')
    require(q['schema']=='EDGE_AI_ALL_CONTEXT_FEEDBACK_QUEUE_V1' and q['rows_sha256']==digest(q['rows']) and q['unknown_records']==0,'CLEAN_BOUND_RAW_QUEUE_REQUIRED')
    splits=read_splits(base);heldout={r['session'] for name in ('validation','historical_test') for r in splits[name]}
    identities={(r['session'],r['identity_hex']) for rows in splits.values() for r in rows};added=[]
    for r in q['rows']:
        require(r['session'] not in heldout,'EVALUATION_SESSION_CANNOT_ENTER_TRAINING')
        require(r['training_candidate'] is True and r['status']=='VALID' and all(type(r['labels'][t]) is bool for t in TARGETS),'INVALID_TRAINING_CANDIDATE')
        require(r['identity_hex'] is not None,'MISSING_PHYSICAL_IDENTITY');validate(r['query'])
        key=(r['session'],r['identity_hex'])
        if key in identities:continue
        identity_query=copy.deepcopy(r['query']);identity_query.pop('receiver_B');identity_query.pop('target')
        added.append(dict(uid=r['uid'],session=r['session'],identity_hex=r['identity_hex'],split='train',
            cv_group='full_'+digest(identity_query),oss_query=r['query'],labels=r['labels'],evidence=r['evidence'],
            source_training_flags_rewritten=False,training_update_review_sha256=sha(approval)))
        identities.add(key)
    require(added,'NO_NEW_REVIEWED_ROWS');out.mkdir(parents=True,exist_ok=False)
    splits['train'].extend(added);manifest={}
    for name,rows in splits.items():
        data=canonical(rows)+b'\n';p=out/(name+'.json');p.write_bytes(data);manifest[p.name]=dict(bytes=len(data),sha256=sha(p))
    (out/'APPROVAL.json').write_bytes(approval.read_bytes())
    spec=dict(schema='EDGE_AI_OSS_REVIEWED_DATASET_V1',files=manifest,added_rows=len(added),
        approval_sha256=sha(approval),approved_queue_sha256=sha(queue),
        unchanged_validation_sha256=digest(splits['validation']),unchanged_historical_sha256=digest(splits['historical_test']))
    (out/'OSS_DATASET.json').write_bytes(canonical(spec)+b'\n');return spec
def load_splits(path):
    path=Path(path);specpath=path/'OSS_DATASET.json'
    if not specpath.exists():
        from custom_ai_data import read_splits
        return read_splits(path)
    spec=read(specpath);a=read(path/'APPROVAL.json')
    require(spec['schema']=='EDGE_AI_OSS_REVIEWED_DATASET_V1' and spec['approval_sha256']==sha(path/'APPROVAL.json') and a.get('reviewed_by_owner') is True and a.get('training_approved_by_user') is True and a.get('queue_file_sha256')==spec['approved_queue_sha256'],'TRAINING_UPDATE_APPROVAL_REQUIRED')
    rows={}
    for name in ('train','validation','historical_test','controls_only'):
        p=path/(name+'.json');proof=spec['files'][p.name]
        require(p.stat().st_size==proof['bytes'] and sha(p)==proof['sha256'],'DATA_SNAPSHOT_CHANGED')
        rows[name]=read(p)
    require(digest(rows['validation'])==spec['unchanged_validation_sha256'] and digest(rows['historical_test'])==spec['unchanged_historical_sha256'],'EVALUATION_SPLIT_CHANGED')
    seen=set()
    for split,rr in rows.items():
        for r in rr:
            key=(r['session'],r['identity_hex']);require(key not in seen and r['split']==split,'PHYSICAL_RECORD_REPLAY_OR_SPLIT');seen.add(key)
            if split!='controls_only':require(all(type(r['labels'][t]) is bool for t in TARGETS),'UNKNOWN_NOT_A_LABEL')
            if 'oss_query' in r:validate(r['oss_query'])
    require(not ({r['session'] for r in rows['train']}&{r['session'] for r in rows['validation']+rows['historical_test']}),'CROSS_SESSION_SPLIT_LEAK')
    return rows
