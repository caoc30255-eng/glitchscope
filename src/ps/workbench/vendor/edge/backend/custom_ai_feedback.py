"""Append-only offline feedback store backed by raw scan reconstruction."""
from pathlib import Path
import json,sqlite3,hashlib,contextlib,sys
from custom_ai_core import TARGETS,CONTEXT,require,canonical,digest

class FeedbackStore:
    def __init__(self,path):
        self.path=Path(path).resolve();self.path.parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(str(self.path));self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript('''CREATE TABLE IF NOT EXISTS sessions (
          session TEXT PRIMARY KEY, inventory_sha TEXT NOT NULL, source_root TEXT NOT NULL,
          unknown_count INTEGER NOT NULL, certificate TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS records (
          physical_key TEXT PRIMARY KEY, uid TEXT NOT NULL UNIQUE, session TEXT NOT NULL,
          record_id INTEGER NOT NULL, status TEXT NOT NULL, eligible INTEGER NOT NULL,
          row_sha TEXT NOT NULL, row_json TEXT NOT NULL,
          FOREIGN KEY(session) REFERENCES sessions(session));''');self.db.commit()
    def close(self):self.db.close()

    def ingest(self,source):
        source=Path(source).resolve();require(source not in self.path.parents and source!=self.path,'DATABASE_MUST_NOT_MODIFY_EVIDENCE')
        cleanup=json.loads((source/'CUSTOM_SCAN/cleanup/state.json').read_bytes())
        require(cleanup['after']['lock_closed'] is True and cleanup['after']['receiver_close_called'] is True and not cleanup['errors'],'CLOSED_SCAN_REQUIRED')
        with contextlib.ExitStack() as stack:
            lock=source.parent/'exclusive.lock'
            if sys.platform.startswith('linux') and lock.is_file():
                import fcntl
                f=stack.enter_context(lock.open('rb'));fcntl.flock(f,fcntl.LOCK_SH|fcntl.LOCK_NB)
            from custom_replay import reconstruct
            rebuilt=reconstruct(source)
            require(rebuilt['status']=='PASS' and rebuilt['origin']=='PYNQ_HARDWARE_CANDIDATE' and rebuilt['raw_MMIO_transaction_binding_verified'] is True,'REAL_RAW_RECONSTRUCTION_REQUIRED')
            rows=rebuilt['records'];require(rows,'EMPTY_SOURCE_SESSION')
            session=rows[0]['session'];unknown=sum(r['status']=='UNKNOWN' for r in rows)
            inv_sha=digest(rebuilt['original_inventory'])
            for name,proof in rebuilt['original_inventory'].items():
                p=(source/name).resolve();require(source in p.parents,'SOURCE_PATH_ESCAPE');b=p.read_bytes()
                require(len(b)==proof['bytes'] and hashlib.sha256(b).hexdigest()==proof['sha256'],'SOURCE_CHANGED_DURING_IMPORT')
            certificate=dict(status='RAW_SCAN_RECONSTRUCTED',session=session,origin=rebuilt['origin'],
                inventory_sha256=inv_sha,unknown_records=unknown,hardware_access=False,new_STARTs=0,
                owner_review_still_required=True,source_bytes_rewritten=False)
            inserted=duplicates=eligible=0
            with self.db:
                old=self.db.execute('SELECT inventory_sha FROM sessions WHERE session=?',(session,)).fetchone()
                if old:require(old[0]==inv_sha,'SESSION_IMPORT_CONFLICT')
                else:self.db.execute('INSERT INTO sessions VALUES (?,?,?,?,?)',(session,inv_sha,str(source),unknown,canonical(certificate).decode()))
                for r in rows:
                    valid=r['status']=='VALID';f=r.get('fault');b=r['requested_receiver_B']
                    supported=valid and r['kind']=='ITEM' and f is not None and r['mode']=='TYPE3A_SINGLE' and r['route_mode']==0 and r['payload_sha256']==CONTEXT['payload_sha256'] and f['byte']==20 and f['bit']==0
                    can_train=bool(supported and not unknown)
                    key=hashlib.sha256((session+'|'+(r.get('identity_hex') or 'UNKNOWN_%d'%r['record_id'])).encode('ascii')).hexdigest()
                    result_path=source/'EXECUTOR'/('record_%08x'%r['record_id'])/'result/result.json'
                    original_result=json.loads(result_path.read_bytes()) if result_path.exists() else {}
                    row=dict(schema='EDGE_AI_FEEDBACK_ROW_V1',physical_key=key,uid=r['uid'],session=session,
                        epoch=r['epoch'],record_id=r['record_id'],identity_hex=r.get('identity_hex'),status=r['status'],kind=r['kind'],
                        features=None if f is None else dict(d=b['d'],s=b['s'],phase=f['phase'],width=f['width']),
                        labels={t:r['labels'][t] for t in TARGETS},mode=r['mode'],route_mode=r['route_mode'],
                        payload_sha256=r['payload_sha256'],fault=f,strict_retired=r['strict_retired'],actual_READY_saved=r['actual_READY_saved'],
                        training_candidate=can_train,training_approved=False,
                        exclusion=None if can_train else 'SESSION_HAS_UNKNOWN' if unknown else 'PREPARATION_OR_UNSUPPORTED_CONTEXT',
                        evidence=r['evidence'],source_inventory_sha256=inv_sha,source_origin='PYNQ_HARDWARE_CANDIDATE')
                    row['source_training_authorized_flag']=original_result.get('training_authorized')
                    row['source_production_billing_finalized']=original_result.get('production_billing_finalized')
                    sha=digest(row);prior=self.db.execute('SELECT row_sha FROM records WHERE physical_key=?',(key,)).fetchone()
                    if prior:require(prior[0]==sha,'PHYSICAL_RECORD_IMPORT_CONFLICT');duplicates+=1
                    else:
                        self.db.execute('INSERT INTO records VALUES (?,?,?,?,?,?,?,?)',(key,r['uid'],session,r['record_id'],r['status'],int(can_train),sha,canonical(row).decode()));inserted+=1
                    eligible+=int(can_train)
            return dict(status='IMPORTED_OFFLINE_RAW_FEEDBACK',session=session,inserted=inserted,duplicates=duplicates,
                training_candidates=eligible,unknown_records=unknown,training_performed=False,hardware_access=False,new_STARTs=0)

    def export_candidates(self,path):
        path=Path(path).resolve();path.parent.mkdir(parents=True,exist_ok=True)
        rows=[]
        for raw,sha in self.db.execute('SELECT row_json,row_sha FROM records WHERE eligible=1 ORDER BY session,record_id'):
            row=json.loads(raw);require(digest(row)==sha,'DATABASE_ROW_CHANGED');rows.append(row)
        payload=dict(schema='EDGE_AI_FEEDBACK_REVIEW_QUEUE_V1',rows=rows,rows_sha256=digest(rows),
            reviewed_for_training=False,training_performed=False,hardware_permission=False)
        with path.open('xb') as f:f.write(canonical(payload)+b'\n')
        return dict(path=str(path),rows=len(rows),review_required=True,training_performed=False)

