"""Additional register scenarios, not FPGA runs. Fails on any unexpected result."""
import argparse
import json
from pathlib import Path
from custom_plan import compile_plan,raw,require
from custom_model import ModelHarness
from tests_backend import request
from learning_domain import CELLS
from custom_replay import reconstruct


def run(output):
    output=Path(output);output.mkdir(parents=True,exist_ok=False);results=[]
    cases=['multi1','multi4','multi255','multi256','multi_last_byte','disabled','bad_multi_ack','wrong_point_count',
           'preparation_failure_config','preparation_failure_control','confirmation_partial_stop','confirmation_unknown','old_epoch','start_input_conflict','full14','limited4']
    for name in cases:
        r=request(repeats=1,limit=3)
        if name.startswith('multi') or name in ('bad_multi_ack','wrong_point_count'):
            count={'multi1':1,'multi4':4,'multi255':255,'multi256':256,'multi_last_byte':1}.get(name,4)
            r['mode']='TYPE3C_CONTIGUOUS';r['fault']=dict(first_byte=275 if name=='multi_last_byte' else 20,count=count,bit=7)
            r['payload_hex']='ff'*256
        if name=='disabled':r['mode']='DISABLED';r['fault']['count']=0
        if name in ('confirmation_partial_stop','confirmation_unknown'):r=request(repeats=3,limit=9,refine=True);r['refinement']['confirmation_repeats']=3
        if name in ('full14','limited4'):
            r=request(3,-1,repeats=3,limit=44 if name=='full14' else 14)
            r['scan']['points']=[dict(phase=c['phase'],width=c['width']) for c in CELLS[:(14 if name=='full14' else 4)]]
            r['refinement']=dict(enabled=False,confirmation_repeats=3,candidates=[dict(phase=c['phase'],width=c['width']) for c in CELLS])
        compiled=compile_plan(r);require(compiled['status']=='ACCEPTED','TEST_PLAN_REJECTED')
        h=ModelHarness(compiled['plan'],output/name);o=h.owner
        try:
            if name.startswith('preparation_failure'):h.baseline_failure_at=1 if name.endswith('config') else 2
            if name=='bad_multi_ack':h.bad_multi_ack=True
            if name=='wrong_point_count':h.wrong_point_count=True
            if name=='confirmation_unknown':
                h.mixed_faults=True;h.run();proposal=o.next_suggestion();h.raise_at=6
                h.step('confirmation_unknown_0001',proposal)
                require(o.state=='BLOCKED_UNKNOWN' and o.status()['confirmation_groups'][0]['unknown']==1,'REFINEMENT_UNKNOWN_NOT_CHARGED')
            elif name=='confirmation_partial_stop':
                h.mixed_faults=True;h.run();require(o.state=='AWAITING_SELECTION','EXPECTED_SELECTION_WAIT')
                proposal=o.next_suggestion();h.step('partial_group_confirmation',proposal);o.request_stop()
                groups=o.status()['confirmation_groups'];require(len(groups)==1 and groups[0]==dict(selection_sha256=proposal['selection_sha256'],condition_id=proposal['condition_id'],required=3,executed=1,valid=1,unknown=0,cancelled=2,complete=False),'PARTIAL_CONFIRMATION_GROUP_HIDDEN')
            elif name=='old_epoch':
                h.s.local_epoch+=1
                try:o.start_once('old_epoch_start_0001');raise AssertionError('OLD_EPOCH_ACCEPTED')
                except ValueError:pass
                require(o.state=='BLOCKED_INPUT' and o.executor.attempts==0,'OLD_EPOCH_SIDE_EFFECT')
                h.s.local_epoch=o.epoch
            elif name=='start_input_conflict':
                o.start_once('same_start_key_0001')
                try:o.start_once('same_start_key_0001','changed_input');raise AssertionError('SAME_KEY_INPUT_CHANGE_ACCEPTED')
                except ValueError as error:require('IDEMPOTENCY_CONFLICT' in str(error),'WRONG_CONFLICT')
                o.request_stop();require(o.executor.attempts==0,'START_SHOULD_BE_SOFTWARE_ONLY')
            else:h.run()
            if name.startswith('preparation_failure'):require(o.state=='BLOCKED_UNKNOWN' and o.executor.attempts==h.baseline_failure_at,'PREPARATION_FAILURE_MUST_STOP')
            elif name in ('bad_multi_ack','wrong_point_count'):require(o.state=='BLOCKED_UNKNOWN' and o.executor.attempts==3 and len(o.receipts)==2,'BAD_MPG1_ORIGINAL_MUST_BLOCK')
            elif name not in ('confirmation_partial_stop','confirmation_unknown','old_epoch','start_input_conflict'):
                require(o.state=='STOPPED_PLAN_COMPLETE' and o.executor.attempts==compiled['plan']['required_records'],'EXPECTED_COMPLETE_PLAN')
            stats=h.save();status=o.status()
            if name=='limited4':require(sum(c['per_target']['B_frame_correct']['state']=='UNMEASURED' for c in stats['conditions'])==10,'MISSING_CELLS_FILLED')
            if name=='full14':require(len(stats['conditions'])==14 and all(c['per_target']['B_frame_correct']['valid']==3 for c in stats['conditions']),'FULL_14_NOT_COVERED')
            if name.startswith('multi') or name=='disabled':
                replay=reconstruct(output/name/'register_model_session')
                require(replay['statistics']['conditions'][0]['per_target']==stats['conditions'][0]['per_target'],'RELOCATED_RAW_REPLAY_DIFFERS')
                (output/name/'replay_report.json').write_bytes(raw(replay)+b'\n')
            before=o.executor.attempts
            for entry in (lambda:h.step('terminal_extra_step'),lambda:o.run('terminal_extra_run'),lambda:o.executor.run_next()):
                try:entry();raise AssertionError('TERMINAL_ENTRY_ALLOWED')
                except (ValueError,RuntimeError):pass
            require(o.executor.attempts==before,'TERMINAL_EXTRA_ATTEMPT')
            (output/name/'result.json').write_bytes(raw(status)+b'\n');results.append(dict(case=name,**status))
            print(name,status['state'],status['attempts'],flush=True)
        except BaseException:
            if not (output/name/'export').exists():h.save()
            raise
        finally:h.close()
    (output/'summary.json').write_bytes(raw(results)+b'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);run(p.parse_args().output)
