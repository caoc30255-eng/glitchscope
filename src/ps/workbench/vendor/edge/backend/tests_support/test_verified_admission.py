"""Source-driver register models + real fsync/control-frame journals. No hardware/HDL."""
from pathlib import Path
from dataclasses import replace
from unittest.mock import patch
import importlib.util,sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'host'),str(ROOT/'tests'),str(ROOT/'host')]
import test_application_owner as app
from test_completion_ledger import StatusBus,reply
from ch1_completion_ledger import CompletionLedger,H1CompletionReader
from ch1_runtime_driver import Binding
from ch1_admission_parts import AdmissionParts
from ch1_verified_admission import FlightContext,VerifiedAdmissionCoordinator,AdmissionTicket
from ch1_verified_item_owner import VerifiedSingleItemOwner
from ch1_control_session import decode_frame,PeerControlSession,frame,event_payload,decode_event,audit_application_journal
from ch1_completion_ledger import _codec
from ch1_peer_archive_driver import AXPeerArchiveDriver
from h1_protocol import Kind
from types import SimpleNamespace
import hashlib
import ch1_evidence_store as store

def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
profilemod=load('profile_driver_src',ROOT/'host/ch0_rx_profile_driver.py')
profilemodel=load('profile_model_src',ROOT/'tests/fixtures/profile/tests/test_profile_driver.py')
ch0mod=load('ch0_v2_src',ROOT/'host/ch0_registration_driver_v0_2.py')
ch0model=load('ch0_v2_model_src',ROOT/'tests/fixtures/registration/tests/test_registration_driver_v2.py')
obsmod=load('observer_driver_src',ROOT/'host/peer_prestart_driver.py')

