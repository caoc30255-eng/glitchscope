"""Real durable driver/codec plus modeled buses and bounded execution; no hardware."""
from pathlib import Path
from types import SimpleNamespace as NS
from dataclasses import replace
from unittest.mock import Mock,patch
import sys,json,uuid,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'host'),str(ROOT/'tests')]
import test_fault_mark_candidate as marks
SnapshotBus=marks.SnapshotBus
from test_idle_journal_segments import Bus
from controlled_trial_executor import ControlledTrialExecutor,TrialRequest
from raw_mark_snapshot import RawMarkCapture
from fault_profile import FaultProfile
from ch1_runtime_driver import Binding
from ch1_completion_ledger import _codec
from ch1_control_session import frame,event_payload,decode_event
from ch1_peer_archive_driver import persist_exact
import ch1_evidence_store as store

class ReArmBus(SnapshotBus):
 def write(self,a,v):
  super().write(a,v)
  if a==0:
   self.count=self.offset=self.address=0;self.valid=False
 def trigger(self,shift=0,width=40):
  self.status=12;self.count=4096;self.offset=2048;self.address=2048<<16
  self.words=bytearray([2]*4096)
  for i in range(2048,2050):self.words[i]|=4
  for i in range(2048+shift,2048+shift+width):self.words[i]|=1

class CountBus(Bus):
 def read(self,a):
  if a in (0x18,0x1c):return 0
  return super().read(a)

def session_fixture(t):
 b={n:CountBus(v,9) for n,v in dict(H1=1,CTRL=1,MAIN=0,AUX=0,MAP=0,CH0=8,PROFILE=4,SYS=0).items()};b['AUX'].aux=True
 s=NS(root=t.j.path.parent,journal=t.j,local_epoch=9,current=None,ticket=None,fault=False,config_owner=None,
      mark_capture=t.cap,last_retired_owner=None,handles=[t.j])
 s.upload=NS(current=None,ready=True,credit=1,seq=0)
 s.completion=NS(current=None,verify_journal=Mock())
 s.peer=NS(journal=t.j,fault=False,events=[],txn=10)
 s.control_transport=NS(journal=t.j,fault=False,busy=False,_saved_capture=None)
 s.gate=NS(journal=t.j,grant=None,bus=b['SYS'])
 s.coordinator=NS(journal=t.j,fault=False,parts=NS(journal=t.j))
 s.runtime=NS(bus=b['CTRL']);s.transport=NS(mmio=b['H1']);s.mapping=NS(bus=b['MAP'])
 s.archive=NS(main=b['MAIN'],aux=b['AUX']);s.ch0=NS(bus=b['CH0']);s.profile=NS(bus=b['PROFILE'])
 def available():
  if s.fault:raise RuntimeError('stopped')
 def stop(exc):s.fault=True
 s._available=available;s._stop=stop
 return s,b

def word_for(fields):
 out=0
 for name,width in store.IDENTITY:out=out<<width|fields[name]
 return out

