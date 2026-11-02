"""Software only: synthetic control states and immutable reviewed data."""
from pathlib import Path
import sys,os,json,copy,uuid,unittest,hashlib
from unittest.mock import patch
ROOT=Path(__file__).resolve().parent;sys.path[:0]=[str(ROOT),str(ROOT/'backend')]
sys.dont_write_bytecode=True
from edge_api import EdgeAI,example_request
from custom_ai_core import query,EdgeModel,digest,load_model,hull,within_polygon
from custom_ai_data import read_splits,normalize
from custom_ai_training import train_bundle
from custom_ai_policy import rank_cells,model_for
from custom_plan import compile_plan,validate_plan
from custom_stats import aggregate
from custom_refine import suggest
from learning_domain import digest as plan_digest
from custom_ai_feedback import FeedbackStore,make_updated_dataset

TEST=Path(os.environ['EDGEAI_TEST_ROOT']);TEST.mkdir(parents=True,exist_ok=True)
def scratch():
    p=TEST/uuid.uuid4().hex;p.mkdir();return p

def synthetic_prefix(plan,values=None,session='SYNTHETIC_ONLY'):
    values=values if values is not None else [True]*3+[False]*3;rows=[]
    for rid in range(1,3+len(values)):
        slot=None if rid<3 else plan['initial_queue'][rid-3]
        c=None if slot is None else next(c for c in plan['conditions'] if c['condition_id']==slot['condition_id'])
        profile=plan['preparation'][rid-1]['receiver_B'] if rid<3 else plan['receiver_B']
        y=True if rid<3 else values[rid-3]
        rows.append(dict(uid=plan_digest(dict(session=session,rid=rid)),session=session,epoch=9,record_id=rid,
            kind='CONFIG' if rid==1 else 'CONTROL' if rid==2 else 'ITEM',identity_hex='%064x'%rid,
            status='UNKNOWN' if y is None else 'VALID',strict_retired=y is not None,actual_READY_saved=y is not None,
            condition_id=None if c is None else c['condition_id'],condition_sha256=None if c is None else c['condition_sha256'],
            requested_receiver_B=profile,actual_receiver_B=dict(profile,RX_profile_verified=True),fault=None if c is None else c['fault'],
            payload_sha256=plan['payload_sha256'],route_mode=0,mode=plan['mode'],
            labels={t:y for t in ('B_frame_correct','STM_payload_correct','STM_business_success')},
            result_sha256=plan_digest(dict(result=rid)),selection_sha256=None,
            evidence=[dict(path='SYNTHETIC_FIXTURE_NOT_REAL',bytes=0,sha256='0'*64)]))
    return rows

