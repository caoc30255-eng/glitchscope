"""Unit contracts: only synthetic checked fixtures; not hardware evidence."""
import ast,copy,json,unittest
from pathlib import Path
from custom_plan import compile_plan,validate_plan,capabilities,condition
from custom_stats import aggregate,group_external
from custom_refine import suggest
from learning_domain import digest

def request(d=2,s=1,repeats=2,limit=8,refine=False):
    return dict(receiver_B=dict(d=d,s=s),mode='TYPE3A_SINGLE',fault=dict(byte=24,bit=2,count=1),scan=dict(points=[dict(phase=7,width=3)]),
        repeats=repeats,max_records=limit,refinement=dict(enabled=refine,confirmation_repeats=2,candidates=[dict(phase=7,width=6)] if refine else []))
def plan(**kwargs):
    result=compile_plan(request(**kwargs));assert result['status']=='ACCEPTED',result;return result['plan']
def rows(p,labels,session='unit_only_session'):
    out=[];condition=p['conditions'][0]
    for rid in range(1,3+len(labels)):
        cid=None if rid<3 else condition['condition_id'];profile=p['preparation'][rid-1]['receiver_B'] if rid<3 else p['receiver_B'];value=True if rid<3 else labels[rid-3]
        lab=dict(B_frame_correct=value,STM_payload_correct=value,STM_business_success=value)
        out.append(dict(uid=digest(dict(session=session,rid=rid)),session=session,epoch=9,record_id=rid,kind='CONFIG' if rid==1 else 'CONTROL' if rid==2 else 'ITEM',
            identity_hex='%064x'%rid,status='UNKNOWN' if value is None else 'VALID',strict_retired=value is not None,actual_READY_saved=value is not None,
            condition_id=cid,condition_sha256=None if rid<3 else condition['condition_sha256'],requested_receiver_B=profile,actual_receiver_B=dict(profile,RX_profile_verified=True),
            fault=None if rid<3 else copy.deepcopy(condition['fault']),payload_sha256=p['payload_sha256'],route_mode=0,mode='TYPE3A_SINGLE',labels=lab,
            result_sha256=digest(dict(result=rid)),selection_sha256=None,evidence=[dict(path='UNIT_FIXTURE_NOT_RAW_EVIDENCE',bytes=0,sha256='0'*64)]))
    return out

