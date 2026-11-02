from active14_bootstrap import bind
bind()
"""Committed custom conditions and actual point counts before retirement."""
from pathlib import Path
import json
from ch1_control_session import event_payload
from ch1_completion_ledger import _codec
from ch1_peer_archive_driver import persist_exact
from multi_point_profile import MultiPointProfile
from custom_plan import validate_plan as validate_schedule
import ch1_evidence_store as store

class CustomMonitor:
    def __init__(self,executor,schedule,*,hardware=False):
        self.hardware=hardware
        validate_schedule(schedule)
        s=executor.session;b=executor.buses
        if (s.fault or s.current is not None or s.config_owner is not None or executor.index or
                getattr(s,'mpg1_monitor',None) is not None or b['SYS'].read(0x18) or b['SYS'].read(0x1c)):
            raise RuntimeError('Fresh exclusive real scan session required')
        preflight=s.root/'MPG1/preflight'
        for n,digest in json.loads((preflight/'committed.json').read_bytes())['files'].items():
            if store.sha((preflight/n).read_bytes())!=digest:raise ValueError('MPG1 preflight changed')
        data=json.loads((preflight/'preflight.json').read_bytes())
        if (data['session']!=s.root.name or data['counts_after']!=[0,0] or any(data['native_identity_words']) or
                s.peer.read(0xd20)!=0x4d504731):raise ValueError('Fresh MPG1 source required')
        self.executor=executor;self.session=s;self.buses=b;self.epoch=s.local_epoch;self.receipts={}
        self.schedule_bytes=store._json(schedule);self.expected=(0,)+tuple(0 if e['profile'] is None else None for e in schedule['items'])
        self.root=s.root/'MPG1_SCAN';self.root.mkdir(exist_ok=False)
        self.source=Path(__file__).resolve();self.source_sha=store.sha(self.source.read_bytes())
        self.plan_sha=store.sha(executor._frozen_plan)
        self.policy=store._json({'schema':'BOUNDARY_RULE_SCAN_COUNT_MONITOR_V0_1','epoch':self.epoch,
            'max_records':schedule['max_records'],'schedule_sha256':store.sha(self.schedule_bytes),'executor_plan_sha256':self.plan_sha,
            'expected_points_by_record':list(self.expected),'source_sha256':self.source_sha,
            'verified_before_retirement':True,'all_points_waveform_verified':False})
        persist_exact(self.root/'policy',{'policy.json':self.policy})
        s.mpg1_monitor=self;s.peer.mpg1_monitor=self
        s.journal.record('boundary_scan_count_monitor_registered',**json.loads(self.policy))

    def _verify(self):
        s=self.session
        if (s.fault or s.local_epoch!=self.epoch or getattr(s,'mpg1_monitor',None) is not self or
                getattr(s.peer,'mpg1_monitor',None) is not self or
                store.sha(self.source.read_bytes())!=self.source_sha or
                store.sha(self.executor._frozen_plan)!=self.plan_sha or
                self.executor._schedule!=self.schedule_bytes or
                (self.root/'policy/policy.json').read_bytes()!=self.policy):
            raise RuntimeError('Real scan monitor source/namespace/ownership changed')
        if json.loads((self.root/'policy/committed.json').read_bytes())['files']!={'policy.json':store.sha(self.policy)}:
            raise ValueError('Monitor policy commitment changed')
        if self.expected!=(0,)+tuple(0 if e['profile'] is None else None for e in json.loads(self.schedule_bytes)['items']):
            raise ValueError('Expected point counts changed')
        for p,digest in self.receipts.values():
            if store.sha(p.read_bytes())!=digest:raise ValueError('Prior actual point proof changed')

    def points(self,rid):
        if rid<=2:return 0
        schedule=json.loads(self.schedule_bytes);cmd=self.executor.bindings[rid]['command']
        c=next(c for c in schedule['conditions'] if c['condition_id']==cmd['point_id'])
        return c['count']

    def authorize_multi_profile(self,identity,profile,inner):
        self.executor._verify_plan();self._verify()
        rid=self.executor.index+1
        if rid<3 or type(profile) is not MultiPointProfile:raise ValueError('EXACT_BOUND_MULTI_PROFILE_REQUIRED')
        from custom_plan import typed_profile
        cmd=self.executor.bindings[rid]['command'];schedule=json.loads(self.schedule_bytes)
        c=next(c for c in schedule['conditions'] if c['condition_id']==cmd['point_id'])
        if profile!=typed_profile(c) or set(self.receipts)!=set(range(1,rid)):raise ValueError('MULTI_PROFILE_OR_PREFIX_CHANGED')
        fields=store._fields(identity,store.IDENTITY)
        old=self.session.last_retired_owner
        if fields['seq']!=rid or fields['run_id']!=self.epoch or old is None or old.phase!='RETIRED' or old.binding.record_id!=rid-1:raise ValueError('MULTI_IDENTITY_OR_RETIREMENT_CHANGED')
        prior=store._fields(old.binding.identity,store.IDENTITY)
        if fields['generation']<=prior['generation'] or any(fields[k]!=prior[k] for k in ('session','route_epoch','run_id','image_id','slot','route_mode')):raise ValueError('MULTI_NAMESPACE_CHANGED')
        if (self.buses['SYS'].read(0x18),self.buses['SYS'].read(0x1c))!=(rid-1,rid-1):raise ValueError('MULTI_COUNTER_CHANGED')
        profile.validate(inner)
        from ch1_completion_ledger import _codec
        decoded=_codec().decode_item(inner)
        if any(decoded[k]!=fields[k] for k in ('run_id','image_id','trial_id','item_index','attempt_id','route_mode')) or inner!=_codec().encode_item(self.epoch,1,decoded['trial_id'],rid-2,len(self.executor.parts),0,0,self.executor.parts[rid-2]):raise ValueError('MULTI_SOURCE_IDENTITY_CHANGED')
        return True

    def verify_completed(self,owner,expected_points):
        self.executor._verify_plan()
        self._verify();b=owner.binding;rid=b.record_id
        if (owner is not self.session.current or not owner.started or not owner.done or b.epoch!=self.epoch or
                not 1<=rid<=len(self.expected) or type(expected_points) is not int or expected_points!=self.points(rid) or
                b.kind!=(2 if rid==1 else 1) or set(self.receipts)!=set(range(1,rid))):
            raise ValueError('Exact active completed record and saved point count required')
        if (self.buses['SYS'].read(0x18),self.buses['SYS'].read(0x1c))!=(rid-1,rid-1):
            raise RuntimeError('Point proof must precede retirement')
        peer=self.session.peer
        read_start=self.session.journal.index
        if peer.read(0xd20)!=0x4d504731:raise ValueError('MPG1 capability changed')
        before=[peer.read(0xd24),peer.read(0xd28)]
        words=[peer.read(a) for a in range(0xd30,0xd50,4)]
        after=[peer.read(0xd24),peer.read(0xd28)]
        read_stop=self.session.journal.index
        observed=dict(epoch=self.epoch,record_id=rid,identity_hex='%064x'%b.identity,expected_points=expected_points,count_status_before=before,count_status_after=after,native_identity_words=words)
        if self.hardware:
            observed['raw_MMIO_window']=dict(path=self.session.journal.path.relative_to(self.session.root).as_posix(),start_index=read_start,stop_index=read_stop,control_epoch=peer.epoch)
        persist_exact(self.root/('record_%08x'%rid)/'completion_readback',{'readback.json':store._json(observed)})
        if before!=after or before!=[expected_points|(expected_points<<9),1]:
            raise ValueError('Actual emitted/configured counts, DONE fence or source fault differs')
        native=0
        for word in words:native=native<<32|word
        if native!=int.from_bytes(event_payload(b.identity,0),'little'):
            raise ValueError('Actual MPG1 identity differs from active record')
        proof={'schema':'BOUNDARY_RULE_SCAN_PRE_RETIREMENT_COUNT_V0_1','epoch':self.epoch,'record_id':rid,
            'identity_hex':'%064x'%b.identity,'native_identity_words':words,
            'count_status_before':before,'count_status_after':after,'configured_points':expected_points,
            'emitted_points':expected_points,'actual_DONE_fenced':True,'source_fault':False,
            'verified_before_retirement':True,'all_points_waveform_verified':False,'dynamic_binding_sha256':store.sha(self.executor._bound_raw[rid]),
            'CAP06_scope':'FIRST_POINT_ONLY' if expected_points else 'UNARMED'}
        if self.hardware:
            from custom_mmio_binding import journal_entries,packets,bind_reads
            entries=journal_entries(self.session.root)
            captures={packet for e in entries for offset,packet in packets(e)}
            binding=bind_reads(entries,captures,proof,observed,observed['raw_MMIO_window'])
            proof['raw_MMIO_binding']=binding
            persist_exact(self.root/('record_%08x'%rid)/'raw_MMIO_binding',{'binding.json':store._json(binding)})
        self.session.journal.verify();directory=self.root/('record_%08x'%rid)/'completed'
        raw=store._json(proof);persist_exact(directory,{'counts.json':raw})
        self.receipts[rid]=(directory/'counts.json',store.sha(raw))
        self.session.journal.record('MPG1_completed_count_before_retirement',**proof)
        return proof
