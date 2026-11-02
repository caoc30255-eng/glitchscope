"""Bounded explicit trial executor candidate. Imports perform no hardware IO.

No algorithm, automatic retry, power-on recovery, global reset or billing API.
Each run_next executes exactly one predeclared record through existing admission.
"""
from pathlib import Path
from dataclasses import dataclass,asdict
import threading,json,time
from h1_protocol import Kind
from ch1_completion_ledger import _codec
from ch1_peer_archive_driver import persist_exact
from fault_profile import FaultProfile
from multi_point_profile import MultiPointProfile
from ps_idle_journal_segments import _idle,rotate_idle_journal,verify_sealed_segments
from fault_pilot_workflow import _one
from raw_mark_snapshot import _same_session_buses
import ch1_evidence_store as store


@dataclass(frozen=True)
class TrialRequest:
    client_request_id:str
    d:int
    s:int
    fault:object=None

    def validate(self,inner):
        if (type(self.client_request_id) is not str or not self.client_request_id or
                len(self.client_request_id)>64 or not self.client_request_id.isascii() or
                any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in self.client_request_id)):
            raise ValueError('Unique ASCII client request ID required')
        if type(self.d) is not int or type(self.s) is not int or self.d not in (1,2,3,4) or not -2<=self.s<=3-self.d:
            raise ValueError('Illegal receiver B profile')
        if self.fault is not None:
            if type(self.fault) not in (FaultProfile,MultiPointProfile):raise TypeError('Explicit typed fault profile required')
            self.fault.validate(inner)
        return {'client_request_id':self.client_request_id,'receiver_B':{'d':self.d,'s':self.s},
                'fault':None if self.fault is None else asdict(self.fault)}


