"""One global d/s candidate set for64 archived ITEM windows, offline only.

Source-assisted warmup reconstructs only the prefix BEFORE sample zero and the
first scheduled inversion; it is an explicit ideal-prefix assumption, not new
measured data. Source values never choose NCO phase by matching target answers.
"""
import copy,json,hashlib,statistics,collections,time,csv
from pathlib import Path
from b_receiver import PROFILES,replay,require
from window_audit import analyze,load_record,verify_directory
from phase_envelope import evaluate

def verify_cycle_model():
    folder=Path(__file__).resolve().parent
    receipt=json.loads((folder/'rtl_cosim_receipt.json').read_bytes())
    require(receipt['status']=='PASS_USER_EXECUTED_RTL_COSIM_LOG_AND_INPUT_REVIEW' and receipt['cases']==1125,'REVIEWED_CYCLE_MODEL_RECEIPT_REQUIRED')
    require(hashlib.sha256((folder/'b_receiver.py').read_bytes()).hexdigest()==receipt['model_sha256'],'FROZEN_CYCLE_MODEL_CHANGED')
    return receipt

def warm_analyze(record):
    r=copy.deepcopy(record);profile=r['context']['arm']['profile']
    target=profile.get('first_byte',profile.get('byte'))
    require(type(target) is int and type(profile['bit']) is int,'TARGET_METADATA_REQUIRED')
    if 'first_byte' in profile:
        require(type(profile['count']) is int and 1<=profile['count']<=256,'NONZERO_CONTIGUOUS_PROFILE_REQUIRED')
        require(20<=target and target+profile['count']<=len(r['source'])-2,'PROFILE_OUTSIDE_PAYLOAD')
    profile['byte']=target  # Derived first-point alias; no original file is modified.
    bit=profile['bit'];levels=r['levels']
    require(0<=bit<=7,'TARGET_BIT')
    lo,hi=2048-(bit+2)*100-2,2048-(bit+1)*100+2
    anchors=[i for i in range(max(1,lo),min(len(levels),hi+1)) if levels[i-1] and not levels[i]]
    # Preserve the original explicit refusal if the edge is not unique.
    if len(anchors)!=1:return analyze(r)
    a=r['lanes']['a']
    if len(a)!=len(r['source']):return analyze(r)
    period=int(statistics.median(a[i+1]['tick']-a[i]['tick'] for i in range(len(a)-1)))
    if not 1000<=period<=1100:return analyze(r)
    anchor=anchors[0];pad=3*period-anchor
    require(target>=3 and pad>0,'THREE_PRIOR_SOURCE_BYTES_REQUIRED')
    prefix=[]
    for sample in range(-pad,0):
        j=target+(sample-anchor)//period;offset=(sample-anchor)%period
        require(0<=j<target,'PREFIX_MUST_PRECEDE_FIRST_FAULT_BYTE')
        prefix.append(0 if offset<100 else ((r['source'][j]>>((offset-100)//100))&1) if offset<900 else 1)
    def decoder(actual,d,s,phase=0,keep_votes=True):
        require(actual==levels,'MEASURED_WINDOW_CHANGED')
        frames=replay(prefix+actual,d,s,(phase-4*pad)%25,keep_votes)
        for f in frames:
            for key in ('start_index','stop_index','valid_index'):f[key]-=pad
            for vote in f['votes']:vote['indices']=[x-pad for x in vote['indices']]
        return frames
    out=analyze(r,decoder=decoder)
    out['warmup']=dict(prefix_samples=pad,prior_character_starts=3,byte_period_clocks=period,
        reconstructed_prefix_measured=False,prefix_before_first_scheduled_fault=True,
        prefix_sha256=hashlib.sha256(bytes(prefix)).hexdigest(),
        assumption='Unobserved prefix follows source UART encoding with100 clocks/bit and measured median character period',
        prefix_used_for_receiver_state_only=True,prefix_in_scoring=False,
        target_value_used_to_choose_phase=False)
    out['model_validation']='FROZEN_RTL_COSIM_1125_CASE_MODEL; NEW_REFERENCE_PREFIX_ALIGNMENT_SOFTWARE_CHECKS_ONLY'
    return out

def evaluate_window(record):
    verify_cycle_model()
    report,baseline=evaluate(record,analyzer=warm_analyze)
    report['warmup']=baseline.get('warmup')
    report['alignment_version']='REFERENCE_PREFIX_WARMUP_V0_1'
    report['conditional_on_unmeasured_ideal_prefix']=bool(baseline.get('warmup'))
    report['target_byte']=baseline.get('target_byte')
    report['actual_profile']=baseline['actual_profile']
    report['actual_local_bit_errors']=baseline.get('actual_compared_bit_errors')
    # Historical output text must not claim the extended alignment was RTL tested.
    report['cycle_model_RTL_cosim_previously_passed']=True
    report['extended_alignment_hardware_accepted']=False
    return report,baseline

def local_reference(windows,expected=64):
    """Rank one uniform d/s on a common, explicitly enumerated observed subset.

    Every compared profile uses the same windows and bit count. Missing windows
    remain missing. Integrity failures/model contradictions never yield advice.
    """
    forbidden={'INTEGRITY_ERROR','NOT_ANALYZED_AFTER_INTEGRITY_FAILURE','MODEL_CONTRADICTED',
               'UNKNOWN_OR_UNRETIRED','ANALYSIS_CANCELLED','NOT_ANALYZED'}
    common=[];excluded=[]
    for w in windows:
        reason=w['state']
        if reason=='LOCAL_ENVELOPE_AVAILABLE':
            by={(p['d'],p['s']):p for p in w['profiles']}
            if set(by)==set(PROFILES) and all(p['scenarios'] and all(t.get('aligned') for t in p['scenarios']) for p in by.values()) and len({p['compared_bits'] for p in by.values()})==1 and all(p['compared_bits']>0 for p in by.values()):
                common.append(w);continue
            reason='NO_COMMON14_ALIGNED_BIT_COVERAGE'
        excluded.append(dict(record_id=w['record_id'],item_index=w['record_id']-2,reason=reason))
    rows=[]
    for d,s in PROFILES:
        bit_lo=bit_hi=frame_lo=frame_hi=bits=0
        for w in common:
            p=next(p for p in w['profiles'] if (p['d'],p['s'])==(d,s))
            bit_lo+=min(t['bit_errors'] for t in p['scenarios']);bit_hi+=max(t['bit_errors'] for t in p['scenarios'])
            frame_lo+=min(t['framing_errors'] for t in p['scenarios']);frame_hi+=max(t['framing_errors'] for t in p['scenarios'])
            bits+=p['compared_bits']
        rows.append(dict(d=d,s=s,evaluated_windows=len(common),compared_local_bits=bits,
                         bit_errors_lower_bound=bit_lo,bit_errors_upper_bound=bit_hi,
                         framing_errors_lower_bound=frame_lo,framing_errors_upper_bound=frame_hi))
    blocked=any(w['state'] in forbidden for w in windows)
    available=bool(common) and not blocked
    best=min((p['framing_errors_upper_bound'],p['bit_errors_upper_bound']) for p in rows) if available else None
    tied=[dict(d=p['d'],s=p['s']) for p in rows if available and (p['framing_errors_upper_bound'],p['bit_errors_upper_bound'])==best]
    present={w['record_id'] for w in windows}
    excluded.extend(dict(record_id=i,item_index=i-2,reason='MISSING_ITEM_WINDOW') for i in range(2,66) if i not in present)
    return dict(state='BLOCKED_EVIDENCE' if blocked else 'AVAILABLE' if available else 'NO_COMMON_USABLE_WINDOWS',
                candidate_set=tied,covered_windows=len(common),expected_windows=expected,
                coverage_fraction=len(common)/expected,included_record_ids=[w['record_id'] for w in common],
                excluded_items=sorted(excluded,key=lambda x:x['record_id']),profiles=rows,
                ranking_rule='On identical common windows: minimize summed worst-case local framing errors, then local bit errors; retain ties',
                same_profile_for_all_evaluated_ITEMS=True,per_ITEM_ds_selection_allowed=False,
                full64_recommendation=False,full_image_optimal_ds_proven=False,hardware_verified=False,
                covers_unmeasured_items=False,reference_only=True)


def summarize(windows,expected=64):
    require(type(expected) is int and expected==64,'EXACT64_REQUIRED')
    require(len({w['record_id'] for w in windows})==len(windows),'DUPLICATE_ITEM_WINDOW')
    require(len({w['session'] for w in windows})<=1,'CROSS_SESSION_POOLING_FORBIDDEN')
    require(len({(w['actual_profile']['d'],w['actual_profile']['s']) for w in windows})<=1,'ACTUAL_TRANSMISSION_MUST_USE_ONE_GLOBAL_DS')
    for w in windows:
        if w['state']=='LOCAL_ENVELOPE_AVAILABLE':
            require(len(w['profiles'])==14 and {(p['d'],p['s']) for p in w['profiles']}==set(PROFILES),'COMPLETE_UNIQUE14_PROFILE_DOMAIN_REQUIRED')
    complete=len(windows)==64 and {w['record_id'] for w in windows}==set(range(2,66))
    usable=[w for w in windows if w['state']=='LOCAL_ENVELOPE_AVAILABLE']
    rows=[]
    for d,s in PROFILES:
        be_lo=be_hi=fe_lo=fe_hi=bits=0;good=0;unresolved=0
        for w in windows:
            row=next((r for r in w.get('profiles',[]) if (r['d'],r['s'])==(d,s)),None)
            if w['state']!='LOCAL_ENVELOPE_AVAILABLE' or row is None:
                unresolved+=1;continue
            scenarios=row['scenarios']
            if not scenarios or not all(t.get('aligned') for t in scenarios):unresolved+=1;continue
            good+=1;bits+=row['compared_bits']
            be_lo+=min(t['bit_errors'] for t in scenarios);be_hi+=max(t['bit_errors'] for t in scenarios)
            fe_lo+=min(t['framing_errors'] for t in scenarios);fe_hi+=max(t['framing_errors'] for t in scenarios)
        eligible=complete and unresolved==0 and good==64
        rows.append(dict(d=d,s=s,evaluated_windows=good,unresolved_windows=unresolved,compared_local_bits=bits,
            bit_errors_lower_bound=be_lo,bit_errors_upper_bound=be_hi,
            framing_errors_lower_bound=fe_lo,framing_errors_upper_bound=fe_hi,
            eligible_for_global_software_ranking=eligible,
            robust_zero_on_all64_local_windows=eligible and be_hi==fe_hi==0,
            scope='PER_WINDOW_PHASE_EXTREMES_SUM_CONSERVATIVE_BOUNDS_NOT_JOINTLY_ATTAINABLE_EXTREMA'))
    eligible=[r for r in rows if r['eligible_for_global_software_ranking']]
    best=min(((r['framing_errors_upper_bound'],r['bit_errors_upper_bound']) for r in eligible),default=None)
    tied=[dict(d=r['d'],s=r['s']) for r in eligible if (r['framing_errors_upper_bound'],r['bit_errors_upper_bound'])==best]
    partial=local_reference(windows,expected)
    for row,local_row in zip(rows,partial['profiles']):
        row.update(local_reference_windows=local_row['evaluated_windows'],local_reference_bit_errors_upper_bound=local_row['bit_errors_upper_bound'],local_reference_framing_errors_upper_bound=local_row['framing_errors_upper_bound'])
    return dict(schema='IMAGE64_GLOBAL_DS_LOCAL_WINDOW_REVIEW_V0_1',
        state='GLOBAL_SOFTWARE_CANDIDATES_AVAILABLE' if tied else 'INSUFFICIENT_COMPLETE64_ALIGNED_EVIDENCE',
        expected_ITEMS=64,provided_ITEMS=len(windows),usable_windows=len(usable),complete64=complete,
        one_ds_for_all_ITEMS=True,per_ITEM_ds_selection_allowed=False,
        profiles=rows,global_minimax_candidate_set=tied,local_reference=partial,
        robust_zero_candidate_set=[dict(d=r['d'],s=r['s']) for r in eligible if r['robust_zero_on_all64_local_windows']],
        ranking_rule='Predeclared: first minimize summed worst-case local framing errors, then summed worst-case local bit errors; retain ties',
        ranking_uses_source_reference=True,phase_fitting_uses_held_out_target_value=False,
        initial_phase_not_forced_unique=True,unmeasured_prefix_assumption=True,
        full_ITEM_BER_evaluated=False,full_image_optimal_ds_proven=False,
        hardware_verified_recommendation=False,hardware_access=False,new_STARTs=0,AI_used=False)

def run(session,output):
    verify_cycle_model()
    root=Path(session).resolve();out=Path(output).resolve()
    require(root!=out and root not in out.parents,'OUTPUT_MUST_NOT_MODIFY_EVIDENCE')
    package=Path(__file__).resolve().parent
    require(out!=package and package not in out.parents,'OUTPUT_OUTSIDE_PACKAGE_REQUIRED')
    out.mkdir(parents=True,exist_ok=False)
    verify_directory(root/'EXECUTOR/plan')
    source=(root/'EXECUTOR/plan/source.bin').read_bytes()
    require(len(source)==64*256,'EXACT64_PAYLOAD_BLOCKS_REQUIRED')
    plan=json.loads((root/'EXECUTOR/plan/plan.json').read_bytes())
    require(hashlib.sha256(source).hexdigest()==plan['source_sha256'],'IMAGE_SOURCE_HASH_DIFFERS_FROM_PLAN')
    windows=[];started=time.monotonic();all_inputs={}
    for rid in range(2,66):
        record=load_record(root,rid)
        # Actual ITEM payload must correspond to this ordered image block.
        require(record['source'][20:-2]==source[(rid-2)*256:(rid-1)*256],'ITEM_SOURCE_ORDER_CHANGED')
        report,baseline=evaluate_window(record)
        report['stimulus']=record['context']['arm']['profile']
        dest=out/('item_%02d'%(rid-2));dest.mkdir()
        (dest/'envelope.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        (dest/'alignment.json').write_text(json.dumps(baseline,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        all_inputs.update(record['input_files']);windows.append(report)
        print('%02d/64 record%d %s retained_phases=%d'%(rid-1,rid,report['state'],len(report['retained_phases'])),flush=True)
    result=summarize(windows)
    result.update(session=root.name,source_sha256=hashlib.sha256(source).hexdigest(),
        elapsed_seconds=time.monotonic()-started,window_states=dict(collections.Counter(w['state'] for w in windows)),
        actual_B_local_bit_errors_from_saved_bytes=sum(w['actual_local_bit_errors'] for w in windows if w['actual_local_bit_errors'] is not None),
        windows_current_target_matches_all_retained_phases=sum(w['current_target_matches_all_retained_phases'] for w in windows),
        actual_B_profiles=sorted({(w['actual_profile']['d'],w['actual_profile']['s']) for w in windows}),
        input_files=all_inputs,input_scope='Hash-checked committed result/CH0/MARK/intent/admission subset; not a new full lifecycle audit',
        model_sha256=hashlib.sha256((package/'b_receiver.py').read_bytes()).hexdigest())
    (out/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    with (out/'global_profiles.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(result['profiles'][0]));w.writeheader();w.writerows(result['profiles'])
    print(json.dumps({k:v for k,v in result.items() if k not in ('profiles','input_files')},ensure_ascii=False,indent=2),flush=True)
    return result

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--session',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();run(a.session,a.output)
