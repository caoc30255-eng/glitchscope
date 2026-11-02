"""Synthetic PREVIEW ledgers and saved plan contracts; never grants real board authority."""
import copy,json,tempfile,unittest,threading,subprocess,sys
from pathlib import Path
from common import ROOT,sha
from demo_authority import Authority,default_scope,plan_limit

class DemoLedger(unittest.TestCase):
    def setUp(self):
        self.base=Path(tempfile.mkdtemp(prefix='demo_ledger_test_',dir=str(ROOT.parent)))
        self.a=Authority(self.base/'book','PREVIEW')
        self.plan=json.loads((ROOT/'checks/regression_saved_plan.json').read_bytes())
    def grant(self,budget=100):return self.a.create_round(budget,default_scope(),'合成软件测试','批准本轮 %d 条'%budget,True)['active_round']
    def reserve(self,job='a'*32,prepare=True):
        p=self.a.reserve('scan',self.plan,job,'测试扫描',expected_round=self.a.status()['active_round']['id'])
        if prepare:self.a.mark_setup(job);self.a.bind_session(job,self.base/'session_00000050')
        return p
    def test_no_implicit_or_inexact_consent(self):
        self.assertIsNone(self.a.status()['active_round']);self.assertFalse(self.a.check_plan('scan',self.plan)['ready'])
        with self.assertRaises(ValueError):self.a.create_round(100,default_scope(),'test','',True)
        with self.assertRaises(ValueError):self.a.create_round(True,default_scope(),'test','批准本轮 1 条',True)
        self.assertIsNone(self.a.status()['active_round'])
    def test_44_reservation_early_stop_and_completed_subset(self):
        self.grant();self.reserve();r=self.a.status()['active_round'];self.assertEqual((r['available'],r['reserved'],r['occupied']),(56,44,0))
        for i in range(1,11):self.a.claim('a'*32,i);self.a.retire('a'*32,i)
        r=self.a.status()['active_round'];self.assertEqual((r['available'],r['reserved'],r['occupied'],r['completed']),(56,34,10,10))
        self.a.settle('a'*32,'STOPPED',True);r=self.a.status()['active_round'];self.assertEqual((r['available'],r['reserved'],r['occupied']),(90,0,10))
    def test_unknown_occupies_and_blocks(self):
        self.grant();self.reserve();self.a.claim('a'*32,1);self.a.settle('a'*32,'FAILED',True,'synthetic unknown')
        r=self.a.status()['active_round'];self.assertEqual((r['available'],r['occupied'],r['unknown'],r['state']),(99,1,1,'BLOCKED'))
        self.assertFalse(self.a.check_plan('scan',self.plan)['ready'])
        with self.assertRaises(ValueError):self.a.top_up(r['id'],10,'追加本轮 10 条')
        with self.assertRaises(ValueError):self.a.close_round(r['id'],'结束本轮')
        self.a.close_round(r['id'],'保留异常并结束本轮');r2=self.grant(50);self.assertEqual(r2['prior_occupied'],1)
    def test_cleanup_uncertain_holds_unused_reservation(self):
        self.grant();self.reserve();self.a.claim('a'*32,1);self.a.settle('a'*32,'FAILED',False,'close could not be confirmed')
        r=self.a.status()['active_round'];self.assertEqual((r['available'],r['reserved']),(56,43))
        with self.assertRaises(ValueError):self.a.close_round(r['id'],'保留异常并结束本轮')
    def test_software_rejection_before_hardware_costs_zero(self):
        self.grant();self.reserve(prepare=False);self.a.settle('a'*32,'SOFTWARE_REJECTED',True)
        r=self.a.status()['active_round'];self.assertEqual((r['available'],r['occupied'],r['completed']),(100,0,0))
    def test_insufficient_budget_scope_and_stale_round(self):
        self.grant(43);self.assertFalse(self.a.check_plan('scan',self.plan)['ready'])
        r=self.a.status()['active_round'];self.a.top_up(r['id'],1,'追加本轮 1 条');self.assertTrue(self.a.check_plan('scan',self.plan)['ready'])
        with self.assertRaises(ValueError):self.a.reserve('scan',self.plan,'a'*32,'test',expected_round='wrong')
        self.assertFalse(self.a._load()[1]['tasks'])
    def test_profile_scope_cannot_be_expanded(self):
        scope=default_scope();scope['profiles']=[dict(d=4,s=-2)]
        self.a.create_round(100,scope,'test','批准本轮 100 条',True)
        self.assertFalse(self.a.check_plan('scan',self.plan)['ready'])
    def test_concurrent_submission_single_hardware_lease(self):
        self.grant(200);results=[]
        def f(job):
            try:self.reserve(job);results.append(True)
            except ValueError:results.append(False)
        threads=[threading.Thread(target=f,args=(c*32,)) for c in ('a','b')]
        for t in threads:t.start()
        for t in threads:t.join()
        self.assertEqual(sorted(results),[False,True]);self.assertEqual(self.a.status()['active_round']['reserved'],44)
    def test_restart_preserves_reservation_and_never_resumes(self):
        self.grant();self.reserve();self.a.claim('a'*32,1)
        fresh=Authority(self.base/'book','PREVIEW');r=fresh.status()['active_round'];self.assertEqual((r['reserved'],r['occupied']),(43,1));self.assertFalse(fresh.check_plan('scan',self.plan)['ready'])
    def test_permit_hash_plan_and_once_only(self):
        self.grant();p=self.reserve()['permit_path'];self.assertEqual(self.a.verify_permit(p,self.plan)['mode'],'PREVIEW')
        self.a.settle('a'*32,'SOFTWARE_REJECTED',True)
        with self.assertRaises(ValueError):self.a.verify_permit(p,self.plan)
    def test_session_identity_only_after_real_allocation(self):
        self.grant();self.reserve(prepare=False);self.assertIsNone(self.a.task('a'*32)['session_name'])
        self.a.mark_setup('a'*32)
        self.a.bind_session('a'*32,self.base/'session_00000050');self.assertEqual(self.a.task('a'*32)['session_name'],'session_00000050')
        with self.assertRaises(ValueError):self.a.bind_session('a'*32,self.base/'session_00000051')
    def test_ledger_corruption_fails_closed(self):
        self.grant();p=self.base/'book/ledger.jsonl';s=p.read_text(encoding='utf-8');p.write_text(s.replace('批准本轮','tampered consent'),encoding='utf-8')
        with self.assertRaises(ValueError):self.a.status()
    def test_new_round_and_topup_are_explicit(self):
        r=self.grant(100)
        with self.assertRaises(ValueError):self.grant(50)
        with self.assertRaises(ValueError):self.a.top_up(r['id'],50,'automatic')
        self.a.top_up(r['id'],50,'追加本轮 50 条');self.assertEqual(self.a.status()['active_round']['total'],150)
    def test_canonical_plan_tamper_rejected(self):
        self.grant();p=copy.deepcopy(self.plan);p['max_records']=43
        with self.assertRaises(ValueError):plan_limit('scan',p)
        self.assertFalse(self.a.check_plan('scan',p)['ready'])
    def test_image65_uniform_profile_matches_round_scope(self):
        from worker import image_bind
        image_bind();from image_plan import schedule
        p=schedule(dict(source_sha256='a'*64,receiver_B=dict(d=4,s=-2),seed=20261018,fault_mode='random',fixed_fault=None));self.grant(100)
        self.assertTrue(self.a.check_plan('image',p)['ready']);v=self.a.reserve('image',p,'b'*32,'图片演示');self.assertEqual(v['max_records'],65)
        self.assertEqual(self.a.status()['active_round']['available'],35)
    def test_record_gate_requires_credit_and_same_session(self):
        self.grant();self.reserve(prepare=False)
        with self.assertRaises(ValueError):self.a.claim('a'*32,1)
        self.a.mark_setup('a'*32);self.a.bind_session('a'*32,self.base/'session_00000050')
        with self.assertRaises(ValueError):self.a.require_record('a'*32,1,self.base/'session_00000050')
        self.a.claim('a'*32,1)
        with self.assertRaises(ValueError):self.a.require_record('a'*32,1,self.base/'session_00000051')
        self.a.require_record('a'*32,1,self.base/'session_00000050');self.a.retire('a'*32,1)
        with self.assertRaises(ValueError):self.a.require_record('a'*32,1,self.base/'session_00000050')
    def test_missing_ledger_cannot_restart_budget(self):
        self.grant();p=self.base/'book/ledger.jsonl';p.rename(self.base/'retained_ledger_for_test.jsonl')
        with self.assertRaises(ValueError):self.a.status()
    def test_small_fixed_scan_does_not_reserve_unused_configured_cap(self):
        r=copy.deepcopy(self.plan['request']);r['scan']['points']=[dict(phase=5,width=1)];r['repeats']=1;r['max_records']=44
        out=self.base/'isolated_plan';out.mkdir();request=out/'request.json';request.write_text(json.dumps(dict(request=r,strategy='sequential')),encoding='utf-8')
        result=subprocess.run([sys.executable,'-B',str(ROOT/'worker.py'),'scan_preview',str(request),str(out)],capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr);p=json.loads((out/'result.json').read_bytes())['plan'];self.assertEqual(plan_limit('scan',p),3)
        self.grant(3);self.assertTrue(self.a.check_plan('scan',p)['ready']);v=self.a.reserve('scan',p,'e'*32,'三个记录');self.assertEqual(v['max_records'],3)

if __name__=='__main__':unittest.main(verbosity=2)
