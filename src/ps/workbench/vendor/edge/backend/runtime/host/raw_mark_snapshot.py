"""One-shot physical CH2 mark snapshot through the reviewed legacy CAP06 block.

The raw block has NO hardware epoch/generation field. Association is an exclusive
one-shot arm receipt + exact P1 FAULT_MARK identity + retained physical waveform.
Each driver remains one-shot. A separately sealed strict retirement can issue
one successor using ordinary ARM. No soft reset or fabricated hardware identity.
"""
from pathlib import Path
from dataclasses import dataclass,asdict
import json,uuid,hashlib,xml.etree.ElementTree as ET
from ch1_peer_archive_driver import persist_exact
from fault_profile import FaultProfile
from multi_point_profile import MultiPointProfile
import ch1_evidence_store as store

HWH_SHA='8d65319fd06ccafb9acdabe1c19868106cd1945f085b2fa03d55b89d238bd2bc'


def analyze_waveform(samples,trigger_offset,expected_bit,width_clks):
    data=bytes(samples)
    if len(data)!=4096 or trigger_offset!=2048 or expected_bit not in (0,1):
        raise ValueError('Expected complete4096/pre2048 snapshot')
    mark=[(x>>2)&1 for x in data];wire=[x&1 for x in data]
    rises=[i for i in range(1,len(mark)) if mark[i] and not mark[i-1]]
    if rises!=[trigger_offset]:raise ValueError('Missing/extra/misaligned physical mark')
    end=trigger_offset
    while end<len(mark) and mark[end]:end+=1
    if not 1<=end-trigger_offset<=4:raise ValueError('Physical mark pulse not one nominal20ns LIFE cycle')
    if any(x!=expected_bit for x in wire[trigger_offset-5:trigger_offset-2]):
        raise ValueError('Pre-mark physical data level differs from source target bit')
    # Two independently synchronized pins can differ by up to two sample clocks.
    starts=[i for i in range(trigger_offset-2,trigger_offset+3)
            if wire[i]==(expected_bit^1) and wire[i-1]==expected_bit]
    if len(starts)!=1:raise ValueError('No unique inversion onset near physical mark')
    inverted_start=starts[0];restored=inverted_start
    while restored<len(wire) and wire[restored]==(expected_bit^1):restored+=1
    observed=restored-inverted_start
    if abs(observed-width_clks*2)>2 or observed<1:
        raise ValueError('Physical inversion duration differs from requested LIFE width')
    if wire[restored:restored+3]!=[expected_bit]*3:
        raise ValueError('Physical target bit did not restore after pulse')
    return {'mark_sample':trigger_offset,'mark_high_samples':end-trigger_offset,
            'inverted_samples':observed,'inversion_start_sample':inverted_start,
            'mark_to_inversion_samples':inverted_start-trigger_offset,'expected_nominal_samples':width_clks*2,
            'nominal_sample_clock_hz':100000000,'expected_source_bit':expected_bit,
            'physical_inversion_verified':True}

@dataclass(frozen=True)
class MarkReceipt:
    token:str
    evidence_dir:str
    manifest_sha256:str