def make_updated_dataset(old_data,queue,review_receipt,output):
    """Explicit reviewed update, preserving validation/test splits and identities."""
    from custom_ai_data import read_splits
    old=Path(old_data).resolve();out=Path(output).resolve();queue=Path(queue)
    require(out!=old and old not in out.parents and out not in old.parents,'OUTPUT_OVERLAPS_DATASET')
    base=read_splits(old);q=json.loads(queue.read_bytes());review=json.loads(Path(review_receipt).read_bytes())
    require(q['schema']=='EDGE_AI_FEEDBACK_REVIEW_QUEUE_V1' and q['rows_sha256']==digest(q['rows']),'FEEDBACK_QUEUE_CHANGED')
    require(review.get('reviewed_by_owner') is True and review.get('training_approved_by_user') is True and review.get('queue_file_sha256')==hashlib.sha256(queue.read_bytes()).hexdigest(),'REVIEWED_UPDATE_AUTHORIZATION_REQUIRED')
    evaluation_sessions={r['session'] for k in ('validation','historical_test') for r in base[k]}
    identities={(r['session'],r['identity_hex']) for rows in base.values() for r in rows}
    added=[]
    for r in q['rows']:
        require(r['session'] not in evaluation_sessions,'EVALUATION_SESSION_CANNOT_ENTER_TRAINING')
        require(r['training_candidate'] is True and r['status']=='VALID' and r['strict_retired'] is True and r['actual_READY_saved'] is True,'INVALID_TRAINING_CANDIDATE')
        if (r['session'],r['identity_hex']) in identities:continue
        require(all(type(r['labels'][t]) is bool for t in TARGETS),'UNKNOWN_NOT_A_LABEL')
        f=r['fault'];features=r['features']
        added.append(dict(schema='B_BOUNDARY_AUDITED_ROW_V0_1',uid=r['physical_key'],session=r['session'],epoch=r['epoch'],record_id=r['record_id'],
            identity_hex=r['identity_hex'],split='train',kind='ITEM',eligible=True,evidence_quality='VALID',strict_retired=True,
            features=features,cv_group='p%d_w%d'%(features['phase'],features['width']),labels=r['labels'],
            payload_sha256=r['payload_sha256'],byte=f['byte'],bit=f['bit'],count=1,route_mode=0,protocol='TYPE3A_SINGLE_POINT',
            evidence=r['evidence'],source_training_authorized_flag=r.get('source_training_authorized_flag'),
            training_update_review_sha256=hashlib.sha256(Path(review_receipt).read_bytes()).hexdigest(),
            source_inventory_sha256=r['source_inventory_sha256']))
        identities.add((r['session'],r['identity_hex']))
    require(added,'NO_NEW_REVIEWED_ROWS');out.mkdir(parents=True,exist_ok=False)
    base['train']=base['train']+added;manifest={}
    for split,rows in base.items():
        raw=b''.join(canonical(r)+b'\n' for r in rows);name=split+'.jsonl';(out/name).write_bytes(raw)
        manifest[name]=dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
    (out/'data_sha256.json').write_bytes(canonical(manifest)+b'\n')
    spec=dict(schema='EDGE_AI_REVIEWED_DATASET_V1',counts={k:len(v) for k,v in base.items()},
        train_sessions=sorted({r['session'] for r in base['train']}),parent_data_manifest_sha256=hashlib.sha256((old/'data_sha256.json').read_bytes()).hexdigest(),
        added_rows=len(added),validation_and_historical_bytes_preserved=True,
        training_update_approval_sha256=hashlib.sha256(Path(review_receipt).read_bytes()).hexdigest(),
        approved_queue_sha256=hashlib.sha256(queue.read_bytes()).hexdigest(),
        evaluation_sha256={k:hashlib.sha256((old/(k+'.jsonl')).read_bytes()).hexdigest() for k in ('validation','historical_test')})
    (out/'TRAINING_UPDATE_APPROVAL.json').write_bytes(Path(review_receipt).read_bytes())
    (out/'DATA_SPEC.json').write_bytes(canonical(spec)+b'\n')
    for split in ('validation','historical_test'):require((out/(split+'.jsonl')).read_bytes()==(old/(split+'.jsonl')).read_bytes(),'EVALUATION_BYTES_CHANGED')
    return spec
