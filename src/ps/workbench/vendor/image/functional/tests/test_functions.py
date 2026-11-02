import ast,copy,inspect,json,os,struct,sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from labutil import *
from scans import *
from learner import *
from learner import evaluate as evaluate_algorithm
from images import *
from controller import Store,live_submit
from executor_contract import MainlineScanAdapter

class Functions(unittest.TestCase):
    def setUp(self):
        scratch=Path(__file__).resolve().parents[2]/'functional_test_work';scratch.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=str(scratch));self.root=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()
    def test_grid_budget_legal_units(self):
        sibling=Path(__file__).resolve().parents[1]/'..'/'functional_path_guard_probe'
        self.assertEqual(output_path(sibling),Path(os.path.abspath(sibling)).resolve())
        p=default_plan();self.assertEqual((sum(c['legal'] for c in p['cells']),p['required_starts']),(14,44))
        self.assertEqual(p['units']['tick_nominal_ns'],20);self.assertEqual(p['units']['sample_nominal_ns'],10)
        with self.assertRaises(Rejected):make_plan(bytes(range(256)),[5],[1],repeats=3,budget=4)
    def test_mutable_plan_detected(self):
        p=default_plan();p['fixed']['d']=4
        with self.assertRaises(Rejected):validate(p)
    def test_all_illegal_rejected(self):
        with self.assertRaises(Rejected):make_plan(b'a',[44],[4],budget=5)
    def test_schedule_empty_and_unknown_STOP(self):
        p=default_plan();self.assertEqual(propose(p,[])['request']['kind'],'CONFIG')
        h=dict(request_index=0,plan_sha256=p['plan_sha256'],identity_hex='1'*64,status='UNKNOWN',result_sha256=None,diagnostic_sha256='a'*64,origin='AUDITED_MEASUREMENT')
        d=propose(p,[h]);self.assertEqual(d['reason'],'UNKNOWN_BLOCKED');self.assertIsNone(d['after_result_sha256'])
    def test_history_wrong_binding_rejected(self):
        p=default_plan();h=dict(request_index=0,plan_sha256='wrong',identity_hex='1'*64,status='VALID',result_sha256='a'*64,origin='AUDITED_MEASUREMENT')
        with self.assertRaises(Rejected):propose(p,[h])
    def test_aggregate_distinguishes_conditions_and_unknown(self):
        p=default_plan();c=dict(block_sha256=p['payload_sha256'],d=3,s=-1,first_byte=20,count=1,bit=0,protocol='TYPE3A',phase=15,width=20)
        r=dict(uid='u',kind='ITEM',condition=c,origin='AUDITED_MEASUREMENT',status='UNKNOWN',labels={t:None for t in TARGETS})
        out=aggregate(p,[r]);cell=next(x for x in out['cells'] if x['point_id']=='p15_w20')
        self.assertEqual(cell['targets']['B_frame_correct']['unknown'],1);self.assertEqual(cell['targets']['B_frame_correct']['failure'],0)
        changed=copy.deepcopy(r);changed['uid']='d4';changed['condition']['d']=4
        self.assertIn('d4',aggregate(p,[changed])['unmatched_uids'])
    def test_unmeasured_and_predictions_separate(self):
        p=default_plan();out=aggregate(p,[],[dict(point_id='p15_w20',estimate=.8)])
        self.assertEqual(out['coverage']['measured'],0);self.assertFalse(out['real_hardware_complete'])
    def test_duplicate_record_and_conflict(self):
        p=default_plan();r=dict(uid='x',kind='ITEM',condition=None,status='UNKNOWN',labels={},origin='AUDITED_MEASUREMENT')
        self.assertEqual(len(aggregate(p,[r,r])['unmatched_uids']),1)
        altered=copy.deepcopy(r);altered['labels']={'B_frame_correct':True}
        with self.assertRaises(Rejected):aggregate(p,[r,altered])
    def test_actual_gp_fit_predict_select_save_load(self):
        m=Estimator().fit([dict(phase=5,width=1,y=1,origin='SIMULATED_DEVELOPMENT'),dict(phase=5,width=30,y=0,origin='SIMULATED_DEVELOPMENT')],'SIMULATED_DEVELOPMENT')
        cells=[c for c in default_plan()['cells'] if c['legal']];pred=m.predict(cells)
        self.assertGreater(next(p['estimate'] for p in pred if p['point_id']=='p5_w1'),next(p['estimate'] for p in pred if p['point_id']=='p5_w30'))
        m.save(self.root/'model.json');loaded=Estimator.load(self.root/'model.json');self.assertEqual(pred,loaded.predict(cells))
        self.assertEqual(m.select(cells,{c['point_id'] for c in cells})['action'],'STOP')
    def test_real_training_denied(self):
        with self.assertRaises(Rejected):Estimator().fit([],origin='AUDITED_MEASUREMENT')
        with self.assertRaises(Rejected):Estimator().fit([dict(phase=5,width=1,y=1,origin='AUDITED_MEASUREMENT')],'SIMULATED_DEVELOPMENT')
    def test_model_tamper_denied(self):
        m=Estimator().fit([],'SIMULATED_DEVELOPMENT');m.save(self.root/'m.json');v=read(self.root/'m.json');v['target']='STM_business_success';write(self.root/'m.json',v)
        with self.assertRaises(Rejected):Estimator.load(self.root/'m.json')
    def test_synthetic_evaluation_no_real_claim(self):
        e=evaluate_algorithm(default_plan(),seeds=(1,2));self.assertFalse(e['real_AI_acceleration_accepted'])
        for r in e['runs']:
            if not r['precision_comparable']:self.assertIsNone(r['synthetic_measurement_reduction'])
            self.assertIsNone(r['hardware_end_to_end_seconds'])
    def test_idempotent_refresh_and_conflict(self):
        s=Store(self.root);p=default_plan();s.plan(p);r=s.start(p['plan_sha256'],1,'grid','same-key-123')
        s.step(r['run_id']);again=s.start(p['plan_sha256'],1,'grid','same-key-123')
        self.assertEqual(again['run_id'],r['run_id']);self.assertEqual(s.runs()[0]['used_starts'],1)
        with self.assertRaises(Rejected):s.start(p['plan_sha256'],2,'grid','same-key-123')
    def test_exclusive_stop_no_refund(self):
        s=Store(self.root);p=default_plan();s.plan(p);r=s.start(p['plan_sha256'],1,'grid','first-key-123');s.step(r['run_id'])
        with self.assertRaises(Rejected):s.start(p['plan_sha256'],2,'grid','second-key-123')
        stopped=s.stop(r['run_id'],'stop-key-123');self.assertEqual(stopped['used_starts'],1)
        self.assertEqual(stopped['cancelled_unstarted'],43);self.assertEqual(s.step(r['run_id'])['used_starts'],1)
    def test_unknown_blocked_no_auto_retry(self):
        s=Store(self.root);p=default_plan();s.plan(p);r=s.start(p['plan_sha256'],1,'grid','unknown-key-123',.5)
        for _ in range(44):
            r=s.step(r['run_id'])
            if r['state']=='BLOCKED_UNKNOWN':break
        self.assertEqual(r['state'],'BLOCKED_UNKNOWN');n=r['used_starts'];self.assertEqual(s.step(r['run_id'])['used_starts'],n)
    def test_restart_blocks_not_resumes(self):
        s=Store(self.root);p=default_plan();s.plan(p);r=s.start(p['plan_sha256'],1,'grid','restart-key-123');s.step(r['run_id'])
        other=Store(self.root);self.assertEqual(other.runs()[0]['state'],'BLOCKED_RESTART');self.assertEqual(other.runs()[0]['used_starts'],1)
    def test_live_disabled(self):
        with self.assertRaisesRegex(Rejected,'NOT_PROVIDED'):live_submit({})
    def test_assembler_order_duplicate_conflict_missing_stop(self):
        cfg=dict(width=4,height=2,total_bytes=8,chunk_size=4,item_total=2);a=Assembler(cfg,'B')
        p=dict(lane='B',item_index=1,payload_hex=b'abcd'.hex(),identity_hex='a'*64)
        self.assertEqual(a.add(p,{}),'ACCEPTED');self.assertEqual(a.add(p,{}),'DUPLICATE');raw,mask,_=a.render()
        self.assertEqual(mask,b'\xff'*4+b'\0'*4);self.assertEqual(raw[4:],b'abcd')
        changed=dict(p,payload_hex=b'abce'.hex())
        with self.assertRaises(Rejected):a.add(changed,{})
        a.stop()
        with self.assertRaises(Rejected):a.add(p,{})
    def test_crc_burst_without_source_input(self):
        original=bytes(range(256));damaged=bytearray(original)
        for i in range(30,56):damaged[i]^=32
        with patch.object(Path,'open',side_effect=AssertionError('repair must not read files')):
            candidates=burst_candidates(bytes(damaged),crc(original))
        self.assertIn(original,candidates);self.assertNotIn('source',inspect.signature(repair).parameters)
    def test_crc_valid_not_automatically_lossless(self):
        cfg=dict(width=2,height=2,total_bytes=4,item_total=1,chunk_size=4,item_crcs=[crc(b'abcd')],image_sha256='0'*64)
        a=Assembler(cfg,'B');a.add(dict(lane='B',item_index=0,payload_hex=b'abcd'.hex()),{})
        out=repair(cfg,{'B':a},'crc_select');self.assertFalse(out['metadata']['whole_received_config_SHA_verified'])
    def test_lossless_view_conversions(self):
        obj={'identity':2**200,'start':5,'deadline':2**63,'ordinary':4};original=copy.deepcopy(obj);v=view(obj)
        self.assertEqual(len(v['identity']),64);self.assertIsInstance(v['start'],str);self.assertIsInstance(v['deadline'],str);self.assertEqual(obj,original)
    def test_contract_mock_and_wrong_budget(self):
        calls=[];p=default_plan()
        def transport(op,args):
            calls.append(op)
            if op=='capabilities':return dict(contract='BOUNDED_SCAN_SERVICE_PROPOSED_V0_1',owns_exclusive_hardware_lock=True,UNKNOWN_blocks=True,strict_retirement_required=True)
            if op=='submit_plan':return dict(plan_sha256=p['plan_sha256'],budget_receipt_verified=True,namespace_reserved=True)
            if op=='stop_unstarted':return dict(refund_or_quota_added=False,inflight_owner='MAINLINE_EXECUTOR')
        adapter=MainlineScanAdapter(transport);adapter.submit(p,dict(plan_sha256=p['plan_sha256'],authorized_starts=44),'approval-key-123');adapter.stop('r','stop-key-123')
        self.assertEqual(calls,['capabilities','submit_plan','stop_unstarted'])
        with self.assertRaises(Rejected):adapter.submit(p,dict(plan_sha256=p['plan_sha256'],authorized_starts=65),'another-key-123')
    def test_python38_syntax(self):
        for p in Path(__file__).resolve().parents[1].glob('*.py'):ast.parse(p.read_text(encoding='utf-8'),feature_version=(3,8))
    def test_package_and_source_output_guards(self):
        with self.assertRaises(Rejected):output_path(Path(__file__).resolve().parents[1]/'accidental_state')
        frozen=self.root/'source';frozen.mkdir();(frozen/'sha256_manifest.json').write_bytes(b'{"files":{}}')
        with self.assertRaises(Rejected):Store(frozen)
        with self.assertRaises(Rejected):write(frozen/'new.json',{})
        self.assertFalse((frozen/'lab_state.sqlite').exists());self.assertFalse((frozen/'new.json').exists())

if __name__=='__main__':unittest.main()
