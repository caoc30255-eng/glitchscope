"""Separate 12-record image allowance; old four-record executor stays frozen."""
from pathlib import Path
import json,threading
from controlled_trial_executor import ControlledTrialExecutor,TrialRequest
from fault_profile import FaultProfile
from scan_plan import validate_schedule
from raw_mark_snapshot import _same_session_buses
from ps_idle_journal_segments import _idle
from ch1_completion_ledger import _codec
from ch1_peer_archive_driver import persist_exact
import ch1_evidence_store as store

class BoundedScanExecutor(ControlledTrialExecutor):
    def __init__(self,session,buses,source,schedule,*,exclusive_owner=False):
        if exclusive_owner is not True:raise ValueError('Exclusive ownership required')
        validate_schedule(schedule);source=bytes(source)
        if source!=bytes(range(256))*11 or store.sha(source)!=schedule['source_sha256']:raise ValueError('Exact fixed 11-block scan source SHA required')
        if (session.fault or session.current is not None or session.config_owner is not None or
                session.mark_capture is None or session.mark_capture.used):
            raise RuntimeError('Fresh initialized session and unarmed CH2 preflight required')
        _same_session_buses(session,buses);_idle(session,buses)
        if buses['SYS'].read(0x18) or buses['SYS'].read(0x1c):raise RuntimeError('Fresh epoch counters required')
        preflight=session.root/'MARK/preflight'
        for name,digest in json.loads((preflight/'committed.json').read_bytes())['files'].items():
            if store.sha((preflight/name).read_bytes())!=digest:raise ValueError('CH2 preflight changed')
        requests=tuple(TrialRequest(e['client_request_id'],e['receiver_B']['d'],e['receiver_B']['s'],
            None if e['profile'] is None else FaultProfile(**e['profile'])) for e in schedule['items'])
        codec=_codec();parts=tuple(source[i:i+256] for i in range(0,2816,256))
        specs=[r.validate(codec.encode_item(session.local_epoch,1,1,i,11,0,0,parts[i])) for i,r in enumerate(requests)]
        config=codec.encode_config(session.local_epoch,1,32,88,2816,11,256,
            bytes.fromhex(schedule['source_sha256']),[store.crc16(p) for p in parts])
        plan={'schema':'BOUNDED_AUTOTUNE_EXECUTOR_V0_1','local_epoch':session.local_epoch,
            'source_sha256':schedule['source_sha256'],'source_bytes':2816,'width':32,'height':88,
            'requests':specs,'max_physical_starts_including_CONFIG':12,
            'random_schedule_sha256':store.sha(store._json(schedule)),
            'automatic_training_allowed':False,'production_billing_finalized':False,
            'scope':'Fixed phase15/width20, feedback-gated d3 evaluation, d4 candidate, fresh-record validation; separate from four-record tuning loop; no automatic retry'}
        self.root=session.root/'EXECUTOR';self.root.mkdir(exist_ok=False)
        persist_exact(self.root/'plan',{'plan.json':store._json(plan),'source.bin':source,'config.bin':config})
        persist_exact(self.root/'random_schedule',{'schedule.json':store._json(schedule)})
        self._frozen_plan=store._json(plan);self._frozen_source=source;self._frozen_config=config
        self._schedule=store._json(schedule);self.session=session;self.buses=buses
        self.requests=requests;self.parts=parts;self._lock=threading.Lock()
        self.index=0;self.stopped=False;self.results=[];self.max_attempts=12;self.attempts=0
        self._policy_owner=None;self._policy_permit=None
        session.journal.record('real_scan_plan_saved',plan_sha256=store.sha(self._frozen_plan),
            random_schedule_sha256=store.sha(self._schedule),stages=3,max_physical_starts=12)

    def _verify_plan(self):
        super()._verify_plan()
        if self.max_attempts!=12 or len(self._frozen_source)!=2816:
            raise ValueError('Bounded image allowance changed')
        directory=self.root/'random_schedule'
        if ((directory/'schedule.json').read_bytes()!=self._schedule or
                json.loads((directory/'committed.json').read_bytes())['files']!={'schedule.json':store.sha(self._schedule)} or
                json.loads(self._frozen_plan)['random_schedule_sha256']!=store.sha(self._schedule)):
            raise ValueError('Saved random schedule changed')

    def _reserve_trial(self,index):
        registry=self.session.root.parent/'trial_registry';registry.mkdir(exist_ok=True)
        trial=max((int(p.stem.split('_')[1],16) for p in registry.glob('trial_*.json')),default=0)+1
        if not 0<trial<65536:raise RuntimeError('Trial ID exhausted')
        store._write(registry/('trial_%04x.json'%trial),store._json({
            'epoch':self.session.local_epoch,'index':index,'attempt':0,'trial_id':trial,
            'client_request_id':self.requests[index].client_request_id,'scope':'real_scan_candidate_v0_1'}))
        store._sync_directory(registry);return trial

    def bind_policy_owner(self,owner):
        if self._policy_owner is not None or self.index or self.attempts:raise RuntimeError('Fresh single policy owner required')
        self._policy_owner=owner

    def authorize_next(self,owner,path,digest):
        path=Path(path).resolve()
        if owner is not self._policy_owner or self._policy_permit is not None:
            raise RuntimeError('Exclusive one-use policy permit required')
        if (self.session.root/'AUTOTUNE_DECISIONS').resolve() not in path.parents:
            raise ValueError('Permit outside current session')
        raw=path.read_bytes();v=json.loads(raw)
        if (store.sha(raw)!=digest or v['expected_executor_index']!=self.index or
                v['executor_plan_sha256']!=store.sha(self._frozen_plan) or
                v['action']!='CONTINUE_PREDECLARED_NEXT' or v['one_use'] is not True):
            raise ValueError('Policy permit is stale or does not authorize the next fixed slot')
        manifest=json.loads((path.parent/'committed.json').read_bytes())
        if manifest['files']!={path.name:digest}:raise ValueError('Permit commitment differs')
        decision=path.parent.parent/'decision.json'
        if store.sha(decision.read_bytes())!=v['decision_sha256']:raise ValueError('Policy decision changed')
        self._policy_permit=(self.index,path,digest)

    def run_next(self):
        permit=self._policy_permit;self._policy_permit=None
        if permit is None or permit[0]!=self.index:raise RuntimeError('No one-use committed policy decision; direct START denied')
        if store.sha(permit[1].read_bytes())!=permit[2]:raise ValueError('Consumed policy permit changed')
        return super().run_next()
