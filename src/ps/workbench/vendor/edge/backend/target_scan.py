"""Stages are separate: software, preview, seal, approval-template, preflight, interactive.
Default is environment only. No Run All hardware operation is provided.
"""
import argparse
import json
import sys
from pathlib import Path


def load(path): return json.loads(Path(path).read_bytes())


def save(path, value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8') as f:
        json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage',nargs='?',default='environment',choices=['environment','software','preview','seal','approval-template','preflight','interactive'])
    parser.add_argument('--input');parser.add_argument('--output');parser.add_argument('--assets');parser.add_argument('--runs');parser.add_argument('--approval')
    args=parser.parse_args()
    from custom_real import environment
    if args.stage=='environment':print(json.dumps(environment(),indent=2));return 0
    if args.stage=='software':
        from target_software_smoke import run
        return run(args.output)
    if not args.input:parser.error('--input required')
    if args.output and Path(args.output).exists():raise FileExistsError(args.output)
    from custom_backend import preview,seal
    compiled=preview(load(args.input))
    if args.stage=='preview':
        save(args.output,compiled);return 0 if compiled['status']=='ACCEPTED' else 2
    if compiled['status']!='ACCEPTED':raise ValueError(compiled)
    plan=compiled['plan']
    if args.stage=='seal':print(json.dumps(seal(plan,args.output)));return 0
    if not args.assets or not args.runs:parser.error('--assets and --runs required')
    assets=load(args.assets)
    if args.stage=='approval-template':
        from custom_real import approval_template
        save(args.output,approval_template(plan,assets,args.runs));return 0
    if not args.approval:parser.error('--approval required; supplied templates approve nothing')
    if args.stage=='preflight':
        from custom_real import local_preflight
        try:report=dict(status='PASS',report=local_preflight(plan,assets,args.runs,args.approval))
        except Exception as error:
            save(args.output,dict(status='FAIL',error=repr(error),no_retry=True));raise
        save(args.output,report);return 0
    # No service exists until the human explicitly requests this initialization stage.
    print('Initialization writes namespace/epoch and HELLO; starts native RT receiver. No Overlay/reset. Physical records still require each STEP.')
    if input('Type INITIALIZE '+plan['sha256'][:12]+': ').strip()!='INITIALIZE '+plan['sha256'][:12]:return 2
    from custom_real import RealHarness
    h=RealHarness(plan,assets,args.runs,args.approval);api=h.backend()
    try:
        # Owner start is software-only; no CONFIG/ITEM is sent by start_once.
        api.start_once('operator_start_'+plan['sha256'][:16])
        while api.status()['state'] in ('RUNNING','AWAITING_SELECTION'):
            state=api.status();print(json.dumps(state,ensure_ascii=False))
            number=state['attempts']+1
            command=input('STEP %d / SUGGEST / STOP: '%number).strip()
            if command=='STOP':api.stop();break
            if command=='SUGGEST':
                proposal=api.next_suggestion();print(json.dumps(proposal,ensure_ascii=False,indent=2))
                if state['state']=='AWAITING_SELECTION' and proposal['action']=='SELECT':
                    if input('CONFIRM '+proposal['selection_sha256']+': ').strip()=='CONFIRM '+proposal['selection_sha256']:
                        api.step('operator_record_%08d'%number,proposal)
                continue
            if command=='STEP %d'%number:api.step('operator_record_%08d'%number)
        api.export(h.session.root/'EXPORT')
        print('Return the complete session, namespace_allocations.jsonl and trial_registry; retain failures. No retry/reset.')
        return 2 if api.status()['state'].startswith('BLOCKED') else 0
    finally:
        h.close()
        if h.owner and not (h.session.root/'EXPORT').exists():api.export(h.session.root/'EXPORT')


if __name__=='__main__':sys.exit(main())
