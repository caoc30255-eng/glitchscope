"""Explicit STOP policy; copied real archives and modeled hardware, no board IO."""
import sys,json
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
import unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'host'),str(ROOT/'tests')]
import test_local_rule_loop as fixtures
from early_stop_trial_loop import EarlyStopTrialLoop,stop_after_control,POLICY_ID,STOP_REASON
from local_rule_trial_loop import local_b_rule
from controlled_trial_executor import ControlledTrialExecutor
from ch1_peer_archive_driver import persist_exact

class EarlyStopTests(unittest.TestCase):
 setUp=fixtures.LocalLoopTests.setUp
 def setup_cap(self):
  self.raw_reads=[]
  def read(a):
   self.raw_reads.append(a)
   return 3 if a==0x20 else 0
  self.s.mark_capture=NS(used=False,read=read)
 def loop(self):self.setup_cap();return EarlyStopTrialLoop(self.ex)
 def test_two_completed_two_cancelled_zero_marked_and_no_more_calls(self):
  loop=self.loop();result=loop.run()
  self.assertEqual(self.actual_calls,2);self.assertTrue(loop.done);self.assertFalse(loop.stopped)
  self.assertTrue(self.ex.stopped);self.assertEqual(result['unstarted_records_cancelled'],2)
  self.assertEqual(result['stop_reason'],STOP_REASON);self.assertEqual(result['decisions_saved'],3)
  self.assertEqual(result['marked_ITEMs_executed'],0)
  self.assertFalse(result['reference_B_already_correct_branch_tested'])
  for method in (loop.run,loop.step):
   with self.assertRaises(RuntimeError):method()
  with self.assertRaises(RuntimeError):ControlledTrialExecutor.run_next(self.ex)
  self.assertEqual(self.actual_calls,2)
  self.assertEqual(self.ex.attempts,2)
  self.assertEqual(set(self.raw_reads),{8,12,16,0x20})
 def test_frozen_stop_policy_has_its_own_source_fingerprint(self):
  loop=self.loop();doc=json.loads((loop.root/'EARLY_STOP_POLICY/policy.json').read_bytes())
  self.assertEqual(doc['policy_id'],POLICY_ID)
  self.assertEqual(doc['policy_module_sha256'],loop._stop_sha)
  self.assertNotEqual(doc['policy_module_sha256'],doc['base_loop_module_sha256'])
 def test_policy_does_not_fabricate_reference_success(self):
  plan=json.loads(self.ex._frozen_plan);plan['plan_sha256']='a'*64
  h=[{'identity_hex':'b'*64,'result_sha256':'c'*64,'labels':{'A_correct':True,'B_correct':True,'STM_success':True}}]*2
  before=json.dumps(h,sort_keys=True);proposal=stop_after_control(plan,h)
  self.assertEqual(proposal['action'],'STOP');self.assertEqual(proposal['after_record_id'],2)
  self.assertEqual(before,json.dumps(h,sort_keys=True))
  self.assertNotEqual(proposal['reason'],'REFERENCE_ALREADY_CORRECT_STOP')
 def test_changed_stop_metadata_denies_first_record(self):
  loop=self.loop();(loop.root/'EARLY_STOP_POLICY/policy.json').write_bytes(b'changed')
  with self.assertRaises(RuntimeError):loop.step()
  self.assertEqual(self.actual_calls,0)
 def test_changed_policy_function_denies_execution(self):
  loop=self.loop();loop.policy=local_b_rule
  with self.assertRaises(RuntimeError):loop.step()
  self.assertEqual(self.actual_calls,0)
 def test_unexpected_raw_ARM_denies_success_certificate(self):
  loop=self.loop();loop.step();loop.step();self.s.mark_capture.used=True
  with self.assertRaises(RuntimeError):loop.step()
  self.assertEqual(self.actual_calls,2);self.assertTrue(loop.stopped)
  self.assertFalse(loop.done);self.assertIsNone(loop.stop_test_summary)
 def test_raw_done_or_stale_capture_denies_success(self):
  loop=self.loop();loop.step();loop.step();self.s.mark_capture.read=lambda a:12 if a==8 else (3 if a==0x20 else 0)
  with self.assertRaises(RuntimeError):loop.step()
  self.assertEqual(self.actual_calls,2);self.assertFalse(loop.done)
 def test_certificate_save_failure_keeps_loop_failed_after_cancel(self):
  loop=self.loop();original=persist_exact
  def save(path,*args,**kwargs):
   if path.name=='EARLY_STOP_RESULT':raise OSError('disk full')
   return original(path,*args,**kwargs)
  with patch('early_stop_trial_loop.persist_exact',side_effect=save):
   with self.assertRaises(OSError):loop.run()
  self.assertEqual(self.actual_calls,2);self.assertTrue(loop.stopped);self.assertFalse(loop.done)
  self.assertTrue(self.ex.stopped)
  with self.assertRaises(RuntimeError):loop.run()
 def test_cancellation_failure_cannot_resume_or_refund(self):
  loop=self.loop()
  with patch.object(self.ex,'cancel_remaining',side_effect=OSError('cancel persistence')):
   with self.assertRaises(OSError):loop.run()
  self.assertEqual(self.actual_calls,2);self.assertTrue(loop.stopped)
  self.assertFalse((loop.root/'EARLY_STOP_RESULT/committed.json').exists())

if __name__=='__main__':unittest.main()