class CompileTests(unittest.TestCase):
    def test_custom_ranges_non_original_grid(self):
        r=request();r['scan']=dict(phase=dict(start=7,stop=11,step=4),width=[3,9]);r['repeats']=1
        v=compile_plan(r);self.assertEqual(v['status'],'ACCEPTED');self.assertEqual(len(v['plan']['coarse_condition_ids']),4)
        self.assertEqual((v['required_records'],v['item_total'],v['source_bytes'],v['CONFIG_height']),(6,7,1792,56))
    def test_condition_includes_all_physical_context(self):
        a=plan();b=plan(d=3,s=-1)
        self.assertNotEqual(a['conditions'][0]['condition_sha256'],b['conditions'][0]['condition_sha256'])
        r=request();r['fault']['byte']=25;c=compile_plan(r)['plan'];self.assertNotEqual(c['conditions'][0]['condition_sha256'],a['conditions'][0]['condition_sha256'])
        r['payload_hex']='ff'*256;d=compile_plan(r)['plan'];self.assertNotEqual(c['conditions'][0]['condition_sha256'],d['conditions'][0]['condition_sha256'])
    def test_receiver_ranges_and_bool(self):
        for d,s in ((1,2),(2,1),(3,0),(4,-2)):self.assertEqual(compile_plan(request(d,s))['status'],'ACCEPTED')
        for d,s in ((True,-1),(0,-1),(4,0),(2,2),(1,-3)):self.assertEqual(compile_plan(request(d,s))['status'],'REJECTED')
    def test_fault_bounds_and_window(self):
        for field,value in [('byte',19),('byte',276),('bit',8),('count',2),('bit',True)]:
            r=request();r['fault'][field]=value;self.assertEqual(compile_plan(r)['status'],'REJECTED')
        for point in (dict(phase=4,width=1),dict(phase=30,width=16),dict(phase=7,width=0)):
            r=request();r['scan']['points']=[point];self.assertEqual(compile_plan(r)['status'],'REJECTED')
    def test_no_silent_drop_or_dedupe(self):
        r=request();r['scan']['points'] += [dict(phase=45,width=1)]
        v=compile_plan(r);self.assertEqual(v['status'],'REJECTED');self.assertEqual(len(v['legal_conditions']),1);self.assertEqual(len(v['rejected_conditions']),1);self.assertIsNone(v['plan'])
        r=request();r['scan']['points']*=2;self.assertEqual(compile_plan(r)['status'],'REJECTED')
    def test_insufficient_budget_includes_two_preparations(self):
        r=request(repeats=3,limit=4);v=compile_plan(r);self.assertEqual(v['required_records'],5);self.assertEqual(v['status'],'REJECTED')
        self.assertEqual(compile_plan(request(limit=45))['status'],'REJECTED')
    def test_multipoint_execution_adapter_declared(self):
        r=request();r['mode']='TYPE3C_CONTIGUOUS';r['fault']['count']=4;v=compile_plan(r)
        self.assertEqual(v['status'],'ACCEPTED');self.assertEqual(v['plan']['conditions'][0]['count'],4)
        r['fault']['count']=256;r['fault']['byte']=21;self.assertNotIn('DRIVER_VALID_BUT',compile_plan(r)['rejected_conditions'][0]['reason'])
    def test_multiple_profiles_and_independent_points_rejected(self):
        r=request();r['receiver_B']=[dict(d=2,s=1),dict(d=3,s=-1)];self.assertEqual(compile_plan(r)['status'],'REJECTED')
        r=request();r['independent_points']=[1,2];self.assertEqual(compile_plan(r)['status'],'REJECTED')
    def test_range_step_and_payload_rejection(self):
        r=request();r['scan']=dict(phase=dict(start=7,stop=10,step=0),width=[1]);self.assertEqual(compile_plan(r)['status'],'REJECTED')
        r=request();r['payload_hex']='aa';self.assertEqual(compile_plan(r)['status'],'REJECTED')
        r=request();r['route_mode']=1;self.assertEqual(compile_plan(r)['status'],'REJECTED')
    def test_determinism_and_frozen_plan(self):
        r=request();a=compile_plan(r);self.assertEqual(a,compile_plan(r));validate_plan(a['plan'])
        a['plan']['max_records']=9
        with self.assertRaises(ValueError):validate_plan(a['plan'])
    def test_capability_split(self):
        c=capabilities();self.assertTrue(c['TYPE3A_SINGLE']['implemented']);self.assertTrue(c['TYPE3C_CONTIGUOUS']['execution_implemented']);self.assertFalse(c['TYPE3C_CONTIGUOUS']['real_hardware_verified']);self.assertEqual(c['new_physical_STARTs_authorized'],0)
    def test_config_profile_explicit(self):
        p=plan();self.assertEqual(p['preparation'],[dict(kind='CONFIG',receiver_B=dict(d=3,s=-1)),dict(kind='CONTROL',receiver_B=dict(d=2,s=1))])

class StatsTests(unittest.TestCase):
    def test_mixed_partial_and_unmeasured(self):
        p=plan(refine=True);r=rows(p,[True,False]);g=aggregate(p,r,'unit_only_session')
        self.assertEqual(g['conditions'][0]['per_target']['B_frame_correct']['state'],'MIXED');self.assertFalse(g['confirmed_domain_complete']);self.assertTrue(g['coarse_domain_complete'])
        self.assertEqual(aggregate(p,r[:-1],'unit_only_session')['conditions'][0]['per_target']['B_frame_correct']['state'],'PARTIAL')
    def test_unknown_not_failure_and_global_preparation(self):
        p=plan();r=rows(p,[None]);g=aggregate(p,r,'unit_only_session');self.assertEqual(g['state'],'BLOCKED_UNKNOWN');self.assertEqual(g['conditions'][0]['per_target']['B_frame_correct']['failure'],0)
        r[-1]['labels']['B_frame_correct']=False
        with self.assertRaises(ValueError):aggregate(p,r,'unit_only_session')
        r=rows(p,[])[:1];r[0]['status']='UNKNOWN';r[0]['labels']={t:None for t in r[0]['labels']};r[0]['strict_retired']=False
        self.assertEqual(aggregate(p,r,'unit_only_session')['state'],'BLOCKED_UNKNOWN')
    def test_target_independence(self):
        p=plan();r=rows(p,[True,True]);r[-1]['labels']['STM_business_success']=False;g=aggregate(p,r,'unit_only_session')['conditions'][0]['per_target']
        self.assertEqual(g['B_frame_correct']['state'],'OBSERVED_ALL_PASS');self.assertEqual(g['STM_business_success']['state'],'MIXED')
    def test_cross_session_identity_replay_and_missing_prefix(self):
        p=plan();r=rows(p,[True])
        for data in (r+[r[-1]],r[2:]):
            with self.assertRaises(ValueError):aggregate(p,data,'unit_only_session')
        with self.assertRaises(ValueError):aggregate(p,r,'other_session')
        r[-1]['identity_hex']=r[0]['identity_hex']
        with self.assertRaises(ValueError):aggregate(p,r,'unit_only_session')
    def test_actual_readback_and_full_condition_binding(self):
        p=plan();r=rows(p,[True]);r[-1]['actual_receiver_B']['d']=3
        with self.assertRaises(ValueError):aggregate(p,r,'unit_only_session')
        r=rows(p,[True]);r[-1]['fault']['byte']=25
        with self.assertRaises(ValueError):aggregate(p,r,'unit_only_session')
    def test_excess_repeats_requires_committed_refinement(self):
        p=plan();r=rows(p,[True,False,True])
        with self.assertRaisesRegex(ValueError,'EXCESS_UNPERMITTED'):aggregate(p,r,'unit_only_session')
    def test_different_profiles_not_grouped_by_phase_width(self):
        p=plan();q=plan(d=3,s=-1)
        a=aggregate(p,rows(p,[True,False],'a'),'a');b=aggregate(q,rows(q,[True,True],'b'),'b')
        self.assertEqual(len(group_external([a,b])['groups']),2)
        with self.assertRaises(ValueError):group_external([a,a])

