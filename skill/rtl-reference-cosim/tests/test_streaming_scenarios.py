import csv,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from make_demo_reference import generate
from compare_trace import compare
class ScenarioTests(unittest.TestCase):
 def trace(self,t):
  p=generate(Path(t)/'ref')
  with (p/'reference.csv').open(encoding='utf-8',newline='') as f:rows=list(csv.DictReader(f))
  return p,rows
 def test_hashing_does_not_read_whole_file(self):
  with tempfile.TemporaryDirectory() as t:
   p,rows=self.trace(t);spec=json.loads((p/'spec.json').read_text(encoding='utf-8'))
   with patch.object(Path,'read_bytes',side_effect=AssertionError('whole-file read forbidden')):self.assertTrue(compare(p/'reference.csv',p/'reference.csv',spec)['passed'])
 def test_continuous_valid_and_overflow(self):
  with tempfile.TemporaryDirectory() as t:
   _,rows=self.trace(t);r=[x for x in rows if x['case']=='1'];self.assertEqual([x['data'] for x in r[2:5]],['250','244','238']);self.assertTrue(all(x['valid']=='1' for x in r[2:]))
 def test_midstream_reset(self):
  with tempfile.TemporaryDirectory() as t:
   _,rows=self.trace(t);r=[x for x in rows if x['case']=='2'];self.assertEqual(r[32]['data'],'0');self.assertEqual(r[32]['valid'],'0')
 def test_backpressure_holds_data_and_state(self):
  with tempfile.TemporaryDirectory() as t:
   _,rows=self.trace(t);r=[x for x in rows if x['case']=='4'];self.assertEqual(len({(x['data'],x['acc']) for x in r[9:30]}),1)
 def test_reset_during_stall(self):
  with tempfile.TemporaryDirectory() as t:
   _,rows=self.trace(t);r=[x for x in rows if x['case']=='5'];self.assertEqual(r[20]['data'],'0');self.assertEqual(r[20]['valid'],'0');self.assertEqual(r[20]['ready'],'1')
if __name__=='__main__':unittest.main()