class ControlledTrialExecutor:
    """Fresh session, fixed source/plan, maximum four physical record attempts.

    The finite allowance is a test limit including CONFIG, not monetary cost.
    No resume exists: uncertain execution stops the whole instance permanently.
    """
    def __init__(self,session,buses,source,requests,*,max_physical_starts,exclusive_owner=False):
        if exclusive_owner is not True:raise ValueError('Exclusive session ownership required')
        requests=tuple(requests);source=bytes(source)
        if (not 1<=len(requests)<=3 or len(source)!=256*len(requests) or
                type(max_physical_starts) is not int or max_physical_starts!=len(requests)+1):
            raise ValueError('Candidate permits 1..3 ITEM plus CONFIG, with exact finite record allowance')
        if session.current is not None or session.config_owner is not None or session.mark_capture is None or session.mark_capture.used:
            raise RuntimeError('Fresh initialized session and unused mark preflight required')
        _same_session_buses(session,buses)
        _idle(session,buses)
        if buses['SYS'].read(0x18) or buses['SYS'].read(0x1c):
            raise RuntimeError('Fresh executor epoch must have zero actual retirement/grant counters')
        preflight=session.root/'MARK/preflight'
        for name,digest in json.loads((preflight/'committed.json').read_bytes())['files'].items():
            if store.sha((preflight/name).read_bytes())!=digest:raise ValueError('Preflight changed')
        codec=_codec();parts=[source[i:i+256] for i in range(0,len(source),256)]
        specs=[]
        for i,r in enumerate(requests):
            if type(r) is not TrialRequest:raise TypeError('Typed immutable trial requests required')
            inner=codec.encode_item(session.local_epoch,1,1,i,len(parts),0,0,parts[i])
            specs.append(r.validate(inner))
        if len({r.client_request_id for r in requests})!=len(requests):raise ValueError('Duplicate client request ID')
        config=codec.encode_config(session.local_epoch,1,32,len(source)//32,len(source),len(parts),256,
                                   bytes.fromhex(store.sha(source)),[store.crc16(p) for p in parts])
        plan={'schema':'CONTROLLED_TRIAL_PLAN_CANDIDATE_V0_2','local_epoch':session.local_epoch,
              'source_sha256':store.sha(source),'source_bytes':len(source),'requests':specs,
              'max_physical_starts_including_CONFIG':max_physical_starts,
              'production_billing_finalized':False,'automatic_training_allowed':False,
              'scope':'explicit bounded executor candidate; offline/simulation acceptance required before hardware pilot'}
        self.root=session.root/'EXECUTOR'
        self.root.mkdir(parents=True,exist_ok=False) # immutable plan reservation, never resume.
        persist_exact(self.root/'plan',{'plan.json':store._json(plan),'source.bin':source,'config.bin':config})
        self._frozen_plan=store._json(plan);self._frozen_source=source;self._frozen_config=config
        self.session=session;self.buses=buses;self.requests=requests;self.parts=tuple(parts)
        self._lock=threading.Lock();self.index=0;self.stopped=False;self.results=[]
        self.max_attempts=max_physical_starts;self.attempts=0
        session.journal.record('controlled_trial_plan_saved',plan_sha256=store.sha(self._frozen_plan),
                               max_physical_starts=max_physical_starts)

    def _verify_plan(self):
        manifest=json.loads((self.root/'plan/committed.json').read_bytes())
        expected={'plan.json':self._frozen_plan,'source.bin':self._frozen_source,'config.bin':self._frozen_config}
        if set(manifest['files'])!=set(expected):raise ValueError('Plan manifest fields changed')
        for name,raw in expected.items():
            if (self.root/'plan'/name).read_bytes()!=raw or manifest['files'][name]!=store.sha(raw):
                raise ValueError('Immutable executor plan/source changed')
        plan=json.loads(self._frozen_plan)
        parts=tuple(self._frozen_source[i:i+256] for i in range(0,len(self._frozen_source),256))
        if (self.parts!=parts or len(self.requests)!=len(parts) or
                self.max_attempts!=plan['max_physical_starts_including_CONFIG']):
            raise ValueError('In-memory executor source/budget changed')
        specs=[]
        for i,request in enumerate(self.requests):
            if type(request) is not TrialRequest:raise TypeError('Trial request type changed')
            inner=_codec().encode_item(self.session.local_epoch,1,1,i,len(parts),0,0,parts[i])
            specs.append(request.validate(inner))
        if specs!=plan['requests'] or self.session.local_epoch!=plan['local_epoch']:
            raise ValueError('In-memory trial requests or epoch changed')

    def _reserve_trial(self,index):
        registry=self.session.root.parent/'trial_registry';registry.mkdir(exist_ok=True)
        trial=max((int(p.stem.split('_')[1],16) for p in registry.glob('trial_*.json')),default=0)+1
        if not 0<trial<65536:raise RuntimeError('Trial ID exhausted')
        store._write(registry/('trial_%04x.json'%trial),store._json({
            'epoch':self.session.local_epoch,'index':index,'attempt':0,'trial_id':trial,
            'client_request_id':self.requests[index].client_request_id,
            'scope':'controlled_executor_candidate_v0_2'}))
        store._sync_directory(registry)
        return trial

    def run_next(self):
        if not self._lock.acquire(False):raise RuntimeError('Concurrent execution denied')
        entered=False
        try:
            if self.stopped:raise RuntimeError('Executor stopped; no retry/resume')
            if self.index>=self.max_attempts:raise RuntimeError('Finite plan complete; no extra START')
            self._verify_plan();_idle(self.session,self.buses);verify_sealed_segments(self.session)
            rid=self.index+1;trial=None
            if self.index==0:
                kind=Kind.CONFIG;inner=self._frozen_config;d,s=3,-1;fault=None;request_id='CONFIG'
            else:
                i=self.index-1;request=self.requests[i];trial=self._reserve_trial(i)
                inner=_codec().encode_item(self.session.local_epoch,1,trial,i,len(self.parts),0,0,self.parts[i])
                request.validate(inner);kind=Kind.ITEM;d,s=request.d,request.s;fault=request.fault;request_id=request.client_request_id
                rotate_idle_journal(self.session,buses=self.buses,next_record_id=rid)
                if fault is not None and self.session.mark_capture.used:
                    self.session.mark_capture=self.session.mark_capture.successor(self.session,self.buses)
            intent={'schema':'CONTROLLED_TRIAL_ATTEMPT_V0_2','record_id':rid,'client_request_id':request_id,
                    'trial_id':trial,'kind':kind.name,'inner_sha256':store.sha(inner),'d':d,'s':s,
                    'fault':None if fault is None else asdict(fault),'attempt_ordinal':self.attempts+1,
                    'actual_START_confirmed':False,'production_cost_finalized':False}
            directory=self.root/('record_%08x'%rid)
            persist_exact(directory/'intent',{'intent.json':store._json(intent),'request.bin':inner})
            self.session.journal.record('controlled_trial_execution_intent',**intent)
            entered=True;self.attempts+=1
            result=_one(self.session,self.buses,kind,inner,rid,profile=fault,d=d,s=s)
            owner=self.session.last_retired_owner
            if owner is None or owner.phase!='RETIRED' or owner.binding.record_id!=rid:
                raise RuntimeError('Exact retired owner was not retained')
            if fault is not None:self.session.mark_capture.seal_retired(self.session,self.buses)
            applied=json.loads((self.session.root/'admission'/('epoch_%08x_record_%08x'%(
                self.session.local_epoch,rid))/'admission.json').read_bytes())['profile']
            if (applied['d'],applied['s'])!=(d,s) or not applied['RX_profile_verified']:
                raise ValueError('Returned actual B profile differs from plan')
            self._verify_plan();verify_sealed_segments(self.session);_idle(self.session,self.buses)
            valid_report=all(result['CH1_classification'].get(k) is True for k in (
                'capture_valid','raw_frame_crc_and_format_valid','wire_identity_match'))
            result={**result,'schema':'CONTROLLED_TRIAL_RESULT_V0_2','client_request_id':request_id,
                    'requested_receiver_B':{'d':d,'s':s},'actual_receiver_B':applied,
                    'identity_hex':'%064x'%owner.binding.identity,
                    'trial_id':trial,'evidence_quality':'VALID' if valid_report else 'INVALID_REPORT',
                    'receiver_A_frame_correct':all(result['CH0_classification'][k] for k in ('a_source_match','a_reception_success')),
                    'receiver_B_frame_correct':all(result['CH0_classification'][k] for k in ('b_source_match','b_reception_success')),
                    'STM_business_success':result['business_success'],'next_trial_allowed_by_plan':rid<self.max_attempts and valid_report,
                    'production_billing_finalized':False,'training_authorized':False}
            persist_exact(directory/'result',{'result.json':store._json(result)})
            self.session.journal.record('controlled_trial_result_saved',record_id=rid,
                                        result_sha256=store.sha(store._json(result)))
            self.results.append(result);self.index+=1
            if not valid_report:
                self.stopped=True
                self.session._stop(RuntimeError('Invalid report evidence blocks remaining plan'))
            return result
        except Exception as exc:
            if not self.stopped and self.index<self.max_attempts:
                self.stopped=True;self.session._stop(exc)
                current=self.session.current
                if current is None:
                    last=self.session.last_retired_owner
                    current=last if last is not None and last.binding.record_id==self.index+1 else None
                # An attempted record may have acted. Never label timeout a free/nonexecuted trial.
                diagnostic={'error':repr(exc),'record_ordinal':self.index+1,'entered_record_execution':entered,
                            'execution_effect':'UNKNOWN' if entered else 'NO_RECORD_EXECUTION_BY_THIS_CALL',
                            'label':None,'automatic_retry_allowed':False,'attempts_reserved':self.attempts}
                diagnostic.update(actual_start_confirmed=bool(getattr(current,'started',False)),
                                  actual_done_confirmed=bool(getattr(current,'done',False)),
                                  known_started_or_done_lower_bound=int(bool(getattr(current,'started',False) or getattr(current,'done',False))))
                persist_exact(self.root/('STOP_'+__import__('uuid').uuid4().hex),{'diagnostic.json':store._json(diagnostic)})
            raise
        finally:self._lock.release()

    def cancel_remaining(self):
        if not self._lock.acquire(False):raise RuntimeError('Cannot cancel active execution')
        try:
            if self.stopped:raise RuntimeError('Already stopped')
            self._verify_plan();_idle(self.session,self.buses)
            persist_exact(self.root/'cancelled',{'cancel.json':store._json({
                'completed_records':self.index,'unstarted_records_cancelled':self.max_attempts-self.index,
                'refund_or_new_quota_created':False,'hardware_writes':0})})
            self.stopped=True
        finally:self._lock.release()
