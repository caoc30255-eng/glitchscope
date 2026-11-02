"""Complete read-only analysis workflow; hardware execution is deliberately absent."""
from pathlib import Path
import json,hashlib,time,csv,copy,sys,platform,os,uuid
from contextlib import contextmanager
from b_receiver import PROFILES,require
from image64 import summarize,evaluate_window,verify_cycle_model
from phase_envelope import evaluate
from window_audit import load_record,analyze
from evidence_input import open_session,read_item,verify_stable,sha

ROOT=Path(__file__).resolve().parent
VERSION='GLITCHSCOPE_DS_WORKBENCH_V0_2'
POLICIES=('reference_prefix','capture_only')

def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    require(not path.exists(),'OUTPUT_ALREADY_EXISTS:'+str(path))
    pending=path.with_name(path.name+'.'+uuid.uuid4().hex+'.partial')
    with pending.open('x',encoding='utf-8') as f:
        json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n');f.flush()
    pending.rename(path)

def verify_package(root=ROOT):
    root=Path(root).resolve()
    manifest=json.loads((root/'sha256_manifest.json').read_bytes())
    for n,proof in manifest.items():
        p=(root/n).resolve();require(root in p.parents,'PACKAGE_PATH_ESCAPE')
        raw=p.read_bytes();require(len(raw)==proof['bytes'] and sha(raw)==proof['sha256'],'PACKAGE_CHANGED:'+n)
    notebook=json.loads((root/'ds_analysis.ipynb').read_bytes())
    actual=[''.join(c['source']) for c in notebook['cells'] if c['cell_type']=='code' and ''.join(c['source']).strip()]
    expected=json.loads((root/'notebook_cells.json').read_bytes())
    require(actual==expected,'NOTEBOOK_CODE_CHANGED_OUTPUTS_ARE_ALLOWED')
    verify_cycle_model();return len(manifest)

@contextmanager
def source_gate(root):
    """POSIX shared file lock blocks concurrent exclusive HIL initialization.
    Existing file opened read-only; no lock file is created or reset.
    """
    p=Path(root).parent/'exclusive.lock';f=None
    try:
        if sys.platform.startswith('linux') and p.is_file():
            import fcntl
            f=p.open('rb');fcntl.flock(f,fcntl.LOCK_SH|fcntl.LOCK_NB)
            yield 'EXISTING_POSIX_SHARED_LOCK_HELD_READ_ONLY'
        else:yield 'OFFLINE_FILE_COPY_NO_POSIX_GATE'
    finally:
        if f is not None:f.close()

def placeholder(root,rid,profile,state,reason):
    return dict(session=Path(root).name,record_id=rid,actual_profile=profile,state=state,reason=reason,
        profiles=[],retained_phases=[],current_target_matches_all_retained_phases=False,
        actual_local_bit_errors=None,hardware_access=False,new_STARTs=0)

def compact_window(w):
    keys=('session','record_id','actual_profile','state','retained_phases','reason',
          'actual_local_bit_errors','current_target_matches_all_retained_phases')
    out={k:w.get(k) for k in keys};out['profiles']=[]
    for p in w.get('profiles',[]):
        out['profiles'].append(dict(d=p['d'],s=p['s'],compared_bits=p['compared_bits'],scenarios=[
            {k:t[k] for k in ('phase','aligned','bit_errors','framing_errors') if k in t} for t in p['scenarios']]))
    return out

def add_regions(summary,max_bits,max_framing,blocked=False):
    require(type(max_bits) is int and max_bits>=0 and type(max_framing) is int and max_framing>=0,'NONNEGATIVE_INTEGER_THRESHOLDS')
    summary['acceptance_thresholds']=dict(max_local_bit_errors=max_bits,max_local_framing_errors=max_framing)
    summary['threshold_candidate_region']=[dict(d=r['d'],s=r['s']) for r in summary['profiles'] if r['eligible_for_global_software_ranking'] and
        r['bit_errors_upper_bound']<=max_bits and r['framing_errors_upper_bound']<=max_framing]
    summary['hardware_verified_region']=[]
    if blocked:
        summary['state']='NO_RECOMMENDATION_BLOCKED'
        summary['local_reference']['state']='BLOCKED_EVIDENCE';summary['local_reference']['candidate_set']=[]
        summary['global_minimax_candidate_set']=[];summary['threshold_candidate_region']=[];summary['robust_zero_candidate_set']=[]
        for r in summary['profiles']:r['eligible_for_global_software_ranking']=False;r['robust_zero_on_all64_local_windows']=False
    return summary