class RefinementTests(unittest.TestCase):
    def call(self,p,r,**kwargs):return suggest(p,r,'unit_only_session',p['max_records']-len(r),confirmed_domain_sha256=digest(p['conditions']),**kwargs)
    def test_mixed_priority_cost_and_determinism(self):
        p=plan(refine=True);r=rows(p,[True,False]);q=self.call(p,r)
        self.assertEqual(q['reason'],'CONFIRM_OBSERVED_MIXED_REGION');self.assertEqual(q['required_records'],2);self.assertEqual(q,self.call(p,r));self.assertFalse(q['hardware_permission'])
    def test_missing_is_not_stable(self):
        p=plan(refine=True);q=self.call(p,rows(p,[True,True]));self.assertEqual(q['reason'],'UNMEASURED_CONFIRMED_CONDITION')
    def test_budget_unknown_and_partial(self):
        p=plan(refine=True,limit=5);r=rows(p,[True,False]);self.assertEqual(self.call(p,r)['action'],'STOP_BUDGET')
        p=plan(refine=True);self.assertEqual(self.call(p,rows(p,[None]))['reason'],'UNKNOWN_BLOCKS_SELECTION')
        self.assertEqual(self.call(p,rows(p,[True]))['reason'],'PARTIAL_GROUP_MUST_FINISH_OR_STOP')
    def test_domain_and_remaining_must_match(self):
        p=plan(refine=True);r=rows(p,[True,False]);q=suggest(p,r,'unit_only_session',1,confirmed_domain_sha256='0'*64);self.assertEqual(q['action'],'ABSTAIN')
    def test_independent_target_proposal(self):
        p=plan(refine=True);r=rows(p,[True,True]);r[-1]['labels']['STM_business_success']=False
        self.assertEqual(self.call(p,r)['reason'],'UNMEASURED_CONFIRMED_CONDITION');self.assertEqual(self.call(p,r,target='STM_business_success')['reason'],'CONFIRM_OBSERVED_MIXED_REGION')
    def test_python38_syntax(self):
        for path in Path(__file__).parent.glob('*.py'):ast.parse(path.read_text(encoding='utf-8'),feature_version=(3,8))
    def test_existing_v02_rule_reused_for_compatible_domain(self):
        from learning_domain import CELLS
        r=request(repeats=3,limit=11,refine=True);r['scan']['points']=[dict(phase=15,width=1),dict(phase=15,width=30)]
        r['refinement']=dict(enabled=True,confirmation_repeats=3,candidates=[dict(phase=c['phase'],width=c['width']) for c in CELLS])
        p=compile_plan(r)['plan'];data=rows(p,[True,True,True,False,False,False]);second=p['conditions'][1]
        for row in data[5:]:row.update(condition_id=second['condition_id'],condition_sha256=second['condition_sha256'],fault=copy.deepcopy(second['fault']))
        proposal=self.call(p,data);self.assertEqual(proposal['rule_version'],'BOUNDARY_BRACKET_EXPLORATION_RULE_V0_2');self.assertEqual(proposal['condition']['fault']['width'],20)

if __name__=='__main__':unittest.main(verbosity=2)
