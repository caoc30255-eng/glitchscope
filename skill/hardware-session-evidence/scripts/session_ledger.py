"""Append-only attempt/evidence ledger. Never sends hardware commands."""
import argparse,contextlib,copy,hashlib,json,os,re,sys,uuid
from pathlib import Path
def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf-8')
def digest(v):return hashlib.sha256(canonical(v)).hexdigest()
def check_plan(p):
    ids=p['record_ids'];cap=p['max_records']
    if type(cap) is not int or cap<1 or not isinstance(ids,list) or len(ids)!=cap or len(set(ids))!=len(ids):raise ValueError('PLAN_CAP_OR_IDS')
    if any(not isinstance(i,str) or not re.fullmatch(r'[a-zA-Z0-9_-]+',i) for i in ids):raise ValueError('PLAN_RECORD_ID')
    if p.get('origin') not in ('SYNTHETIC','ADAPTER_REPORTED'):raise ValueError('ORIGIN_REQUIRED')
    canonical(p);return p
def file_sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()
def artifact(root,rel,sha):
    p=Path(rel)
    if p.is_absolute() or '..' in p.parts or not p.parts:raise ValueError('EVIDENCE_PATH')
    target=(root/p).resolve()
    try:target.relative_to(root.resolve())
    except ValueError:raise ValueError('EVIDENCE_ESCAPES_ROOT')
    if not target.is_file() or (root/p).is_symlink():raise ValueError('EVIDENCE_MISSING_OR_LINK')
    if not re.fullmatch('[0-9a-f]{64}',sha) or file_sha(target)!=sha:raise ValueError('EVIDENCE_HASH')
def reduce_event(s,e,root):
    kind=e['kind'];data=e['data']
    if kind=='CREATED':
        if s:raise ValueError('DUPLICATE_CREATION')
        p=check_plan(data['plan'])
        s.update(plan=p,plan_sha256=digest(p),session_id=data['session_id'],attempts=[],completed=[],unknown=[],pending=None,state='READY',cleanup_reported=False)
        return
    if not s:raise ValueError('CREATION_REQUIRED')
    if kind=='ATTEMPT':
        if s['state'] not in ('READY','RUNNING') or s['pending'] is not None:raise ValueError('TERMINAL_OR_PENDING')
        index=len(s['attempts'])
        if index>=s['plan']['max_records'] or data['record_id']!=s['plan']['record_ids'][index]:raise ValueError('ORDER_BUDGET_OR_DUPLICATE')
        if data['context_sha256']!=digest(data['context']):raise ValueError('CONTEXT_HASH')
        s['attempts'].append(data['record_id']);s['pending']=data['record_id'];s['state']='RUNNING'
    elif kind in ('COMPLETE','UNKNOWN'):
        if s['pending'] is None or s['state']!='RUNNING' or data['record_id']!=s['pending']:raise ValueError('NO_MATCHING_ATTEMPT')
        if kind=='COMPLETE':
            if not data['files']:raise ValueError('NO_EVIDENCE')
            for rel,sha in data['files'].items():artifact(root,rel,sha)
            s['completed'].append(data['record_id'])
            if len(s['attempts'])==s['plan']['max_records']:s['state']='STOPPED_BUDGET'
        else:
            for rel,sha in data.get('files',{}).items():artifact(root,rel,sha)
            s['unknown'].append(data['record_id']);s['state']='BLOCKED_UNKNOWN'
        s['pending']=None
    elif kind=='STOP':
        if s['state'] not in ('READY','RUNNING'):raise ValueError('ALREADY_TERMINAL')
        if s['pending'] is not None:s['unknown'].append(s['pending']);s['pending']=None;s['state']='BLOCKED_UNKNOWN'
        else:s['state']='STOPPED_USER'
    elif kind=='CLEANUP_REPORTED':
        if s['state'] in ('READY','RUNNING') or s['cleanup_reported']:raise ValueError('CLEANUP_STATE')
        if data.get('receiver_released') is not True or data.get('lock_closed') is not True:raise ValueError('CLEANUP_INCOMPLETE')
        s['cleanup_reported']=True
    else:raise ValueError('UNKNOWN_EVENT')
def read(root):
    root=Path(root);p=root/'journal.jsonl'
    if p.is_symlink():raise ValueError('JOURNAL_LINK')
    s={};events=[];previous='0'*64
    with p.open(encoding='utf-8') as f:
        for index,line in enumerate(f):
            if not line.endswith('\n'):raise ValueError('TRUNCATED_JOURNAL')
            e=json.loads(line);proof=e.pop('sha256')
            if e.get('seq')!=index or e.get('previous')!=previous or digest(e)!=proof:raise ValueError('JOURNAL_CHAIN')
            reduce_event(s,e,root);previous=proof;e['sha256']=proof;events.append(e)
    if not events:raise ValueError('EMPTY_JOURNAL')
    return s,events
@contextlib.contextmanager
def writer(root):
    p=Path(root)/'writer.lock'
    with p.open('x',encoding='ascii') as f:f.write(str(os.getpid()))
    try:yield
    finally:p.unlink()
def append(root,kind,data):
    root=Path(root)
    with writer(root):
        s,events=read(root)
        e=dict(seq=len(events),previous=events[-1]['sha256'],kind=kind,data=data)
        reduce_event(s,e,root) # Validate transition and artifacts before appending.
        e['sha256']=digest(e)
        with (root/'journal.jsonl').open('ab') as f:f.write(canonical(e)+b'\n');f.flush();os.fsync(f.fileno())
    return audit(root)
