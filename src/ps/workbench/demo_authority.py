"""Human-confirmed demo rounds, plan reservations and conservative record accounting.

No device import. No grant is created by starting the service or querying status.
Permits derive from an explicit parent consent; they do not fabricate per-plan approvals.
"""
import copy,hashlib,json,os,re,sys,time,uuid,platform,struct
from pathlib import Path
from contextlib import contextmanager
from common import ROOT,raw,digest,sha,write,require,verify,verify_execution

LIVE_ACTIONS={'live_scan':'scan','live_image':'image'}
FREE_ACTIONS=('scan_preview','scan_replay','ai_predict','ai_suggest','image_preview','image_repair','ds_analysis','approval_template')
ASSETS=dict(bit='0c0b686e80e37e49e64ab07b719a0c1ea3387451f3ceebdba5dcf38b8c68b61c',hwh='8d65319fd06ccafb9acdabe1c19868106cd1945f085b2fa03d55b89d238bd2bc',native='e3514adfe6aef5269d0ff833b18404ba27be8435c2c3f3631d3e475ef108bdd8')
RULES=dict(hardware='真实扫描/AI选点的硬件执行，以及图片传输，占用硬件记录额度。CONFIG和无扰动参照也计入。',software='上传预览、计划生成、模型预测、图片修复、波形分析、历史查看和导出均不消耗额度。',reservation='任务先锁定上限；进入逐条硬件执行尝试即占用，严格完成后计为已完成。',release='任务安全结束后，仅释放明确尚未进入执行的预留；状态不明的尝试仍占用，并阻断本轮。',counts='已完成、执行中和UNKNOWN都包含在已占用中，不重复相加。历史已执行记录不回收。')
RULES['unit']='1条额度对应1次CONFIG、参照或ITEM记录的执行尝试；不是一个毛刺、像素或采样点。一个ITEM内的多点毛刺仍只占1条。已完成表示严格退役，不等于被测判据成功。'

def process_identity(pid=None):
    pid=os.getpid() if pid is None else pid
    if sys.platform.startswith('linux'):
        text=Path('/proc/%d/stat'%pid).read_text();return dict(pid=pid,boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),start_ticks=text.rsplit(')',1)[1].split()[19])
    return dict(pid=pid,verification='UNAVAILABLE_ON_THIS_PREVIEW_PLATFORM')
def same_process(identity):
    if not sys.platform.startswith('linux'):return None
    try:return process_identity(identity['pid'])==identity
    except (OSError,ValueError,KeyError):return False
def sync_dir(path):
    if os.name=='posix':
        fd=os.open(str(path),os.O_RDONLY)
        try:os.fsync(fd)
        finally:os.close(fd)

def default_scope():
    return dict(functions=['scan','image'],profiles=[dict(d=d,s=s) for d in range(1,5) for s in range(-2,4-d)],modes=['TYPE3A_SINGLE','TYPE3C_CONTIGUOUS','DISABLED'],image_fault_modes=['random','fixed','disabled'],payloads=['incremental','zero','ones'])
def validate_scope(value):
    ref=default_scope();require(type(value) is dict and set(value)==set(ref),'SCOPE_FIELDS')
    for k in ('functions','modes','image_fault_modes','payloads'):
        require(type(value[k]) is list and value[k] and all(type(x) is str and x in ref[k] for x in value[k]) and len(set(value[k]))==len(value[k]),'SCOPE_'+k)
    profiles=value['profiles'];require(type(profiles) is list and 1<=len(profiles)<=14,'SCOPE_PROFILES')
    seen=set()
    for p in profiles:
        require(type(p) is dict and set(p)=={'d','s'} and type(p['d']) is int and type(p['s']) is int and 1<=p['d']<=4 and -2<=p['s']<=3-p['d'],'ILLEGAL_SCOPE_DS')
        require((p['d'],p['s']) not in seen,'DUPLICATE_SCOPE_DS');seen.add((p['d'],p['s']))
    return copy.deepcopy(value)
