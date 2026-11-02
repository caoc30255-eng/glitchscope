"""Local software CLI; all hardware execution requires a separate reviewed plan."""
from pathlib import Path
import sys,json,argparse
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT/'backend'))
from edge_api import EdgeAI,example_request
from custom_ai_core import query,canonical

def save(value,path):
    if path:
        path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as f:f.write(canonical(value)+b'\n')
    visible=value
    if path and type(value) is dict and 'plan' in value:
        plan=value['plan'];visible=dict(status=value['status'],output=str(path),errors=value.get('errors'),
            plan_sha256=plan.get('sha256') if plan else None,max_records=plan.get('max_records') if plan else None,
            required_coarse_records=plan.get('required_records') if plan else None,hardware_permission=False)
    print(json.dumps(visible,ensure_ascii=False,indent=2))

def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
    q=sub.add_parser('predict');q.add_argument('--query');q.add_argument('--d',type=int,default=3);q.add_argument('--s',type=int,default=-1)
    q.add_argument('--phase',type=int,default=15);q.add_argument('--width',type=int,default=5);q.add_argument('--target',default='B_frame_correct');q.add_argument('--model');q.add_argument('--output')
    c=sub.add_parser('capabilities');c.add_argument('--model');c.add_argument('--output')
    c=sub.add_parser('plan');c.add_argument('--request');c.add_argument('--target',default='B_frame_correct');c.add_argument('--d',type=int,default=3);c.add_argument('--s',type=int,default=-1);c.add_argument('--budget',type=int,default=14);c.add_argument('--output',required=True)
    c=sub.add_parser('suggest');c.add_argument('--plan',required=True);c.add_argument('--records',required=True);c.add_argument('--session',required=True);c.add_argument('--output')
    c=sub.add_parser('ingest');c.add_argument('--db',required=True);c.add_argument('--session',required=True)
    c=sub.add_parser('export-feedback');c.add_argument('--db',required=True);c.add_argument('--output',required=True)
    c=sub.add_parser('update-template');c.add_argument('--queue',required=True);c.add_argument('--output',required=True)
    c=sub.add_parser('make-dataset');c.add_argument('--data',default=str(ROOT/'data'));c.add_argument('--queue',required=True);c.add_argument('--review',required=True);c.add_argument('--output',required=True)
    c=sub.add_parser('register');c.add_argument('--training-output',required=True)
    a=p.parse_args()
    if a.command=='predict':
        request=json.loads(Path(a.query).read_bytes()) if a.query else query(d=a.d,s=a.s,phase=a.phase,width=a.width,target=a.target)
        save(EdgeAI(a.model).predict(request),a.output)
    elif a.command=='capabilities':save(EdgeAI(a.model).capabilities(),a.output)
    elif a.command=='plan':
        request=json.loads(Path(a.request).read_bytes()) if a.request else example_request(a.target,a.d,a.s,a.budget)
        save(EdgeAI().compile(request),a.output)
    elif a.command=='suggest':
        value=json.loads(Path(a.plan).read_bytes());plan=value.get('plan',value)
        save(EdgeAI(plan['request']['edge_ai']['model_file_sha256']).suggest(plan,json.loads(Path(a.records).read_bytes()),a.session),a.output)
    elif a.command in ('ingest','export-feedback'):
        from custom_ai_feedback import FeedbackStore
        store=FeedbackStore(a.db)
        try:save(store.ingest(a.session) if a.command=='ingest' else store.export_candidates(a.output),None)
        finally:store.close()
    elif a.command=='update-template':
        import hashlib
        save(dict(schema='EDGE_AI_TRAINING_UPDATE_REVIEW_V1',reviewed_by_owner=False,training_approved_by_user=False,
            queue_file_sha256=hashlib.sha256(Path(a.queue).read_bytes()).hexdigest(),approval_reference='',
            note='Template only. Requires source review and explicit user approval before training updates.'),a.output)
    elif a.command=='make-dataset':
        from custom_ai_feedback import make_updated_dataset
        save(make_updated_dataset(a.data,a.queue,a.review,a.output),None)
    elif a.command=='register':
        from edge_registry import install
        save(install(a.training_output),None)

if __name__=='__main__':main()