def create(root,plan):
    plan=check_plan(plan);root=Path(root);root.mkdir()
    (root/'raw').mkdir()
    e=dict(seq=0,previous='0'*64,kind='CREATED',data=dict(session_id=uuid.uuid4().hex,plan=plan));e['sha256']=digest(e)
    with (root/'journal.jsonl').open('xb') as f:f.write(canonical(e)+b'\n');f.flush();os.fsync(f.fileno())
    return audit(root)
def begin(root,record_id,context):return append(root,'ATTEMPT',dict(record_id=record_id,context=context,context_sha256=digest(context)))
def complete(root,record_id,files):return append(root,'COMPLETE',dict(record_id=record_id,files=files))
def unknown(root,record_id,reason,files=None):return append(root,'UNKNOWN',dict(record_id=record_id,reason=str(reason),files=files or {}))
def stop(root,reason='operator'):return append(root,'STOP',dict(reason=reason))
def cleanup(root,receiver_released,lock_closed):return append(root,'CLEANUP_REPORTED',dict(receiver_released=receiver_released,lock_closed=lock_closed))
def audit(root):
    s,events=read(root);return summarize(s)
def summarize(s):
    occupied=len(s['attempts']);unstarted=s['plan']['max_records']-occupied
    return dict(status='PASS_JOURNAL_AND_FILE_INTEGRITY',state='UNRESOLVED_ATTEMPT' if s['pending'] else s['state'],session_id=s['session_id'],origin=s['plan']['origin'],plan_sha256=s['plan_sha256'],occupied=occupied,
                recorded_completions=len(s['completed']),unknown_or_unresolved=len(s['unknown'])+int(s['pending'] is not None),reserved_unstarted=0 if s['cleanup_reported'] else unstarted,
                cancelled_unstarted=unstarted if s['cleanup_reported'] else 0,cleanup_adapter_reported=s['cleanup_reported'],hardware_authenticity_verified=False,physical_starts_not_inferred=True,
                scope='Append-only local metadata and referenced-file integrity; no FPGA protocol decoder, external signature or OS liveness measurement')
class SessionWriter:
    """Owned writer. Fast mode is explicit; final full audit remains mandatory."""
    def __init__(self,root,incremental=False):self.root=Path(root);self.incremental=incremental;self.fault=False
    def __enter__(self):
        self.guard=writer(self.root);self.guard.__enter__()
        try:
            self.state,events=read(self.root);self.seq=len(events);self.head=events[-1]['sha256'];self.file=(self.root/'journal.jsonl').open('ab');self.expected=self.signature()
        except Exception:
            self.guard.__exit__(*sys.exc_info());raise
        return self
    def signature(self):
        p=self.root/'journal.jsonl'
        if p.is_symlink():raise ValueError('JOURNAL_LINK')
        v=p.stat();return v.st_dev,v.st_ino,v.st_size,v.st_mtime_ns
    def event(self,kind,data):
        if self.fault:raise ValueError('WRITER_FAULTED')
        try:
            if self.signature()!=self.expected:raise ValueError('JOURNAL_CHANGED_DURING_OWNED_WRITE')
            if not self.incremental:
                _,checked=read(self.root)
                if len(checked)!=self.seq or checked[-1]['sha256']!=self.head:raise ValueError('OWNED_HEAD_MISMATCH')
            state=copy.deepcopy(self.state);e=dict(seq=self.seq,previous=self.head,kind=kind,data=data)
            reduce_event(state,e,self.root);e['sha256']=digest(e)
            self.file.write(canonical(e)+b'\n');self.file.flush();os.fsync(self.file.fileno())
            self.state=state;self.head=e['sha256'];self.seq+=1;self.expected=self.signature()
            r=summarize(state);r.update(status='INCREMENTAL_OWNED_WRITER_STATE' if self.incremental else 'FULL_PRE_EVENT_CHECKED_WRITER_STATE',final_full_audit_required=True)
            return r
        except Exception:self.fault=True;raise
    def begin(self,record,context):return self.event('ATTEMPT',dict(record_id=record,context=context,context_sha256=digest(context)))
    def complete(self,record,files):return self.event('COMPLETE',dict(record_id=record,files=files))
    def unknown(self,record,reason,files=None):return self.event('UNKNOWN',dict(record_id=record,reason=str(reason),files=files or {}))
    def stop(self,reason='operator'):return self.event('STOP',dict(reason=reason))
    def __exit__(self,typ,value,tb):
        try:
            self.file.close()
            # Even the fast path audits every journal entry and evidence file on close.
            self.final_report=audit(self.root)
        finally:self.guard.__exit__(typ,value,tb)

def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=['init','begin','complete','unknown','stop','cleanup','audit']);p.add_argument('--root',required=True);p.add_argument('--plan');p.add_argument('--record');p.add_argument('--context');p.add_argument('--files');p.add_argument('--reason',default='operator');p.add_argument('--receiver-released',action='store_true');p.add_argument('--lock-closed',action='store_true')
    a=p.parse_args()
    try:
        if a.command=='init':r=create(a.root,json.loads(Path(a.plan).read_text(encoding='utf-8')))
        elif a.command=='begin':r=begin(a.root,a.record,json.loads(Path(a.context).read_text(encoding='utf-8')))
        elif a.command=='complete':r=complete(a.root,a.record,json.loads(Path(a.files).read_text(encoding='utf-8')))
        elif a.command=='unknown':r=unknown(a.root,a.record,a.reason,json.loads(Path(a.files).read_text(encoding='utf-8')) if a.files else None)
        elif a.command=='stop':r=stop(a.root,a.reason)
        elif a.command=='cleanup':r=cleanup(a.root,a.receiver_released,a.lock_closed)
        else:r=audit(a.root)
    except Exception as e:r=dict(status='BLOCKED',error=type(e).__name__,message=str(e));print(json.dumps(r));return 2
    print(json.dumps(r,indent=2));return 0
if __name__=='__main__':sys.exit(main())
