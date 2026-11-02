"""Idle segment boundaries with real durable journals and modeled read-only buses."""
from pathlib import Path
from types import SimpleNamespace as NS
import sys,uuid,json,hashlib,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'host'))
import ps_idle_journal_segments as segments
from ch1_control_session import ApplicationJournal,audit_application_journal
from ch1_admission_parts import _has_exact_rx
class Bus:
 def __init__(self,status=0,epoch=1):self.status=status;self.epoch=epoch;self.writes=[];self.errors=0;self.orphans=0
 def read(self,a):
  if a==4:return self.status
  if a==8:return self.errors if getattr(self,'aux',False) else self.epoch
  if a==12:return self.orphans
  raise AssertionError('Unreviewed offset')
 def write(self,*args):self.writes.append(args);raise AssertionError('No hardware write allowed')
class SegmentTests(unittest.TestCase):
 def setUp(self):
  self.root=ROOT/'evidence/offline_segment_tests'/uuid.uuid4().hex
  j=ApplicationJournal(self.root,1)
  b={n:Bus(v) for n,v in dict(H1=1,CTRL=0x11,MAIN=0,AUX=0,MAP=0,CH0=8,PROFILE=4,SYS=0).items()};b['AUX'].aux=True
  self.b=b
  s=NS(root=self.root,journal=j,local_epoch=1,current=None,ticket=None,handles=[j],fault=False)
  s.upload=NS(current=None,ready=True,credit=1,seq=4);s.completion=NS(current=None)
  s.peer=NS(journal=j,fault=False,events=[],txn=100)
  s.control_transport=NS(journal=j,fault=False,busy=False,_saved_capture=('old',))
  s.gate=NS(journal=j,grant=None,bus=b['SYS'])
  s.coordinator=NS(journal=j,fault=False,parts=NS(journal=j))
  s.runtime=NS(bus=b['CTRL']);s.transport=NS(mmio=b['H1']);s.mapping=NS(bus=b['MAP'])
  s.archive=NS(main=b['MAIN'],aux=b['AUX']);s.ch0=NS(bus=b['CH0'])
  s.config_owner=NS(journal=j)
  def available():
   if s.fault:raise RuntimeError('stopped')
  def stop(exc):
   s.fault=True
   try:s.journal.record('PS_stop',error=str(exc))
   except Exception:pass
  s._available=available;s._stop=stop;self.s=s;self.old=j
  self.addCleanup(lambda:[h.close() for h in s.handles])
 def rotate(self,n=5):return segments.rotate_idle_journal(self.s,buses=self.b,next_record_id=n)
 def test_switches_all_live_consumers_but_not_retired_owner(self):
  out=self.rotate();s=self.s
  self.assertIs(s.config_owner.journal,self.old);self.assertTrue(self.old.file.closed)
  for consumer in segments._consumers(s):self.assertIs(consumer.journal,s.journal)
  self.assertIsNone(s.control_transport._saved_capture);self.assertEqual(out['hardware_writes'],0)
  self.assertEqual(s.peer.txn,100);self.assertEqual(s.upload.seq,4)
  self.assertFalse(any(b.writes for b in self.b.values()))
 def test_hash_link_and_each_chain_are_valid(self):
  out=self.rotate();p=self.s._sealed_application_segments[0][1]
  self.assertEqual(p['previous_sha256'],hashlib.sha256(self.old.path.read_bytes()).hexdigest())
  self.assertEqual(audit_application_journal(self.old.path)['last_event'],'application_segment_sealed')
  self.assertEqual(audit_application_journal(self.s.journal.path)['last_event'],'application_segment_activated')
  self.assertEqual(segments.verify_sealed_segments(self.s),1)
 def test_old_config_ack_remains_verifiable(self):
  raw='a55a0179203000000f000000012000000f00000000011000000f0100000000000000000001b129'
  self.old.record('control_rx_stream',raw_hex=raw);self.rotate()
  self.assertTrue(_has_exact_rx(self.s.config_owner.journal,raw))
 def test_active_flight_rejected(self):
  self.s.current=object()
  with self.assertRaises(RuntimeError):self.rotate()
  self.assertIs(self.s.journal,self.old);self.assertFalse(self.old.file.closed)
 def test_unconsumed_READY_rejected(self):
  self.s.upload.credit=0
  with self.assertRaises(RuntimeError):self.rotate()
 def test_busy_transport_rejected(self):
  self.s.control_transport.busy=True
  with self.assertRaises(RuntimeError):self.rotate()
 def test_actual_pending_AUX_rejected(self):
  self.b['AUX'].orphans=1
  with self.assertRaises(RuntimeError):self.rotate()
 def test_live_consumer_mismatch_rejected(self):
  self.s.peer.journal=object()
  with self.assertRaises(ValueError):self.rotate()
 def test_wrong_bus_object_rejected(self):
  self.b['CTRL']=Bus(0x11)
  with self.assertRaises(ValueError):self.rotate()
 def test_duplicate_boundary_rejected(self):
  self.rotate()
  with self.assertRaises(RuntimeError):self.rotate()
  self.assertEqual(len(self.s._sealed_application_segments),1)
 def test_old_middle_tampering_detected(self):
  self.rotate();data=self.old.path.read_bytes();self.old.path.write_bytes(data.replace(b'begin',b'begix',1))
  with self.assertRaises(ValueError):segments.verify_sealed_segments(self.s)
  self.assertTrue(self.s.fault)
 def test_active_middle_tampering_detected(self):
  self.rotate();p=self.s.journal.path;p.write_bytes(p.read_bytes().replace(b'begin',b'begix',1))
  with self.assertRaises(ValueError):segments.verify_sealed_segments(self.s)
  self.assertTrue(self.s.fault)
 def test_seal_link_disk_failure_stops_before_switch(self):
  original=ApplicationJournal.record
  def record(j,event,**fields):
   if event=='application_segment_link':raise OSError('disk full')
   return original(j,event,**fields)
  with patch.object(ApplicationJournal,'record',record):
   with self.assertRaises(OSError):self.rotate()
  self.assertTrue(self.s.fault);self.assertIs(self.s.journal,self.old)
 def test_multiple_completed_boundaries_preserve_all_files(self):
  self.rotate();self.s.upload.seq=5;self.s.peer.txn=200;self.rotate(6)
  self.assertEqual(segments.verify_sealed_segments(self.s),2)
  self.assertTrue(self.old.path.exists())
 def test_hardware_change_during_seal_denies_switch(self):
  original=ApplicationJournal.record
  def record(j,event,**fields):
   value=original(j,event,**fields)
   if event=='application_segment_link':self.b['CTRL'].status=3
   return value
  with patch.object(ApplicationJournal,'record',record):
   with self.assertRaises(RuntimeError):self.rotate()
  self.assertTrue(self.s.fault);self.assertIs(self.s.journal,self.old)
 def test_sealed_state_mutation_detected(self):
  self.rotate();self.old.index+=1
  with self.assertRaises(ValueError):segments.verify_sealed_segments(self.s)
 def test_frozen_journal_cannot_be_appended(self):
  self.rotate();before=self.old.path.read_bytes()
  with self.assertRaises(ValueError):self.old.record('late_write')
  self.assertEqual(before,self.old.path.read_bytes())
