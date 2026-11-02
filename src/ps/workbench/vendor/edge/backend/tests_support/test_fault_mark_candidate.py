"""Modeled physical samples, real protocol/CRC and durable files; no hardware."""
from pathlib import Path
from dataclasses import replace
from types import SimpleNamespace as NS
from collections import deque
from unittest.mock import patch,Mock
import sys,json,uuid,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'host'),str(ROOT/'tests')]
from fault_profile import FaultProfile
from raw_mark_snapshot import RawMarkCapture,MarkReceipt,analyze_waveform
from ch1_control_session import ApplicationJournal,PeerControlSession,frame,decode_frame,event_payload,decode_event
from ch1_completion_ledger import _codec
from ch1_runtime_driver import Binding
from ch1_item_owner import SingleItemOwner
from test_evidence_store import fixture
import ch1_evidence_store as store

class SnapshotBus:
 def __init__(self):
  self.cfg=0x201;self.status=0;self.count=0;self.offset=0;self.address=0;self.index=0;self.valid=False
  self.words=bytearray([2]*4096);self.writes=[];self.live=0;self.bad_padding=0;self.bad_index=False;self.mutate_count=False
 def read(self,a):
  if a==4:return self.cfg
  if a==8:return self.status|(16 if self.valid else 0)
  if a==12:return self.count
  if a==16:return self.offset
  if a==0x20:return self.live
  if a==0x28:return self.address
  if a==0x18:return self.index^(1 if self.bad_index else 0)
  if a==0x1c:
   self.valid=True
   if self.mutate_count and self.index==2000:self.count=4095
   return 0x100|self.words[self.index]|self.bad_padding
  raise AssertionError(a)
 def write(self,a,v):
  self.writes.append((a,v))
  if a==4:self.cfg=v
  elif a==0:
   assert v==1,'No reset allowed';self.status=3
  elif a==0x18:self.index=v;self.valid=False
  else:raise AssertionError(a)
 def trigger(self,shift=0):
  self.status=12;self.count=4096;self.offset=2048;self.address=2048<<16
  for i in range(2048,2050):self.words[i]|=4
  for i in range(2048+shift,2088+shift):self.words[i]|=1

