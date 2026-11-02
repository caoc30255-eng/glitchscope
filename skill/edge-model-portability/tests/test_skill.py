import copy,json,math,runpy,sys,tempfile,unittest,subprocess,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from golden_check import compare,load
from inference_bench import bench
class GoldenTests(unittest.TestCase):
 def fixture(self):return load(ROOT/'examples/golden.json'),load(ROOT/'examples/tolerance.json')
 def test_exact_pass(self):
  a,s=self.fixture();self.assertTrue(compare(a,copy.deepcopy(a),s)['passed'])
 def test_known_tiny_score_drift_passes(self):
  a,s=self.fixture();b=copy.deepcopy(a);b['queries'][0]['result']['score']+=2.22e-16;r=compare(a,b,s);self.assertTrue(r['passed']);self.assertEqual(len(r['changed_queries']),1)
 def test_large_drift_refused(self):
  a,s=self.fixture();b=copy.deepcopy(a);b['queries'][0]['result']['score']+=1e-4;self.assertFalse(compare(a,b,s)['passed'])
 def test_permissions_never_toleranced(self):
  a,s=self.fixture();b=copy.deepcopy(a);b['queries'][0]['result']['execution_allowed']=0;self.assertFalse(compare(a,b,s)['passed'])
 def test_action_change_refused(self):
  a,s=self.fixture();b=copy.deepcopy(a);b['queries'][0]['result']['action']='ABSTAIN';self.assertFalse(compare(a,b,s)['passed'])
 def test_model_binding_refused(self):
  a,s=self.fixture();b=copy.deepcopy(a);b['model_sha256']='0'*64;self.assertFalse(compare(a,b,s)['passed'])
 def test_input_float_change_refused(self):
  a,s=self.fixture();b=copy.deepcopy(a);b['queries'][0]['input']['width']=1.0;self.assertFalse(compare(a,b,s)['passed'])
 def test_short_queries_refused(self):
  a,s=self.fixture();b=copy.deepcopy(a);b['queries'].pop();self.assertFalse(compare(a,b,s)['passed'])
 def test_nonfinite_refused_even_at_allowed_path(self):
  a,s=self.fixture();b=copy.deepcopy(a);b['queries'][0]['result']['score']=float('nan');self.assertFalse(compare(a,b,s)['passed'])
 def test_nonfinite_and_duplicate_json_rejected_at_load(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'x'
   for text in ['{"x": NaN}','{"x":1,"x":2}']:
    p.write_text(text)
    with self.assertRaises(ValueError):load(p)
 def test_missing_result_key_refused(self):
  a,s=self.fixture();b=copy.deepcopy(a);b['queries'][0]['result'].pop('action');self.assertFalse(compare(a,b,s)['passed'])
 def test_benchmark_separates_warmup_memory_and_timing(self):
  calls=[]
  def predict(q):calls.append(q);return {'score':.5}
  r=bench(predict,[{'x':1}],calls=7,warmup=2,memory_probes=3)
  self.assertEqual(len(calls),12);self.assertEqual(r['calls'],7);self.assertFalse(r['RSS_measured']);self.assertFalse(r['hardware_time_measured'])
 def test_example_runner_refuses_unsupported_domain(self):
  f=runpy.run_path(str(ROOT/'examples/demo_runner.py'))['predict'];self.assertEqual(f({'width':True,'gap':1})['action'],'ABSTAIN')
 def test_declared_c_float_profile(self):
  a,_=self.fixture();s=load(ROOT/'examples/tolerance_c.json');b=copy.deepcopy(a);b['queries'][0]['result']['score']+=7.5e-8
  self.assertTrue(compare(a,b,s)['passed']);b['queries'][0]['result']['action']='ABSTAIN';self.assertFalse(compare(a,b,s)['passed'])
 def test_explicit_artifact_binding_export(self):
  with tempfile.TemporaryDirectory() as t:
   model=Path(t)/'weights.bin';model.write_bytes((ROOT/'examples/weights.txt').read_bytes().replace(b'threshold_width=8',b'threshold_width=12'));out=Path(t)/'actual.json'
   p=subprocess.run([sys.executable,'-B',str(ROOT/'scripts/export_predictions.py'),'--runner',str(ROOT/'examples/demo_runner.py'),'--queries',str(ROOT/'examples/queries.json'),'--model-artifact',str(model),'--output',str(out)],capture_output=True)
   self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(load(out)['model_sha256'],hashlib.sha256(model.read_bytes()).hexdigest())
 def test_demo_model_source_identity_bound_to_golden(self):
  a,_=self.fixture();self.assertEqual(hashlib.sha256((ROOT/'examples/weights.txt').read_bytes()).hexdigest(),a['model_sha256'])
if __name__=='__main__':unittest.main()
