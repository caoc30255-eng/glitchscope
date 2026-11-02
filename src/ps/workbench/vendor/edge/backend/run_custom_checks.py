"""Register/serial model evidence for custom-domain backend contracts."""
import argparse,copy,json
from pathlib import Path
from custom_plan import compile_plan,raw,require
from custom_stats import aggregate,group_external
from custom_model import ModelHarness
from tests_backend import request

def run(output):
    output=Path(output);output.mkdir(parents=True,exist_ok=False);summaries=[];groups=[]
    cases=['custom_ranges','same_coords_d3','profile_d4_payload','mixed_refinement','legacy_refinement','partial_stop','unknown_fault','unknown_preparation','source_tamper','raw_tamper','duplicate_calls']
    for name in cases:
        r=request(repeats=3,limit=9,refine=name=='mixed_refinement')
        if name=='custom_ranges':r['scan']=dict(phase=dict(start=7,stop=11,step=4),width=[3,9]);r['repeats']=1;r['max_records']=8
        if name=='profile_d4_payload':r=request(4,-2,repeats=1,limit=5);r['fault']=dict(byte=275,bit=7,count=1);r['payload_hex']='ff'*256
        if name=='same_coords_d3':r=request(3,-1,repeats=1,limit=5)
        if name=='legacy_refinement':
            from learning_domain import CELLS
            r=request(3,-1,repeats=3,limit=11,refine=True);r['fault']=dict(byte=20,bit=0,count=1)
            r['scan']['points']=[dict(phase=15,width=1),dict(phase=15,width=30)]
            r['refinement']=dict(enabled=True,confirmation_repeats=3,candidates=[dict(phase=c['phase'],width=c['width']) for c in CELLS])
        compiled=compile_plan(r);require(compiled['status']=='ACCEPTED','TEST_PLAN_REJECTED')
        h=ModelHarness(compiled['plan'],output/name);o=h.owner
        try:
            if name=='mixed_refinement':
                h.mixed_faults=True;h.run();require(o.state=='AWAITING_SELECTION','EXPECTED_EXPLICIT_SELECTION_WAIT')
                before=o.executor.attempts;proposal=o.next_suggestion();require(proposal==o.next_suggestion(),'NONDETERMINISTIC_SELECTION')
                require(proposal['reason']=='CONFIRM_OBSERVED_MIXED_REGION' and proposal['required_records']==2,'MIXED_FIRST')
                count=0
                while o.state not in ('STOPPED_BUDGET','STOPPED_PLAN_COMPLETE'):
                    count+=1;require(count<=20,'LOOP_BOUND')
                    if o.state=='AWAITING_SELECTION':h.step('refine_confirm_%03d'%count,o.next_suggestion())
                    else:h.step('refine_record_%03d'%count)
                require(o.executor.attempts==9 and before==5,'REFINEMENT_BUDGET_MISMATCH')
            elif name=='legacy_refinement':
                h.run();require(o.state=='AWAITING_SELECTION','EXPECTED_SELECTION_WAIT')
                p=o.next_suggestion();require(p['rule_version']=='BOUNDARY_BRACKET_EXPLORATION_RULE_V0_2' and p['condition']['fault']['width']==20,'EXACT_EXISTING_RULE')
                h.step('legacy_choice_0001',p)
                h.step('legacy_record_0002');h.step('legacy_record_0003');h.step('legacy_finish_0004')
            elif name=='partial_stop':
                o.start_once('manual_start_0001')
                for rid in range(1,4):h.step('manual_record_%03d'%rid)
                o.request_stop();require(o.executor.attempts==3,'PARTIAL_STOP_ATTEMPTS')
            elif name=='source_tamper':
                f=o.executor.root/'plan/source.bin';f.write_bytes(f.read_bytes()+b'tamper')
                try:h.run();raise AssertionError('TAMPER_NOT_BLOCKED')
                except ValueError:pass
                require(o.state=='BLOCKED_INPUT' and o.executor.attempts==0,'PRE_EFFECT_TAMPER')
            elif name=='raw_tamper':
                original=h.one
                def one(*a,**kw):
                    result=original(*a,**kw)
                    if a[4]==3:
                        f=Path(result['CH0_evidence_dir'])/'b_raw.bin';f.write_bytes(f.read_bytes()+b'bad')
                    return result
                h.one=one;h.run();require(o.state=='BLOCKED_UNKNOWN' and o.executor.attempts==3,'RAW_MUST_BLOCK')
            elif name=='duplicate_calls':
                o.start_once('same_start_0001');o.start_once('same_start_0001')
                first=h.step('same_record_0001');require(first==h.step('same_record_0001'),'IDEMPOTENT_RECEIPT')
                require(o.executor.attempts==1,'DUPLICATE_STEP_EXECUTED')
                b=o.executor.bindings[1]
                try:o.executor.bind_next(o,b['command'],b['permit'],b['external_proof']);raise AssertionError('PERMIT_REPLAY_ACCEPTED')
                except ValueError:pass
                o.request_stop()
            else:
                if name.startswith('unknown_'):h.raise_at=1 if name=='unknown_preparation' else 3
                h.run()
            expected={'custom_ranges':6,'same_coords_d3':3,'profile_d4_payload':3,'mixed_refinement':9,'legacy_refinement':11,'partial_stop':3,'unknown_fault':3,'unknown_preparation':1,'source_tamper':0,'raw_tamper':3,'duplicate_calls':1}[name]
            require(o.executor.attempts==expected,'EXPECTED_ATTEMPTS:'+name)
            stats=h.save()
            if name=='partial_stop':require(stats['conditions'][0]['per_target']['B_frame_correct']['state']=='PARTIAL','PARTIAL_NOT_MAJORITY')
            if name.startswith('unknown_') or name=='raw_tamper':require(stats['state']=='BLOCKED_UNKNOWN','UNKNOWN_NOT_GLOBAL_BLOCK')
            if name=='mixed_refinement':
                require(stats['conditions'][0]['per_target']['B_frame_correct']['state']=='MIXED','MIXED_LOST')
                require(not stats['confirmed_domain_complete'],'UNMEASURED_FINE_POINT_NOT_COMPLETE')
            if name in ('custom_ranges','same_coords_d3','profile_d4_payload'):groups.append(stats)
            before=h.counter
            for call in (lambda:h.step('terminal_new_key_0001'),lambda:o.executor.run_next()):
                try:call();raise AssertionError('TERMINAL_CONTINUATION_ACCEPTED')
                except (ValueError,RuntimeError):pass
            require(h.counter==before and o.cleanup['after']['lock_closed'] and all(o.cleanup['after']['handles_closed']),'TERMINAL_CLEANUP')
            result=dict(case=name,status=o.status(),source_scope='REGISTER_DRIVER_MODEL',new_physical_STARTs=0)
            (output/name/'result.json').write_bytes(raw(result)+b'\n');summaries.append(result);print(name,o.state,o.executor.attempts,flush=True)
        finally:h.close()
    descriptive=group_external(groups);require(len(descriptive['groups'])==6,'D_S_GROUPING_LOST')
    same_geometry=[g for g in descriptive['groups'] if g['condition']['fault']==dict(byte=24,bit=2,phase=7,width=3)]
    require(len(same_geometry)==2 and {g['condition']['receiver_B']['d'] for g in same_geometry}=={2,3},'SAME_GEOMETRY_DIFFERENT_D_NOT_SEPARATED')
    (output/'different_profiles_descriptive.json').write_bytes(raw(descriptive)+b'\n')
    (output/'summary.json').write_bytes(raw(summaries)+b'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();run(a.output)
