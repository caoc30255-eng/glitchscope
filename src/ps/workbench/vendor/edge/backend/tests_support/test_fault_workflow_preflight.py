"""Pilot staging/file checks; all hardware calls are models."""
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock,patch
import unittest,sys,uuid,json
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'host'),str(ROOT/'tests')]
import fault_pilot_workflow as workflow
from fault_profile import FaultProfile
from raw_mark_snapshot import RawMarkCapture
from ch1_control_session import ApplicationJournal
from test_fault_mark_candidate import SnapshotBus
class WorkflowTests(unittest.TestCase):
 def setUp(self):
  self.root=ROOT/'evidence/offline_fault_workflow'/uuid.uuid4().hex/'session'
  self.j=ApplicationJournal(self.root,9);self.addCleanup(self.j.close)
  self.bus=SnapshotBus();self.bus.live=3
  self.capture=RawMarkCapture(self.bus,self.root/'MARK')
  self.session=NS(root=self.root,journal=self.j,current=None,config_owner=None,
                  mark_capture=self.capture,local_epoch=9,_stop=Mock())
  self.session.configure_fault_capture=Mock(return_value={'hardware_writes':0})
  self.profile=FaultProfile(20,0,15,20)
 def inspect(self):return workflow.inspect_raw_mark_interface(self.session,Mock(),Path('reviewed.hwh'))
 def test_preflight_reads_and_saves_without_ARM(self):
  result=self.inspect();self.assertEqual(result['actual_raw_registers']['live_sample'],3)
  self.assertFalse(self.bus.writes);self.assertTrue((self.root/'MARK/preflight/committed.json').is_file())
 def test_old_snapshot_preflight_denies_no_ARM(self):
  self.bus.trigger()
  with self.assertRaises(RuntimeError):self.inspect()
  self.assertFalse(self.bus.writes)
 def test_nonidle_physical_inputs_deny_no_ARM(self):
  self.bus.live=7
  with self.assertRaises(RuntimeError):self.inspect()
  self.assertFalse(self.bus.writes)
 def test_pair_without_saved_preflight_does_not_start(self):
  with patch.object(workflow,'_one') as one:
   with self.assertRaises(RuntimeError):workflow.run_single_item_pair(self.session,{},bytes(range(256))*2,profile=self.profile)
  one.assert_not_called();self.assertFalse(hasattr(self.session,'_fault_pilot_started'))
 def test_changed_preflight_denies_pair(self):
  self.inspect();(self.root/'MARK/preflight/preflight.json').write_bytes(b'changed')
  with patch.object(workflow,'_one') as one:
   with self.assertRaises(ValueError):workflow.run_single_item_pair(self.session,{},bytes(range(256))*2,profile=self.profile)
  one.assert_not_called()
 def test_source_mismatch_does_not_start(self):
  with patch.object(workflow,'_one') as one:
   with self.assertRaises(ValueError):workflow.run_single_item_pair(self.session,{},bytes(512),profile=self.profile)
  one.assert_not_called()
 def test_pair_sequences_one_baseline_one_explicit_fault_without_image_success(self):
  self.inspect();counter=[0];calls=[]
  class Sys:
   def read(_,a):assert a in (0x18,0x1c);return counter[0]
  def one(session,buses,kind,inner,record_id,**kw):
   calls.append((kind,record_id,kw['profile']));counter[0]+=1
   return {'business_success':kw['profile'] is None,'record_id':record_id}
  with patch.object(workflow,'_one',side_effect=one),patch.object(workflow,'rotate_idle_journal'),patch.object(workflow,'verify_sealed_segments'):
   result=workflow.run_single_item_pair(self.session,{'SYS':Sys()},bytes(range(256))*2,profile=self.profile)
  self.assertEqual([r[1] for r in calls],[1,2,3])
  self.assertEqual([r[2] for r in calls],[None,None,self.profile])
  self.assertFalse(result['marked_business_success']);self.assertTrue(result['all_three_records_retired'])
  with self.assertRaises(RuntimeError):workflow.run_single_item_pair(self.session,{},bytes(range(256))*2,profile=self.profile)
