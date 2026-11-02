"""Frozen per-record random profiles and actual counts before retirement."""
from pathlib import Path
import json
from ch1_control_session import event_payload
from ch1_completion_ledger import _codec
from ch1_peer_archive_driver import persist_exact
from multi_point_profile import MultiPointProfile
from paired_random_plan import validate_schedule
import ch1_evidence_store as store

class PairedImageMonitor:
    def __init__(self,executor,schedule):
        validate_schedule(schedule)
        s=executor.session;b=executor.buses
        if (s.fault or s.current is not None or s.config_owner is not None or executor.index or
                getattr(s,'mpg1_monitor',None) is not None or b['SYS'].read(0x18) or b['SYS'].read(0x1c)):
            raise RuntimeError('Fresh exclusive random image session required')
        preflight=s.root/'MPG1/preflight'
        for n,digest in json.loads((preflight/'committed.json').read_bytes())['files'].items():
            if store.sha((preflight/n).read_bytes())!=digest:raise ValueError('MPG1 preflight changed')
        data=json.loads((preflight/'preflight.json').read_bytes())
        if (data['session']!=s.root.name or data['counts_after']!=[0,0] or any(data['native_identity_words']) or
                s.peer.read(0xd20)!=0x4d504731):raise ValueError('Fresh MPG1 source required')
        self.executor=executor;self.session=s;self.buses=b;self.epoch=s.local_epoch;self.receipts={}
        self.schedule_bytes=store._json(schedule);self.expected=(0,)+tuple(e['count'] for e in schedule['items'])
        self.root=s.root/'MPG1_IMAGE';self.root.mkdir(exist_ok=False)
        self.source=Path(__file__).resolve();self.source_sha=store.sha(self.source.read_bytes())
        self.plan_sha=store.sha(executor._frozen_plan)
        self.policy=store._json({'schema':'RANDOM_IMAGE_COUNT_MONITOR_V0_1','epoch':self.epoch,
            'max_records':65,'schedule_sha256':store.sha(self.schedule_bytes),'executor_plan_sha256':self.plan_sha,
            'expected_points_by_record':list(self.expected),'source_sha256':self.source_sha,
            'verified_before_retirement':True,'all_points_waveform_verified':False})
        persist_exact(self.root/'policy',{'policy.json':self.policy})
        s.mpg1_monitor=self;s.peer.mpg1_monitor=self
        s.journal.record('random_image_count_monitor_registered',**json.loads(self.policy))

    def _verify(self):
        s=self.session
        if (s.fault or s.local_epoch!=self.epoch or getattr(s,'mpg1_monitor',None) is not self or
                getattr(s.peer,'mpg1_monitor',None) is not self or
                store.sha(self.source.read_bytes())!=self.source_sha or
                store.sha(self.executor._frozen_plan)!=self.plan_sha or
                self.executor._schedule!=self.schedule_bytes or
                (self.root/'policy/policy.json').read_bytes()!=self.policy):
            raise RuntimeError('Random image monitor source/namespace/ownership changed')
        if json.loads((self.root/'policy/committed.json').read_bytes())['files']!={'policy.json':store.sha(self.policy)}:
            raise ValueError('Monitor policy commitment changed')
        if self.expected!=(0,)+tuple(e['count'] for e in json.loads(self.schedule_bytes)['items']):
            raise ValueError('Expected point counts changed')
        for p,digest in self.receipts.values():
            if store.sha(p.read_bytes())!=digest:raise ValueError('Prior actual point proof changed')

    def authorize_multi_profile(self,identity,profile,inner):
        self._verify();f=store._fields(identity,store.IDENTITY);rid=f['seq']
        if not 2<=rid<=65 or set(self.receipts)!=set(range(1,rid)):
            raise RuntimeError('Prior records must complete before this image ITEM')
        entry=json.loads(self.schedule_bytes)['items'][rid-2]
        if type(profile) is not MultiPointProfile or profile.validate(inner)!=entry['profile']:
            raise ValueError('Profile differs from pre-saved random schedule')
        item=_codec().decode_item(bytes(inner));old=self.session.last_retired_owner
        if (not item['valid'] or item['item_index']!=rid-2 or item['item_total']!=64 or
                item['payload']!=self.executor.parts[rid-2] or old is None or old.phase!='RETIRED' or
                old.binding.record_id!=rid-1 or old.binding.epoch!=self.epoch or
                (self.buses['SYS'].read(0x18),self.buses['SYS'].read(0x1c))!=(rid-1,rid-1)):
            raise RuntimeError('Exact previous retirement and current original ITEM required')
        prev=store._fields(old.binding.identity,store.IDENTITY)
        if (f['run_id']!=self.epoch or f['generation']<=prev['generation'] or
                any(f[k]!=prev[k] for k in ('session','route_epoch','run_id','image_id','slot','route_mode'))):
            raise ValueError('Random profile must advance within current full namespace')
        if self.session.peer.read(0xd20)!=0x4d504731:raise ValueError('Actual MPG1 changed')

    def verify_completed(self,owner,expected_points):
        self._verify();b=owner.binding;rid=b.record_id
        if (owner is not self.session.current or not owner.started or not owner.done or b.epoch!=self.epoch or
                not 1<=rid<=65 or type(expected_points) is not int or expected_points!=self.expected[rid-1] or
                b.kind!=(2 if rid==1 else 1) or set(self.receipts)!=set(range(1,rid))):
            raise ValueError('Exact active completed record and saved point count required')
        if (self.buses['SYS'].read(0x18),self.buses['SYS'].read(0x1c))!=(rid-1,rid-1):
            raise RuntimeError('Point proof must precede retirement')
        peer=self.session.peer
        if peer.read(0xd20)!=0x4d504731:raise ValueError('MPG1 capability changed')
        before=[peer.read(0xd24),peer.read(0xd28)]
        words=[peer.read(a) for a in range(0xd30,0xd50,4)]
        after=[peer.read(0xd24),peer.read(0xd28)]
        if before!=after or before!=[expected_points|(expected_points<<9),1]:
            raise ValueError('Actual emitted/configured counts, DONE fence or source fault differs')
        native=0
        for word in words:native=native<<32|word
        if native!=int.from_bytes(event_payload(b.identity,0),'little'):
            raise ValueError('Actual MPG1 identity differs from active record')
        proof={'schema':'RANDOM_IMAGE_PRE_RETIREMENT_COUNT_V0_1','epoch':self.epoch,'record_id':rid,
            'identity_hex':'%064x'%b.identity,'native_identity_words':words,
            'count_status_before':before,'count_status_after':after,'configured_points':expected_points,
            'emitted_points':expected_points,'actual_DONE_fenced':True,'source_fault':False,
            'verified_before_retirement':True,'all_points_waveform_verified':False,
            'CAP06_scope':'FIRST_POINT_ONLY' if expected_points else 'UNARMED'}
        self.session.journal.verify();directory=self.root/('record_%08x'%rid)/'completed'
        raw=store._json(proof);persist_exact(directory,{'counts.json':raw})
        self.receipts[rid]=(directory/'counts.json',store.sha(raw))
        self.session.journal.record('MPG1_completed_count_before_retirement',**proof)
        return proof