class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.service=EdgeAI();cls.splits=read_splits(ROOT/'data')
    def plan(self,**kwargs):
        r=example_request(**kwargs);p=compile_plan(r);self.assertEqual(p['status'],'ACCEPTED');return p['plan']
    def test_model_three_independent_targets(self):
        for t in ('B_frame_correct','STM_payload_correct','STM_business_success'):
            p=self.service.predict(query(target=t));self.assertEqual(p['target'],t);self.assertFalse(p['measurement_claim'])
    def test_stm_score_does_not_learn_B_ds_as_cause(self):
        for t in ('STM_payload_correct','STM_business_success'):
            self.assertEqual(self.service.predict(query(d=3,target=t))['score'],self.service.predict(query(d=4,target=t))['score'])
    def test_unseen_interior_gets_estimate_not_measurement(self):
        p=self.service.predict(query(phase=15,width=5));self.assertIsNotNone(p['score']);self.assertIsNone(p['training_observation'])
        self.assertEqual(p['support'],'UNSEEN_CONDITION_INSIDE_TRAINING_HULL');self.assertFalse(p['hardware_permission'])
    def test_context_outside_domain_refuses(self):
        for q in (query(d=1,s=2),query(phase=44,width=1),query(byte=21),query(bit=1),query(count=2),query(payload_sha256='0'*64)):
            p=self.service.predict(q);self.assertEqual(p['action'],'ABSTAIN');self.assertIsNone(p['score'])
    def test_boolean_nan_and_postmeasurement_input_refused(self):
        qs=[query(d=True),query(phase=float('nan')),query(width=0)]
        q=query();q['labels']={'B_frame_correct':True};qs.append(q)
        for q in qs:self.assertEqual(self.service.predict(q)['action'],'ABSTAIN')
    def test_known_repeat_conflict_retained(self):
        for q in (query(d=3,phase=15,width=10),query(d=4,phase=15,width=20)):
            p=self.service.predict(q);self.assertEqual(p['action'],'ABSTAIN');self.assertEqual(p['reason'],'TRAINING_REPEAT_CONFLICT')
            self.assertGreater(p['training_repeat_disagreement'],0)
    def test_snapshot_mutation_not_internal_state(self):
        before=self.service.predict(query());s=self.service.model.snapshot;s['targets']['B_frame_correct']['cells'][0]['n']=999
        self.assertEqual(before,self.service.predict(query()))
    def test_private_state_replacement_blocks(self):
        m=EdgeModel(self.service.model.snapshot);m._state=();self.assertEqual(m.predict(query())['reason'],'MODEL_RUNTIME_STATE_CHANGED')
    def test_model_hash_and_leaf_count_corruption_refused(self):
        s=self.service.model.snapshot;s['train_rows']=1
        with self.assertRaises(ValueError):EdgeModel(s)
        s=self.service.model.snapshot;s['targets']['B_frame_correct']['cells'][0]['successes']=99;s['model_sha256']=digest({k:v for k,v in s.items() if k!='model_sha256'})
        with self.assertRaises(ValueError):EdgeModel(s)
    def test_model_file_hash_mismatch_refused(self):
        path=scratch()/'model.json';path.write_text(json.dumps(self.service.model.snapshot))
        with self.assertRaises(ValueError):load_model(path,'0'*64)
    def test_convex_hull_boundaries(self):
        poly=hull([(5,1),(5,40),(35,10),(35,1)])
        self.assertTrue(within_polygon((15,5),poly));self.assertFalse(within_polygon((40,1),poly));self.assertTrue(within_polygon((5,40),poly))
    def test_training_split_and_uid_leak_rejected(self):
        rows=normalize(self.splits['train']);bad=rows+[normalize(self.splits['validation'])[0]]
        with self.assertRaises(ValueError):train_bundle(bad)
        with self.assertRaises(ValueError):train_bundle(rows+[rows[0]])
    def test_deterministic_rebuild_matches_shipped_weights(self):
        model,folds=train_bundle(normalize(self.splits['train']))
        self.assertEqual(model['model_sha256'],self.service.model.model_sha256)
        self.assertEqual({r['cv_group'] for r in folds['B_frame_correct']},{r['cv_group'] for r in self.splits['train']})
    def test_plan_model_and_strategy_are_bound(self):
        p=self.plan();validate_plan(p);p['request']['edge_ai']['max_extra_groups']=2
        with self.assertRaises(ValueError):validate_plan(p)
    def test_ai_suggestion_deterministic_and_no_hardware_grant(self):
        p=self.plan();r=synthetic_prefix(p)
        a=self.service.suggest(p,r,'SYNTHETIC_ONLY');b=self.service.suggest(p,r,'SYNTHETIC_ONLY')
        self.assertEqual(a,b);self.assertEqual(a['action'],'SELECT');self.assertFalse(a['hardware_permission'])
        self.assertEqual(a['required_records'],3);self.assertEqual(a['budget_after'],3)
        self.assertIn(a['condition_id'],{c['condition_id'] for c in p['conditions']})
    def test_budget_stops_without_short_repeat_group(self):
        p=self.plan(max_records=10);r=synthetic_prefix(p);s=self.service.suggest(p,r,'SYNTHETIC_ONLY')
        self.assertEqual(s['action'],'STOP_BUDGET')
    def test_wrong_budget_domain_and_session_refused(self):
        p=self.plan();r=synthetic_prefix(p)
        a=suggest(p,r,'SYNTHETIC_ONLY',99,confirmed_domain_sha256=plan_digest(p['conditions']));self.assertEqual(a['action'],'ABSTAIN')
        a=suggest(p,r,'SYNTHETIC_ONLY',6,confirmed_domain_sha256='0'*64);self.assertEqual(a['action'],'ABSTAIN')
        self.assertEqual(self.service.suggest(p,r,'wrong_session')['action'],'ABSTAIN')
    def test_unknown_and_partial_do_not_turn_into_fail_labels(self):
        p=self.plan();r=synthetic_prefix(p,[True]*3+[False,False,None]);a=self.service.suggest(p,r,'SYNTHETIC_ONLY')
        self.assertEqual(a['reason'],'UNKNOWN_BLOCKS_SELECTION')
        r=synthetic_prefix(p,[True]*3+[False]);self.assertEqual(self.service.suggest(p,r,'SYNTHETIC_ONLY')['reason'],'PARTIAL_REPEAT_GROUP_BLOCKS_SELECTION')
    def test_model_corruption_never_silent_rule_fallback(self):
        request=example_request();request['edge_ai']['model_file_sha256']='0'*64;p=compile_plan(request)['plan'];r=synthetic_prefix(p)
        a=self.service.suggest(p,r,'SYNTHETIC_ONLY');self.assertEqual(a['action'],'ABSTAIN');self.assertTrue(a['blocked_input'])
    def test_unsupported_model_profile_uses_declared_rule(self):
        p=self.plan(d=2,s=1);a=self.service.suggest(p,synthetic_prefix(p),'SYNTHETIC_ONLY')
        self.assertEqual(a['action'],'SELECT');self.assertFalse(a['training_model_used']);self.assertEqual(a['reason'],'RULE_FALLBACK_UNSUPPORTED_CONTEXT')
    def test_repeat_cap_prevents_reusing_mixed_forever(self):
        p=self.plan();r=synthetic_prefix(p,[True,False,True]+[False]*3);state=aggregate(p,r,'SYNTHETIC_ONLY')
        ranked=rank_cells(state['conditions'],p['target'],self.service.model,3,0)
        self.assertFalse(any(x['condition_id']==p['coarse_condition_ids'][0] for x in ranked))
    def test_single_phase_after_three_cells_forces_cross_phase(self):
        p=self.plan();state=aggregate(p,synthetic_prefix(p),'SYNTHETIC_ONLY');target=p['target']
        extra=next(c for c in state['conditions'] if c['condition']['fault']['phase']==15 and c['condition']['fault']['width']==10)
        extra['per_target'][target].update(valid=3,success=2,failure=1,state='MIXED')
        ranked=rank_cells(state['conditions'],target,self.service.model,3,1)
        self.assertTrue(ranked);self.assertTrue(all(c['condition']['fault']['phase']!=15 for c in ranked))
    def test_inference_model_never_changes_with_session_feedback(self):
        p=self.plan();before=self.service.model.model_sha256
        self.service.suggest(p,synthetic_prefix(p),'SYNTHETIC_ONLY');self.assertEqual(before,self.service.model.model_sha256)
    def test_fake_hardware_approval_refused_before_pynq(self):
        from custom_authorization import read_approval
        p=self.plan();path=scratch()/'NOT_APPROVED.json';path.write_text('{"schema":"SCAN_EXPLICIT_APPROVAL_V0_2","approved_by_user":false,"reviewed_by_owner":false}')
        with self.assertRaises(ValueError):read_approval(path,p,{},scratch(),'physical_records')
        self.assertNotIn('pynq',sys.modules)
    def test_future_training_update_keeps_explicit_approval_gate(self):
        p=scratch();queue=p/'queue.json';queue.write_text('{"schema":"EDGE_AI_FEEDBACK_REVIEW_QUEUE_V1","rows":[],"rows_sha256":"'+digest([])+'"}')
        review=p/'NOT_APPROVED.json';review.write_text(json.dumps(dict(reviewed_by_owner=False,training_approved_by_user=False,queue_file_sha256=hashlib.sha256(queue.read_bytes()).hexdigest())))
        with self.assertRaisesRegex(ValueError,'REVIEWED_UPDATE_AUTHORIZATION_REQUIRED'):make_updated_dataset(ROOT/'data',queue,review,p/'new_dataset')
        self.assertFalse((p/'new_dataset').exists())
    def test_database_corruption_not_exported_as_training(self):
        folder=scratch();store=FeedbackStore(folder/'test.sqlite')
        try:
            store.db.execute('INSERT INTO sessions VALUES (?,?,?,?,?)',('SYNTHETIC','0'*64,str(folder),0,'{}'))
            store.db.execute('INSERT INTO records VALUES (?,?,?,?,?,?,?,?)',('k','u','SYNTHETIC',1,'VALID',1,'0'*64,'{}'));store.db.commit()
            with self.assertRaisesRegex(ValueError,'DATABASE_ROW_CHANGED'):store.export_candidates(folder/'queue.json')
        finally:store.close()

