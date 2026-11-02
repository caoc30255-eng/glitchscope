import copy,hashlib,json,runpy,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from inference_bench import load_runner,bench
from golden_check import compare
class LoadingTests(unittest.TestCase):
 def test_model_file_changes_real_predictions(self):
  with tempfile.TemporaryDirectory() as t:
   file=Path(t)/'model.txt';file.write_bytes((ROOT/'examples/weights.txt').read_bytes().replace(b'threshold_width=8',b'threshold_width=12'))
   changed,r=load_runner(ROOT/'examples/demo_runner.py',file);normal,_=load_runner(ROOT/'examples/demo_runner.py')
   self.assertNotEqual(changed({'width':9,'gap':0})['score'],normal({'width':9,'gap':0})['score']);self.assertEqual(r['model_sha256'],hashlib.sha256(file.read_bytes()).hexdigest());self.assertTrue(r['model_load_hook_verified'])
 def test_declaring_artifact_without_loader_rejected(self):
  with tempfile.TemporaryDirectory() as t:
   f=Path(t)/'runner.py';f.write_text('def predict(q):return q\n');model=Path(t)/'x';model.write_text('x')
   with self.assertRaisesRegex(ValueError,'LOAD_HOOK'):load_runner(f,model)
 def test_loaded_predict_does_not_read_model_each_call(self):
  predict,_=load_runner(ROOT/'examples/demo_runner.py')
  with patch.object(Path,'read_bytes',side_effect=AssertionError('IO inside predict')):self.assertEqual(predict({'width':1,'gap':2})['action'],'PREDICT')
 def test_benchmark_does_not_claim_unknown_runner_is_pure(self):
  report=bench(lambda q:dict(x=1),[{}],2,0,0);self.assertFalse(report['inference_only']);self.assertEqual(report['timing_scope'],'predict_call_elapsed');self.assertFalse(report['runner_internal_io_excluded'])
 def test_per_field_absolute_and_relative_tolerance(self):
  a=json.loads((ROOT/'examples/golden.json').read_text(encoding='utf-8'));b=copy.deepcopy(a);a['queries'][0]['result']['score']=1000.;b['queries'][0]['result']['score']=1000.0005
  spec=dict(fields={'/score':dict(abs=.0001,rel=1e-6,unit='millivolts',rationale='ADC scale')})
  self.assertTrue(compare(a,b,spec)['passed'])
 def test_exact_semantic_path_cannot_be_toleranced(self):
  a=json.loads((ROOT/'examples/golden.json').read_text(encoding='utf-8'))
  with self.assertRaises(ValueError):compare(a,a,dict(fields={'/execution_allowed':dict(abs=1,rel=1,unit='bool',rationale='bad')}))
 def test_tolerance_typo_or_empty_unit_rejected(self):
  a=json.loads((ROOT/'examples/golden.json').read_text(encoding='utf-8'))
  for policy in [dict(abs_tol=1,unit='x',rationale='wrong key'),dict(abs=1,unit='',rationale='missing unit')]:
   with self.assertRaises(ValueError):compare(a,a,dict(fields={'/score':policy}))
 def test_threshold_class_flip_refused_within_score_tolerance(self):
  a=json.loads((ROOT/'examples/golden.json').read_text(encoding='utf-8'));b=copy.deepcopy(a)
  a['queries'][0]['result'].update(score=.50000001,predicted_class=1);b['queries'][0]['result'].update(score=.49999999,predicted_class=0)
  spec=json.loads((ROOT/'examples/tolerance_c.json').read_text(encoding='utf-8'));self.assertFalse(compare(a,b,spec)['passed'])
 def test_unknown_model_format_refused(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'x';p.write_bytes(b'not a model')
   with self.assertRaises(ValueError):load_runner(ROOT/'examples/demo_runner.py',p)
if __name__=='__main__':unittest.main()