class RawMarkCapture:
    def __init__(self,bus,root):
        self.bus=bus;self.root=Path(root);self.used=False
        self.arm_receipt=None;self._arm_bytes=None;self.receipts={}
        self._predecessor=None;self._retired_seal=None;self._successor_created=False
        self._hardware_replaced=False
    @classmethod
    def from_reviewed_hwh(cls,mmio_factory,root,hwh_path):
        raw=Path(hwh_path).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=HWH_SHA:raise ValueError('Unreviewed HWH; no MMIO mapping')
        matches=[n for n in ET.fromstring(raw).iter('MEMRANGE')
                 if n.get('INSTANCE')=='raw_snapshot_axi_lite_0' and n.get('SLAVEBUSINTERFACE')=='S_AXI']
        if len(matches)!=1 or (int(matches[0].get('BASEVALUE'),0),int(matches[0].get('HIGHVALUE'),0))!=(0x43c00000,0x43c0ffff):
            raise ValueError('Raw snapshot address contract differs')
        return cls(mmio_factory(0x43c00000,0x10000),root)
    def read(self,a):return int(self.bus.read(a))
    def arm(self,binding,inner,profile):
        if self.used or type(profile) not in (FaultProfile,MultiPointProfile) or binding.kind!=1:
            raise RuntimeError('Fresh one-shot Direct ITEM mark capture required')
        coordinates=profile.validate(inner)
        from ch1_completion_ledger import _codec
        from ch1_runtime_driver import unsigned
        unsigned(binding.epoch,32,'mark epoch',1);unsigned(binding.record_id,32,'mark record',1)
        fields=store._fields(binding.identity,store.IDENTITY);decoded=_codec().decode_item(bytes(inner))
        if fields['reserved'] or not fields['generation'] or not fields['session'] or not fields['seq']:
            raise ValueError('Complete mark binding required')
        if any(fields[k]!=decoded[k] for k in ('run_id','image_id','trial_id','item_index','attempt_id','route_mode')):
            raise ValueError('Raw mark source does not match full trial identity')
        if self._predecessor is None:
            if self.read(8)&0x3f or self.read(12) or self.read(16):
                raise RuntimeError('Existing raw snapshot state retained; no reset/rearm')
        else:
            previous,receipt,old_binding=self._predecessor
            previous._verify_retired_seal()
            previous.verify_saved(receipt,old_binding)
            old_fields=store._fields(old_binding.identity,store.IDENTITY)
            if (binding.epoch!=old_binding.epoch or binding.record_id<=old_binding.record_id or
                    fields['seq']<=old_fields['seq'] or fields['generation']<=old_fields['generation'] or
                    any(fields[k]!=old_fields[k] for k in ('session','route_epoch','run_id','image_id','route_mode'))):
                raise ValueError('Next snapshot must advance actual record/seq/generation in same namespace')
        if self.read(0x20)&4:raise RuntimeError('Physical mark already high before arm')
        self.used=True
        context={'epoch':binding.epoch,'record_id':binding.record_id,'identity':binding.identity,
                 'profile':coordinates,'expected_bit':(bytes(inner)[profile.byte]>>profile.bit)&1,
                 'source_sha256':store.sha(bytes(inner)),'hardware_identity_embedded':False}
        if self._predecessor is not None:
            context['replaces_retired_snapshot']=dict(self._predecessor[0]._retired_seal[1])
        directory=self.root/('epoch_%08x_record_%08x'%(binding.epoch,binding.record_id))
        persist_exact(directory/'arm',{'intent.json':store._json(context)})
        self.bus.write(4,0x201) # trigger channel2, rising edge enabled.
        if self._predecessor is not None:
            # CAP06 has no generation register: even equal metadata cannot prove
            # that an old driver's snapshot remains in RAM after another ARM.
            self._predecessor[0]._hardware_replaced=True
        self.bus.write(0,1)     # ARM only: old snapshot may be replaced ONLY via retired seal.
        if self.read(4)!=0x201 or self.read(8)&15!=3 or self.read(12) or self.read(16):
            raise RuntimeError('Actual raw snapshot ARM not verified')
        self.arm_receipt={**context,'arm_dir':str(directory/'arm')}
        self._arm_bytes=store._json(self.arm_receipt)
        persist_exact(directory/'armed',{'receipt.json':self._arm_bytes})
        self.verify_armed(binding)
        return dict(self.arm_receipt)
    def _context(self,binding):
        if self.arm_receipt is None or store._json(self.arm_receipt)!=self._arm_bytes:
            raise ValueError('Mark arm receipt changed/missing')
        if any(self.arm_receipt[k]!=getattr(binding,k) for k in ('epoch','record_id','identity')):
            raise ValueError('Raw mark associated with another trial')
        p=Path(self.arm_receipt['arm_dir']).parent/'armed/receipt.json'
        if p.read_bytes()!=self._arm_bytes:raise ValueError('Persisted mark arm context changed')
        for directory in (Path(self.arm_receipt['arm_dir']),p.parent):
            for name,digest in json.loads((directory/'committed.json').read_bytes())['files'].items():
                if store.sha((directory/name).read_bytes())!=digest:raise ValueError('Mark arm intent/receipt archive changed')
    def verify_armed(self,binding):
        self._context(binding)
        if self.read(4)!=0x201 or self.read(8)&15!=3 or self.read(0x20)&4:
            raise RuntimeError('Raw snapshot no longer clean/armed before START')
        return True
    def archive(self,binding,mark_event):
        from ch1_control_session import decode_event
        self._context(binding)
        if decode_event(bytes.fromhex(mark_event['raw_hex']))!=mark_event or mark_event['type']!=0x33 or mark_event['identity']!=binding.identity or mark_event['record_id']!=0:
            raise ValueError('Exact actual FAULT_MARK notification required')
        metadata=[self.read(a) for a in (4,8,12,16,0x28)]
        if metadata[0]!=0x201 or metadata[1]&15!=12 or metadata[2:4]!=[4096,2048]:
            raise RuntimeError('Physical raw mark snapshot not complete')
        physical=metadata[4]
        if physical&0xf000f000 or (((physical>>16)&4095)-(physical&4095))&4095!=2048:
            raise ValueError('Physical raw snapshot address/trigger offset mismatch')
        samples=bytearray();words=[]
        for index in range(4096):
            self.bus.write(0x18,index)
            if self.read(0x18)!=index:raise RuntimeError('Snapshot read index delivery mismatch')
            for _ in range(1000):
                word=self.read(0x1c)
                if word&0x100:break
            else:raise TimeoutError('Snapshot sample R delivery not valid')
            if word&~0x1ff:raise ValueError('Raw snapshot reserved sample bits')
            samples.append(word&255);words.append(word)
        after=[self.read(a) for a in (4,8,12,16,0x28)]
        if after[0]!=metadata[0] or after[1]&15!=12 or after[2:]!=metadata[2:]:
            raise RuntimeError('Raw snapshot metadata changed during full readout')
        analysis=analyze_waveform(samples,2048,self.arm_receipt['expected_bit'],self.arm_receipt['profile']['width'])
        if 'count' in self.arm_receipt['profile']:
            analysis.pop('physical_inversion_verified')
            analysis.update(first_point_physical_inversion_verified=True,verification_scope='FIRST_POINT_ONLY',
                configured_points=self.arm_receipt['profile']['count'],all_points_waveform_verified=False)
        directory=Path(self.arm_receipt['arm_dir']).parent/'saved'
        payload={'binding':{'epoch':binding.epoch,'record_id':binding.record_id,'identity':binding.identity},
                 'arm':self.arm_receipt,'mark_event':mark_event,'metadata':metadata,'analysis':analysis,
                 'read_indices_delivered':4096,'raw_hardware_has_identity_register':False}
        persist_exact(directory,{'samples.bin':bytes(samples),'read_DWORDs.json':store._json(words),'context.json':store._json(payload)})
        receipt=MarkReceipt(uuid.uuid4().hex,str(directory),store.sha((directory/'committed.json').read_bytes()))
        self.receipts[receipt.token]=(receipt,store._json(asdict(receipt)),binding,metadata)
        self.verify_saved(receipt,binding)
        return receipt
    def verify_saved(self,receipt,binding):
        if self._hardware_replaced:raise RuntimeError('Old snapshot is archive-only after successor ARM')
        self.verify_archived(receipt,binding)
        metadata=self.receipts[receipt.token][3]
        if self.read(4)!=0x201 or self.read(8)&15!=12 or [self.read(a) for a in (12,16,0x28)]!=metadata[2:]:
            raise RuntimeError('Actual saved raw snapshot no longer held')
        return {'mark_record_id':binding.record_id,'identity':binding.identity,
                'epoch':binding.epoch,'evidence_dir':receipt.evidence_dir,'physical_mark_snapshot_saved':True}
    def verify_archived(self,receipt,binding):
        """Historical file integrity only; never claims old hardware still holds data."""
        if type(receipt) is not MarkReceipt or receipt.token not in self.receipts:raise ValueError('No driver-issued raw mark proof')
        obj,frozen,old,metadata=self.receipts[receipt.token]
        if obj is not receipt or store._json(asdict(receipt))!=frozen or old!=binding:raise ValueError('Raw mark receipt/owner changed')
        self._context(binding);directory=Path(receipt.evidence_dir)
        raw=(directory/'committed.json').read_bytes()
        if store.sha(raw)!=receipt.manifest_sha256:raise ValueError('Raw mark manifest changed')
        for name,digest in json.loads(raw)['files'].items():
            if store.sha((directory/name).read_bytes())!=digest:raise ValueError('Raw mark original changed')
        return {'historical_archive_integrity_verified':True,'hardware_still_holds_old_snapshot':None}

    def seal_retired(self,session,buses):
        """Seal permission to replace one completed capture, after exact READY and idle."""
        from ps_idle_journal_segments import _idle,verify_sealed_segments
        owner=session.last_retired_owner
        _same_session_buses(session,buses)
        if self.root.resolve()!=(session.root/'MARK').resolve():
            raise ValueError('Raw capture archive root differs from session')
        if (session.mark_capture is not self or self._retired_seal is not None or
                owner is None or owner.phase!='RETIRED' or owner.fault or
                not owner.mark_required or owner.mark_capture is not self or
                not owner.local_retired or not owner.peer_retired or not owner.retire_sent):
            raise RuntimeError('Matching strictly retired marked owner required before snapshot replacement')
        _idle(session,buses);verify_sealed_segments(session)
        owner.journal.verify();session.completion.verify_journal()
        owner._strict_local_recheck()
        proof=self.verify_saved(owner.mark_receipt,owner.binding)
        if owner.binding.epoch!=session.local_epoch or session.upload.seq!=store._fields(owner.binding.identity,store.IDENTITY)['seq']:
            raise RuntimeError('Saved actual READY sequence/epoch differs from retired owner')
        payload={'scope':'software permission to replace completed raw snapshot; not hardware epoch',
                 'proof':proof,'old_manifest_sha256':owner.mark_receipt.manifest_sha256,
                 'actual_READY_consumed':True,'three_party_retired':True,
                 'next_ARM_only':True,'soft_reset_allowed':False}
        directory=Path(owner.mark_receipt.evidence_dir).parent/'retired_for_next'
        persist_exact(directory,{'retired.json':store._json(payload)})
        self._retired_seal=(directory,payload,store._json(payload),owner.mark_receipt,owner.binding)
        session.journal.record('raw_snapshot_retired_for_next',**payload)
        self._verify_retired_seal()
        return payload

    def _verify_retired_seal(self):
        if self._retired_seal is None:raise RuntimeError('No strictly retired snapshot replacement seal')
        directory,payload,frozen,receipt,binding=self._retired_seal
        if store._json(payload)!=frozen or (directory/'retired.json').read_bytes()!=frozen:
            raise ValueError('Snapshot retirement seal changed')
        manifest=json.loads((directory/'committed.json').read_bytes())
        if manifest['files']!={'retired.json':store.sha(frozen)}:
            raise ValueError('Snapshot retirement seal manifest changed')
        self.verify_archived(receipt,binding)
        return payload

    def successor(self,session,buses):
        """Read-only boundary check; actual overwrite happens in the new ARM later."""
        from ps_idle_journal_segments import _idle,verify_sealed_segments
        _same_session_buses(session,buses)
        if session.mark_capture is not self or self._successor_created:
            raise RuntimeError('Exactly one successor may be issued by current capture owner')
        _idle(session,buses);verify_sealed_segments(session)
        self._verify_retired_seal()
        _,_,_,receipt,binding=self._retired_seal
        self.verify_saved(receipt,binding)
        if self.read(0x20)&7!=3:raise RuntimeError('Physical input pins not idle before next snapshot')
        self._successor_created=True
        new=RawMarkCapture(self.bus,self.root)
        new._predecessor=(self,receipt,binding)
        session.journal.record('raw_snapshot_successor_issued',previous_identity=binding.identity,
                               previous_record_id=binding.record_id,hardware_writes=0)
        return new


def _same_session_buses(session,buses):
    expected={'H1':session.transport.mmio,'CTRL':session.runtime.bus,
              'MAIN':session.archive.main,'AUX':session.archive.aux,
              'MAP':session.mapping.bus,'CH0':session.ch0.bus,'SYS':session.gate.bus,
              'PROFILE':session.profile.bus}
    if any(buses.get(name) is not bus for name,bus in expected.items()):
        raise ValueError('MMIO buses differ from existing session drivers')