class ModelIntegration(unittest.TestCase):
    def test_ai_owner_closes_bounded_synthetic_run_and_replays(self):
        from custom_model import ModelHarness,Backend
        from custom_replay import reconstruct
        plan=EdgeAI().compile(example_request(max_records=14))['plan'];h=ModelHarness(plan,scratch()/'run')
        try:
            api=Backend(h);api.start_once('edge_ai_synthetic_start')
            while h.owner.state in ('RUNNING','AWAITING_SELECTION'):
                status=api.status()
                if status['completed_coarse_records']>=status['coarse_records'] and status['attempts']<14:
                    choice=api.next_suggestion();api.step('synthetic_step_%03d'%status['attempts'],choice if choice['action']=='SELECT' else None)
                else:api.step('synthetic_step_%03d'%status['attempts'])
            self.assertEqual(api.status()['attempts'],14);self.assertEqual(api.status()['new_physical_STARTs'],0)
            self.assertEqual(api.status()['valid_records'],14)
            h.save();rebuilt=reconstruct(h.directory/'register_model_session')
            self.assertEqual(rebuilt['status'],'PASS');self.assertEqual(rebuilt['origin'],'REGISTER_DRIVER_MODEL')
            with self.assertRaisesRegex(ValueError,'TERMINAL'):api.step('synthetic_forbidden_extra_step')
            store=FeedbackStore(scratch()/'no_synthetic_training.sqlite')
            try:
                with self.assertRaises(ValueError):store.ingest(h.directory/'register_model_session')
            finally:store.close()
        finally:h.close()
