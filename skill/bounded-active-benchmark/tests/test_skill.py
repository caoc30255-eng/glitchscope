import copy,json,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
import benchmark as b
class BenchmarkTests(unittest.TestCase):
 def experiment(self):return json.loads((ROOT/'examples/experiment.json').read_text(encoding='utf-8'))
 def test_equal_budget_counts_preparation(self):
  e=self.experiment();r=b.simulate(e,b.coverage_policy);self.assertEqual(r['used_records'],14);self.assertEqual(len(r['events']),4)
 def test_selector_receives_prefix_only(self):
  seen=[]
  def spy(s):
   self.assertEqual(set(s),{'domain','observed','groups_per_point','remaining_records','repeats','max_groups_per_point'})
   self.assertEqual(len(s['observed']),len(seen));seen.append(s);return b.coverage_policy(s)
  b.simulate(self.experiment(),spy)
 def test_reference_not_modified_or_shared_as_observed(self):
  e=self.experiment();before=copy.deepcopy(e)
  def mutate(s):
   p=b.coverage_policy(s);s['domain'].clear();s['observed'].clear();return p
  b.simulate(e,mutate);self.assertEqual(e,before)
 def test_out_of_domain_refused(self):
  with self.assertRaises(ValueError):b.simulate(self.experiment(),lambda s:'not-a-point')
 def test_duplicate_limit_refused(self):
  with self.assertRaises(ValueError):b.simulate(self.experiment(),lambda s:'p0')
 def test_unknown_not_a_failure_label(self):
  e=self.experiment();e['reference']['p0'][0]=None
  with self.assertRaises(ValueError):b.simulate(e,b.coverage_policy)
 def test_boolean_budget_refused(self):
  e=self.experiment();e['budget']=True
  with self.assertRaises(ValueError):b.validate(e)
 def test_tampered_decision_detected(self):
  e=self.experiment();r=b.simulate(e,b.coverage_policy);r['events'][0]['chosen']='p8'
  with self.assertRaises(ValueError):b.replay(e,r)
 def test_fake_feedback_before_selection_refused(self):
  e=self.experiment();r=b.simulate(e,b.coverage_policy);r['events'][0]['input']['observed']={'p8':[False]*3}
  with self.assertRaises(ValueError):b.replay(e,r)
 def test_counter_change_refused(self):
  e=self.experiment();r=b.simulate(e,b.coverage_policy);r['used_records']=2
  with self.assertRaises(ValueError):b.replay(e,r)
 def test_early_stop_does_not_claim_equal_actual_spend(self):
  e=self.experiment();a=b.simulate(e,b.coverage_policy);c=b.simulate(e,lambda s:None)
  r=b.compare(e,{'a':a,'c':c});self.assertFalse(r['equal_actual_records']);self.assertTrue(r['same_declared_budget_not_same_actual_spend'])
 def test_synthetic_results_never_accept_hardware_gain(self):
  e=self.experiment();r=b.evaluate(e,b.simulate(e,b.boundary_policy));self.assertFalse(r['hardware_speedup_accepted']);self.assertFalse(r['full_map_observed'])
 def test_hardware_input_cannot_enter_demo(self):
  e=self.experiment();e['origin']='HARDWARE'
  with self.assertRaises(ValueError):b.validate(e)
 def test_schema_bool_refused(self):
  e=self.experiment();e['schema']=True
  with self.assertRaises(ValueError):b.validate(e)
 def test_rehashed_bool_integer_prefix_forgery_refused(self):
  e=self.experiment();r=b.simulate(e,b.coverage_policy);event=r['events'][1];event['input']['observed']['p0'][0]=1
  event['decision_sha256']=b.digest({k:v for k,v in event.items() if k not in ('decision_sha256','outcomes','event_sha256')})
  event['event_sha256']=b.digest({k:v for k,v in event.items() if k!='event_sha256'})
  with self.assertRaisesRegex(ValueError,'PREFIX'):b.replay(e,r)
if __name__=='__main__':unittest.main()
