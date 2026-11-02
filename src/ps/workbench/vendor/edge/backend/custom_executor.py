"""Compiled custom-condition capacity and one-use dynamic record bindings.

The reviewed ControlledTrialExecutor.run_next and original drivers are unchanged.
"""
from pathlib import Path
import json,threading
from active14_bootstrap import bind
ROOT=bind()
from controlled_trial_executor import ControlledTrialExecutor,TrialRequest
from fault_profile import FaultProfile
from ch1_completion_ledger import _codec
from ch1_peer_archive_driver import persist_exact
from raw_mark_snapshot import _same_session_buses
from ps_idle_journal_segments import _idle
import ch1_evidence_store as store
from custom_plan import typed_profile,validate_plan
from learning_domain import digest
from custom_plan import raw

class CustomExecutor(ControlledTrialExecutor):
    def __init__(self,session,buses,schedule,*,exclusive_owner=False):
        if exclusive_owner is not True:raise ValueError('EXCLUSIVE_OWNER_REQUIRED')
        if (session.fault or session.current is not None or session.config_owner is not None or
            session.mark_capture is None or session.mark_capture.used):raise RuntimeError('FRESH_INITIALIZED_SESSION_REQUIRED')
        _same_session_buses(session,buses);_idle(session,buses)
        if buses['SYS'].read(0x18) or buses['SYS'].read(0x1c):raise RuntimeError('FRESH_COUNTERS_REQUIRED')
        pf=session.root/'MARK/preflight'
        manifest=json.loads((pf/'committed.json').read_bytes())['files']
        if not manifest:raise ValueError('PREFLIGHT_MISSING')
        for name,proof in manifest.items():
            p=(pf/name).resolve()
            if pf.resolve() not in p.parents or store.sha(p.read_bytes())!=proof:raise ValueError('PREFLIGHT_CHANGED')
        from custom_plan import typed_profile,validate_plan
        validate_plan(schedule)
        source=bytes.fromhex(schedule['payload_hex'])*schedule['item_total'];parts=tuple(source[i:i+256] for i in range(0,len(source),256))
        config=_codec().encode_config(session.local_epoch,1,32,len(source)//32,len(source),schedule['item_total'],256,
            bytes.fromhex(store.sha(source)),[store.crc16(p) for p in parts])
        domain=schedule
        plan=dict(schema='BOUNDARY_RULE_SCAN_EXECUTOR_V0_1',local_epoch=session.local_epoch,
            source_sha256=store.sha(source),source_bytes=len(source),width=32,height=len(source)//32,
            max_physical_starts_including_CONFIG=domain['max_records'],domain=domain,
            coordinates='PER_RECORD_COMMITTED_BINDING_ONLY',automatic_retry=False,
            production_billing_finalized=False,automatic_training_allowed=False)
        self.root=session.root/'EXECUTOR';self.root.mkdir(exist_ok=False)
        persist_exact(self.root/'plan',{'plan.json':store._json(plan),'source.bin':source,'config.bin':config})
        self._frozen_plan=store._json(plan);self._frozen_source=source;self._frozen_config=config
        self._schedule=store._json(domain);self._epoch=session.local_epoch
        self.session=session;self.buses=buses;self.parts=parts;self.requests=[None]*domain['item_total']
        self._lock=threading.Lock();self.index=0;self.attempts=0;self.max_attempts=domain['max_records']
        self.stopped=False;self.results=[];self.bindings={};self._pending=None
        self._bound_raw={};self._permit_shas=set();self._bridge_owner=None
        session.journal.record('dynamic_domain_plan_saved',plan_sha256=store.sha(self._frozen_plan),
            max_physical_starts=domain['max_records'],source_sha256=store.sha(source))

    def claim(self,owner):
        if self._bridge_owner is not None or self.bindings or self.index:raise RuntimeError('FRESH_SINGLE_BRIDGE_REQUIRED')
        self._bridge_owner=owner

    def bind_next(self,owner,command,permit,proof):
        if owner is not self._bridge_owner or self._pending is not None or self.stopped:
            raise RuntimeError('EXCLUSIVE_ONE_USE_BINDING_REQUIRED')
        self._verify_plan()
        self._verify_external(proof,command,permit)
        rid=self.index+1
        if command['record_id']!=rid or rid in self.bindings or rid>self.max_attempts:raise ValueError('DYNAMIC_INDEX_OR_REPLAY')
        if (permit['commit_sha256'] in self._permit_shas or permit['command_sha256']!=digest(command) or
            permit['commit_sha256']!=digest({k:v for k,v in permit.items() if k!='commit_sha256'}) or
            permit['expected_completed_records']!=self.index or permit['epoch']!=self._epoch or
            command['epoch']!=self._epoch or command['session']!=self.session.root.name or
            command['plan_sha256']!=store.sha(self._frozen_plan)):
            raise ValueError('DYNAMIC_PERMIT_REPLAY_OR_COMMAND_CHANGED')
        if rid==1:
            if command['kind']!='CONFIG' or command['fault'] is not None or command['receiver_B']!=dict(d=3,s=-1):raise ValueError('EXACT_CONFIG_SLOT_REQUIRED')
            request=None
        elif rid==2:
            if command['kind']!='CONTROL' or command['fault'] is not None or command['receiver_B']!=json.loads(self._schedule)['receiver_B']:raise ValueError('EXACT_CONTROL_SLOT_REQUIRED')
            b=json.loads(self._schedule)['receiver_B'];request=TrialRequest('custom_control',b['d'],b['s'],None)
        else:
            schedule=json.loads(self._schedule);condition=next((c for c in schedule['conditions'] if c['condition_id']==command['point_id']),None)
            if condition is None or command['fault']!=condition['fault'] or command.get('condition_sha256')!=condition['condition_sha256'] or command['receiver_B']!=condition['receiver_B'] or command['kind']!='ITEM':raise ValueError('FULL_CONDITION_OUTSIDE_FROZEN_PLAN')
            if type(command['repeat']) is not int or not 1<=command['repeat']<=self.max_attempts:raise ValueError('INVALID_REPEAT')
            b=condition['receiver_B'];request=TrialRequest('custom_%02d_%s'%(rid,condition['condition_id']),b['d'],b['s'],typed_profile(condition))
        if request is not None:
            request.validate(_codec().encode_item(self._epoch,1,1,rid-2,len(self.parts),0,0,self.parts[rid-2]))
        value=dict(schema='DYNAMIC_RECORD_BINDING_V0_2',record_id=rid,command=command,
            permit=permit,external_proof=proof,request_spec=None if request is None else request.validate(
                _codec().encode_item(self._epoch,1,1,rid-2,len(self.parts),0,0,self.parts[rid-2])))
        data=store._json(value);directory=self.root/'dynamic_bindings'/('record_%08x'%rid)
        persist_exact(directory,{'binding.json':data})
        self._bound_raw[rid]=data;self.bindings[rid]=json.loads(data)
        if request is not None:self.requests[rid-2]=request
        self._permit_shas.add(permit['commit_sha256']);self._pending=rid
        self.session.journal.record('dynamic_record_bound_before_execution',record_id=rid,
            binding_sha256=store.sha(data),command_sha256=digest(command))

    def _verify_plan(self):
        manifest=json.loads((self.root/'plan/committed.json').read_bytes())['files']
        expected={'plan.json':self._frozen_plan,'source.bin':self._frozen_source,'config.bin':self._frozen_config}
        if manifest!={n:store.sha(v) for n,v in expected.items()}:raise ValueError('DYNAMIC_PLAN_MANIFEST_CHANGED')
        for n,v in expected.items():
            if (self.root/'plan'/n).read_bytes()!=v:raise ValueError('DYNAMIC_PLAN_OR_SOURCE_CHANGED')
        plan=json.loads(self._frozen_plan)
        schedule=json.loads(self._schedule);validate_plan(schedule)
        if (plan['domain']!=schedule or self.max_attempts!=schedule['max_records'] or self.session.local_epoch!=self._epoch or len(self.requests)!=schedule['item_total'] or self.parts!=tuple(self._frozen_source[i:i+256] for i in range(0,len(self._frozen_source),256))):raise ValueError('DYNAMIC_MEMORY_DOMAIN_CHANGED')
        if set(self.bindings)!=set(self._bound_raw) or set(self.bindings) not in (set(range(1,self.index+1)),set(range(1,self.index+2))):
            raise ValueError('DYNAMIC_BINDING_SEQUENCE_CHANGED')
        for rid,data in self._bound_raw.items():
            d=self.root/'dynamic_bindings'/('record_%08x'%rid)
            if ((d/'binding.json').read_bytes()!=data or
                json.loads((d/'committed.json').read_bytes())['files']!={'binding.json':store.sha(data)} or
                store._json(self.bindings[rid])!=data):raise ValueError('DYNAMIC_BINDING_CHANGED')
            self._verify_external(self.bindings[rid]['external_proof'],self.bindings[rid]['command'],self.bindings[rid]['permit'])
            if rid>=2:
                r=self.requests[rid-2]
                if type(r) is not TrialRequest or r.validate(_codec().encode_item(self._epoch,1,1,rid-2,len(self.parts),0,0,self.parts[rid-2]))!=self.bindings[rid]['request_spec']:
                    raise ValueError('DYNAMIC_REQUEST_CHANGED')
        for i,r in enumerate(self.requests):
            if i+2 not in self.bindings and r is not None:raise ValueError('UNCOMMITTED_FUTURE_REQUEST')

    def run_next(self):
        if getattr(self,'_active_owner_thread',None)!=threading.get_ident():raise RuntimeError('EXTERNAL_RUN_NEXT_DENIED')
        if self._pending!=self.index+1:raise RuntimeError('DIRECT_EXECUTION_WITHOUT_DYNAMIC_BINDING_DENIED')
        self._pending=None
        return super().run_next()

    def execute_bound(self,owner):
        if owner is not self._bridge_owner or getattr(self,'_active_owner_thread',None) is not None:raise RuntimeError('EXCLUSIVE_BOUND_OWNER_REQUIRED')
        if getattr(owner,'execution_context',None) is not None:
            owner.execution_context.verify_record(owner.plan,self.session,owner.board_lock,self.index+1)
        self._active_owner_thread=threading.get_ident()
        try:return self.run_next()
        finally:self._active_owner_thread=None

    def _verify_external(self,proof,command,permit):
        values={}
        for role in ('decision_source','permit_source'):
            ref=proof[role];path=(self.session.root/ref['path']).resolve()
            if self.session.root.resolve() not in path.parents:raise ValueError('PROOF_OUTSIDE_CURRENT_SESSION')
            data=path.read_bytes()
            if store.sha(data)!=ref['sha256'] or json.loads((path.parent/'committed.json').read_bytes())['files']!={path.name:ref['sha256']}:raise ValueError('EXTERNAL_COMMITMENT_CHANGED')
            values[role]=json.loads(data)
        if values['decision_source']['command']!=command or values['permit_source']!=dict(command=command,permit=permit):raise ValueError('EXTERNAL_DECISION_PERMIT_MISMATCH')
