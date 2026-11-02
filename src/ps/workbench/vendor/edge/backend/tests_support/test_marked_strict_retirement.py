"""Full modeled strict marked START->pin snapshot->CH0/CH1->MARK_STORED->READY."""
from pathlib import Path
from unittest.mock import patch
import sys,unittest,json
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'host'),str(ROOT/'tests')]
import test_verified_retirement as r
import test_verified_admission as v
from test_fault_mark_candidate import SnapshotBus
from raw_mark_snapshot import RawMarkCapture
from fault_profile import FaultProfile
from ch1_control_session import frame,decode_frame,event_payload
from ch1_completion_ledger import _codec
from ch1_axi_archive_driver import CH1ArchiveDriver
from test_evidence_store import packed
from test_axi_archive_driver import MainModel,AuxModel
import ch1_evidence_store as store

class MarkedRetirementTests(unittest.TestCase):
 issue=v.VerifiedTests.issue
 deliver=v.VerifiedTests.deliver
 owner=v.VerifiedTests.owner
 start=v.VerifiedTests.start
 arm=r.RetirementTests.arm
 retire=r.RetirementTests.retire
 ready=r.RetirementTests.ready
 def setUp(self):
  r.RetirementTests.setUp(self)
  self.config=v.VerifiedTests.item_fixture(self)
  self.raw_bus=SnapshotBus();self.capture=RawMarkCapture(self.raw_bus,self.root/'physical_mark')
  self.fault_profile=FaultProfile(20,0,15,20);self.suppress_pin=False
  original=self.wire.exchange
  def exchange(request,expected):
   if request and decode_frame(request)[0]==0x11:
    self.wire.requests.append(request)
    p=decode_frame(request)[1]
    if not self.suppress_pin:self.raw_bus.trigger()
    return (frame(0x31,event_payload(self.identity,0))+
            frame(0x33,event_payload(self.identity,0))+
            frame(0x80,bytes([0x11])+p+bytes([1]))+
            frame(0x32,event_payload(self.identity,0)))
   return original(request,expected)
  self.wire.exchange=exchange
  original_issue=self.coordinator.issue
  self.coordinator.issue=lambda *a,**kw:original_issue(*a,**kw,
      fault_profile=self.fault_profile,mark_capture=self.capture)
 def begin(self):r.RetirementTests.begin(self,config_owner=self.config)
 def types(self):return [decode_frame(x)[0] for x in self.wire.requests if x]
 def test_complete_marked_strict_retirement_requires_actual_pin_archive(self):
  self.begin();self.assertTrue(self.o.mark_required and self.o.mark_seen)
  result=self.retire();self.assertTrue(result['peer_retirement_verified'])
  kinds=self.types();self.assertLess(kinds.index(0x35),kinds.index(0x36));self.assertLess(kinds.index(0x36),kinds.index(0x37))
  proof=self.capture.verify_saved(self.o.mark_receipt,self.binding)
  self.assertTrue(proof['physical_mark_snapshot_saved'])
  self.assertTrue(self.ready()['next_item_allowed'])
 def test_missing_pin_mark_blocks_before_any_local_release(self):
  self.suppress_pin=True;self.begin()
  with self.assertRaises(RuntimeError):self.retire()
  self.assertFalse(self.ch0_bus.released);self.assertEqual(self.runtime_bus.count,0)
  self.assertNotIn(0x36,self.types());self.assertNotIn(0x37,self.types())
 def test_mark_snapshot_save_failure_blocks_local_release(self):
  self.begin()
  with patch('raw_mark_snapshot.persist_exact',side_effect=OSError('disk')):
   with self.assertRaises(OSError):self.retire()
  self.assertFalse(self.ch0_bus.released);self.assertEqual(self.runtime_bus.count,0)
  self.assertNotIn(0x36,self.types())
 def test_tamper_after_LOCAL_ACK_blocks_MARK_STORED_and_RETIRE(self):
  self.begin();original=self.peer.request_event
  def request(typ,identity,record):
   result=original(typ,identity,record)
   if typ==0x35:
    p=Path(self.o.mark_receipt.evidence_dir)/'samples.bin';p.write_bytes(bytes(4096))
   return result
  self.peer.request_event=request
  with self.assertRaises(ValueError):self.retire()
  self.assertNotIn(0x36,self.types());self.assertNotIn(0x37,self.types())
 def test_expected_bad_payload_is_preserved_and_can_retire_without_image_success(self):
  self.begin();item=_codec().decode_item(self.inner)
  changed=bytes([item['payload'][0]^1])+item['payload'][1:]
  raw=_codec().encode_report(item['run_id'],item['image_id'],item['trial_id'],item['item_index'],item['attempt_id'],0,0,3,changed)
  d={'epoch':9,'reserved':0,'identity':self.identity,'record_id':self.binding.record_id,'kind':1,
     'reason':1,'raw_count':len(raw),'start':1000,'deadline':300000,'close':278100,
     'frame_valid':1,'report_status':3,'report_flags':0,'management_status':0,
     'uart_errors':0,'observed_flags':0,'first_error_tick':0}
  descriptor=packed([(width,d[name]) for name,width in store.FIELDS])
  samples=b''.join(((byte<<68)|(1100+1000*i)).to_bytes(10,'big') for i,byte in enumerate(raw))
  self.main=MainModel(self.root,descriptor,samples);self.aux=AuxModel(self.root)
  self.archive=CH1ArchiveDriver(self.main,self.aux,self.root)
  self.runtime_bus.main=self.main;self.runtime_bus.tick=d['close']+1
  self.ch0_bus.raw=self.inner[:20]+bytes([self.inner[20]^1])+self.inner[21:]
  result=self.retire();self.assertTrue(result['peer_retirement_verified'])
  self.assertFalse(self.o.business_success)
  self.assertEqual((Path(self.o.saved_proof['evidence_dir'])/'raw_packet.bin').read_bytes(),raw)
  self.assertTrue(self.ready()['next_item_allowed'])