def aggregate_measured(items):
    result={}
    for lane in ('A','B'):
        rows=[i['metrics'][lane] for i in items if i.get('metrics')]
        result[lane]=dict(retired_items_with_bytes=len(rows),frame_correct=sum(r['frame_correct'] for r in rows),
            equal_length_items=sum(r['positional_frame_bit_errors'] is not None for r in rows),
            positional_frame_bit_errors=sum(r['positional_frame_bit_errors'] or 0 for r in rows),
            payload_comparable_items=sum(r['payload_comparison_valid'] for r in rows),
            payload_bit_errors=sum(r['payload_bit_errors'] or 0 for r in rows),
            flagged_bytes=sum(r['flagged_bytes'] for r in rows),
            scope='Actual saved receiver bytes at one actual profile; no candidate full-image prediction')
    return result

def run(session,output,policy='reference_prefix',max_bits=0,max_framing=0,progress=None,stop_event=None):
    verify_package();require(policy in POLICIES,'ALIGNMENT_POLICY')
    package_sha=sha((ROOT/'sha256_manifest.json').read_bytes())
    code_snapshot={p.name:sha(p.read_bytes()) for p in sorted(ROOT.glob('*.py'))}
    root=Path(session).resolve();out=Path(output).resolve()
    require(out!=root and root not in out.parents and out not in root.parents,'OUTPUT_OVERLAPS_INPUT')
    require(out!=ROOT and ROOT not in out.parents and out not in ROOT.parents,'OUTPUT_OVERLAPS_PACKAGE')
    require(type(max_bits) is int and max_bits>=0 and type(max_framing) is int and max_framing>=0,'THRESHOLDS')
    out.mkdir(parents=True,exist_ok=False)
    requested=dict(schema=VERSION,session_path=str(root),alignment_policy=policy,max_local_bit_errors=max_bits,
        max_local_framing_errors=max_framing,one_ds_for_all_ITEMS=True,hardware_access=False,new_STARTs=0)
    write(out/'request.json',requested)
    started=time.monotonic();windows=[];items=[];errors=[];blocked=False;cancelled=False
    header=None;gate_scope='NOT_ACQUIRED';profile=dict(d=3,s=-1)
    try:
        with source_gate(root) as gate_scope:
            header=open_session(root);profile=header['actual_profile']
            for rid in range(2,66):
                if blocked or cancelled or (stop_event is not None and stop_event.is_set()):
                    cancelled=cancelled or not blocked
                    w=placeholder(root,rid,profile,'NOT_ANALYZED_AFTER_INTEGRITY_FAILURE' if blocked else 'ANALYSIS_CANCELLED','No synthetic measurement inserted')
                    items.append(dict(record_id=rid,item_index=rid-2,state=w['state'],reason=w['reason'],metrics=None));windows.append(w);continue
                raw_record=None;baseline={};received=None
                try:
                    received=read_item(header,rid)
                    if received['state']=='HAS_WINDOW':
                        raw_record=load_record(root,rid)
                        if policy=='reference_prefix':w,baseline=evaluate_window(raw_record)
                        else:
                            r=copy.deepcopy(raw_record);p=r['context']['arm']['profile'];p['byte']=p.get('first_byte',p.get('byte'))
                            w,baseline=evaluate(r)
                            w.update(actual_profile=baseline['actual_profile'],actual_local_bit_errors=baseline.get('actual_compared_bit_errors'),
                                conditional_on_unmeasured_ideal_prefix=False,alignment_version='CAPTURE_ONLY_COLD_START')
                        header['inventory'].update(raw_record['input_files'])
                        w['stimulus']=received['stimulus']
                    else:w=placeholder(root,rid,profile,received['state'],received['reason'])
                except KeyboardInterrupt:
                    cancelled=True;w=placeholder(root,rid,profile,'ANALYSIS_CANCELLED','Operator interrupted software analysis')
                except Exception as error:
                    blocked=True;errors.append(dict(record_id=rid,error_type=type(error).__name__,reason=str(error)))
                    w=placeholder(root,rid,profile,'INTEGRITY_ERROR',str(error))
                item=dict(record_id=rid,item_index=rid-2,state=w['state'],reason=w.get('reason'),
                    stimulus=header['plan']['requests'][rid-2]['fault'],metrics=received.get('metrics') if received else None,
                    phase_count=len(w.get('retained_phases',[])),actual_target_all_phases=w.get('current_target_matches_all_retained_phases',False))
                items.append(item);windows.append(compact_window(w))
                folder=out/'items'/('item_%02d'%(rid-2));write(folder/'envelope.json',w)
                write(folder/'alignment.json',{k:v for k,v in baseline.items() if k not in ('profiles','input_files')})
                from report_export import viewer_item
                write(folder/'viewer.json',viewer_item(item,w,baseline,raw_record))
                if progress:progress(rid-1,64,copy.deepcopy(item))
                else:print('%02d/64 %s'%(rid-1,w['state']),flush=True)
            verify_stable(header)
            require(sha((ROOT/'sha256_manifest.json').read_bytes())==package_sha,'PACKAGE_MANIFEST_CHANGED_DURING_ANALYSIS')
            verify_package()
    except KeyboardInterrupt:
        cancelled=True;errors.append(dict(reason='Operator interrupted input verification'))
    except Exception as error:
        blocked=True;errors.append(dict(error_type=type(error).__name__,reason=str(error)))
    # Missing input or a partial software run never becomes a full recommendation.
    while len(windows)<64:
        rid=len(windows)+2;w=placeholder(root,rid,profile,'NOT_ANALYZED','Input unavailable or analysis interrupted')
        windows.append(w);items.append(dict(record_id=rid,item_index=rid-2,state=w['state'],metrics=None))
    summary=summarize(windows)
    add_regions(summary,max_bits,max_framing,blocked or cancelled)
    summary.update(schema=VERSION,job_state='BLOCKED_INTEGRITY' if blocked else 'CANCELLED' if cancelled else
        'COMPLETE' if summary['global_minimax_candidate_set'] else 'COMPLETE_WITH_EVIDENCE_GAPS',
        alignment_policy=policy,unmeasured_prefix_assumption=policy=='reference_prefix',
        session=root.name,source_sha256=header['config']['source_sha256'] if header else None,
        actual_profile=profile if header else None,actual_full_frame_observations=aggregate_measured(items),
        provided_ITEMS=sum(bool(i.get('metrics')) for i in items),
        complete64=not blocked and not cancelled and all(w['state']=='LOCAL_ENVELOPE_AVAILABLE' for w in windows),
        stimulus_origin='SAVED_PS_RANDOM_PLAN' if header and header['schedule'] else 'SAVED_EXECUTOR_PLAN',
        random_seed=header['schedule'].get('seed') if header and header['schedule'] else None,
        actual_local_bit_errors_from_saved_bytes=sum(w.get('actual_local_bit_errors') or 0 for w in windows),
        current_target_all_phase_matches=sum(bool(w.get('current_target_matches_all_retained_phases')) for w in windows),
        items=items,errors=errors,input_gate=gate_scope,elapsed_seconds=time.monotonic()-started,
        package_manifest_sha256=package_sha,
        python=sys.version,machine=platform.machine(),analysis_only=True,
        evidence_audit_scope='Committed plan/config/CH0/MARK/result/admission subset; not a new full lifecycle audit',
        candidate_full_frame_prediction_available=False,hardware_verified_recommendation=False)
    write(out/'summary.json',summary)
    write(out/'input_manifest.json',header['inventory'] if header else {})
    write(out/'analysis_code.json',code_snapshot)
    with (out/'profiles.csv').open('x',encoding='utf-8-sig',newline='') as f:
        label=root.name
        if label[:1] in ('=','+','-','@'):label="'"+label
        context=dict(session=label,source_sha256=summary['source_sha256'],alignment_policy=policy,job_state=summary['job_state'])
        writer=csv.DictWriter(f,fieldnames=list(context)+list(summary['profiles'][0]));writer.writeheader()
        writer.writerows(dict(context,**row) for row in summary['profiles'])
    from report_export import render,seal_output
    render(out);seal_output(out)
    print('REPORT '+str(out/'report.html'),flush=True)
    return summary

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--session',required=True);p.add_argument('--output',required=True)
    p.add_argument('--policy',choices=POLICIES,default='reference_prefix');p.add_argument('--max-bit-errors',type=int,default=0);p.add_argument('--max-framing-errors',type=int,default=0)
    a=p.parse_args();result=run(a.session,a.output,a.policy,a.max_bit_errors,a.max_framing_errors)
    raise SystemExit(2 if result['job_state']=='BLOCKED_INTEGRITY' else 3 if result['job_state']=='CANCELLED' else 0)
