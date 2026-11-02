"""Isolated workers prevent mixing incompatible board driver namespaces."""
import argparse,json,sys,traceback,hashlib,time
from pathlib import Path
from types import SimpleNamespace
from common import ROOT,raw,write,require,verify,read_gate
sys.dont_write_bytecode=True
def bind(kind):
    root=ROOT/'vendor'/kind
    paths=[root]
    if kind=='edge':paths += [root/'backend',root/'backend/oss_runtime']
    if kind=='image':paths += [root/'functional',root/'runtime/host']
    sys.path[:0]=[str(p) for p in paths];return root
def image_bind():
    bind('image');sys.path.insert(0,str(ROOT/'vendor/image_execution'))
def event(output,**value):
    with (output/'events.jsonl').open('ab') as f:f.write(raw(value).replace(b'\n',b' ')+b'\n');f.flush()
def repair_session(session,out,progress,live=False):
    image_bind()
    from image_results import build_results
    plan=json.loads((session/'EXECUTOR/plan/plan.json').read_bytes())
    files=sorted((session/'EXECUTOR').glob('record_*/result/result.json'))
    results=[json.loads(p.read_bytes()) for p in files]
    require(results and [r['record_id'] for r in results]==list(range(1,len(results)+1)),'CONTIGUOUS_RESULTS_REQUIRED')
    require(len(results)<=65 and all(r['evidence_quality']=='VALID' for r in results),'VALID_IMAGE_RECORDS_REQUIRED')
    frozen=(session/'EXECUTOR/plan/source.bin').read_bytes()
    require(len(frozen)==16384 and hashlib.sha256(frozen).hexdigest()==plan['source_sha256'],'SOURCE_BINDING')
    e=SimpleNamespace(session=SimpleNamespace(root=session,local_epoch=plan['local_epoch']),root=session/'EXECUTOR',
        index=len(results),results=results,_frozen_config=(session/'EXECUTOR/plan/config.bin').read_bytes(),_frozen_source=frozen)
    progress(stage='REPAIR_RECEIVED_BYTES',completed_records=len(results))
    return build_results(e,out/'images',capture_origin='NEW_LIVE_CAPTURE_PENDING_SOURCE_REVIEW' if live else 'HISTORICAL_REAL_RAW_REPLAY')
def execute(action,request,out):
    progress=lambda **v:event(out,**v)
    if action=='validate_plan':
        if request['kind']=='scan':
            bind('edge');from custom_plan import validate_plan
            validate_plan(request['plan'])
        else:
            image_bind();from image_plan import validate
            validate(request['plan'])
        return dict(status='VALIDATED_PLAN',hardware_access=False,new_STARTs=0)
    if action=='approval_template':
        from live import approval_request
        c=request['live_config'];return approval_request(request['kind'],request['plan'],c['assets'],c['runs'])
    if action in ('scan_preview','ai_predict','ai_suggest','scan_replay'):
        bind('edge')
        if action=='scan_preview':
            from custom_plan import compile_plan
            r=request['request']
            if request.get('strategy')=='ai':
                from oss_portable import load_default,STRATEGY
                r=dict(r,edge_ai=dict(strategy=STRATEGY,model_file_sha256=load_default().file_sha256,max_extra_groups=request.get('max_extra_groups',2),allow_rule_fallback=True))
            return compile_plan(r)
        if action=='ai_predict':
            from oss_portable import load_default
            m=load_default();return dict(predictions=[m.predict(q) for q in request['queries']],model_file_sha256=m.file_sha256)
        if action=='ai_suggest':
            from custom_replay import reconstruct
            from custom_refine import suggest
            from learning_domain import digest
            evidence=reconstruct(request['session']);plan=evidence['plan']
            return suggest(plan,evidence['records'],evidence['statistics']['session'],plan['max_records']-len(evidence['records']),confirmed_domain_sha256=digest(plan['conditions']))
        from custom_replay import reconstruct
        progress(stage='VERIFY_RAW_SCAN_EVIDENCE');return reconstruct(request['session'])
    if action=='image_preview':
        image_bind();from image_plan import schedule
        return dict(status='ACCEPTED',plan=schedule(request),hardware_permission=False)
    if action=='image_repair':return repair_session(Path(request['session']),out,progress)
    if action=='ds_analysis':
        bind('ds');from workbench import run
        class Stop:
            def is_set(self):return (out/'STOP_REQUESTED').exists()
        result=run(request['session'],out/'analysis',policy=request.get('policy','reference_prefix'),
            max_bits=request.get('max_bits',0),max_framing=request.get('max_framing',0),
            stop_event=Stop(),progress=lambda current,total,item:progress(stage='ANALYZING',completed_records=current,max_records=total,item_state=item['state']))
        # Native page uses exactly the payload already exported by the reviewed renderer.
        import re
        html=(out/'analysis/report.html').read_text(encoding='utf-8')
        match=re.search(r'<script id="payload" type="application/json">([\s\S]*?)</script>',html)
        require(match is not None,'DS_VIEWER_PAYLOAD_REQUIRED')
        data=json.loads(match.group(1));require(len(data['items'])==64,'DS_VIEWER_EXPECTS64_ITEMS')
        write(out/'analysis/viewer_data.json',data)
        return result
    if action in ('live_scan','live_image'):
        from live import run
        return run(action,request,out,progress)
    raise ValueError('UNKNOWN_WORKER_ACTION')
def main():
    p=argparse.ArgumentParser();p.add_argument('action');p.add_argument('request');p.add_argument('output');a=p.parse_args()
    out=Path(a.output);request=json.loads(Path(a.request).read_bytes());started=time.monotonic()
    try:
        verify()
        with read_gate(request.get('session')):value=execute(a.action,request,out)
        write(out/'result.json',value);write(out/'receipt.json',dict(status='COMPLETE',action=a.action,seconds=time.monotonic()-started,hardware_access=a.action.startswith('live_')))
    except BaseException as e:
        if a.action in ('live_scan','live_image') and request.get('job_id')==out.name:
            try:
                from demo_authority import Authority
                authority=Authority.for_live(request['live_config']);task=authority.task(request['job_id'])
                if task and not task['terminal'] and not task['hardware_setup']:
                    write(out/'demo_accounting.json',authority.settle(request['job_id'],'SOFTWARE_REJECTED',True,repr(e)))
            except BaseException:pass
        write(out/'error.json',dict(error=type(e).__name__,message=str(e),traceback=traceback.format_exc(),automatic_retry=False))
        raise
if __name__=='__main__':main()