def plan_limit(kind,plan):
    require(kind in ('scan','image') and type(plan) is dict,'PLAN_KIND')
    key=plan.get('sha256');require(type(key) is str and re.fullmatch('[0-9a-f]{64}',key),'PLAN_SHA')
    body={k:v for k,v in plan.items() if k!='sha256'}
    expected=hashlib.sha256(json.dumps(body,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')).hexdigest() if kind=='scan' else digest(body)
    require(key==expected,'PLAN_HASH_CHANGED')
    limit=plan.get('max_records') if kind=='scan' else plan.get('max_records_including_CONFIG')
    require(type(limit) is int and (2<=limit<=44 if kind=='scan' else limit==65),'PLAN_RECORD_CAP')
    if kind=='scan' and not plan['refinement']['enabled']:
        required=plan['required_records'];require(type(required) is int and required==2+len(plan['initial_queue']) and 2<=required<=limit,'EXACT_FIXED_QUEUE_CAP');limit=required
    return limit
def check_scope(scope,kind,plan):
    limit=plan_limit(kind,plan);require(kind in scope['functions'],'FUNCTION_OUTSIDE_ROUND')
    allowed={(p['d'],p['s']) for p in scope['profiles']}
    def profile(p):require(type(p) is dict and type(p.get('d')) is int and type(p.get('s')) is int and (p['d'],p['s']) in allowed,'DS_OUTSIDE_ROUND')
    if kind=='scan':
        profile(plan['receiver_B']);require(plan['mode'] in scope['modes'],'MODE_OUTSIDE_ROUND')
        require(plan['route_mode']==0,'DIRECT_ROUTE_ONLY');payload=plan['payload_hex']
        name='incremental' if payload==bytes(range(256)).hex() else 'zero' if payload=='00'*256 else 'ones' if payload=='ff'*256 else None
        require(name in scope['payloads'],'PAYLOAD_OUTSIDE_ROUND')
        require(type(plan['conditions']) is list and 0<len(plan['conditions'])<=256,'CONDITIONS')
        for c in plan['conditions']:
            profile(c['receiver_B']);f=c['fault'];count=c['count']
            require(all(type(f.get(k)) is int for k in ('byte','bit','phase','width')) and type(count) is int,'INTEGER_FAULT')
            require(20<=f['byte']<=275 and 0<=f['bit']<=7 and f['phase']>=5 and f['width']>=1 and f['phase']+f['width']<=45,'FAULT_OUTSIDE_RELEASE_CAPS')
            require(0<=count<=256 and f['byte']+count<=276,'FAULT_COUNT_RANGE')
    else:
        r=plan['request'];profile(r['receiver_B']);require(r['fault_mode'] in scope['image_fault_modes'],'IMAGE_FAULT_MODE_OUTSIDE_ROUND')
        require(len(plan['items'])==64 and all(i['receiver_B']==r['receiver_B'] for i in plan['items']),'ONE_DS_FOR_ALL64_REQUIRED')
        require(plan['CONFIG_receiver_B']=={'d':3,'s':-1},'FIXED_CONFIG_PROFILE')
    return limit

@contextmanager
def file_lock(root):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    f=(root/'authority.lock').open('a+b')
    try:
        if os.name=='nt':
            import msvcrt
            if f.seek(0,2)==0:f.write(b'0');f.flush()
            f.seek(0);deadline=time.monotonic()+10
            while True:
                try:msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1);break
                except OSError:
                    if time.monotonic()>deadline:raise ValueError('AUTHORITY_BUSY')
                    time.sleep(.02)
        else:
            import fcntl
            fcntl.flock(f,fcntl.LOCK_EX)
        yield
    finally:
        try:
            if os.name=='nt':
                import msvcrt
                f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl
                fcntl.flock(f,fcntl.LOCK_UN)
        finally:f.close()

class Authority:
    def __init__(self,root,mode='PREVIEW',config=None):
        require(mode in ('PREVIEW','LIVE'),'AUTHORITY_MODE');self.root=Path(root).resolve();self.mode=mode;self.config=config
    @classmethod
    def for_live(cls,config):
        runs=Path(config['runs']).resolve();return cls(runs/'DEMO_AUTHORITY_V1','LIVE',config)
    def release(self,quick=False):
        verify_execution() if quick else verify()
        result=dict(mode=self.mode,ui_manifest_sha256=sha(ROOT/'manifest.json'),capabilities_version='DEMO_ROUND_CAPS_V1')
        if self.mode=='LIVE':
            require(self.config is not None,'LIVE_CONFIG_REQUIRED')
            assets={k:sha(p) for k,p in self.config['assets'].items()};require(assets==ASSETS,'ORIGINAL_ASSETS_REQUIRED')
            require(type(self.config.get('software_receipt')) is str and Path(self.config['software_receipt']).is_file(),'请先完成本版本的板侧软件检查')
            receipt=Path(self.config['software_receipt']);v=json.loads(receipt.read_bytes())
            require(v.get('status')=='PASS_TARGET_DEMO_SOFTWARE' and v.get('ui_manifest_sha256')==result['ui_manifest_sha256'] and v.get('hardware_access') is False and v.get('new_STARTs')==0,'TARGET_SOFTWARE_RECEIPT_REQUIRED')
            require(sys.platform.startswith('linux') and platform.machine()=='armv7l' and struct.calcsize('P')==4 and v.get('machine')=='armv7l' and v.get('bits')==32,'TARGET_ARM32_RECEIPT_REQUIRED')
            result.update(asset_sha256=assets,runs_directory=str(Path(self.config['runs']).resolve()),software_receipt_sha256=sha(receipt))
            from installation_state import fresh_identity
            origin=fresh_identity(self.config)
            if origin:result.update(installation_mode='fresh',installation_id=origin['id'],fresh_installation_sha256=self.config['fresh_installation_sha256'])
        return result
    def legacy_floor(self):
        if self.mode!='LIVE':return 0
        from installation_state import fresh_identity
        if fresh_identity(self.config):return 0
        runs=Path(self.config['runs']);values=[707]
        for p in (runs/'unified_ui_approval_consumed').glob('*.json'):
            v=json.loads(p.read_bytes());require(type(v.get('cumulative_limit')) is int,'LEGACY_ACCOUNTING_CHANGED');values.append(v['cumulative_limit'])
        return max(values)
    def _load(self):
        path=self.root/'ledger.jsonl';records=[]
        if path.exists():
            for line in path.read_text(encoding='utf-8').splitlines():
                v=json.loads(line);body={k:x for k,x in v.items() if k!='sha256'}
                require(v['seq']==len(records)+1 and v['prev']==(records[-1]['sha256'] if records else '0'*64) and digest(body)==v['sha256'],'LEDGER_INTEGRITY_REQUIRED');records.append(v)
        elif (self.root/'initialized.json').exists() or any((self.root/'permits').glob('*.json')):raise ValueError('LEDGER_MISSING_REQUIRE_REVIEW')
        elif self.mode=='LIVE':
            for label in Path(self.config['runs']).glob('session_*/DEMO_UI/session_label.json'):
                require(not json.loads(label.read_bytes()).get('round_id'),'LEDGER_MISSING_WITH_EXISTING_DEMO_SESSION')
        if path.exists() and not records and (self.root/'initialized.json').exists():raise ValueError('LEDGER_EMPTY_REQUIRE_REVIEW')
        state=dict(rounds={},tasks={},active=None)
        for e in records:
            p=e['payload'];event=e['event']
            if event=='CONSENT':
                require(state['active'] is None,'OVERLAPPING_ROUNDS');r=copy.deepcopy(p);r.update(total=p['budget'],state='OPEN',grant_sha256=e['sha256']);state['rounds'][r['id']]=r;state['active']=r['id']
            elif event=='TOPUP':state['rounds'][p['round_id']]['total']+=p['amount']
            elif event=='RESERVED':
                require(p['job_id'] not in state['tasks'],'JOB_ALREADY_RESERVED');t=copy.deepcopy(p);t.update(state='RESERVED',attempts=[],retired=[],hardware_setup=False,session_name=None,terminal=False);state['tasks'][p['job_id']]=t
            elif event=='WORKER':state['tasks'][p['job_id']]['worker']=p['identity']
            elif event=='SETUP':state['tasks'][p['job_id']].update(state='PREPARING',hardware_setup=True)
            elif event=='SESSION':
                t=state['tasks'][p['job_id']];require(t['session_name'] is None,'SESSION_ALREADY_ALLOCATED');t.update(session_name=p['session_name'],session_path=p['session_path'])
            elif event=='ATTEMPT':
                t=state['tasks'][p['job_id']];require(not t['terminal'] and p['record_id']==len(t['attempts'])+1 and len(t['attempts'])<t['limit'],'ATTEMPT_ORDER_OR_LIMIT');t['attempts'].append(p['record_id']);t['state']='RUNNING'
            elif event=='RETIRED':
                t=state['tasks'][p['job_id']];require(p['record_id']==len(t['retired'])+1 and p['record_id'] in t['attempts'],'RETIRE_ORDER');t['retired'].append(p['record_id'])
            elif event=='TERMINAL':
                t=state['tasks'][p['job_id']];require(not t['terminal'],'TERMINAL_ALREADY_RECORDED');t.update(terminal=True,state=p['state'],cleanup_confirmed=p['cleanup_confirmed'],reason=p['reason']);
                if p['block_round']:state['rounds'][t['round_id']]['state']='BLOCKED'
            elif event=='AUDIT_RECONCILED':
                t=state['tasks'][p['job_id']];require(t['terminal'] and t['attempts']==p['verified_retired_ids'] and t['session_name']==p['session_name'],'AUDIT_PREFIX_OR_SESSION_CHANGED')
                require(p['worker_exited'] is True and p['host_lock_free'] is True and p['raw_MMIO_verified'] is True,'AUDIT_CLEANUP_PROOF_REQUIRED')
                t.update(retired=list(p['verified_retired_ids']),cleanup_confirmed=True,state='STOPPED_SOFTWARE_FAULT_AUDITED',audit_reference=p['audit_reference'])
                state['rounds'][t['round_id']]['state']='BLOCKED'
            elif event=='CLOSED':state['rounds'][p['round_id']]['state']='CLOSED';state['active']=None
            else:raise ValueError('UNKNOWN_LEDGER_EVENT')
        return records,state
    def _append(self,records,event,payload):
        body=dict(seq=len(records)+1,prev=records[-1]['sha256'] if records else '0'*64,event=event,payload=payload)
        value=dict(body,sha256=digest(body))
        with (self.root/'ledger.jsonl').open('ab') as f:f.write(json.dumps(value,ensure_ascii=False,separators=(',',':')).encode('utf-8')+b'\n');f.flush();os.fsync(f.fileno())
        sync_dir(self.root)
        return value
    def _snapshot(self,state):
        active=state['rounds'].get(state['active']);result=dict(mode=self.mode,active_round=None,rules=RULES,scope_capabilities=default_scope(),hardware_access=False,new_STARTs=0)
        if not active:return result
        tasks=[t for t in state['tasks'].values() if t['round_id']==active['id']]
        occupied=sum(len(t['attempts']) for t in tasks);completed=sum(len(t['retired']) for t in tasks)
        reserved=sum(t['limit']-len(t['attempts']) for t in tasks if not t['terminal'] or not t.get('cleanup_confirmed'))
        unknown=sum(len(t['attempts'])-len(t['retired']) for t in tasks if t['terminal'])
        in_flight=sum(len(t['attempts'])-len(t['retired']) for t in tasks if not t['terminal'])
        view={k:v for k,v in active.items() if k!='release'};view.update(available=active['total']-occupied-reserved,reserved=reserved,occupied=occupied,completed=completed,unknown=unknown,in_flight=in_flight,hardware_tasks=len(tasks),active_tasks=[self.task_view(t) for t in tasks if not t['terminal']],current_ui_version=active['release']['ui_manifest_sha256']==sha(ROOT/'manifest.json'))
        if any(t.get('worker') and same_process(t['worker']) is False for t in tasks if not t['terminal']):view['state']='NEEDS_REVIEW'
        view['cumulative_authorized_ceiling']=active['prior_occupied']+active['total']
        view['unsettled_tasks']=[self.task_view(t) for t in tasks if not t['terminal'] or not t.get('cleanup_confirmed')]
        result['lifetime_occupied']=self.legacy_floor()+sum(len(t['attempts']) for t in state['tasks'].values())
        require(view['available']>=0,'QUOTA_OVERSPENT');result['active_round']=view;return result
    @staticmethod
    def task_view(t):
        return dict(job_id=t['job_id'],round_id=t['round_id'],kind=t['kind'],session_alias=t['session_alias'],session_name=t.get('session_name'),session_path=t.get('session_path'),limit=t['limit'],occupied=len(t['attempts']),completed=len(t['retired']),unknown=max(0,len(t['attempts'])-len(t['retired'])) if t['terminal'] else 0,reserved=0 if t['terminal'] and t.get('cleanup_confirmed') else t['limit']-len(t['attempts']),state=t['state'],terminal=t['terminal'],hardware_setup=t['hardware_setup'],cleanup_confirmed=t.get('cleanup_confirmed'),worker_alive=same_process(t['worker']) if t.get('worker') and not t['terminal'] else None)
    def status(self):
        with file_lock(self.root):_,s=self._load();return self._snapshot(s)
    def create_round(self,budget,scope,operator,confirmation,acknowledged):
        require(type(budget) is int and 1<=budget<=1000000,'ROUND_BUDGET_INTEGER_1_TO_1000000');scope=validate_scope(scope)
        require(type(operator) is str and 1<=len(operator.strip())<=40 and not any(ord(c)<32 for c in operator),'OPERATOR_NAME_REQUIRED')
        require(acknowledged is True and confirmation=='批准本轮 %d 条'%budget,'EXPLICIT_ROUND_CONSENT_REQUIRED')
        release=self.release()
        with file_lock(self.root):
            records,s=self._load();require(s['active'] is None,'CLOSE_EXISTING_ROUND_FIRST')
            if not records:
                write(self.root/'initialized.json',dict(schema='DEMO_AUTHORITY_INITIALIZED_V1',mode=self.mode));sync_dir(self.root)
            p=dict(id=uuid.uuid4().hex,budget=budget,scope=copy.deepcopy(scope),operator=operator.strip(),confirmation=confirmation,acknowledged=True,release=release,mode=self.mode,legacy_floor=self.legacy_floor(),prior_occupied=self.legacy_floor()+sum(len(t['attempts']) for t in s['tasks'].values()),created=time.time())
            self._append(records,'CONSENT',p);return self.status_unlocked()
    def status_unlocked(self):_,s=self._load();return self._snapshot(s)
    def top_up(self,round_id,amount,confirmation):
        require(type(amount) is int and 1<=amount<=1000000 and confirmation=='追加本轮 %d 条'%amount,'EXPLICIT_TOPUP_REQUIRED');release=self.release()
        with file_lock(self.root):
            records,s=self._load();r=s['rounds'].get(round_id);require(s['active']==round_id and r['state']=='OPEN','ROUND_NOT_OPEN');require(r['total']+amount<=1000000,'ROUND_CAP')
            require(r['release']==release,'RELEASE_CHANGED_NEW_ROUND_REQUIRED')
            self._append(records,'TOPUP',dict(round_id=round_id,amount=amount,confirmation=confirmation,created=time.time()));return self.status_unlocked()
    def close_round(self,round_id,confirmation):
        with file_lock(self.root):
            records,s=self._load();r=s['rounds'].get(round_id);require(s['active']==round_id and r is not None,'ROUND_NOT_ACTIVE')
            tasks=[t for t in s['tasks'].values() if t['round_id']==round_id]
            require(all(t['terminal'] and t.get('cleanup_confirmed') for t in tasks),'UNSETTLED_TASKS_REQUIRE_REVIEW')
            require(confirmation==('保留异常并结束本轮' if r['state']=='BLOCKED' else '结束本轮'),'CLOSE_CONFIRMATION_REQUIRED')
            self._append(records,'CLOSED',dict(round_id=round_id,confirmation=confirmation,created=time.time()));return self.status_unlocked()
    def _admit(self,s,kind,plan):
        require(s['active'] is not None,'请先在界面确认本轮演示额度');r=s['rounds'][s['active']]
        require(r['state']=='OPEN','本轮已阻断，需保留现场并核对');require(r['release']['ui_manifest_sha256']==sha(ROOT/'manifest.json'),'界面版本已改变，请结束原轮次后重新确认')
        require(r['legacy_floor']==self.legacy_floor(),'检测到其他入口的额度变更，请核对后重新授权')
        cap=check_scope(r['scope'],kind,plan);snapshot=self._snapshot(s)['active_round']
        require(not snapshot['active_tasks'] and snapshot['reserved']==0,'已有硬件任务或未结清预留，请先完成或核对')
        require(snapshot['available']>=cap,'本轮可用%d条，任务需预留%d条'%(snapshot['available'],cap))
        return r,cap
    def check_plan(self,kind,plan):
        try:
            with file_lock(self.root):_,s=self._load();r,cap=self._admit(s,kind,plan);return dict(ready=True,state='WITHIN_DEMO_ROUND',reason='在本轮授权范围内；启动将预留%d条'%cap,round_id=r['id'],max_records=cap,mode=self.mode)
        except (ValueError,KeyError,TypeError,OSError) as e:return dict(ready=False,state='DEMO_ROUND_REQUIRED_OR_LIMITED',reason=str(e),mode=self.mode)
    def reserve(self,kind,plan,job_id,alias,expected_round=None,task_confirmation=None,manual_ready=False,review_ack=False):
        require(re.fullmatch('[0-9a-f]{32}',job_id or ''),'JOB_ID');require(type(alias) is str and 1<=len(alias.strip())<=80 and not any(ord(c)<32 for c in alias),'SESSION_ALIAS_REQUIRED');self.release()
        if self.mode=='LIVE':require(task_confirmation=='执行本任务 %d 条'%plan_limit(kind,plan) and manual_ready is True and review_ack is True,'EXPLICIT_TASK_REVIEW_AND_PREPARATION_REQUIRED')
        with file_lock(self.root):
            records,s=self._load();r,cap=self._admit(s,kind,plan);require(expected_round is None or expected_round==r['id'],'ROUND_CHANGED_REVIEW_PLAN_AGAIN');require(job_id not in s['tasks'],'JOB_REPLAY')
            permit=dict(schema='GLITCHSCOPE_DEMO_PERMIT_V1',job_id=job_id,round_id=r['id'],grant_sha256=r['grant_sha256'],kind=kind,plan_sha256=plan['sha256'],limit=cap,session_alias=alias.strip(),release=r['release'],authority_root=str(self.root),mode=self.mode,task_confirmation=task_confirmation,manual_ready=manual_ready is True,review_ack=review_ack is True)
            permit['sha256']=digest(permit);p=self.root/'permits'/(job_id+'.json');write(p,permit)
            sync_dir(p.parent);sync_dir(self.root)
            self._append(records,'RESERVED',dict(job_id=job_id,round_id=r['id'],kind=kind,plan_sha256=plan['sha256'],limit=cap,session_alias=alias.strip(),permit_sha256=sha(p)))
            return dict(permit_path=str(p),round_id=r['id'],max_records=cap,session_alias=alias.strip())
    def verify_permit(self,path,plan,allow_terminal=False):
        p=Path(path).resolve();require(p.parent==self.root/'permits','PERMIT_PATH');v=json.loads(p.read_bytes());body={k:x for k,x in v.items() if k!='sha256'}
        require(v['schema']=='GLITCHSCOPE_DEMO_PERMIT_V1' and digest(body)==v['sha256'],'PERMIT_HASH');plan_limit(v['kind'],plan)
        require(v['plan_sha256']==plan['sha256'] and v['mode']==self.mode and v['limit']==plan_limit(v['kind'],plan),'PERMIT_PLAN_OR_MODE');require(self.release(quick=True)==v['release'],'PERMIT_RELEASE_CHANGED')
        with file_lock(self.root):
            _,s=self._load();t=s['tasks'][v['job_id']];r=s['rounds'][v['round_id']]
            require(t['permit_sha256']==sha(p) and r['grant_sha256']==v['grant_sha256'] and r['release']==v['release'],'PERMIT_PARENT_BINDING')
            require(allow_terminal or (not t['terminal'] and r['state']=='OPEN' and s['active']==r['id']),'TERMINAL_OR_BLOCKED_NO_EXECUTION');check_scope(r['scope'],v['kind'],plan)
            require(r['legacy_floor']==self.legacy_floor(),'OTHER_ENTRY_BUDGET_CHANGED')
            return v
    def _task_event(self,job_id,event,payload):
        with file_lock(self.root):
            records,s=self._load();require(job_id in s['tasks'] and not s['tasks'][job_id]['terminal'],'TASK_NOT_ACTIVE');t=s['tasks'][job_id]
            if event=='SESSION':require(t['session_name'] is None and t['hardware_setup'],'SESSION_ALREADY_ALLOCATED_OR_NOT_PREPARED')
            if event=='WORKER':require(not t.get('worker'),'WORKER_ALREADY_BOUND_NO_RESUME')
            if event=='SETUP':require(not t['hardware_setup'],'SETUP_ALREADY_STARTED')
            if event=='RETIRED':require(payload['record_id']==len(t['retired'])+1 and payload['record_id'] in t['attempts'],'RETIRE_ORDER')
            self._append(records,event,dict(payload,job_id=job_id))
    def bind_worker(self,job_id):self._task_event(job_id,'WORKER',dict(identity=process_identity()))
    def mark_setup(self,job_id):self._task_event(job_id,'SETUP',{})
    def bind_session(self,job_id,path):
        p=Path(path).resolve();require(re.fullmatch('session_[0-9a-f]{8}',p.name),'REAL_SESSION_NAME');self._task_event(job_id,'SESSION',dict(session_name=p.name,session_path=str(p)))
    def claim(self,job_id,rid):
        with file_lock(self.root):
            records,s=self._load();t=s['tasks'][job_id];r=s['rounds'][t['round_id']];require(r['state']=='OPEN' and not t['terminal'] and t['hardware_setup'] and t['session_name'] is not None and rid==len(t['attempts'])+1 and len(t['attempts'])<t['limit'] and len(t['attempts'])==len(t['retired']),'NO_RECORD_CREDIT_OR_ORDER');self._append(records,'ATTEMPT',dict(job_id=job_id,record_id=rid))
    def retire(self,job_id,rid):self._task_event(job_id,'RETIRED',dict(record_id=rid))
    def require_record(self,job_id,rid,session_path):
        with file_lock(self.root):
            _,s=self._load();t=s['tasks'][job_id];r=s['rounds'][t['round_id']]
            require(not t['terminal'] and r['state']=='OPEN' and t['hardware_setup'],'RECORD_NOT_ACTIVE')
            if self.mode=='LIVE':require(t.get('worker')==process_identity(),'RECORD_WORKER_IDENTITY_CHANGED')
            require(type(rid) is int and len(t['attempts'])==rid and len(t['retired'])==rid-1,'RECORD_CREDIT_NOT_CLAIMED_OR_REPLAYED')
            require(t['session_path']==str(Path(session_path).resolve()),'RECORD_SESSION_CHANGED')
    def settle(self,job_id,state,cleanup_confirmed,reason='',block=False):
        with file_lock(self.root):
            records,s=self._load();t=s['tasks'][job_id]
            if t['terminal']:return self.task_view(t)
            unknown=len(t['attempts'])-len(t['retired']);self._append(records,'TERMINAL',dict(job_id=job_id,state='BLOCKED_UNKNOWN' if unknown else state,cleanup_confirmed=cleanup_confirmed is True,reason=str(reason)[:1000],block_round=bool(block or unknown or not cleanup_confirmed)))
            _,s=self._load();return self.task_view(s['tasks'][job_id])
    def task(self,job_id):
        with file_lock(self.root):_,s=self._load();t=s['tasks'].get(job_id);return None if t is None else self.task_view(t)

def read_scan_permit(path,plan,assets,runs,stage):
    require(stage in ('local_read_preflight','initialize_namespace_and_receiver','physical_records'),'PERMIT_STAGE')
    root=Path(runs).resolve()/'DEMO_AUTHORITY_V1';p=Path(path).resolve();value=json.loads(p.read_bytes());require(value.get('mode')=='LIVE' and value.get('kind')=='scan','LIVE_SCAN_PARENT_CONSENT_REQUIRED')
    release=value['release'];require(release['runs_directory']==str(Path(runs).resolve()) and release['asset_sha256']=={k:sha(v) for k,v in assets.items()},'PERMIT_ASSETS_RUNS')
    # Receipt location is an installation attribute, never an HTTP field supplied by the operator.
    installation=json.loads((root/'installation.json').read_bytes())
    from installation_state import installed_config
    authority=Authority.for_live(installed_config(runs,installation))
    authority.verify_permit(p,plan);return value,p.read_bytes()

def scan_record_authority(permit,runs):
    root=Path(runs).resolve()/'DEMO_AUTHORITY_V1';installation=json.loads((root/'installation.json').read_bytes())
    from installation_state import installed_config
    return Authority.for_live(installed_config(runs,installation))
