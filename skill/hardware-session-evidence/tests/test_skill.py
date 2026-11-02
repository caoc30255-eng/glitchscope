import copy,hashlib,json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
import session_ledger as s
class LedgerTests(unittest.TestCase):
 def make(self,t):
  root=Path(t)/'session';plan=json.loads((ROOT/'examples/plan.json').read_text(encoding='utf-8'));s.create(root,plan);return root
 def evidence(self,root,name='one.bin'):
  p=root/'raw'/name;p.write_bytes(b'SYNTHETIC_NOT_A_HARDWARE_RECEIPT');return {'raw/'+name:hashlib.sha256(p.read_bytes()).hexdigest()}
 def test_charge_before_completion(self):
  with tempfile.TemporaryDirectory() as t:
   r=self.make(t);a=s.begin(r,'setup',{'x':1});self.assertEqual(a['occupied'],1);self.assertEqual(a['unknown_or_unresolved'],1);self.assertFalse(a['hardware_authenticity_verified'])
 def test_record_then_hash_audit(self):
  with tempfile.TemporaryDirectory() as t:
   r=self.make(t);s.begin(r,'setup',{});a=s.complete(r,'setup',self.evidence(r));self.assertEqual(a['recorded_completions'],1)
 def test_timeout_is_not_refunded(self):
  with tempfile.TemporaryDirectory() as t:
   r=self.make(t);s.begin(r,'setup',{});s.unknown(r,'setup','timeout');a=s.cleanup(r,True,True)
   self.assertEqual(a['occupied'],1);self.assertEqual(a['cancelled_unstarted'],2)
   with self.assertRaises(ValueError):s.begin(r,'reference',{})
 def test_reservation_held_without_cleanup(self):
  with tempfile.TemporaryDirectory() as t:
   r=self.make(t);s.stop(r);self.assertEqual(s.audit(r)['reserved_unstarted'],3)
 def test_incomplete_cleanup_rejected(self):
  with tempfile.TemporaryDirectory() as t:
   r=self.make(t);s.stop(r)
   with self.assertRaises(ValueError):s.cleanup(r,False,True)
 def test_out_of_order_id_rejected_before_append(self):
  with tempfile.TemporaryDirectory() as t:
   r=self.make(t);before=(r/'journal.jsonl').read_bytes()
   with self.assertRaises(ValueError):s.begin(r,'measurement',{})
   self.assertEqual(before,(r/'journal.jsonl').read_bytes())
 def test_crashed_pending_cannot_start_next(self):
  with tempfile.TemporaryDirectory() as t:
   r=self.make(t);s.begin(r,'setup',{})
   with self.assertRaises(ValueError):s.begin(r,'reference',{})
 def test_file_tampering_blocks_audit(self):
  with tempfile.TemporaryDirectory() as t:
   r=self.make(t);s.begin(r,'setup',{});s.complete(r,'setup',self.evidence(r));(r/'raw/one.bin').write_bytes(b'changed')
   with self.assertRaises(ValueError):s.audit(r)
 def test_truncated_journal_refused(self):
  with tempfile.TemporaryDirectory() as t:
   r=self.make(t);p=r/'journal.jsonl';p.write_bytes(p.read_bytes().rstrip(b'\n'))
   with self.assertRaises(ValueError):s.audit(r)
 def test_external_evidence_path_refused(self):
  with tempfile.TemporaryDirectory() as t:
   r=self.make(t);s.begin(r,'setup',{})
   with self.assertRaises(ValueError):s.complete(r,'setup',{'../x':'0'*64})
 def test_budget_end_no_fourth_record(self):
  with tempfile.TemporaryDirectory() as t:
   r=self.make(t)
   for i,n in enumerate(['setup','reference','measurement']):s.begin(r,n,{});s.complete(r,n,self.evidence(r,str(i)))
   self.assertEqual(s.audit(r)['state'],'STOPPED_BUDGET')
   with self.assertRaises(ValueError):s.begin(r,'extra',{})
 def test_existing_session_not_overwritten(self):
  with tempfile.TemporaryDirectory() as t:
   r=self.make(t)
   with self.assertRaises(FileExistsError):s.create(r,json.loads((ROOT/'examples/plan.json').read_text(encoding='utf-8')))
 def test_existing_writer_lock_not_removed(self):
  with tempfile.TemporaryDirectory() as t:
   r=self.make(t);p=r/'writer.lock';p.write_text('other process')
   with self.assertRaises(FileExistsError):s.begin(r,'setup',{})
   self.assertTrue(p.exists())
if __name__=='__main__':unittest.main()
