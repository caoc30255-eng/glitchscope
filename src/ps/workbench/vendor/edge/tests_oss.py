"""Standard-library deployment contracts; no upstream packages or hardware."""
from pathlib import Path
import sys,json,copy,unittest,os
ROOT=Path(__file__).resolve().parent;sys.path[:0]=[str(ROOT/'oss'),str(ROOT/'backend'),str(ROOT)]
from portable import load_default,from_condition,STRATEGY,features,validate,TARGETS,PortableForest,canonical
from custom_plan import compile_plan,validate_plan
from custom_refine import suggest
from learning_domain import digest
from tests_edge import synthetic_prefix,scratch
from feedback_oss import prepare_snapshot,load_splits

def request(d=3,s=-1,mode='TYPE3A_SINGLE',byte=20,bit=0,count=1,payload=None):
    r=dict(receiver_B=dict(d=d,s=s),mode=mode,fault=dict(byte=byte,bit=bit,count=count),
        scan=dict(points=[dict(phase=15,width=1),dict(phase=15,width=30)]),repeats=3,max_records=14,
        target=TARGETS[0],refinement=dict(enabled=True,confirmation_repeats=3,candidates=[dict(phase=15,width=10),dict(phase=5,width=10)]),
        edge_ai=dict(strategy=STRATEGY,model_file_sha256=load_default().file_sha256,max_extra_groups=1,allow_rule_fallback=True))
    if payload is not None:r['payload_hex']=payload.hex()
    return r
def plan(**kw):
    r=compile_plan(request(**kw));assert r['status']=='ACCEPTED',r['errors'];return r['plan']
