import csv,json,shutil,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from compare_trace import compare,check_log
from make_demo_reference import generate
class TraceTests(unittest.TestCase):
 def fixture(self,t):
  d=generate(Path(t)/'ref');a=Path(t)/'actual.csv';shutil.copy2(d/'reference.csv',a);return d/'reference.csv',a,json.loads((d/'spec.json').read_text(encoding='utf-8'))
 def change(self,p,index,key,value):
  with p.open(newline='') as f:r=list(csv.DictReader(f))
  r[index][key]=value
  with p.open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=['case','cycle','ready','valid','data','acc']);w.writeheader();w.writerows(r)
 def test_finite_trace_passes(self):
  with tempfile.TemporaryDirectory() as t:
   r,a,s=self.fixture(t);x=compare(r,a,s);self.assertTrue(x['passed']);self.assertEqual(x['compared_cycles'],384)
 def test_hold_value_compared_when_invalid(self):
  with tempfile.TemporaryDirectory() as t:
   r,a,s=self.fixture(t);self.change(a,0,'data','1');self.assertFalse(compare(r,a,s)['passed'])
 def test_short_trace_refused(self):
  with tempfile.TemporaryDirectory() as t:
   r,a,s=self.fixture(t);a.write_text('\n'.join(a.read_text(encoding='utf-8').splitlines()[:-1])+'\n')
   with self.assertRaisesRegex(ValueError,'LENGTH'):compare(r,a,s)
 def test_duplicate_cycle(self):
  with tempfile.TemporaryDirectory() as t:
   r,a,s=self.fixture(t);self.change(a,3,'cycle','2')
   with self.assertRaisesRegex(ValueError,'CYCLE'):compare(r,a,s)
 def test_unknown_logic_value_refused(self):
  with tempfile.TemporaryDirectory() as t:
   r,a,s=self.fixture(t);self.change(a,2,'data','xx')
   with self.assertRaisesRegex(ValueError,'NON_INTEGER'):compare(r,a,s)
 def test_width_violation(self):
  with tempfile.TemporaryDirectory() as t:
   r,a,s=self.fixture(t);self.change(a,2,'data','256')
   with self.assertRaisesRegex(ValueError,'WIDTH'):compare(r,a,s)
 def test_wrong_expected_count(self):
  with tempfile.TemporaryDirectory() as t:
   r,a,s=self.fixture(t);s['expected_rows']=385
   with self.assertRaises(ValueError):compare(r,a,s)
 def test_pass_substring_is_not_exact_marker(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'log';p.write_text('prefix PASS suffix\n')
   with self.assertRaises(ValueError):check_log(p,'PASS','FAIL')
 def test_fail_overrides_pass(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'log';p.write_text('PASS\nFAIL mismatch\n')
   with self.assertRaises(ValueError):check_log(p,'PASS','FAIL')
 def test_case_initial_cycle_required(self):
  with tempfile.TemporaryDirectory() as t:
   r,a,s=self.fixture(t);self.change(a,64,'cycle','1')
   with self.assertRaises(ValueError):compare(r,a,s)
 def test_schema_bool_refused(self):
  with tempfile.TemporaryDirectory() as t:
   r,a,s=self.fixture(t);s['schema']=True
   with self.assertRaises(ValueError):compare(r,a,s)
if __name__=='__main__':unittest.main()
