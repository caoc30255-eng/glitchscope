"""Fixed-profile custom execution adapter; current actual hardware authorization is zero."""
import copy,hashlib,json,threading
from pathlib import Path
from active14_bootstrap import bind
ROOT=bind()
from custom_plan import validate_plan,require,raw,CONFIRMATION,TARGETS
from custom_executor import CustomExecutor
from custom_feedback import CustomFeedback
from custom_monitor import CustomMonitor
from custom_refine import suggest
from learning_domain import digest
from ps_candidate_session import CandidateSession
from ch1_peer_archive_driver import persist_exact
from ps_idle_journal_segments import _idle,verify_sealed_segments

TERMINAL={'STOPPED','STOPPED_PLAN_COMPLETE','STOPPED_BUDGET','STOPPED_PREPARATION_FAILED','BLOCKED_UNKNOWN','BLOCKED_INPUT'}

class CustomOwner:
    def __init__(self,session,buses,board_lock,plan,*,execution_context=None):
        validate_plan(plan)
        self.execution_context=execution_context;self._execution_context=execution_context;self._final_counters=None
        if isinstance(session,CandidateSession):
            from custom_authorization import ExecutionContext
            require(type(execution_context) is ExecutionContext,'LIVE_EXECUTION_REQUIRES_REVIEWED_ASSEMBLY')
            execution_context.verify(plan,session,board_lock)
        else:require(execution_context is None,'MODEL_CANNOT_USE_LIVE_PERMISSION')
        self.origin='PYNQ_HARDWARE_CANDIDATE' if execution_context else 'REGISTER_DRIVER_MODEL'
        import fcntl
        require(not board_lock.closed and Path(board_lock.name).resolve()==(session.root.parent/'exclusive.lock').resolve(),'CURRENT_EXCLUSIVE_LOCK')
        fcntl.flock(board_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        self.session=session;self.buses=buses;self.board_lock=board_lock;self.epoch=session.local_epoch
        self._plan=copy.deepcopy(plan);self._plan_bytes=raw(plan)
        self.executor=CustomExecutor(session,buses,plan,exclusive_owner=True);self.executor.claim(self)
        self.monitor=CustomMonitor(self.executor,plan,hardware=execution_context is not None);self.feedback=CustomFeedback(self.executor)
        self.root=session.root/'CUSTOM_SCAN';self.root.mkdir(exist_ok=False)
        code=list(ROOT.glob('custom_*.py'))+list((ROOT/'runtime').rglob('*.py'))+[ROOT/n for n in ('boundary_rule.py','learning_domain.py','conservative_model.py','active14_bootstrap.py')]
        if plan['request'].get('edge_ai'):
            from custom_ai_policy import model_for
            model_for(plan['request']['edge_ai'])
            if plan['request']['edge_ai']['strategy']=='EDGE_AI_OSS_ENTROPY_COVERAGE_V1':
                code.extend([ROOT/'oss_policy.py',*list((ROOT/'oss_runtime').rglob('*.py'))])
                code.append(ROOT/'oss_runtime/models'/(plan['request']['edge_ai']['model_file_sha256']+'.json'))
            else:code.append(ROOT/'models'/(plan['request']['edge_ai']['model_file_sha256']+'.json'))
        self._code={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in code}
        self._scope=dict(plan_sha256=plan['sha256'],source_sha256=plan['source_sha256'],epoch=self.epoch,session=session.root.name,
            origin=self.origin,new_physical_STARTs=0,code_sha256={p.relative_to(ROOT).as_posix():v for p,v in self._code.items()})
        self.refs=[];self._save('scope','scope.json',self._scope)
        self.receipts=[];self.decisions=[];self._queue=copy.deepcopy(plan['initial_queue']);self._cursor=0
        self._runtime_snapshot=digest(dict(receipts=[],decisions=[],queue=self._queue,cursor=0))
        self._keys={};self._keys_snapshot=digest({});self._lock=threading.Lock();self._stop=threading.Event();self.state='READY';self.cleanup=None
    @property
    def plan(self):return copy.deepcopy(self._plan)
    def _save(self,directory,name,value):
        path=self.root/directory;persist_exact(path,{name:raw(value)})
        for f in (path/name,path/'committed.json'):self.refs.append((f,hashlib.sha256(f.read_bytes()).hexdigest()))
        return dict(path=(path/name).relative_to(self.session.root).as_posix(),sha256=hashlib.sha256((path/name).read_bytes()).hexdigest())
    def _snapshot(self):return digest(dict(receipts=self.receipts,decisions=self.decisions,queue=self._queue,cursor=self._cursor))
    def _verify(self):
        require(self.execution_context is self._execution_context and self.session is self.executor.session,'EXECUTION_CONTEXT_CHANGED')
        require(raw(self._plan)==self._plan_bytes and json.loads(self.executor._schedule)==self._plan,'PLAN_RUNTIME_CHANGED')
        require(not self.board_lock.closed and self.session.local_epoch==self.epoch,'SESSION_EPOCH_OR_LOCK_CHANGED')
        if self.execution_context:self.execution_context.verify(self._plan,self.session,self.board_lock)
        require(self._snapshot()==self._runtime_snapshot,'RUNTIME_FEEDBACK_OR_QUEUE_CHANGED')
        require(digest(self._keys)==self._keys_snapshot,'OPERATION_CACHE_CHANGED')
        self.executor._verify_plan();self.monitor._verify();self.session.journal.verify()
        require(self.executor.index==len(self.receipts) and self.executor.attempts==self.executor.index,'UNRESOLVED_OR_EXTERNAL_EXECUTION')
        for p,expected in list(self._code.items())+self.refs:require(hashlib.sha256(p.read_bytes()).hexdigest()==expected,'CODE_OR_FROZEN_EVIDENCE_CHANGED')
        for rid,receipt in enumerate(self.receipts,1):require(self.feedback._feedback(rid)==receipt,'RAW_FEEDBACK_CHANGED')
    def start_once(self,key,confirmation=CONFIRMATION):
        require(type(key) is str and 8<=len(key)<=128,'OPERATION_KEY')
        require(digest(self._keys)==self._keys_snapshot,'OPERATION_CACHE_CHANGED')
        if 'start' in self._keys:
            require(self._keys['start']['confirmation']==confirmation,'IDEMPOTENCY_CONFLICT')
            require(self._keys['start']['key']==key,'ALREADY_STARTED_NO_RESUME');return copy.deepcopy(self._keys['start'])
        require(self.state=='READY' and confirmation==CONFIRMATION,'OFFLINE_START_ONLY')
        try:self._verify()
        except BaseException as error:
            self.state='BLOCKED_INPUT';self.executor.stopped=True
            self._save('blocked','diagnostic.json',dict(reason=repr(error),attempts=self.executor.attempts,valid_receipts=len(self.receipts),labels=None,next_START_allowed=False))
            self._close();raise
        receipt=dict(key=key,confirmation=confirmation,plan_sha256=self._plan['sha256'],state='RUNNING',hardware_permission=bool(self.execution_context))
        self._save('start','intent.json',receipt);self._keys['start']=receipt;self._keys_snapshot=digest(self._keys);self.state='RUNNING';return copy.deepcopy(receipt)
    def next_suggestion(self,target=None):
        require(self.state not in TERMINAL,'TERMINAL_NO_SELECTION')
        self._verify();return suggest(self._plan,self.checked_records(),self.session.root.name,self._plan['max_records']-self.executor.attempts,
            target=target,confirmed_domain_sha256=digest(self._plan['conditions']))
    def step(self,key,selection=None):
        require(type(key) is str and 8<=len(key)<=128,'OPERATION_KEY')
        request=digest(dict(key=key,selection=selection))
        require(digest(self._keys)==self._keys_snapshot,'OPERATION_CACHE_CHANGED')
        if key in self._keys:
            require(self._keys[key]['request']==request,'IDEMPOTENCY_CONFLICT');return copy.deepcopy(self._keys[key]['result'])
        require(self.state in ('RUNNING','AWAITING_SELECTION'),'TERMINAL_OR_NOT_STARTED')
        require(self._lock.acquire(False),'OWNER_BUSY')
        try:
            self._verify()
            if self._stop.is_set():return self._finish('STOPPED')
            if self.executor.attempts>=self._plan['max_records']:return self._finish('STOPPED_PLAN_COMPLETE' if not self._plan['refinement']['enabled'] and self._cursor>=len(self._queue) else 'STOPPED_BUDGET')
            if self.executor.index>=2 and self._cursor>=len(self._queue):
                if not self._plan['refinement']['enabled']:return self._finish('STOPPED_PLAN_COMPLETE')
                expected=self.next_suggestion()
                if self._plan['request'].get('edge_ai') and expected['action'] in ('ABSTAIN','WAIT'):
                    raise ValueError('AI_SELECTION_BLOCKED:'+expected.get('reason','UNKNOWN'))
                if expected['action']!='SELECT':return self._finish('STOPPED_BUDGET' if expected['action']=='STOP_BUDGET' else 'STOPPED_PLAN_COMPLETE')
                if selection is None:self.state='AWAITING_SELECTION';return self.status()
                require(selection==expected,'STALE_OR_CHANGED_SELECTION')
                self._save('selections/selection_%03d'%len(self.decisions),'selection.json',selection)
                cid=selection['condition_id'];start=1+sum(q['condition_id']==cid for q in self._queue)
                self._queue.extend(dict(condition_id=cid,repeat=start+i,selection_sha256=selection['selection_sha256']) for i in range(selection['required_records']))
                self._runtime_snapshot=self._snapshot();self.state='RUNNING'
            else:require(selection is None,'SELECTION_ONLY_AT_REFINEMENT_BOUNDARY')
            rid=self.executor.index+1;slot=None if rid<=2 else self._queue[self._cursor]
            c=None if slot is None else next(c for c in self._plan['conditions'] if c['condition_id']==slot['condition_id'])
            kind='CONFIG' if rid==1 else 'CONTROL' if rid==2 else 'ITEM'
            b=self._plan['preparation'][rid-1]['receiver_B'] if rid<=2 else c['receiver_B']
            command=dict(record_id=rid,kind=kind,point_id=None if c is None else c['condition_id'],condition_sha256=None if c is None else c['condition_sha256'],
                fault=None if c is None else c['fault'],receiver_B=b,repeat=None if slot is None else slot['repeat'],epoch=self.epoch,
                session=self.session.root.name,plan_sha256=hashlib.sha256(self.executor._frozen_plan).hexdigest())
            decision=dict(command=command,domain_sha256=digest(self._plan['conditions']),input_sha256=digest(self.receipts),
                input_records=[dict(record_id=r['record_id'],identity_hex=r['identity_hex'],result_sha256=r['result_sha256']) for r in self.receipts],
                selection_sha256=None if slot is None else slot.get('selection_sha256'),reason='COMPILED_COARSE_QUEUE' if slot is None or not slot.get('selection_sha256') else 'CONFIRMED_REFINEMENT',hardware_permission=bool(self.execution_context))
            decision_ref=self._save('decisions/record_%03d'%rid,'decision.json',decision)
            permit=dict(command_sha256=digest(command),expected_completed_records=self.executor.index,epoch=self.epoch,decision=decision_ref)
            permit['commit_sha256']=digest(permit);permit_ref=self._save('permits/record_%03d'%rid,'permit.json',dict(command=command,permit=permit))
            # Both source commitments are checked again immediately before binding.
            self._verify();self.executor.bind_next(self,command,permit,dict(decision_source=decision_ref,permit_source=permit_ref))
            self.executor.execute_bound(self);receipt=self.feedback._feedback(rid)
            self._save('feedback/record_%03d'%rid,'feedback.json',receipt);self.receipts.append(receipt);self.decisions.append(decision)
            if slot is not None:self._cursor+=1
            self._runtime_snapshot=self._snapshot()
            if rid<=2 and not (all(receipt['labels'][t] is True for t in ('A_correct','B_correct','STM_success')) and (rid==1 or receipt['labels']['STM_payload_correct'] is True)):
                result=self._finish('STOPPED_PREPARATION_FAILED')
            elif self._stop.is_set():result=self._finish('STOPPED')
            else:result=self.status()
            entry=dict(request=request,result=copy.deepcopy(result));self._save('operations/record_%03d'%rid,'receipt.json',dict(key=key,**entry));self._keys[key]=entry;self._keys_snapshot=digest(self._keys)
            return result
        except BaseException as error:
            self.state='BLOCKED_UNKNOWN' if self.executor.attempts>len(self.receipts) else 'BLOCKED_INPUT';self.executor.stopped=True
            self._save('blocked','diagnostic.json',dict(reason=repr(error),attempts=self.executor.attempts,valid_receipts=len(self.receipts),labels=None,next_START_allowed=False))
            self.session._stop(error);self._close();return self.status()
        finally:self._lock.release()
    def run(self,key):
        require(self.state not in TERMINAL,'TERMINAL_NO_RUN')
        self.start_once(key)
        while self.state=='RUNNING':self.step('%s_step_%03d'%(key,self.executor.index+1))
        return self.status()
    def request_stop(self):
        require(self.state not in TERMINAL,'TERMINAL_NO_RESUME');self._stop.set()
        if self._lock.acquire(False):
            try:self._finish('STOPPED')
            finally:self._lock.release()
    def _finish(self,state):
        _idle(self.session,self.buses);verify_sealed_segments(self.session)
        if not self.executor.stopped:self.executor.cancel_remaining()
        self.state=state;self._close();self._save('terminal','summary.json',self.status());return self.status()
    def _close(self):
        if self.cleanup is not None:return
        closed=lambda h:bool(getattr(h,'closed',getattr(getattr(h,'file',None),'closed',False)))
        before=dict(lock_closed=self.board_lock.closed,handles_closed=[closed(h) for h in self.session.handles])
        errors=[]
        try:self._final_counters=dict(strict_retired=self.buses['SYS'].read(0x18),grants=self.buses['SYS'].read(0x1c))
        except Exception as error:
            self._final_counters=dict(strict_retired=None,grants=None);errors.append(repr(error))
        try:
            transport=self.session.control_transport
            if getattr(transport,'context',None):self._save('cleanup_receiver','state.json',transport.pending_snapshot(limit=65536))
        except Exception as error:errors.append(repr(error))
        try:self.session.control_transport.close()
        except Exception as error:errors.append(repr(error))
        for h in self.session.handles:
            try:h.close()
            except Exception as error:errors.append(repr(error))
        try:self.board_lock.close()
        except Exception as error:errors.append(repr(error))
        self.cleanup=dict(before=before,after=dict(lock_closed=self.board_lock.closed,handles_closed=[closed(h) for h in self.session.handles],receiver_close_called=True),errors=errors,global_reset=False)
        self._save('cleanup','state.json',self.cleanup)
    def confirmation_groups(self):
        groups={}
        for i,q in enumerate(self._queue):
            sha=q.get('selection_sha256')
            if not sha:continue
            g=groups.setdefault(sha,dict(selection_sha256=sha,condition_id=q['condition_id'],required=0,executed=0,valid=0,unknown=0,cancelled=0,complete=False))
            g['required']+=1
            # Queue position i maps to record i+3, including an attempted UNKNOWN.
            rid=i+3
            if rid<=self.executor.attempts:g['executed']+=1
            if rid<=len(self.receipts):g['valid']+=1
            elif rid<=self.executor.attempts:g['unknown']+=1
        for g in groups.values():
            g['cancelled']=g['required']-g['executed'] if self.state in TERMINAL else 0
            g['complete']=g['valid']==g['required']
        return list(groups.values())

    def status(self):
        return dict(state=self.state,plan_sha256=self._plan['sha256'],session=self.session.root.name,epoch=self.epoch,origin=self.origin,
            attempts=self.executor.attempts,valid_records=len(self.receipts),max_records=self._plan['max_records'],remaining_records=self._plan['max_records']-self.executor.attempts,
            confirmation_groups=self.confirmation_groups(),completed_coarse_records=min(self._cursor,len(self._plan['initial_queue'])),coarse_records=len(self._plan['initial_queue']),cleanup=copy.deepcopy(self.cleanup),
            execution_plan_complete=self.state in ('STOPPED','STOPPED_BUDGET','STOPPED_PLAN_COMPLETE'),
            new_physical_STARTs=(None if self.executor.attempts>len(self.receipts) else len(self.receipts)) if self.execution_context else 0,
            physical_STARTs_known_lower_bound=len(self.receipts) if self.execution_context else 0,
            physical_START_count_scope='VALID_STRICTLY_RETIRED_LOWER_BOUND_UNKNOWN_ATTEMPTS_NOT_INVENTED' if self.execution_context else 'MODEL_NO_PHYSICAL_START',
            strict_retired=(self._final_counters['strict_retired'] if self._final_counters is not None else self.buses['SYS'].read(0x18)),grants=(self._final_counters['grants'] if self._final_counters is not None else self.buses['SYS'].read(0x1c)),cancelled_unstarted=self._plan['max_records']-self.executor.attempts if self.state in TERMINAL else 0)
    def checked_records(self):
        rows=[];root=self.session.root
        for rid,receipt in enumerate(self.receipts,1):
            binding=self.executor.bindings[rid];cmd=binding['command'];labels=receipt['labels'];suffix='epoch_%08x_record_%08x'%(self.epoch,rid)
            directories=[self.executor.root/('record_%08x'%rid),root/'CH0'/suffix,root/'CH1/main'/suffix,root/'admission'/suffix,root/'MPG1_SCAN'/('record_%08x'%rid),root/'TYPE3C'/suffix]
            if rid>=3:directories.append(root/'MARK'/suffix)
            refs=[dict(path=f.relative_to(root).as_posix(),bytes=f.stat().st_size,sha256=hashlib.sha256(f.read_bytes()).hexdigest()) for d in directories for f in sorted(d.rglob('*')) if f.is_file()]
            rows.append(dict(uid=digest(dict(session=root.name,identity=receipt['identity_hex'])),session=root.name,epoch=self.epoch,record_id=rid,kind=cmd['kind'],
                identity_hex=receipt['identity_hex'],trial_id=self.executor.results[rid-1].get('trial_id'),status='VALID',strict_retired=True,actual_READY_saved=True,
                condition_id=cmd['point_id'],condition_sha256=cmd['condition_sha256'],requested_receiver_B=cmd['receiver_B'],actual_receiver_B=receipt['actual_receiver_B'],
                selection_sha256=self.decisions[rid-1]['selection_sha256'],
                fault=cmd['fault'],payload_sha256=self._plan['payload_sha256'],route_mode=0,mode=self._plan['mode'],
                labels=dict(B_frame_correct=labels['B_correct'],STM_payload_correct=labels['STM_payload_correct'],STM_business_success=labels['STM_success']),
                result_sha256=receipt['result_sha256'],evidence=refs))
        if self.executor.attempts>len(rows):
            rid=len(rows)+1;cmd=self.executor.bindings[rid]['command'];path=self.root/'blocked/diagnostic.json'
            rows.append(dict(uid=digest(dict(session=root.name,unknown_record=rid)),session=root.name,epoch=self.epoch,record_id=rid,kind=cmd['kind'],identity_hex=None,trial_id=None,
                status='UNKNOWN',strict_retired=False,actual_READY_saved=False,selection_sha256=json.loads((root/self.executor.bindings[rid]['external_proof']['decision_source']['path']).read_bytes())['selection_sha256'],condition_id=cmd['point_id'],condition_sha256=cmd['condition_sha256'],requested_receiver_B=cmd['receiver_B'],
                actual_receiver_B=dict(d=None,s=None,RX_profile_verified=False),fault=cmd['fault'],payload_sha256=self._plan['payload_sha256'],route_mode=0,mode=self._plan['mode'],
                labels={t:None for t in TARGETS},result_sha256=None,evidence=[dict(path=path.relative_to(root).as_posix(),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),bytes=path.stat().st_size)]))
        return rows
