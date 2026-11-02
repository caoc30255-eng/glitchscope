"""Read-only relocated raw reconstruction, never imports a model or PYNQ.

No saved summary label is used as the classification source. Stored result fields
are cross-checked against original samples/protocol/point count/waveform files.
"""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from custom_plan import validate_plan, typed_profile, raw, require
from custom_feedback import CustomFeedback
from custom_stats import aggregate
from learning_domain import digest
from controlled_trial_executor import TrialRequest
from ch1_control_session import audit_application_journal
import ch1_evidence_store as store


def reconstruct(session_root):
    root=Path(session_root).resolve();exroot=root/'EXECUTOR'
    source_session=json.loads((root/'CUSTOM_SCAN/scope/scope.json').read_bytes())['session']
    sealed=json.loads((exroot/'plan/plan.json').read_bytes());plan=sealed['domain'];validate_plan(plan)
    source=(exroot/'plan/source.bin').read_bytes();config=(exroot/'plan/config.bin').read_bytes()
    require(source==bytes.fromhex(plan['payload_hex'])*plan['item_total'],'RAW_SOURCE_DIFFERS_FROM_PLAN')
    epoch=sealed['local_epoch'];session=SimpleNamespace(root=root,local_epoch=epoch,source_session_name=source_session)
    parts=tuple(source[i:i+256] for i in range(0,len(source),256))
    from ch1_completion_ledger import _codec
    expected_config=_codec().encode_config(epoch,1,32,len(source)//32,len(source),len(parts),256,
        bytes.fromhex(store.sha(source)),[store.crc16(p) for p in parts])
    require(config==expected_config,'RAW_CONFIG_CAPACITY_OR_SOURCE_CHANGED')
    # Verify every committed original, including decisions, permits, failures and snapshots.
    inventory={}
    for f in sorted(root.rglob('*')):
        if f.is_file():inventory[f.relative_to(root).as_posix()]=dict(bytes=f.stat().st_size,sha256=store.sha(f.read_bytes()))
    for marker in root.rglob('committed.json'):
        for name,proof in json.loads(marker.read_bytes())['files'].items():
            path=(marker.parent/name).resolve();require(root in path.parents,'ORIGINAL_PATH_ESCAPE')
            data=path.read_bytes();expected=proof if isinstance(proof,str) else proof['sha256']
            require(store.sha(data)==expected,'BAD_COMMITTED_ORIGINAL:'+str(path.relative_to(root)))
            if isinstance(proof,dict):require(len(data)==proof['bytes'],'BAD_ORIGINAL_LENGTH')
    journals=[audit_application_journal(p) for p in root.rglob('application_*.jsonl')]
    require(journals,'APPLICATION_JOURNAL_REQUIRED')
    scope=json.loads((root/'CUSTOM_SCAN/scope/scope.json').read_bytes())
    origin=scope['origin'];require(origin in ('REGISTER_DRIVER_MODEL','PYNQ_HARDWARE_CANDIDATE'),'EVIDENCE_ORIGIN_REQUIRED')
    requests=[];results=[];commands=[];decisions=[];bindings=[]
    for f in sorted((exroot/'dynamic_bindings').glob('record_*/binding.json')):
        binding=json.loads(f.read_bytes());cmd=binding['command'];rid=cmd['record_id']
        require(rid==len(bindings)+1 and binding['record_id']==rid and cmd['epoch']==epoch and cmd['session']==source_session and cmd['plan_sha256']==store.sha((exroot/'plan/plan.json').read_bytes()),'BINDING_SEQUENCE_OR_PLAN_CHANGED')
        permit=binding['permit'];require(permit['commit_sha256']==digest({k:v for k,v in permit.items() if k!='commit_sha256'}) and permit['command_sha256']==digest(cmd) and permit['expected_completed_records']==rid-1 and permit['epoch']==epoch,'PERMIT_CHANGED')
        evidence={}
        for role in ('decision_source','permit_source'):
            ref=binding['external_proof'][role];path=(root/ref['path']).resolve();require(root in path.parents,'EXTERNAL_PROOF_ESCAPE')
            data=path.read_bytes();require(store.sha(data)==ref['sha256'],'EXTERNAL_PROOF_CHANGED');evidence[role]=json.loads(data)
        decision=evidence['decision_source'];require(decision['command']==cmd and evidence['permit_source']==dict(command=cmd,permit=permit),'DECISION_BINDING_CHANGED')
        if rid>=2:
            c=None if rid==2 else next(c for c in plan['conditions'] if c['condition_id']==cmd['point_id'])
            b=plan['receiver_B'];request=TrialRequest('replay_%d'%rid,b['d'],b['s'],None if c is None else typed_profile(c));requests.append(request)
            if c is not None:require(cmd['condition_sha256']==c['condition_sha256'] and cmd['fault']==c['fault'] and cmd['receiver_B']==b,'FULL_CONDITION_CHANGED')
        result=exroot/('record_%08x/result/result.json'%rid)
        if result.exists():results.append(json.loads(result.read_bytes()))
        commands.append(cmd);decisions.append(decision);bindings.append(binding)
    ex=SimpleNamespace(root=exroot,session=session,parts=parts,requests=requests,results=results,
                       _frozen_config=config,max_attempts=plan['max_records'])
    checker=CustomFeedback(ex);records=[];receipts=[];hardware_proofs=[];selections_seen={};selection_numeric_compatibility=[]
    trace=None
    if origin=='PYNQ_HARDWARE_CANDIDATE':
        from custom_hardware_audit import load_trace,record_audit
        trace=load_trace(root)
    for rid,result in enumerate(results,1):
        receipt=checker._feedback(rid);cmd=commands[rid-1]
        require(decisions[rid-1]['input_sha256']==digest(receipts),'DECISION_INPUT_PREFIX_CHANGED')
        receipts.append(receipt)
        if trace is not None:hardware_proofs.append(record_audit(root,rid,result,None if rid==1 else requests[rid-2].fault,trace))
        suffix='epoch_%08x_record_%08x'%(epoch,rid)
        directories=[exroot/('record_%08x'%rid),root/'CH0'/suffix,root/'CH1/main'/suffix,root/'admission'/suffix,root/'MPG1_SCAN'/('record_%08x'%rid),root/'TYPE3C'/suffix]
        if rid>=3:directories.append(root/'MARK'/suffix)
        refs=[dict(path=f.relative_to(root).as_posix(),bytes=f.stat().st_size,sha256=store.sha(f.read_bytes())) for directory in directories for f in sorted(directory.rglob('*')) if f.is_file()]
        selection_sha=decisions[rid-1]['selection_sha256']
        if selection_sha and selection_sha not in selections_seen:
            from custom_refine import suggest
            proposed=suggest(plan,records,source_session,plan['max_records']-len(records),confirmed_domain_sha256=digest(plan['conditions']))
            matches=[json.loads(f.read_bytes()) for f in (root/'CUSTOM_SCAN/selections').glob('*/selection.json') if json.loads(f.read_bytes()).get('selection_sha256')==selection_sha]
            from custom_selection_compat import compare_selection
            comparison=compare_selection(proposed,matches[0]) if len(matches)==1 else {'passed':False}
            require(len(matches)==1 and comparison['passed'] and proposed['condition_id']==cmd['point_id'],'SAVED_SELECTION_DOES_NOT_REPLAY')
            if comparison.get('numeric_differences'):selection_numeric_compatibility.append(dict(selection_sha256=selection_sha,**comparison))
            selections_seen[selection_sha]=dict(selection_sha256=selection_sha,condition_id=cmd['point_id'],required=proposed['required_records'],executed=0,valid=0,complete=False)
        if selection_sha:
            selections_seen[selection_sha]['executed']+=1;selections_seen[selection_sha]['valid']+=1
            require(selections_seen[selection_sha]['executed']<=selections_seen[selection_sha]['required'],'SELECTION_REPLAY_OVER_CONSUMED')
        records.append(dict(uid=digest(dict(session=source_session,identity=receipt['identity_hex'])),session=source_session,epoch=epoch,record_id=rid,
            kind=cmd['kind'],identity_hex=receipt['identity_hex'],trial_id=result['trial_id'],status='VALID',strict_retired=True,actual_READY_saved=True,
            condition_id=cmd['point_id'],condition_sha256=cmd['condition_sha256'],requested_receiver_B=cmd['receiver_B'],actual_receiver_B=receipt['actual_receiver_B'],
            selection_sha256=decisions[rid-1]['selection_sha256'],fault=cmd['fault'],payload_sha256=plan['payload_sha256'],route_mode=0,mode=plan['mode'],
            labels=dict(B_frame_correct=receipt['labels']['B_correct'],STM_payload_correct=receipt['labels']['STM_payload_correct'],STM_business_success=receipt['labels']['STM_success']),
            result_sha256=receipt['result_sha256'],evidence=refs))
    if len(bindings)>len(results):
        # A bound request does not prove START. An intent does reserve an attempt.
        rid=len(results)+1;intent=exroot/('record_%08x/intent/intent.json'%rid)
        if intent.exists():
            cmd=commands[rid-1];selection_sha=decisions[rid-1]['selection_sha256']
            if selection_sha:
                if selection_sha not in selections_seen:
                    from custom_refine import suggest
                    proposed=suggest(plan,records,source_session,plan['max_records']-len(records),confirmed_domain_sha256=digest(plan['conditions']))
                    matches=[json.loads(f.read_bytes()) for f in (root/'CUSTOM_SCAN/selections').glob('*/selection.json') if json.loads(f.read_bytes()).get('selection_sha256')==selection_sha]
                    from custom_selection_compat import compare_selection
                    comparison=compare_selection(proposed,matches[0]) if len(matches)==1 else {'passed':False}
                    require(len(matches)==1 and comparison['passed'] and proposed['condition_id']==cmd['point_id'],'UNKNOWN_SELECTION_DOES_NOT_REPLAY')
                    if comparison.get('numeric_differences'):selection_numeric_compatibility.append(dict(selection_sha256=selection_sha,**comparison))
                    selections_seen[selection_sha]=dict(selection_sha256=selection_sha,condition_id=cmd['point_id'],required=proposed['required_records'],executed=0,valid=0,complete=False)
                selections_seen[selection_sha]['executed']+=1;selections_seen[selection_sha]['unknown']=1
            records.append(dict(uid=digest(dict(session=source_session,unknown_record=rid)),session=source_session,epoch=epoch,record_id=rid,kind=cmd['kind'],
                identity_hex=None,selection_sha256=selection_sha,status='UNKNOWN',strict_retired=False,actual_READY_saved=False,condition_id=cmd['point_id'],condition_sha256=cmd['condition_sha256'],
                requested_receiver_B=cmd['receiver_B'],actual_receiver_B=dict(d=None,s=None,RX_profile_verified=False),fault=cmd['fault'],payload_sha256=plan['payload_sha256'],route_mode=0,mode=plan['mode'],labels={t:None for t in ('B_frame_correct','STM_payload_correct','STM_business_success')},
                evidence=[dict(path=intent.relative_to(root).as_posix(),**inventory[intent.relative_to(root).as_posix()])]))
    stats=aggregate(plan,records,source_session)
    for group in selections_seen.values():
        group['complete']=group['valid']==group['required']
        group['unexecuted']=group['required']-group['executed']
    stats['confirmation_groups']=list(selections_seen.values())
    return dict(status='PASS',origin=origin,hardware_acceptance=False,verified_feedback_receipts=receipts,selection_numeric_compatibility=selection_numeric_compatibility,raw_MMIO_transaction_binding_verified=(all(p['raw_MMIO_transaction_binding_verified'] for p in hardware_proofs) if hardware_proofs else None),plan=plan,records=records,statistics=stats,journals=journals,original_inventory=inventory,hardware_proofs=hardware_proofs,
                limits='Replay checks raw classifications and saved evidence, not a fresh live CSR read or timing measurement. Independent owner review remains required.')


def main():
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--session',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    out=Path(a.output);out.mkdir(parents=True,exist_ok=False)
    try:
        result=reconstruct(a.session)
        from custom_heatmaps import write_maps
        write_maps(out/'heatmaps',result['statistics'],result['origin'])
    except Exception as error:
        (out/'report.json').write_bytes(raw(dict(status='FAIL',error=repr(error),hardware_acceptance=False))+b'\n');raise
    (out/'report.json').write_bytes(raw(result)+b'\n')
    print('PASS raw reconstruction; origin:',result['origin'],'records:',len(result['records']))


if __name__=='__main__':main()
