"""Software orchestration tests: register models + real local persistence, no RTL."""
from pathlib import Path
import sys, uuid, unittest
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'host'), str(ROOT/'tests')]
from ch1_runtime_driver import CH1RuntimeDriver
from ch1_axi_archive_driver import CH1ArchiveDriver
from test_axi_archive_driver import MainModel, AuxModel
from test_evidence_store import fixture
import ch1_evidence_store as store


class RuntimeModel:
    def __init__(self):
        self.regs = {}; self.epoch = 0; self.live = False; self.pending = False
        self.fault = False; self.tick = 0; self.seq = 0; self.snap = None
        self.mask = 0; self.count = 0; self.writes = []; self.binding_regs = {}
        self.main = None; self.capacity = False; self.physical_done = False
        self.aux_pending = False; self.reject_snapshot = False; self.arm_pending = False
        self.complete_on_command = False; self.bad_mask = False; self.lost_release_reply = False
        self.accept_arm = True

    def qualified(self):
        return self.physical_done and self.main is not None and self.main.effects == 1

    def retire(self):
        if self.pending and self.capacity and not self.aux_pending and self.qualified():
            self.live = False; self.pending = False; self.count = (self.count+1)&0xffffffff

    def read(self, a):
        if a == 0: return 0x48315231
        if a == 4:
            return int(bool(self.epoch)) | (2 if self.live else 0) | (4 if self.pending else 0) | (8 if self.fault else 0) | (16 if self.snap else 0) | (32 if self.arm_pending else 0) | (64 if self.live and self.main is not None else 0) | (128 if self.qualified() else 0) | (256 if self.aux_pending else 0)
        if a == 8: return self.epoch
        if a == 12: return 1
        if a == 0x24: return self.count
        if a == 0x28: return self.mask if not self.bad_mask else 7
        if a in (0x14,0x18,0x1c,0x20):
            self.mask |= 1<<((a-0x14)//4)
            return self.snap[(a-0x14)//4]
        return self.binding_regs[a]

    def write(self, a, v):
        self.writes.append((a,v))
        if a == 0x34:
            self.epoch = self.regs[0x30]; self.snap = None; self.mask = 0
        elif a == 0x10:
            if self.reject_snapshot: return
            if self.snap and self.mask != 15: raise RuntimeError('Unread old snapshot')
            self.seq += 1; self.snap = [self.tick>>32,self.tick&0xffffffff,self.epoch,self.seq]; self.mask=0
        elif a == 0x70:
            self.live = True
            self.arm_pending = not self.accept_arm
            start = self.tick+self.regs[0x48]; deadline=start+self.regs[0x4c]
            self.binding_regs = {0x100:self.regs[0x44],0x104:self.regs[0x40],0x108:start>>32,
                0x10c:start&0xffffffff,0x110:deadline>>32,0x114:deadline&0xffffffff}
            for i in range(8): self.binding_regs[0x120+4*i]=self.regs[0x50+4*i]
        elif a == 0xa8:
            assert self.qualified(), 'Release before durable proof and physical completion'
            assert self.regs[0x80]==self.epoch and self.regs[0x84]==self.binding_regs[0x100]
            assert all(self.regs[0x88+4*i]==self.binding_regs[0x120+4*i] for i in range(8))
            self.pending=True
            if self.complete_on_command: self.retire()
            if self.lost_release_reply:
                self.lost_release_reply=False; raise OSError('Lost release reply after execution')
        elif a != 0xb0: self.regs[a]=v


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.root=ROOT/'evidence/offline_runtime_tests'/('test_'+uuid.uuid4().hex)
        self.bus=RuntimeModel(); self.driver=CH1RuntimeDriver(self.bus,poll_limit=3)
        self.driver.activate_epoch(1)

    def setup_record(self,name='max',reason=1):
        d,s,raw,w=fixture(name,reason=reason)
        decoded=store.descriptor_decode(d)
        self.main=MainModel(self.root,d,s); self.aux=AuxModel(self.root)
        self.archive=CH1ArchiveDriver(self.main,self.aux,self.root)
        self.bus.main=self.main
        bound=self.driver.arm(kind=1,record_id=17,identity=decoded['identity'],delay_ticks=50,duration_ticks=799950)
        self.bus.tick=w
        return bound,raw

    def test_wrong_controller_identity_never_writes(self):
        b=RuntimeModel(); b.read=lambda a:0
        with self.assertRaises(RuntimeError): CH1RuntimeDriver(b)
        self.assertEqual(b.writes,[])

    def test_snapshot_low_word_rollover_and_partial_read_recovery(self):
        self.bus.tick=0xffffffff; first=self.driver.snapshot()
        self.assertEqual(first['tick'],0xffffffff)
        self.bus.mask=1; self.bus.tick=0x100000001
        second=self.driver.snapshot()
        self.assertEqual(second['tick'],0x100000001); self.assertEqual(self.bus.mask,15)

    def test_rejected_snapshot_never_reuses_old_watermark(self):
        self.driver.snapshot(); self.bus.reject_snapshot=True
        with self.assertRaises(RuntimeError): self.driver.snapshot()

    def test_incomplete_snapshot_delivery_denied(self):
        self.bus.bad_mask=True
        with self.assertRaises(RuntimeError): self.driver.snapshot()

    def test_invalid_arm_rejected_before_writes(self):
        before=len(self.bus.writes)
        with self.assertRaises(ValueError): self.driver.arm(kind=1,record_id=1,identity=0,delay_ticks=50,duration_ticks=100)
        self.assertEqual(len(self.bus.writes),before)

    def test_busy_arm_never_restarts_record(self):
        bound,_=self.setup_record(); before=len(self.bus.writes)
        with self.assertRaises(RuntimeError): self.driver.arm(kind=1,record_id=18,identity=bound.identity,delay_ticks=50,duration_ticks=100)
        self.assertEqual(len(self.bus.writes),before)

    def test_actual_arm_acceptance_required(self):
        self.bus.accept_arm=False
        with self.assertRaises(TimeoutError): self.setup_record()
        self.assertEqual(sum(a==0x70 for a,_ in self.bus.writes),1)

    def test_complete_save_pending_capacity_then_actual_retirement(self):
        bound,raw=self.setup_record(); self.bus.physical_done=True
        saved,ticket=self.driver.archive_and_request_release(self.archive,expected_payload=raw[18:-2])
        self.assertTrue(saved['business_success']); self.assertEqual(len(self.main.coverage),1620)
        self.assertFalse(saved['hardware_retirement_verified'])
        with self.assertRaises(TimeoutError): self.driver.wait_retirement(ticket)
        before=len(self.bus.writes)
        self.assertEqual(self.driver.request_release(bound),ticket)
        self.assertEqual(len(self.bus.writes),before)
        self.bus.capacity=True; self.bus.retire()
        self.assertTrue(self.driver.wait_retirement(ticket)['hardware_retirement_verified'])

    def test_immediate_retirement_does_not_require_observing_pulse(self):
        _,raw=self.setup_record(); self.bus.physical_done=True
        self.bus.capacity=True; self.bus.complete_on_command=True
        _,ticket=self.driver.archive_and_request_release(self.archive,expected_payload=raw[18:-2])
        self.assertTrue(self.driver.wait_retirement(ticket)['hardware_retirement_verified'])

    def test_missing_physical_done_preserves_archive_without_release(self):
        self.setup_record()
        with self.assertRaises(RuntimeError): self.driver.archive_and_request_release(self.archive)
        self.assertTrue(list((self.root/'main').glob('*/committed.json')))
        self.assertFalse(any(a==0xa8 for a,_ in self.bus.writes))

    def test_fsync_failure_never_releases(self):
        self.setup_record(); self.bus.physical_done=True
        with patch.object(store,'_write',side_effect=OSError('Persistence failed')):
            with self.assertRaises(OSError): self.driver.archive_and_request_release(self.archive)
        self.assertFalse(any(a==0xa8 for a,_ in self.bus.writes))
        self.assertEqual(self.main.effects,0)

    def test_bad_crc_never_releases(self):
        self.setup_record(); self.main.bad_crc=True
        with self.assertRaises(ValueError): self.driver.archive_and_request_release(self.archive)
        self.assertFalse(any(a==0xa8 for a,_ in self.bus.writes))

    def test_failure_report_is_saved_and_retired_without_image_success(self):
        self.setup_record('bad_crc',2); self.bus.physical_done=True
        saved,ticket=self.driver.archive_and_request_release(self.archive)
        self.assertFalse(saved['business_success'])
        self.bus.capacity=True; self.bus.retire()
        self.assertTrue(self.driver.wait_retirement(ticket)['hardware_retirement_verified'])

    def test_pending_late_aux_can_be_drained_while_waiting(self):
        self.setup_record(); self.bus.physical_done=True
        _,ticket=self.driver.archive_and_request_release(self.archive)
        self.bus.capacity=True; self.bus.aux_pending=True; self.bus.retire()
        self.assertTrue(self.bus.live)
        def drained(): self.bus.aux_pending=False; self.bus.retire()
        self.assertTrue(self.driver.wait_retirement(ticket,drain_aux=drained)['hardware_retirement_verified'])

    def test_fault_during_wait_never_returns_success(self):
        self.setup_record(); self.bus.physical_done=True
        _,ticket=self.driver.archive_and_request_release(self.archive); self.bus.fault=True
        with self.assertRaises(RuntimeError): self.driver.wait_retirement(ticket)

    def test_reset_or_extra_retirement_rejected(self):
        self.setup_record(); self.bus.physical_done=True
        _,ticket=self.driver.archive_and_request_release(self.archive)
        self.bus.epoch=0
        with self.assertRaises(RuntimeError): self.driver.wait_retirement(ticket)
        self.bus.epoch=1; self.bus.count=2; self.bus.live=False
        with self.assertRaises(RuntimeError): self.driver.wait_retirement(ticket)

    def test_abort_does_not_claim_retirement(self):
        self.setup_record(); result=self.driver.abort()
        self.assertFalse(result['hardware_retirement_verified']); self.assertTrue(self.bus.live)

    def test_lost_release_reply_recovers_pending_without_restaging(self):
        bound,_=self.setup_record(); self.bus.physical_done=True
        self.bus.lost_release_reply=True
        with self.assertRaises(OSError): self.driver.archive_and_request_release(self.archive)
        before=len(self.bus.writes); ticket=self.driver.request_release(bound)
        self.assertEqual(len(self.bus.writes),before)
        self.bus.capacity=True; self.bus.retire()
        self.assertTrue(self.driver.wait_retirement(ticket)['hardware_retirement_verified'])


if __name__=='__main__': unittest.main(verbosity=2)
