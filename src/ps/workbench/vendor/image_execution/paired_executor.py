"""Separate 65-record image allowance; old four-record executor stays frozen."""
from pathlib import Path
import json,threading
from controlled_trial_executor import ControlledTrialExecutor,TrialRequest
from multi_point_profile import MultiPointProfile
from paired_random_plan import validate_schedule,IMAGE_SHA
from raw_mark_snapshot import _same_session_buses
from ps_idle_journal_segments import _idle
from ch1_completion_ledger import _codec
from ch1_peer_archive_driver import persist_exact
import ch1_evidence_store as store

class PairedImageExecutor(ControlledTrialExecutor):
    def __init__(self,session,buses,source,schedule,*,exclusive_owner=False):
        if exclusive_owner is not True:raise ValueError('Exclusive ownership required')
        validate_schedule(schedule);source=bytes(source)
        if len(source)!=16384 or store.sha(source)!=schedule['source_sha256']:raise ValueError('Exact uploaded128x128 source SHA required')
        if (session.fault or session.current is not None or session.config_owner is not None or
                session.mark_capture is None or session.mark_capture.used):
            raise RuntimeError('Fresh initialized session and unarmed CH2 preflight required')
        _same_session_buses(session,buses);_idle(session,buses)
        if buses['SYS'].read(0x18) or buses['SYS'].read(0x1c):raise RuntimeError('Fresh epoch counters required')
        preflight=session.root/'MARK/preflight'
        for name,digest in json.loads((preflight/'committed.json').read_bytes())['files'].items():
            if store.sha((preflight/name).read_bytes())!=digest:raise ValueError('CH2 preflight changed')
        requests=tuple(TrialRequest(e['client_request_id'],e['receiver_B']['d'],e['receiver_B']['s'],
            None if e['profile'] is None else MultiPointProfile(**e['profile'])) for e in schedule['items'])
        codec=_codec();parts=tuple(source[i:i+256] for i in range(0,16384,256))
        specs=[r.validate(codec.encode_item(session.local_epoch,1,1,i,64,0,0,parts[i])) for i,r in enumerate(requests)]
        config=codec.encode_config(session.local_epoch,1,128,128,16384,64,256,
            bytes.fromhex(schedule['source_sha256']),[store.crc16(p) for p in parts])
        plan={'schema':'RANDOM_IMAGE_EXECUTOR_PLAN_V0_1','local_epoch':session.local_epoch,
            'source_sha256':schedule['source_sha256'],'source_bytes':16384,'width':128,'height':128,
            'requests':specs,'max_physical_starts_including_CONFIG':65,
            'random_schedule_sha256':store.sha(store._json(schedule)),
            'automatic_training_allowed':False,'production_billing_finalized':False,
            'scope':'One bounded image demonstration; separate from four-record tuning loop; no automatic retry'}
        self.root=session.root/'EXECUTOR';self.root.mkdir(exist_ok=False)
        persist_exact(self.root/'plan',{'plan.json':store._json(plan),'source.bin':source,'config.bin':config})
        persist_exact(self.root/'random_schedule',{'schedule.json':store._json(schedule)})
        self._frozen_plan=store._json(plan);self._frozen_source=source;self._frozen_config=config
        self._schedule=store._json(schedule);self.session=session;self.buses=buses
        self.requests=requests;self.parts=parts;self._lock=threading.Lock()
        self.index=0;self.stopped=False;self.results=[];self.max_attempts=65;self.attempts=0
        session.journal.record('random_image_plan_saved',plan_sha256=store.sha(self._frozen_plan),
            random_schedule_sha256=store.sha(self._schedule),seed=schedule['seed'],max_physical_starts=65)

    def _verify_plan(self):
        super()._verify_plan()
        if self.max_attempts!=65 or len(self._frozen_source)!=16384:
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
            'client_request_id':self.requests[index].client_request_id,'scope':'random_image_candidate_v0_1'}))
        store._sync_directory(registry);return trial
