"""Strict source drivers with synchronous register/control models and real fsync."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'host'), str(ROOT/'tests'), str(ROOT/'host'),
               str(ROOT/'tests/fixtures/registration/tests')]
import test_verified_admission as v
import test_registration_driver_v2 as reg
from ch0_registration_driver_v0_2 import CH0RegistrationDriverV2
import ch0_archive_driver as ch0store
from ch1_mapping_driver import CH1MappingDriver
from ch1_runtime_driver import CH1RuntimeDriver
from ch1_axi_archive_driver import CH1ArchiveDriver
from test_runtime_driver import RuntimeModel
from test_mapping_driver import MappingModel
from test_axi_archive_driver import MainModel, AuxModel
from test_evidence_store import fixture, packed
import ch1_evidence_store as store
from test_completion_ledger import reply


class CH0Bus(reg.Bus):
    def __init__(self, root):
        super().__init__()
        self.root=root; self.closed=False; self.released=False; self.fault=False
        self.count=0; self.raw=b''; self.release_count=0; self.meta=set(); self.parts=set(); self.proof={}
        self.lost=False
    def read(self, a):
        if a==4:
            return 8 if self.released or not self.bound else (7 if self.fault else 3 if self.closed else 0x11)
        if a==0x14:return self.release_count
        if a==0x1c:return 5 if self.fault else 0
        if a==0x20:return 0x1ffffff if len(self.meta)==25 else 0
        if a==0x24:return (self.count<<16)|self.count if len(self.parts)==6*self.count else 0
        if a in (8,12,0x140,0x144,0x148,0x14c,0x150,0x154):
            if self.closed:self.meta.add(a)
            return self.count if a in (8,12) else 0
        if a in (0x158,0x15c,0x160):return 0
        if 0x100<=a<0x140 or a==0x170:
            if self.closed:self.meta.add(a)
            return super().read(a)
        if 0x400<=a<0x2600 or 0x2800<=a<0x4a00:
            base=0x400 if a<0x2600 else 0x2800
            i, offset=divmod(a-base,16)
            assert self.closed and i<self.count and offset in (0,4,8)
            self.parts.add(a)
            raw=((self.raw[i]<<68)|(100+i)).to_bytes(10,'big')+b'\0\0'
            return int.from_bytes(raw[offset:offset+4],'big')
        return super().read(a)
    def write(self,a,value):
        if 0x80<=a<=0xac:
            assert self.closed and not self.fault
            self.proof[a]=value; self.writes.append((a,value)); return
        if a==0x74:
            self.writes.append((a,value))
            assert not self.fault and len(self.meta)==25 and len(self.parts)==6*self.count
            expected={0x80:self.bound[0],0x84:self.bound[1],0x88:(self.count<<16)|self.count}
            expected.update({0x90+4*i:self.bound[4+i] for i in range(8)})
            assert self.proof==expected
            directory=self.root/f'epoch_{self.bound[0]:08x}_record_{self.bound[1]:08x}'
            assert (directory/'committed.json').is_file() and list(directory.glob('release_intent_*.json'))
            self.released=True; self.release_count+=1
            if self.lost:raise OSError('Lost CH0 actual release reply')
            return
        super().write(a,value)


class RuntimeBus(RuntimeModel):
    def __init__(self, mapping):
        super().__init__(); self.mapping=mapping
    def write(self,a,value):
        super().write(a,value)
        if a==0x70:self.mapping.state=2
    def retire(self):
        before=self.count
        super().retire()
        if self.count!=before:
            self.mapping.state=0; self.mapping.retired+=1


class RetirementTests(unittest.TestCase):
    issue=v.VerifiedTests.issue
    deliver=v.VerifiedTests.deliver
    owner=v.VerifiedTests.owner
    start=v.VerifiedTests.start
    def setUp(self):
        v.VerifiedTests.setUp(self)
        self.ch0_bus=CH0Bus(self.root/'ch0')
        self.ch0=CH0RegistrationDriverV2(self.ch0_bus,expected_clock_hz=100000000)
        self.coordinator.ch0=self.ch0
        self.ch0_archive=ch0store.CH0ArchiveDriver(self.ch0,self.root/'ch0')
        self.map_bus=MappingModel(self.upload); self.map_bus.epoch=9
        self.mapping=CH1MappingDriver(self.map_bus)
        self.runtime_bus=RuntimeBus(self.map_bus)
        self.runtime=CH1RuntimeDriver(self.runtime_bus,poll_limit=3)
        self.runtime.activate_epoch(9); self.coordinator.runtime=self.runtime
    def arm(self,context):
        self.order.append('ARM')
        bound=self.mapping.arm_prepared(self.runtime,self.reader,self.upload,epoch=9,peer_epoch=1,
            record_id=context.record_id,kind=context.kind,identity=self.identity,delay_ticks=1000,duration_ticks=299000)
        self.assertEqual(bound,self.binding)
        self.runtime_bus.tick=1500
        return bound
    def begin(self, *, done=True, config_owner=None):
        ticket=self.issue() if config_owner is None else self.coordinator.issue(self.context,self.upload,self.completion,
            arm_ch1=self.arm,deliver_and_archive=self.deliver,d=2,s=0,ch0_delay_ticks=4,ch0_duration_ticks=4000,config_owner=config_owner)
        self.o=self.owner(); self.start(self.o,ticket)
        self.ch0_bus.closed=True; self.ch0_bus.raw=self.inner; self.ch0_bus.count=len(self.inner)
        if done:
            self.status_bus.events=[reply(self.inner,0x83,seq=self.upload.current[1])]; self.reader.read_and_preserve()
        descriptor,samples,raw,w=fixture('config_ack',kind=2)
        d=store.descriptor_decode(descriptor)
        if self.binding.kind==1:
            item=v._codec().decode_item(self.inner)
            raw=v._codec().encode_report(item['run_id'],item['image_id'],item['trial_id'],item['item_index'],item['attempt_id'],item['route_mode'],0,0,item['payload'])
        d.update(epoch=9,identity=self.identity,record_id=self.binding.record_id,kind=self.binding.kind,
                 raw_count=len(raw),start=1000,deadline=300000,close=1100+1000*(len(raw)-1)+2000)
        descriptor=packed([(width,d[name]) for name,width in store.FIELDS])
        samples=b''.join(((byte<<68)|(1100+1000*i)).to_bytes(10,'big') for i,byte in enumerate(raw))
        self.main=MainModel(self.root,descriptor,samples); self.aux=AuxModel(self.root)
        self.archive=CH1ArchiveDriver(self.main,self.aux,self.root)
        self.runtime_bus.main=self.main; self.runtime_bus.tick=d['close']+1
        self.runtime_bus.physical_done=True; self.runtime_bus.capacity=True; self.runtime_bus.complete_on_command=True
    def retire(self):
        return self.o.retire_verified(self.peer,ch0_archive=self.ch0_archive,mapping=self.mapping,
                                      reader=self.reader,archive=self.archive)
    def ready(self,credit=1):
        self.status_bus.events=[reply(self.inner,0x80,seq=0,crc=0,credit=credit)]
        return self.o.accept_ready_verified(self.reader)
    def test_full_strict_START_save_three_retirements_then_actual_READY(self):
        self.begin(); result=self.retire()
        self.assertTrue(result['peer_retirement_verified']);self.assertFalse(result['next_item_allowed'])
        self.assertEqual(self.upload.credit,0)
        self.assertTrue(self.ready()['next_item_allowed'])
        self.assertEqual(self.upload.credit,1);self.assertEqual(self.o.phase,'RETIRED')
        self.assertEqual((self.ch0_bus.release_count,self.runtime_bus.count,self.map_bus.retired),(1,1,1))
    def test_legacy_flags_cannot_bypass_strict_retirement(self):
        self.begin(); count=len(self.wire.requests)
        with self.assertRaises(RuntimeError):self.o.retire_peer(self.peer,dict(hardware_retirement_verified=True,mapping_retirement_verified=True))
        with self.assertRaises(RuntimeError):self.o.accept_ready(dict(state=0x80,credit=1))
        self.assertEqual(count,len(self.wire.requests));self.assertFalse(self.ch0_bus.released)
    def test_missing_saved_H1_DONE_no_local_or_peer_release(self):
        self.begin(done=False); count=len(self.wire.requests)
        with self.assertRaises(RuntimeError):self.retire()
        self.assertFalse(self.ch0_bus.released);self.assertEqual(count,len(self.wire.requests))
    def test_CH0_still_open_no_CH1_release(self):
        self.begin();self.ch0_bus.closed=False
        with self.assertRaises(RuntimeError):self.retire()
        self.assertEqual(self.main.effects,0);self.assertEqual(self.runtime_bus.count,0)
    def test_CH0_fault_retains_diagnostic_no_peer_retire(self):
        self.begin(); self.ch0_bus.fault=True; count=len(self.wire.requests)
        with self.assertRaises(RuntimeError):self.retire()
        self.assertFalse(self.ch0_bus.released);self.assertEqual(count,len(self.wire.requests))
        self.assertTrue(list((self.root/'ch0').glob('*/committed.json')))
    def test_CH0_disk_failure_no_release(self):
        self.begin()
        with patch.object(ch0store,'write_new',side_effect=OSError('disk failed')):
            with self.assertRaises(OSError):self.retire()
        self.assertFalse(self.ch0_bus.released);self.assertEqual(self.main.effects,0)
    def test_CH0_lost_release_reply_no_repeat_or_peer_release(self):
        self.begin();self.ch0_bus.lost=True;count=len(self.wire.requests)
        with self.assertRaises(OSError):self.retire()
        with self.assertRaises(RuntimeError):self.retire()
        self.assertEqual(self.ch0_bus.release_count,1);self.assertEqual(count,len(self.wire.requests))
    def test_CH1_missing_physical_guard_no_peer_credit(self):
        self.begin();self.runtime_bus.physical_done=False;count=len(self.wire.requests)
        with self.assertRaises(RuntimeError):self.retire()
        self.assertTrue(self.ch0_bus.released);self.assertEqual(self.runtime_bus.count,0)
        self.assertEqual(count,len(self.wire.requests));self.assertEqual(self.upload.credit,0)
    def test_mapping_retirement_missing_no_peer_retire(self):
        self.begin(); count=len(self.wire.requests)
        self.runtime_bus.retire=RuntimeModel.retire.__get__(self.runtime_bus)
        with self.assertRaises(RuntimeError):self.retire()
        self.assertEqual(self.runtime_bus.count,1);self.assertEqual(count,len(self.wire.requests))
    def test_wrong_CH0_driver_denied(self):
        self.begin();wrong=ch0store.CH0ArchiveDriver(CH0RegistrationDriverV2(CH0Bus(self.root/'other'),expected_clock_hz=100000000),self.root/'other')
        with self.assertRaises(RuntimeError):self.o.retire_verified(self.peer,ch0_archive=wrong,mapping=self.mapping,reader=self.reader,archive=self.archive)
        self.assertFalse(self.ch0_bus.released)
    def test_no_READY_waits_without_credit(self):
        self.begin();self.retire()
        result=self.o.accept_ready_verified(self.reader)
        self.assertTrue(result['waiting_for_actual_READY']);self.assertFalse(self.o.fault)
        self.assertEqual(self.upload.credit,0)
    def test_READY_credit_zero_denied(self):
        self.begin();self.retire()
        with self.assertRaises(ValueError):self.ready(0)
        self.assertEqual(self.upload.credit,0)
    def test_CH0_raw_tamper_before_READY_denied(self):
        self.begin();self.retire()
        (Path(self.o.strict_ch0_release['evidence_dir'])/'a_raw.bin').write_bytes(b'changed')
        with self.assertRaises(ValueError):self.ready()
        self.assertEqual(self.upload.credit,0)
    def test_actual_CH1_epoch_change_before_READY_denied(self):
        self.begin();self.retire();self.runtime_bus.epoch=10
        with self.assertRaises(RuntimeError):self.ready()
        self.assertEqual(self.upload.credit,0)
    def test_peer_retirement_reply_lost_no_retry(self):
        self.begin();original=self.wire.exchange
        def lost(request,expected):
            result=original(request,expected)
            if request and v.decode_frame(request)[0]==0x37:raise OSError('Lost peer retire reply')
            return result
        self.wire.exchange=lost
        with self.assertRaises(OSError):self.retire()
        count=len(self.wire.requests)
        with self.assertRaises(RuntimeError):self.retire()
        self.assertEqual(count,len(self.wire.requests));self.assertEqual(self.upload.credit,0)

    def test_CH1_archive_tamper_before_READY_denied(self):
        self.begin();self.retire()
        (Path(self.o.strict_saved['evidence_dir'])/'samples.bin').write_bytes(b'changed')
        with self.assertRaises(ValueError):self.ready()
        self.assertEqual(self.upload.credit,0)

    def test_CH0_release_dictionary_cannot_be_copied_into_proof(self):
        self.begin();self.retire()
        self.o.strict_ch0_release=dict(self.o.strict_ch0_release)
        with self.assertRaises(RuntimeError):self.ready()
        self.assertEqual(self.upload.credit,0)

    def test_pending_extra_H1_event_after_READY_denies_credit(self):
        self.begin();self.retire()
        self.status_bus.events=[reply(self.inner,0x80,seq=0,crc=0,credit=1),reply(self.inner,0x83,seq=1)]
        with self.assertRaises(RuntimeError):self.o.accept_ready_verified(self.reader)
        self.assertEqual(self.upload.credit,0)

    def test_actual_epoch_mutation_during_READY_save_denies_credit(self):
        self.begin();self.retire();original=self.status_bus.write
        def late(a,value):
            original(a,value)
            if a==0x34:self.runtime_bus.epoch=10
        self.status_bus.write=late
        with self.assertRaises(RuntimeError):self.ready()
        self.assertEqual(self.upload.credit,0)

    def test_changed_completion_fingerprint_no_local_release(self):
        self.begin();self.completion.receipt['inner_sha256']='bad'
        with self.assertRaises(ValueError):self.retire()
        self.assertFalse(self.ch0_bus.released)

    def test_ITEM_source_payload_compared_before_next_credit(self):
        config_owner=v.VerifiedTests.item_fixture(self)
        self.begin(config_owner=config_owner)
        self.retire()
        self.assertTrue(self.o.business_success)
        self.assertTrue(self.ready()['next_item_allowed'])
        saved=Path(self.o.strict_saved['evidence_dir'])
        self.assertEqual((saved/'expected_payload.bin').read_bytes(),bytes(range(256)))

    def test_delayed_peer_retirement_requires_actual_notification(self):
        self.begin();original=self.wire.exchange
        def delayed(request,expected):
            result=original(request,expected)
            if request and v.decode_frame(request)[0]==0x37:
                return v.frame(0x77,v.decode_frame(request)[1])
            return result
        self.wire.exchange=delayed
        result=self.retire();self.assertFalse(result['peer_retirement_verified'])
        self.assertEqual(self.upload.credit,0)
        self.wire.inject=v.frame(0x38,v.event_payload(self.identity,self.binding.record_id))
        self.assertTrue(self.o.poll_lifecycle(self.peer)['peer_retirement_confirmed'])
        self.assertTrue(self.ready()['next_item_allowed'])

    def test_credit_cannot_be_granted_twice(self):
        self.begin();self.retire();self.ready()
        with self.assertRaises(RuntimeError):self.o.accept_ready_verified(self.reader)
        self.assertIsNone(self.upload.current)


if __name__=='__main__':unittest.main(verbosity=2)
