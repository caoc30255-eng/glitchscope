"""MPG1 count/identity evidence before retirement; first four-record pilot only."""
from pathlib import Path
import json
from ch1_control_session import event_payload
from ch1_peer_archive_driver import persist_exact
import ch1_evidence_store as store


class MPG1TrialMonitor:
    def __init__(self,session,buses):
        if (session.fault or session.current is not None or session.config_owner is not None or
                getattr(session,'mpg1_monitor',None) is not None or
                buses['SYS'].read(0x18) or buses['SYS'].read(0x1c)):
            raise RuntimeError('Fresh initialized exclusive MPG1 pilot session required')
        preflight=session.root/'MPG1/preflight'
        for name,digest in json.loads((preflight/'committed.json').read_bytes())['files'].items():
            if store.sha((preflight/name).read_bytes())!=digest:raise ValueError('MPG1 preflight changed')
        data=json.loads((preflight/'preflight.json').read_bytes())
        if data['session']!=session.root.name or data['counts_after']!=[0,0] or any(data['native_identity_words']):
            raise ValueError('Fresh MPG1 preflight must match this namespace')
        if session.peer.read(0xd20)!=0x4d504731:raise ValueError('Actual MPG1 capability missing')
        self.session=session;self.buses=buses;self.receipts={};self.epoch=session.local_epoch
        self.root=session.root/'MPG1_TRIAL';self.root.mkdir(exist_ok=False)
        self.source=Path(__file__).resolve();self.source_sha=store.sha(self.source.read_bytes())
        policy={'schema':'MPG1_FOUR_RECORD_MONITOR_V0_1','epoch':session.local_epoch,
            'expected_points_by_record':[0,0,1,4],'TYPE3C_only_record_id':4,
            'multi_profile':{'first_byte':20,'count':4,'bit':0,'phase':15,'width':20},
            'source_sha256':self.source_sha,'count_evidence_required_before_retirement':True,
            'CAP06_scope':'FIRST_POINT_ONLY','all_points_waveform_verified':False,
            'automatic_retry_allowed':False,'training_authorized':False,'production_billing_finalized':False}
        self.policy=store._json(policy)
        persist_exact(self.root/'policy',{'policy.json':self.policy})
        session.journal.record('MPG1_trial_monitor_registered',**policy)
        session.mpg1_monitor=self;session.peer.mpg1_monitor=self

    def _verify(self):
        if (self.session.fault or self.session.local_epoch!=self.epoch or getattr(self.session,'mpg1_monitor',None) is not self or
                getattr(self.session.peer,'mpg1_monitor',None) is not self or
                store.sha(self.source.read_bytes())!=self.source_sha or
                (self.root/'policy/policy.json').read_bytes()!=self.policy):
            raise RuntimeError('MPG1 monitor ownership/policy changed')
        for name,digest in json.loads((self.root/'policy/committed.json').read_bytes())['files'].items():
            if store.sha((self.root/'policy'/name).read_bytes())!=digest:raise ValueError('MPG1 policy archive changed')
        for rid,(path,digest) in self.receipts.items():
            if store.sha(path.read_bytes())!=digest:raise ValueError('Prior MPG1 count evidence changed')

    def authorize_multi_profile(self,identity,profile,inner):
        from multi_point_profile import MultiPointProfile
        self._verify()
        if type(profile) is not MultiPointProfile or profile!=MultiPointProfile(20,4,0,15,20):
            raise ValueError('First pilot allows exactly four contiguous byte20..23 bit0 points')
        profile.validate(inner)
        fields=store._fields(identity,store.IDENTITY)
        old=self.session.last_retired_owner
        if (fields['seq']!=4 or set(self.receipts)!={1,2,3} or old is None or old.phase!='RETIRED' or
                old.binding.record_id!=3 or old.binding.epoch!=self.session.local_epoch or
                self.buses['SYS'].read(0x18)!=3 or self.buses['SYS'].read(0x1c)!=3):
            raise RuntimeError('TYPE3C requires three completed prior pilot records and strict retirement')
        prior=store._fields(old.binding.identity,store.IDENTITY)
        if (fields['generation']<=prior['generation'] or
                any(fields[k]!=prior[k] for k in ('session','route_epoch','run_id','image_id','slot','route_mode')) or
                fields['run_id']!=self.session.local_epoch):
            raise ValueError('TYPE3C must advance generation in this exact pilot namespace')
        if self.session.peer.read(0xd20)!=0x4d504731:raise ValueError('Actual MPG1 capability changed')
        return True

    def verify_completed(self,owner,expected_points):
        self._verify()
        b=owner.binding;rid=b.record_id
        if (owner is not self.session.current or not owner.started or not owner.done or
                b.epoch!=self.session.local_epoch or rid not in (1,2,3,4) or
                type(expected_points) is not int or expected_points!=(0,0,1,4)[rid-1] or
                set(self.receipts)!=set(range(1,rid))):
            raise ValueError('Count proof must bind exact active completed owner in frozen record order')
        if (self.buses['SYS'].read(0x18),self.buses['SYS'].read(0x1c))!=(rid-1,rid-1):
            raise RuntimeError('Count evidence must precede this record retirement/grant')
        peer=self.session.peer
        if peer.read(0xd20)!=0x4d504731:raise ValueError('MPG1 capability changed')
        before=(peer.read(0xd24),peer.read(0xd28))
        words=[peer.read(a) for a in range(0xd30,0xd50,4)]
        after=(peer.read(0xd24),peer.read(0xd28))
        if before!=after or before!=(expected_points|(expected_points<<9),1):
            raise ValueError('Actual points, DONE fence or source fault differs; do not retire')
        native=0
        for word in words:native=native<<32|word
        if native!=int.from_bytes(event_payload(b.identity,0),'little'):
            raise ValueError('Actual MPG1 identity differs; do not retire')
        proof={'schema':'MPG1_PRE_RETIREMENT_COUNT_V0_1','epoch':b.epoch,'record_id':rid,
            'identity_hex':'%064x'%b.identity,'native_identity_words':words,
            'count_status_before':list(before),'count_status_after':list(after),
            'configured_points':expected_points,'emitted_points':expected_points,
            'actual_DONE_fenced':True,'source_fault':False,'verified_before_retirement':True,
            'all_points_waveform_verified':False,'CAP06_scope':'FIRST_POINT_ONLY' if expected_points else 'UNARMED'}
        self.session.journal.verify()
        path=self.root/('record_%08x'%rid)/'completed'
        persist_exact(path,{'counts.json':store._json(proof)})
        self.receipts[rid]=(path/'counts.json',store.sha((path/'counts.json').read_bytes()))
        self.session.journal.record('MPG1_completed_count_before_retirement',**proof)
        return proof