class SuccessorTests(unittest.TestCase):
 setUp=marks.MarkTests.setUp
 def prepare(self):
  self.bus=ReArmBus();self.bus.live=3;self.cap=RawMarkCapture(self.bus,self.j.path.parent/'MARK')
  self.cap.arm(self.binding,self.inner,self.profile);self.bus.trigger()
  receipt=self.cap.archive(self.binding,self.event)
  self.s,self.b=session_fixture(self)
  owner=NS(phase='RETIRED',fault=False,mark_required=True,mark_capture=self.cap,local_retired=True,
           peer_retired=True,retire_sent=True,binding=self.binding,mark_receipt=receipt,
           journal=self.j,_strict_local_recheck=Mock())
  self.s.last_retired_owner=owner;self.s.upload.seq=store._fields(self.identity,store.IDENTITY)['seq']
  self.owner=owner;self.receipt=receipt
  return receipt
 def next_binding(self):
  fields=store._fields(self.identity,store.IDENTITY)
  fields['seq']+=1;fields['generation']+=1;fields['trial_id']+=1
  return Binding(9,self.binding.record_id+1,1,word_for(fields),100,10000),_codec().encode_item(
   fields['run_id'],fields['image_id'],fields['trial_id'],fields['item_index'],64,fields['attempt_id'],0,bytes(range(256)))
 def successor(self):
  self.cap.seal_retired(self.s,self.b);return self.cap.successor(self.s,self.b)
 def test_two_actual_driver_captures_keep_distinct_originals_without_soft_reset(self):
  self.prepare();old=(Path(self.receipt.evidence_dir)/'samples.bin').read_bytes()
  new=self.successor();binding,inner=self.next_binding()
  self.s.mark_capture=new
  new.arm(binding,inner,FaultProfile(20,0,25,10));self.bus.trigger(width=20)
  event=decode_event(frame(0x33,event_payload(binding.identity,0)))
  receipt=new.archive(binding,event)
  self.assertEqual(json.loads((Path(receipt.evidence_dir)/'context.json').read_bytes())['analysis']['inverted_samples'],20)
  self.assertNotEqual(old,(Path(receipt.evidence_dir)/'samples.bin').read_bytes())
  self.assertEqual(old,(Path(self.receipt.evidence_dir)/'samples.bin').read_bytes())
  self.assertTrue(self.cap.verify_archived(self.receipt,self.binding)['historical_archive_integrity_verified'])
  with self.assertRaises(RuntimeError):self.cap.verify_saved(self.receipt,self.binding)
  self.assertEqual([v for a,v in self.bus.writes if a==0],[1,1])
 def test_no_retirement_seal_denies_successor(self):
  self.prepare()
  with self.assertRaises(RuntimeError):self.cap.successor(self.s,self.b)
 def test_not_retired_owner_denied(self):
  self.prepare();self.owner.phase='DONE'
  with self.assertRaises(RuntimeError):self.cap.seal_retired(self.s,self.b)
 def test_pending_peer_event_denied(self):
  self.prepare();self.s.peer.events.append('pending')
  with self.assertRaises(RuntimeError):self.cap.seal_retired(self.s,self.b)
 def test_unconsumed_ready_denied(self):
  self.prepare();self.s.upload.credit=0
  with self.assertRaises(RuntimeError):self.cap.seal_retired(self.s,self.b)
 def test_wrong_bus_mapping_denied(self):
  self.prepare();self.b['SYS']=CountBus(0,9)
  with self.assertRaises(ValueError):self.cap.seal_retired(self.s,self.b)
 def test_old_wave_tamper_denies_successor_no_ARM(self):
  self.prepare();self.cap.seal_retired(self.s,self.b)
  (Path(self.receipt.evidence_dir)/'samples.bin').write_bytes(bytes(4096))
  with self.assertRaises(ValueError):self.cap.successor(self.s,self.b)
  self.assertEqual([v for a,v in self.bus.writes if a==0],[1])
 def test_seal_tamper_denies_ARM(self):
  self.prepare();new=self.successor();binding,inner=self.next_binding()
  (self.cap._retired_seal[0]/'retired.json').write_bytes(b'changed')
  with self.assertRaises(ValueError):new.arm(binding,inner,self.profile)
  self.assertEqual([v for a,v in self.bus.writes if a==0],[1])
 def test_duplicate_successor_denied(self):
  self.prepare();self.successor()
  with self.assertRaises(RuntimeError):self.cap.successor(self.s,self.b)
 def test_same_binding_cannot_reuse_old_capture_identity(self):
  self.prepare();new=self.successor()
  with self.assertRaises(ValueError):new.arm(self.binding,self.inner,self.profile)
 def test_actual_raw_state_changed_denies_next_ARM(self):
  self.prepare();new=self.successor();binding,inner=self.next_binding();self.bus.count=0
  with self.assertRaises(RuntimeError):new.arm(binding,inner,self.profile)
 def test_save_failure_cannot_issue_permission(self):
  self.prepare()
  with patch('raw_mark_snapshot.persist_exact',side_effect=OSError('disk')):
   with self.assertRaises(OSError):self.cap.seal_retired(self.s,self.b)
  with self.assertRaises(RuntimeError):self.cap.successor(self.s,self.b)
 def test_inputs_not_idle_deny_successor(self):
  self.prepare();self.cap.seal_retired(self.s,self.b);self.bus.live=7
  with self.assertRaises(RuntimeError):self.cap.successor(self.s,self.b)

