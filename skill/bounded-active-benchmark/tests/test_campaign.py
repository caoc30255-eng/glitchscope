import copy,json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
import campaign as c
class CampaignTests(unittest.TestCase):
 def config(self):return json.loads((ROOT/'examples/noisy_campaign.json').read_text(encoding='utf-8'))
 def test_fresh_repeats_use_new_index(self):
  calls=[];config=self.config();config.update(max_groups_per_point=4)
  oracle=c.NoisyOracle(config['truth_probabilities'],7,0)
  def collect(r):calls.append(r);return oracle(r)
  run=c.run_policy(config,lambda s:'p4',collect,'x')
  indices=[r['repeat_index'] for r in calls if r['kind']=='ITEM'];self.assertEqual(indices,list(range(12)));self.assertEqual(run['groups_per_point']['p4'],4)
 def test_unknown_stops_immediately_not_false(self):
  x=self.config();run=c.run_policy(x,c.coverage,c.NoisyOracle(x['truth_probabilities'],1,1),'x')
  self.assertEqual(run['occupied'],1);self.assertEqual(run['unknown_records'],1);self.assertEqual(run['observed'],{});self.assertEqual(run['terminal'],'BLOCKED_UNKNOWN')
 def test_partial_group_not_used_for_next_decision(self):
  x=self.config();oracle=c.NoisyOracle(x['truth_probabilities'],1,0);calls=[]
  def collect(req):
   calls.append(req);reply=oracle(req)
   if len(calls)==4:reply.update(status='UNKNOWN',outcome=None)
   return reply
  run=c.run_policy(x,c.coverage,collect,'x');self.assertEqual(run['occupied'],4);self.assertEqual(run['observed'],{});self.assertEqual(len(run['decisions']),1)
 def test_receiver_echo_mismatch_is_unknown(self):
  x=self.config()
  def wrong(req):return dict(record_id='other',request_sha256='0'*64,status='VALID',outcome=True)
  run=c.run_policy(x,c.coverage,wrong,'x');self.assertEqual(run['unknown_records'],1)
 def test_real_adapter_requires_full_hooks(self):
  with self.assertRaises(ValueError):c.run_policy(self.config(),c.coverage,lambda r:None,'x',origin='ADAPTER_REPORTED')
 def test_attempt_hook_precedes_collect_and_result_hook(self):
  x=self.config();order=[];oracle=c.NoisyOracle(x['truth_probabilities'],1,0)
  def before(req):order.append(('before',req['record_id']))
  def collect(req):self.assertEqual(order[-1],('before',req['record_id']));return oracle(req)
  def after(req,row):order.append(('after',req['record_id']))
  run=c.run_policy(x,c.coverage,collect,'x','ADAPTER_REPORTED',before,lambda req,r:True,after)
  self.assertEqual(len(order),2*run['occupied'])
 def test_replay_rejects_fake_counters(self):
  x=self.config();run=c.run_policy(x,c.coverage,c.NoisyOracle(x['truth_probabilities'],1,0),'x');run['completed_records']=0
  with self.assertRaises(ValueError):c.audit_run(run)
 def test_policy_does_not_receive_truth(self):
  x=self.config()
  def policy(s):self.assertNotIn('truth_probabilities',s);self.assertNotIn('seeds',s);return c.coverage(s)
  c.run_policy(x,policy,c.NoisyOracle(x['truth_probabilities'],1,0),'x')
 def test_predeclared_seed_reproducibility(self):
  x=self.config();a=c.NoisyOracle(x['truth_probabilities'],123,0);b=c.NoisyOracle(x['truth_probabilities'],123,0)
  for i in range(20):
   request=dict(record_id=str(i),point_id='p4',repeat_index=i,kind='ITEM');self.assertEqual(a(request),b(request))
 def test_wilson_interval_and_paired_campaign_unit(self):
  lo,hi=c.wilson(5,10);self.assertLess(lo,.5);self.assertGreater(hi,.5);r=c.paired_interval([2]*10,[1]*10,200);self.assertEqual(r['ci95'],[1,1]);self.assertEqual(r['campaigns'],10)
 def test_bootstrap_invalid_counts_rejected(self):
  with self.assertRaises(ValueError):c.paired_interval([1,2],[1,2],True)
 def test_rehashed_bool_integer_receipt_and_counter_types_rejected(self):
  x=self.config();run=c.run_policy(x,c.coverage,c.NoisyOracle(x['truth_probabilities'],1,0),'x');bad=copy.deepcopy(run)
  row=bad['records'][-1];row['receipt']['outcome']=int(row['outcome']);row['sha256']=c.digest({k:v for k,v in row.items() if k!='sha256'})
  with self.assertRaises(ValueError):c.audit_run(bad)
  bad=copy.deepcopy(run);bad['completed_records']=True
  with self.assertRaises(ValueError):c.audit_run(bad)
 def test_unknown_at_setup_cannot_hide_extra_decisions(self):
  x=self.config();run=c.run_policy(x,c.coverage,c.NoisyOracle(x['truth_probabilities'],1,1),'x');run['decisions']=[{}]
  with self.assertRaises(ValueError):c.audit_run(run)
if __name__=='__main__':unittest.main()