class MarkTests(unittest.TestCase):
 def setUp(self):
  self.root=ROOT/'evidence/offline_fault_mark_tests'/uuid.uuid4().hex
  self.identity=store.descriptor_decode(fixture()[0])['identity']
  self.inner=_codec().encode_item(1,2,3,4,64,1,0,bytes(range(256)))
  self.binding=Binding(9,2,1,self.identity,100,10000)
  self.profile=FaultProfile(20,0,15,20);self.bus=SnapshotBus();self.cap=RawMarkCapture(self.bus,self.root/'mark')
  self.j=ApplicationJournal(self.root/('model_session_'+uuid.uuid4().hex),9);self.addCleanup(self.j.close)
  self.event=decode_event(frame(0x33,event_payload(self.identity,0)))
 def arm(self):return self.cap.arm(self.binding,self.inner,self.profile)
 def save(self):self.arm();self.bus.trigger();return self.cap.archive(self.binding,self.event)
 def peer(self,bad=False):
  calls=[]
  class Wire:
   def exchange(_,request,expected):
    calls.append(request);typ,p=decode_frame(request)
    assert typ==0x3a and expected==0x7a
    if bad:p=p[:-1]+bytes([p[-1]^1])
    return frame(0x7a,p)
  return PeerControlSession(Wire(),self.j,1),calls
 def test_profile_wire_matches_independent_RTL_byte_fields(self):
  peer,calls=self.peer();p=peer.request_profile_fault(self.identity,self.profile,self.inner)
  typ,data=decode_frame(calls[0]);self.assertEqual(typ,0x3a)
  self.assertEqual(len(data),32);self.assertEqual(data[23],1)
  self.assertEqual((data[24]<<8)|data[25],20);self.assertEqual(data[26],0)
  self.assertEqual((data[27]<<8)|data[28],15);self.assertEqual((data[29]<<8)|data[30],20)
  self.assertEqual(data[31],0);self.assertTrue(p['mark_required'])
 def test_wrong_policy_ACK_rejected(self):
  peer,calls=self.peer(True)
  with self.assertRaises(ValueError):peer.request_profile_fault(self.identity,self.profile,self.inner)
  self.assertTrue(peer.fault)
 def test_profile_identity_mismatch_has_no_TX(self):
  peer,calls=self.peer()
  with self.assertRaises(ValueError):peer.request_profile_fault(self.identity^(1<<32),self.profile,self.inner)
  self.assertEqual(calls,[])
 def test_header_target_rejected(self):
  with self.assertRaises(ValueError):FaultProfile(19,0,15,20).validate(self.inner)
 def test_crc_target_rejected(self):
  with self.assertRaises(ValueError):FaultProfile(len(self.inner)-2,0,15,20).validate(self.inner)
 def test_zero_width_rejected(self):
  with self.assertRaises(ValueError):FaultProfile(20,0,15,0).validate(self.inner)
 def test_outside_interior_window_rejected(self):
  for p in (FaultProfile(20,0,0,20),FaultProfile(20,0,30,20)):
   with self.assertRaises(ValueError):p.validate(self.inner)
 def test_bad_bit_rejected(self):
  with self.assertRaises(ValueError):FaultProfile(20,8,15,20).validate(self.inner)
 def test_clean_arm_only_config_and_ARM_no_reset(self):
  self.arm();self.assertEqual(self.bus.writes,[(4,0x201),(0,1)])
  self.assertTrue(self.cap.verify_armed(self.binding))
 def test_old_snapshot_retained_without_any_write(self):
  self.bus.trigger()
  with self.assertRaises(RuntimeError):self.arm()
  self.assertFalse(self.bus.writes)
 def test_high_mark_before_arm_denied(self):
  self.bus.live=4
  with self.assertRaises(RuntimeError):self.arm()
  self.assertFalse(self.bus.writes)
 def test_one_shot_cannot_rearm(self):
  self.arm();n=len(self.bus.writes)
  with self.assertRaises(RuntimeError):self.arm()
  self.assertEqual(len(self.bus.writes),n)
 def test_preSTART_early_trigger_denies(self):
  self.arm();self.bus.trigger()
  with self.assertRaises(RuntimeError):self.cap.verify_armed(self.binding)
 def test_complete_4096_reads_and_durable_receipt(self):
  receipt=self.save();proof=self.cap.verify_saved(receipt,self.binding)
  self.assertTrue(proof['physical_mark_snapshot_saved'])
  self.assertEqual(len([a for a,v in self.bus.writes if a==0x18]),4096)
  self.assertEqual((Path(receipt.evidence_dir)/'samples.bin').read_bytes(),bytes(self.bus.words))
 def test_pin_skew_minus_two_and_plus_two_samples_supported(self):
  for shift in (-2,2):
   bus=SnapshotBus();bus.trigger(shift)
   out=analyze_waveform(bus.words,2048,0,20)
   self.assertEqual(out['mark_to_inversion_samples'],shift)
 def test_no_mark_waveform_rejected(self):
  self.bus.trigger();self.bus.words[2048]&=~4;self.bus.words[2049]&=~4
  with self.assertRaises(ValueError):analyze_waveform(self.bus.words,2048,0,20)
 def test_extra_physical_mark_rejected(self):
  self.bus.trigger();self.bus.words[3000]|=4
  with self.assertRaises(ValueError):analyze_waveform(self.bus.words,2048,0,20)
 def test_mark_without_actual_inversion_rejected(self):
  self.bus.trigger();self.bus.words=bytearray(x&~1 for x in self.bus.words)
  with self.assertRaises(ValueError):analyze_waveform(self.bus.words,2048,0,20)
 def test_wrong_width_rejected(self):
  self.bus.trigger()
  with self.assertRaises(ValueError):analyze_waveform(self.bus.words,2048,0,5)
 def test_notification_wrong_identity_denied(self):
  self.arm();self.bus.trigger();other=decode_event(frame(0x33,event_payload(self.identity^(1<<32),0)))
  with self.assertRaises(ValueError):self.cap.archive(self.binding,other)
 def test_incomplete_capture_denied(self):
  self.arm()
  with self.assertRaises(RuntimeError):self.cap.archive(self.binding,self.event)
 def test_read_index_delivery_denied(self):
  self.arm();self.bus.trigger();self.bus.bad_index=True
  with self.assertRaises(RuntimeError):self.cap.archive(self.binding,self.event)
 def test_DWORD_reserved_bits_denied(self):
  self.arm();self.bus.trigger();self.bus.bad_padding=0x200
  with self.assertRaises(ValueError):self.cap.archive(self.binding,self.event)
 def test_metadata_mutation_during_read_denied(self):
  self.arm();self.bus.trigger();self.bus.mutate_count=True
  with self.assertRaises(RuntimeError):self.cap.archive(self.binding,self.event)
 def test_saved_sample_tamper_denied(self):
  receipt=self.save();p=Path(receipt.evidence_dir)/'samples.bin';p.write_bytes(bytes(4096))
  with self.assertRaises(ValueError):self.cap.verify_saved(receipt,self.binding)
 def test_forged_receipt_denied(self):
  receipt=self.save()
  with self.assertRaises(ValueError):self.cap.verify_saved(replace(receipt),self.binding)
 def test_arm_context_tamper_denied(self):
  self.arm();p=Path(self.cap.arm_receipt['arm_dir'])/'intent.json';p.write_bytes(b'{}')
  with self.assertRaises(ValueError):self.cap.verify_armed(self.binding)
 def test_intent_fsync_failure_sends_no_ARM(self):
  with patch('raw_mark_snapshot.persist_exact',side_effect=OSError('disk')):
   with self.assertRaises(OSError):self.arm()
  self.assertFalse(self.bus.writes)
 def test_unreviewed_HWH_maps_nothing(self):
  p=self.root/'wrong.hwh';p.parent.mkdir(exist_ok=True);p.write_bytes(b'not reviewed')
  factory=Mock()
  with self.assertRaises(ValueError):RawMarkCapture.from_reviewed_hwh(factory,self.root,p)
  factory.assert_not_called()
 def owner(self,marked=True):
  upload=NS(current=(3,1,self.inner,b'outer'),fault=False)
  owner=SingleItemOwner(self.j,self.binding,upload,NS());owner.phase='START_REQUESTED';owner.mark_required=marked
  peer=NS(events=deque(),ack_notification=Mock(),limit=64)
  return owner,peer
 def push(self,peer,typ,identity=None):
  event=decode_event(frame(typ,event_payload(self.identity if identity is None else identity,0)))
  self.j.record('control_rx_stream',raw_hex=event['raw_hex']);peer.events.append(event)
 def test_marked_notifications_exact_order_and_replay(self):
  o,p=self.owner();self.push(p,0x31);self.push(p,0x33);self.push(p,0x32);o.drain_notifications(p)
  self.assertTrue(o.started and o.mark_seen and o.done)
  self.push(p,0x33);o.drain_notifications(p)
  rows=[json.loads(x) for x in self.j.path.read_text().splitlines()]
  self.assertEqual(sum(x.get('effect')=='FAULT_MARK' for x in rows),1)
  self.assertEqual(p.ack_notification.call_count,4)
 def test_DONE_without_required_mark_cannot_complete(self):
  o,p=self.owner();self.push(p,0x31);o.drain_notifications(p);self.push(p,0x32)
  with self.assertRaises(ValueError):o.drain_notifications(p)
  self.assertFalse(o.done);self.assertTrue(o.fault)
 def test_unmarked_owner_still_rejects_mark(self):
  o,p=self.owner(False);self.push(p,0x31);o.drain_notifications(p);self.push(p,0x33)
  with self.assertRaises(ValueError):o.drain_notifications(p)
 def test_changed_mark_identity_preserves_first(self):
  o,p=self.owner();self.push(p,0x31);self.push(p,0x33);o.drain_notifications(p)
  original=dict(o.notifications[0x33]);self.push(p,0x33,self.identity^(1<<32))
  with self.assertRaises(ValueError):o.drain_notifications(p)
  self.assertEqual(o.notifications[0x33],original)
 def test_mark_effect_fsync_failure_sends_no_notification_ACK(self):
  o,p=self.owner();self.push(p,0x31);o.drain_notifications(p);n=p.ack_notification.call_count
  self.push(p,0x33)
  with patch.object(self.j,'record_many',side_effect=OSError('disk')):
   with self.assertRaises(OSError):o.drain_notifications(p)
  self.assertFalse(o.mark_seen);self.assertEqual(p.ack_notification.call_count,n)