class ExecutorTests(unittest.TestCase):
 setUp=marks.MarkTests.setUp
 def setup_service(self,requests=None):
  self.bus=ReArmBus();self.bus.live=3;self.cap=RawMarkCapture(self.bus,self.j.path.parent/'MARK')
  self.s,self.b=session_fixture(self)
  self.addCleanup(lambda:[h.close() for h in self.s.handles])
  persist_exact(self.s.root/'MARK/preflight',{'preflight.json':store._json({'fresh':True})})
  self.requests=requests or [TrialRequest('baseline',3,-1),TrialRequest('reference-mark',3,-1,self.profile),TrialRequest('candidate-mark',4,-1,self.profile)]
  return ControlledTrialExecutor(self.s,self.b,bytes(range(256))*len(self.requests),self.requests,
                                 max_physical_starts=len(self.requests)+1,exclusive_owner=True)
 def one(self,s,b,kind,inner,rid,*,profile,d,s_value=None,**kwargs):pass
 def modeled_record(self,session,buses,kind,inner,rid,**kw):
  request=(_codec().decode_config(inner) if kind==2 else _codec().decode_item(inner))
  fields=store._fields(self.identity,store.IDENTITY)
  fields.update(seq=rid,generation=rid,run_id=9,image_id=1,trial_id=request.get('trial_id',0),
                item_index=request.get('item_index',0),attempt_id=0,route_mode=0)
  binding=Binding(9,rid,2 if kind==2 else 1,word_for(fields),100,10000)
  owner=NS(phase='RETIRED',fault=False,mark_required=kw['profile'] is not None,mark_capture=session.mark_capture,
           local_retired=True,peer_retired=True,retire_sent=True,binding=binding,journal=session.journal,
           _strict_local_recheck=Mock())
  if kw['profile'] is not None:
   cap=session.mark_capture;cap.arm(binding,inner,kw['profile']);self.bus.trigger()
   owner.mark_receipt=cap.archive(binding,decode_event(frame(0x33,event_payload(binding.identity,0))))
  session.last_retired_owner=owner;session.upload.seq=rid
  if kind==2:session.config_owner=owner
  profile={'d':kw['d'],'s':kw['s'],'profile_seq':rid,'RX_profile_verified':True}
  persist_exact(session.root/'admission'/('epoch_00000009_record_%08x'%rid),{'admission.json':store._json({'profile':profile})})
  marked=kw['profile'] is not None
  return {'record_id':rid,'business_success':not marked,'CH0_classification':{
   'a_source_match':not marked,'a_reception_success':not marked,'b_source_match':not marked or kw['d']==4,
   'b_reception_success':not marked or kw['d']==4},'CH1_classification':{
   'capture_valid':True,'raw_frame_crc_and_format_valid':True,'wire_identity_match':True}}
 def test_bounded_four_records_with_two_marked_snapshots_and_split_labels(self):
  service=self.setup_service()
  with patch('controlled_trial_executor._one',side_effect=self.modeled_record):
   results=[service.run_next() for _ in range(4)]
  self.assertTrue(results[3]['receiver_B_frame_correct']);self.assertFalse(results[3]['STM_business_success'])
  self.assertFalse(results[2]['receiver_B_frame_correct'])
  self.assertEqual([v for a,v in self.bus.writes if a==0],[1,1])
  self.assertEqual(len(list(self.cap.root.glob('epoch_*/saved/samples.bin'))),2)
  with self.assertRaises(RuntimeError):service.run_next()
 def test_max_start_allowance_must_be_explicit_and_exact(self):
  service=self.setup_service()
  with self.assertRaises(ValueError):ControlledTrialExecutor(self.s,self.b,bytes(768),self.requests,max_physical_starts=5,exclusive_owner=True)
 def test_invalid_profile_rejected_before_plan_or_hardware(self):
  with self.assertRaises(ValueError):self.setup_service([TrialRequest('invalid',4,0)])
  self.assertFalse(self.bus.writes)
 def test_duplicate_request_id_rejected(self):
  with self.assertRaises(ValueError):self.setup_service([TrialRequest('same',3,-1),TrialRequest('same',4,-1)])
 def test_unknown_execution_stops_and_cannot_retry(self):
  service=self.setup_service()
  with patch('controlled_trial_executor._one',side_effect=TimeoutError('unknown')) as one:
   with self.assertRaises(TimeoutError):service.run_next()
   with self.assertRaises(RuntimeError):service.run_next()
  self.assertEqual(one.call_count,1)
  diagnostic=json.loads(next(service.root.glob('STOP_*/diagnostic.json')).read_bytes())
  self.assertEqual(diagnostic['execution_effect'],'UNKNOWN');self.assertIsNone(diagnostic['label'])
 def test_modified_plan_denied_before_record_execution(self):
  service=self.setup_service();(service.root/'plan/source.bin').write_bytes(bytes(768))
  with patch('controlled_trial_executor._one') as one:
   with self.assertRaises(ValueError):service.run_next()
  one.assert_not_called()
 def test_changed_in_memory_request_denied_before_execution(self):
  service=self.setup_service();service.requests=(TrialRequest('changed',4,-1),)+service.requests[1:]
  with patch('controlled_trial_executor._one') as one:
   with self.assertRaises(ValueError):service.run_next()
  one.assert_not_called()
 def test_increased_in_memory_budget_denied_before_execution(self):
  service=self.setup_service();service.max_attempts=100
  with patch('controlled_trial_executor._one') as one:
   with self.assertRaises(ValueError):service.run_next()
  one.assert_not_called()
 def test_no_restart_resume_into_same_plan_directory(self):
  service=self.setup_service()
  with self.assertRaises(FileExistsError):ControlledTrialExecutor(self.s,self.b,bytes(range(256))*3,self.requests,max_physical_starts=4,exclusive_owner=True)
 def test_busy_execution_denies_second_call_without_stopping_first(self):
  service=self.setup_service();service._lock.acquire()
  try:
   with self.assertRaises(RuntimeError):service.run_next()
  finally:service._lock.release()
  self.assertFalse(service.stopped)
 def test_cancel_unstarted_remaining_does_not_create_quota(self):
  service=self.setup_service();service.cancel_remaining()
  self.assertFalse(self.bus.writes)
  with self.assertRaises(RuntimeError):service.run_next()
 def test_invalid_report_blocks_next_trial_after_retired_record(self):
  service=self.setup_service()
  def one(*a,**kw):
   result=self.modeled_record(*a,**kw);result['CH1_classification']['capture_valid']=False;return result
  with patch('controlled_trial_executor._one',side_effect=one):result=service.run_next()
  self.assertEqual(result['evidence_quality'],'INVALID_REPORT');self.assertFalse(result['next_trial_allowed_by_plan'])
  with self.assertRaises(RuntimeError):service.run_next()
 def test_result_save_failure_stops_without_executing_again(self):
  service=self.setup_service();original=persist_exact
  def save(path,*args,**kw):
   if path.name=='result':raise OSError('disk full')
   return original(path,*args,**kw)
  with patch('controlled_trial_executor._one',side_effect=self.modeled_record),patch('controlled_trial_executor.persist_exact',side_effect=save):
   with self.assertRaises(OSError):service.run_next()
  self.assertTrue(service.stopped)
  diagnostic=json.loads(next(service.root.glob('STOP_*/diagnostic.json')).read_bytes())
  self.assertFalse(diagnostic['automatic_retry_allowed'])

if __name__=='__main__':unittest.main()