class ObserverBus:
 def __init__(self,upload,identity):self.upload=upload;self.identity=identity;self.seq=0;self.valid=False;self.live=True;self.wrong=False
 def read(self,a):
  if a==0:return 0x48505131
  if a==4:return (0xe7 if self.live else 0xc7) if self.valid else 0x85
  if a==8:return self.seq
  if a==0xc:return 0xfff
  fields=store._fields(self.identity,store.IDENTITY);kind,seq,inner,outer=self.upload.current
  ident=self.identity ^ (1<<88) if self.wrong else self.identity
  values=[fields['route_epoch'],(ident>>88)&0xffffffff,(len(inner)<<8)|int(kind),fields['session'],*[(ident>>(224-32*i))&0xffffffff for i in range(8)]]
  return values[(a-0x100)//4]
 def write(self,a,v):assert a==0x10 and v==1;self.valid=True;self.seq+=1
class Runtime:
 def __init__(self):self.bound=None;self.tick=1500;self.seq=0
 def binding(self):return self.bound
 def snapshot(self):self.seq+=1;return {'epoch':self.bound.epoch,'tick':self.tick,'seq':self.seq}

class VerifiedTests(unittest.TestCase):
 def setUp(self):
  app.AppTests.setUp(self)
  self.identity &= ~((0xffff<<32)|(0xffff<<16)|(0xff<<8));self.wire.identity=self.identity
  self.binding=Binding(9,17,2,self.identity,1000,300000)
  self.completion=CompletionLedger(self.root/'completion',local_epoch=9,peer_epoch=1,session=self.upload.session);self.addCleanup(self.completion.close)
  self.status_bus=StatusBus(self.completion);self.reader=H1CompletionReader(self.status_bus,self.completion)
  self.runtime=Runtime();self.order=[]
  self.profile_bus=profilemodel.Bus();self.profile=profilemod.CH0RXProfileDriver(self.profile_bus)
  self.ch0_bus=ch0model.Bus();self.ch0=ch0mod.CH0RegistrationDriverV2(self.ch0_bus,expected_clock_hz=100000000)
  self.observer_bus=ObserverBus(self.upload,self.identity);self.observer=obsmod.PeerPrestartDriver(self.observer_bus)
  self.parts=AdmissionParts(self.root/'flight',self.journal)
  self.coordinator=VerifiedAdmissionCoordinator(self.root/'admission',self.journal,peer=self.peer,observer=self.observer,parts=self.parts,profile=self.profile,ch0=self.ch0,runtime=self.runtime)
  self.wire.exchange_checked=lambda request,expected,guard:(guard(),self.wire.exchange(request,expected))[1]
  self.context=FlightContext(9,17,2,self.identity)
 def arm(self,c):
  self.order.append('ARM');self.runtime.bound=self.binding;self.reader.bind_prepared(self.binding,self.upload);return self.binding
 def deliver(self,b):
  self.order.append('H1_DELIVER_ARCHIVE');receipt=app.AppTests.archive(self)
  self.status_bus.events=[reply(self.inner,seq=self.upload.current[1])];self.reader.read_and_preserve();return receipt
 def issue(self):
  return self.coordinator.issue(self.context,self.upload,self.completion,arm_ch1=self.arm,deliver_and_archive=self.deliver,d=2,s=0,ch0_delay_ticks=4,ch0_duration_ticks=4000)
 def owner(self):return VerifiedSingleItemOwner(self.journal,self.binding,self.upload,self.completion)
 def start(self,o,t):return o.start_verified(self.peer,self.coordinator,t,ch0_margin_ticks=100,ch1_margin_ticks=100)
 def starts(self):return sum(decode_frame(r)[0]==0x11 for r in self.wire.requests if r)
 def item_fixture(self):
  old=self.binding;payload=bytes(range(256));codec=_codec()
  cfg=codec.encode_config(1,2,16,16,256,1,256,hashlib.sha256(payload).digest(),[store.crc16(payload)])
  ack=decode_event(frame(0x79,event_payload(old.identity,17)));self.journal.record('control_rx_stream',raw_hex=ack['raw_hex'])
  config=SimpleNamespace(fault=False,phase='RETIRED',business_success=True,config_success_ack=ack,prepared_inner=cfg,binding=old,journal=self.journal)
  self.upload.current=None;self.upload.credit=1;self.upload.seq=1
  self.inner=codec.encode_item(1,2,3,0,1,0,0,payload);self.upload.prepare(Kind.ITEM,self.inner)
  self.identity=(old.identity & ~((0xffffffff<<155)|(0xffffffff<<88)|(0xffff<<32)))|(2<<155)|(2<<88)|(3<<32)
  self.binding=Binding(9,18,1,self.identity,1000,300000);self.context=FlightContext(9,18,1,self.identity)
  self.cache=app.PeerCache(self.root/'peer',self.upload);self.wire=app.WirePeer(self.cache,self.identity)
  original=self.wire.exchange
  def policy(request,expected):
   if request and decode_frame(request)[0]==0x3a:
    self.wire.requests.append(request);return frame(0x7a,decode_frame(request)[1])
   return original(request,expected)
  self.wire.exchange=policy;self.peer=PeerControlSession(self.wire,self.journal,0x73000001)
  self.driver=AXPeerArchiveDriver(self.peer,self.root/'peer',poll_limit=3)
  self.observer_bus=ObserverBus(self.upload,self.identity);self.observer=obsmod.PeerPrestartDriver(self.observer_bus)
  self.wire.exchange_checked=lambda request,expected,guard:(guard(),self.wire.exchange(request,expected))[1]
  self.coordinator.peer=self.peer;self.coordinator.observer=self.observer
  return config
 def test_item_requires_prior_exact_config_approval(self):
  self.item_fixture()
  with self.assertRaises(RuntimeError):self.issue()
  self.assertEqual(self.starts(),0)
 def test_item_with_exact_config_ack_and_disabled_policy(self):
  config=self.item_fixture()
  t=self.coordinator.issue(self.context,self.upload,self.completion,arm_ch1=self.arm,deliver_and_archive=self.deliver,d=2,s=0,ch0_delay_ticks=4,ch0_duration_ticks=4000,config_owner=config)
  self.start(self.owner(),t);self.assertEqual(self.starts(),1)
  kinds=[decode_frame(r)[0] for r in self.wire.requests if r];self.assertIn(0x3a,kinds)
 def test_actual_source_drivers_real_seal_and_exact_control_start(self):
  ticket=self.issue();owner=self.owner();result=self.start(owner,ticket)
  self.assertEqual(self.order,['ARM','H1_DELIVER_ARCHIVE']);self.assertEqual(self.starts(),1)
  record=self.coordinator.tickets[ticket.token];self.assertEqual(record['ch0_binding']['epoch'],9);self.assertEqual(record['ch0_binding']['peer_epoch'],1)
  self.assertTrue((record['directory']/'committed.json').is_file());self.assertTrue((record['directory']/'consumed.json').is_file())
  self.assertTrue(result['physical_start_confirmed'] and result['physical_done_confirmed']);self.assertEqual(owner.phase,'DONE')
 def test_sealed_is_not_start_and_windows_use_independent_ticks(self):
  t=self.issue();self.assertEqual(self.starts(),0);r=self.coordinator.tickets[t.token]
  self.assertNotEqual(r['ch0_binding']['start'],r['binding'].start)
  owner=self.owner();self.start(owner,t);self.assertEqual(self.starts(),1)
 def test_strict_stage_does_not_retire_peer_or_unlock_next_item(self):
  t=self.issue();o=self.owner();self.start(o,t);before=len(self.wire.requests)
  with self.assertRaises(RuntimeError):o.retire_peer(self.peer,{})
  with self.assertRaises(RuntimeError):o.accept_ready({})
  self.assertEqual(len(self.wire.requests),before);self.assertIsNotNone(self.upload.current);self.assertEqual(self.upload.credit,0)
 def test_boolean_flags_cannot_enter_strict_owner(self):
  t=self.issue();o=self.owner()
  with self.assertRaises(RuntimeError):o.start(self.peer,self.runtime,{},dict(CH0_registered=True),minimum_remaining_ticks=1)
  self.assertEqual(self.starts(),0)
 def test_reconstructed_ticket_rejected_before_window(self):
  t=self.issue();o=self.owner();before=len(self.wire.requests)
  with self.assertRaises(RuntimeError):self.start(o,AdmissionTicket(t.token))
  self.assertEqual(len(self.wire.requests),before);self.assertEqual(self.starts(),0)
 def test_peer_generation_mismatch_no_ticket(self):
  self.observer_bus.wrong=True
  with self.assertRaises((ValueError,RuntimeError)):self.issue()
  self.assertEqual(self.starts(),0);self.assertFalse(self.coordinator.tickets)
 def test_changed_snapshot_sequence_denied(self):
  t=self.issue();self.observer_bus.seq+=1
  with self.assertRaises(RuntimeError):self.start(self.owner(),t)
  self.assertEqual(self.starts(),0)
 def test_peer_no_longer_live_denied(self):
  t=self.issue();self.observer_bus.live=False
  with self.assertRaises(RuntimeError):self.start(self.owner(),t)
  self.assertEqual(self.starts(),0)
 def test_profile_changed_denied(self):
  t=self.issue();self.profile_bus.d=1
  with self.assertRaises(RuntimeError):self.start(self.owner(),t)
  self.assertEqual(self.starts(),0)
 def test_ch0_closed_or_received_denied(self):
  t=self.issue();self.ch0_bus.live=1
  with self.assertRaises(RuntimeError):self.start(self.owner(),t)
  self.assertEqual(self.starts(),0)
 def test_completion_fault_no_start(self):
  t=self.issue();self.completion.fault=True
  with self.assertRaises(RuntimeError):self.start(self.owner(),t)
  self.assertEqual(self.starts(),0)
 def test_completion_full_binding_changed_no_start(self):
  t=self.issue();self.completion.current['binding']['record_id']=99
  with self.assertRaises(ValueError):self.start(self.owner(),t)
  self.assertEqual(self.starts(),0)
 def test_ch1_expired_denied(self):
  t=self.issue();self.runtime.tick=self.binding.deadline
  with self.assertRaises(RuntimeError):self.start(self.owner(),t)
  self.assertEqual(self.starts(),0)
 def test_actual_ch1_binding_changed_denied(self):
  t=self.issue();self.runtime.bound=replace(self.binding,record_id=18)
  with self.assertRaises(RuntimeError):self.start(self.owner(),t)
  self.assertEqual(self.starts(),0)
 def test_peer_archive_corruption_before_ticket(self):
  original=self.deliver
  def corrupt(b):
   proof=original(b);(Path(proof['directory'])/'inner.bin').write_bytes(b'bad');return proof
  self.deliver=corrupt
  with self.assertRaises(ValueError):self.issue()
  self.assertEqual(self.starts(),0)
 def test_sealed_receipt_corruption_denied(self):
  t=self.issue();r=self.coordinator.tickets[t.token];(r['directory']/'admission.json').write_bytes(b'bad')
  with self.assertRaises(ValueError):self.start(self.owner(),t)
  self.assertEqual(self.starts(),0)
 def test_flight_corruption_denied(self):
  t=self.issue();r=self.coordinator.tickets[t.token];(Path(r['parts']['flight_dir'])/'outer.bin').write_bytes(b'bad')
  with self.assertRaises(ValueError):self.start(self.owner(),t)
  self.assertEqual(self.starts(),0)
 def test_consumption_disk_failure_no_start(self):
  t=self.issue();original=store._write
  def fail(p,raw):
   if Path(p).name=='consumed.json':raise OSError('consumption fsync failed')
   return original(p,raw)
  with patch.object(store,'_write',side_effect=fail):
   with self.assertRaises(OSError):self.start(self.owner(),t)
  self.assertEqual(self.starts(),0);self.assertEqual(self.coordinator.tickets[t.token]['phase'],'CONSUMED')
 def test_window_can_expire_during_consumption_fsync(self):
  t=self.issue();original=store._write
  def delayed(p,raw):
   result=original(p,raw)
   if Path(p).name=='consumed.json':self.runtime.tick=self.binding.deadline
   return result
  with patch.object(store,'_write',side_effect=delayed):
   with self.assertRaises(RuntimeError):self.start(self.owner(),t)
  self.assertEqual(self.starts(),0)
 def test_expiry_during_control_tx_intent_fsync_prevents_wire_start(self):
  t=self.issue();original=self.journal.record
  def delayed(event,**fields):
   result=original(event,**fields)
   if event=='control_tx_intent' and fields.get('raw_hex') and decode_frame(bytes.fromhex(fields['raw_hex']))[0]==0x11:self.runtime.tick=self.binding.deadline
   return result
  with patch.object(self.journal,'record',side_effect=delayed):
   with self.assertRaises(RuntimeError):self.start(self.owner(),t)
  self.assertEqual(self.starts(),0);self.assertTrue(self.peer.fault)
 def test_uncertain_start_cannot_retry(self):
  t=self.issue();o=self.owner();original=self.wire.exchange
  def lost(request,expected):
   if request and decode_frame(request)[0]==0x11:self.wire.requests.append(request);raise OSError('lost START reply')
   return original(request,expected)
  self.wire.exchange=lost
  with self.assertRaises(OSError):self.start(o,t)
  self.assertEqual(self.starts(),1)
  with self.assertRaises(RuntimeError):self.start(o,t)
  self.assertEqual(self.starts(),1);self.assertTrue(o.fault)
  self.assertEqual(audit_application_journal(self.journal.path)['start_intents'],1)
if __name__=='__main__':unittest.main(verbosity=2)
