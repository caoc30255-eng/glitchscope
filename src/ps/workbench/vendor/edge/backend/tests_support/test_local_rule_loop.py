"""Modeled executor plus copied real payload archives. Never accesses hardware.
Fixture paths are rebased in copied result files; source session is not changed.
"""
from pathlib import Path
from types import SimpleNamespace as NS,MethodType
from unittest.mock import patch
import sys,json,shutil,uuid,unittest,threading
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'host'),str(ROOT/'tests')]
from local_rule_trial_loop import LocalRuleTrialLoop,local_b_rule
from controlled_trial_executor import ControlledTrialExecutor,TrialRequest
from fault_profile import FaultProfile
from ch1_control_session import ApplicationJournal
from ch1_runtime_driver import Binding
from test_controlled_executor import session_fixture
import ch1_evidence_store as store

WORK=ROOT.parents[2]
ORIGINAL=WORK/'session_0000001c'

class LocalLoopTests(unittest.TestCase):
 def setUp(self):
  self.root=ROOT/'evidence/offline_local_loop'/uuid.uuid4().hex
  self.archive=self.root/'session';shutil.copytree(ORIGINAL,self.archive)
  self.j=ApplicationJournal(self.archive/'modeled_current_journal',0x1000001c);self.addCleanup(self.j.close)
  self.cap=None;self.s,self.b=session_fixture(self);self.s.root=self.archive;self.s.local_epoch=0x1000001c
  for bus in self.b.values():bus.epoch=self.s.local_epoch
  self.ex=object.__new__(ControlledTrialExecutor)
  self.ex.session=self.s;self.ex.buses=self.b;self.ex.root=self.archive/'EXECUTOR'
  self.ex.index=self.ex.attempts=0;self.ex.results=[];self.ex.stopped=False;self.ex._lock=threading.Lock()
  self.ex._frozen_plan=(self.ex.root/'plan/plan.json').read_bytes()
  self.ex._frozen_source=(self.ex.root/'plan/source.bin').read_bytes()
  self.ex._frozen_config=(self.ex.root/'plan/config.bin').read_bytes()
  self.ex.parts=tuple(self.ex._frozen_source[i:i+256] for i in range(0,768,256));self.ex.max_attempts=4
  self.ex.requests=(TrialRequest('baseline',3,-1),TrialRequest('reference_mark',3,-1,FaultProfile(20,0,15,20)),TrialRequest('candidate_mark',4,-1,FaultProfile(20,0,15,20)))
  original_read=self.b['SYS'].read
  self.b['SYS'].read=lambda a:self.ex.index if a in (0x18,0x1c) else original_read(a)
  self.actual_calls=0
  for rid in range(1,5):
   path=self.ex.root/('record_%08x/result'%rid);result=json.loads((path/'result.json').read_bytes())
   suffix='epoch_1000001c_record_%08x'%rid
   result['CH0_evidence_dir']=str(self.archive/'CH0'/suffix)
   result['CH1_evidence_dir']=str(self.archive/'CH1/main'/suffix)
   (path/'result.json').write_bytes(store._json(result))
   (path/'committed.json').write_bytes(store._json({'files':{'result.json':store.sha(store._json(result))}}))
  def run_next(ex):
   self.actual_calls+=1
   if ex.stopped or ex.index>=4:raise RuntimeError('stopped/exhausted')
   rid=ex.index+1
   result=json.loads((ex.root/('record_%08x/result/result.json'%rid)).read_bytes())
   descriptor=store.descriptor_decode((self.archive/'CH1/main'/('epoch_1000001c_record_%08x'%rid)/'descriptor.bin').read_bytes())
   self.s.last_retired_owner=NS(binding=Binding(**{k:descriptor[k] for k in ('epoch','record_id','kind','identity','start','deadline')}),
                                 phase='RETIRED',started=True,done=True)
   ex.index+=1;ex.attempts+=1;ex.results.append(result);return result
  self.ex.run_next=MethodType(run_next,self.ex)
 def loop(self,policy=local_b_rule):return LocalRuleTrialLoop(self.ex,policy=policy)
 def test_real_archives_feedback_drives_reference_failure_to_candidate_success(self):
  loop=self.loop();summary=loop.run()
  self.assertEqual(self.actual_calls,4);self.assertEqual(summary['decisions_saved'],5)
  self.assertFalse(summary['history'][2]['labels']['B_correct'])
  self.assertTrue(summary['history'][3]['labels']['B_correct'])
  self.assertFalse(summary['history'][3]['labels']['STM_success'])
  self.assertFalse(summary['teammate_algorithm_called']);self.assertTrue(loop.done)
  decisions=[json.loads(p.read_bytes()) for p in sorted(loop.root.glob('decision_*/proposal.json'))]
  self.assertEqual(decisions[3]['reason'],'REFERENCE_B_FALSE_TRY_PREDECLARED_CANDIDATE')
  self.assertEqual(decisions[4]['action'],'STOP')
  with self.assertRaises(RuntimeError):loop.run()
  self.assertEqual(self.actual_calls,4)
 def test_rule_stops_when_reference_B_already_correct(self):
  plan=json.loads(self.ex._frozen_plan);plan['plan_sha256']='a'*64
  history=[{'identity_hex':'b'*64,'result_sha256':'c'*64,'labels':{'A_correct':False,'B_correct':True,'STM_success':False}}]*3
  proposal=local_b_rule(plan,history)
  self.assertEqual(proposal['action'],'STOP');self.assertIsNone(proposal['next_request'])
 def test_early_stop_cancels_only_unstarted_records(self):
  def policy(plan,history):
   p=local_b_rule(plan,history)
   if len(history)==2:p.update(action='STOP',next_request=None,reason='EXPLICIT_STOP')
   return p
  loop=self.loop(policy);summary=loop.run()
  self.assertEqual(self.actual_calls,2);self.assertEqual(summary['completed_records'],2)
  self.assertTrue((self.ex.root/'cancelled/committed.json').is_file())
 def test_extra_parameter_not_next_frozen_slot_rejected_before_any_record(self):
  def policy(plan,history):
   p=local_b_rule(plan,history);p['next_request']['receiver_B']['d']=2;return p
  loop=self.loop(policy)
  with self.assertRaises(RuntimeError):loop.step()
  self.assertEqual(self.actual_calls,0);self.assertTrue(self.ex.stopped)
 def test_numeric_type_change_cannot_match_frozen_integer_parameter(self):
  def policy(plan,history):
   p=local_b_rule(plan,history);p['next_request']['receiver_B']['d']=3.0;return p
  loop=self.loop(policy)
  with self.assertRaises(RuntimeError):loop.step()
  self.assertEqual(self.actual_calls,0)
 def test_old_feedback_binding_proposal_rejected(self):
  def policy(plan,history):
   p=local_b_rule(plan,history)
   if history:p['after_result_sha256']='0'*64
   return p
  loop=self.loop(policy);loop.step()
  with self.assertRaises(RuntimeError):loop.step()
  self.assertEqual(self.actual_calls,1)
 def test_decision_save_failure_cannot_execute_record(self):
  loop=self.loop()
  with patch('local_rule_trial_loop.persist_exact',side_effect=OSError('disk')):
   with self.assertRaises(OSError):loop.step()
  self.assertEqual(self.actual_calls,0);self.assertTrue(self.ex.stopped)
 def test_changed_saved_feedback_stops_before_next_record(self):
  loop=self.loop();loop.step()
  path=self.ex.root/'record_00000001/result/result.json';path.write_bytes(b'changed')
  with self.assertRaises(RuntimeError):loop.step()
  self.assertEqual(self.actual_calls,1)
 def test_B_label_cannot_be_faked_even_with_rehashed_result(self):
  loop=self.loop()
  for _ in range(3):loop.step()
  path=self.ex.root/'record_00000003/result'
  result=json.loads((path/'result.json').read_bytes());result['receiver_B_frame_correct']=True
  (path/'result.json').write_bytes(store._json(result));(path/'committed.json').write_bytes(store._json({'files':{'result.json':store.sha(store._json(result))}}))
  self.ex.results[2]=result
  with self.assertRaises(RuntimeError):loop.step()
  self.assertEqual(self.actual_calls,3)
 def test_actual_B_raw_tamper_denies_next_decision(self):
  loop=self.loop()
  for _ in range(3):loop.step()
  (self.archive/'CH0/epoch_1000001c_record_00000003/b_raw.bin').write_bytes(bytes(278))
  with self.assertRaises(RuntimeError):loop.step()
  self.assertEqual(self.actual_calls,3)
 def test_rehashed_wrong_admission_identity_denies_next_record(self):
  loop=self.loop();loop.step()
  directory=self.archive/'admission/epoch_1000001c_record_00000001'
  admission=json.loads((directory/'admission.json').read_bytes());admission['context']['identity']+=1
  (directory/'admission.json').write_bytes(store._json(admission))
  manifest=json.loads((directory/'committed.json').read_bytes());manifest['files']['admission.json']=store.sha(store._json(admission))
  (directory/'committed.json').write_bytes(store._json(manifest))
  with self.assertRaises(RuntimeError):loop.step()
  self.assertEqual(self.actual_calls,1)
 def test_rehashed_wrong_retirement_seal_denies_candidate(self):
  loop=self.loop()
  for _ in range(3):loop.step()
  directory=self.archive/'MARK/epoch_1000001c_record_00000003/retired_for_next'
  seal=json.loads((directory/'retired.json').read_bytes());seal['proof']['identity']+=1
  (directory/'retired.json').write_bytes(store._json(seal))
  (directory/'committed.json').write_bytes(store._json({'files':{'retired.json':store.sha(store._json(seal))}}))
  with self.assertRaises(RuntimeError):loop.step()
  self.assertEqual(self.actual_calls,3)
 def test_unknown_execution_stops_no_retry(self):
  def uncertain(ex):
   self.actual_calls+=1;ex.attempts+=1;ex.stopped=True;raise TimeoutError('uncertain START')
  self.ex.run_next=MethodType(uncertain,self.ex);loop=self.loop()
  with self.assertRaises(TimeoutError):loop.step()
  with self.assertRaises(RuntimeError):loop.step()
  self.assertEqual(self.actual_calls,1)
  d=json.loads(next(loop.root.glob('STOP_*/diagnostic.json')).read_bytes())
  self.assertEqual(d['effect'],'UNKNOWN');self.assertIsNone(d['label'])
 def test_external_executor_call_is_detected(self):
  loop=self.loop();self.ex.run_next()
  with self.assertRaises(RuntimeError):loop.step()
  self.assertEqual(self.actual_calls,1)
 def test_changed_plan_after_loop_creation_denied(self):
  loop=self.loop();loop.plan['requests'][2]['receiver_B']['d']=2
  with self.assertRaises(RuntimeError):loop.step()
  self.assertEqual(self.actual_calls,0)
 def test_policy_replacement_denied(self):
  loop=self.loop();loop.policy=lambda p,h:None
  with self.assertRaises(RuntimeError):loop.step()
  self.assertEqual(self.actual_calls,0)
 def test_loop_directory_cannot_resume(self):
  loop=self.loop();del self.ex._rule_loop_owner
  with self.assertRaises(FileExistsError):self.loop()
 def test_concurrent_step_denied_without_extra_record(self):
  loop=self.loop();loop._lock.acquire()
  try:
   with self.assertRaises(RuntimeError):loop.step()
  finally:loop._lock.release()
  self.assertEqual(self.actual_calls,0);self.assertFalse(loop.stopped)
 def test_rule_decision_owns_no_training_or_billing_authority(self):
  loop=self.loop();summary=loop.run()
  self.assertFalse(summary['AI_training_run']);self.assertFalse(summary['production_billing_finalized'])

if __name__=='__main__':unittest.main()