class OSSContracts(unittest.TestCase):
    def test_all14_profiles_and_three_modes_compile_without_claiming_learning(self):
        total=0
        for d in range(1,5):
            for s in range(-2,4-d):
                for mode,count in [('TYPE3A_SINGLE',1),('TYPE3C_CONTIGUOUS',5),('DISABLED',0)]:
                    p=plan(d=d,s=s,mode=mode,count=count,byte=24,bit=2)
                    validate_plan(p);self.assertFalse(p['live_execution_authorized']);total+=1
                    self.assertIsNone(load_default().predict(from_condition(p['conditions'][0],p['target']))['score'])
        self.assertEqual(total,42)
    def test_every_payload_byte_bit_can_be_selected(self):
        for byte in range(20,276):
            for bit in range(8):
                r=request(byte=byte,bit=bit);r['refinement']['candidates']=[]
                self.assertEqual(compile_plan(r)['status'],'ACCEPTED')
    def test_boundary_contiguous_count_and_arbitrary_payload(self):
        p=plan(mode='TYPE3C_CONTIGUOUS',count=256,payload=bytes(256))
        self.assertEqual(p['conditions'][0]['count'],256)
        self.assertIsNone(load_default().predict(from_condition(p['conditions'][0],p['target']))['score'])
        r=request(mode='TYPE3C_CONTIGUOUS',byte=275,count=2);self.assertEqual(compile_plan(r)['status'],'REJECTED')
    def test_estimate_never_becomes_measured_label(self):
        p=plan();r=load_default().predict(from_condition(p['conditions'][0],p['target']))
        self.assertEqual(r['action'],'ESTIMATE');self.assertIsNone(r['prediction']);self.assertFalse(r['measurement_claim'])
    def test_invalid_conditions_and_postmeasurement_fields_refused(self):
        q=from_condition(plan()['conditions'][0],TARGETS[0])
        for key,value in [('count',2),('phase',True),('width',float('nan'))]:
            bad=copy.deepcopy(q);bad['fault'][key]=value;self.assertEqual(load_default().predict(bad)['action'],'ABSTAIN')
        q['actual_error']=1;self.assertEqual(load_default().predict(q)['action'],'ABSTAIN')
    def test_stm_models_exclude_B_profile_features(self):
        p=plan();q=from_condition(p['conditions'][0],TARGETS[1]);other=copy.deepcopy(q);other['receiver_B']=dict(d=4,s=-1)
        self.assertEqual(features(q),features(other));self.assertEqual(load_default().predict(q)['score'],load_default().predict(other)['score'])
    def test_exact_remaining_budget_domain_and_session(self):
        p=plan();rr=synthetic_prefix(p)
        for remaining,domain,session in [(100,digest(p['conditions']),'SYNTHETIC_ONLY'),(6,'0'*64,'SYNTHETIC_ONLY'),(6,digest(p['conditions']),'WRONG')]:
            self.assertEqual(suggest(p,rr,session,remaining,confirmed_domain_sha256=domain)['action'],'ABSTAIN')
    def test_unknown_partial_groups_block(self):
        p=plan()
        for vals,reason in [([True]*3+[False,False,None],'UNKNOWN_BLOCKS_SELECTION'),([True]*3+[False],'PARTIAL_REPEAT_GROUP_BLOCKS_SELECTION')]:
            rr=synthetic_prefix(p,vals);r=suggest(p,rr,'SYNTHETIC_ONLY',14-len(rr),confirmed_domain_sha256=digest(p['conditions']))
            self.assertEqual(r['reason'],reason)
    def test_unknown_context_uses_explicit_exploration(self):
        p=plan(d=1,s=2,byte=100,bit=7);rr=synthetic_prefix(p)
        r=suggest(p,rr,'SYNTHETIC_ONLY',6,confirmed_domain_sha256=digest(p['conditions']))
        self.assertEqual(r['action'],'SELECT');self.assertFalse(r['training_model_used']);self.assertIsNone(r['selected_model_prediction']['score'])
    def test_no_fallback_means_no_unlearned_selection(self):
        r=request(d=1,s=2);r['edge_ai']['allow_rule_fallback']=False;p=compile_plan(r)['plan'];rr=synthetic_prefix(p)
        self.assertEqual(suggest(p,rr,'SYNTHETIC_ONLY',6,confirmed_domain_sha256=digest(p['conditions']))['action'],'STOP')
    def test_corrupt_model_never_silent_fallback(self):
        r=request();r['edge_ai']['model_file_sha256']='0'*64;p=compile_plan(r)['plan'];rr=synthetic_prefix(p)
        v=suggest(p,rr,'SYNTHETIC_ONLY',6,confirmed_domain_sha256=digest(p['conditions']))
        self.assertEqual(v['action'],'ABSTAIN');self.assertTrue(v['blocked_input'])
    def test_source_snapshot_and_mutation_isolation(self):
        m=load_default();before=m.model_sha256;s=m.snapshot;s['train_rows']=0;self.assertNotEqual(m.snapshot['train_rows'],0);self.assertEqual(m.model_sha256,before)
        p=scratch()/'bad.json';p.write_bytes(canonical(s))
        import hashlib
        with self.assertRaises(ValueError):PortableForest(p,hashlib.sha256(p.read_bytes()).hexdigest())
    def test_future_feedback_training_still_requires_user_approval(self):
        p=scratch();q=p/'queue.json';q.write_text('{}');a=p/'approval.json';a.write_text('{}')
        with self.assertRaisesRegex(ValueError,'REVIEWED_UPDATE_AUTHORIZATION_REQUIRED'):prepare_snapshot(ROOT/'data',q,a,p/'snapshot')
        self.assertFalse((p/'snapshot').exists())
    def test_two_candidate_models_remain_independent(self):
        from edge_api import EdgeAI
        self.assertNotEqual(EdgeAI().model.model_sha256,load_default().model_sha256)
    def test_complete_synthetic_scan_uses_oss_policy_and_closes(self):
        from custom_model import ModelHarness,Backend
        p=plan();h=ModelHarness(p,scratch()/'oss_synthetic_run')
        try:
            api=Backend(h);api.start_once('oss_synthetic')
            while h.owner.state in ('RUNNING','AWAITING_SELECTION'):
                st=api.status()
                if st['completed_coarse_records']>=st['coarse_records'] and st['attempts']<14:
                    choice=api.next_suggestion();api.step('oss_step_%03d'%st['attempts'],choice if choice['action']=='SELECT' else None)
                else:api.step('oss_step_%03d'%st['attempts'])
            self.assertEqual(api.status()['valid_records'],14);self.assertEqual(api.status()['new_physical_STARTs'],0)
            self.assertTrue(api.status()['cleanup']['after']['lock_closed'])
            h.save()
            from custom_replay import reconstruct
            self.assertEqual(reconstruct(h.directory/'register_model_session')['origin'],'REGISTER_DRIVER_MODEL')
        finally:h.close()
