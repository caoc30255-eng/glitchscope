"""Full legal configuration preview and portable inference; no hardware calls."""
from pathlib import Path
import sys,json,argparse
ROOT=Path(__file__).resolve().parent;sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'oss')]
from portable import load_default,from_condition,STRATEGY,canonical

def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
    c=sub.add_parser('predict');c.add_argument('--query',required=True)
    c=sub.add_parser('plan');c.add_argument('--request',required=True);c.add_argument('--output',required=True)
    c=sub.add_parser('suggest');c.add_argument('--plan',required=True);c.add_argument('--records',required=True);c.add_argument('--session',required=True)
    c=sub.add_parser('collect');c.add_argument('--session',required=True);c.add_argument('--output',required=True)
    c=sub.add_parser('prepare-dataset');c.add_argument('--queue',required=True);c.add_argument('--approval',required=True);c.add_argument('--output',required=True)
    a=p.parse_args();model=load_default()
    if a.command=='predict':v=model.predict(json.loads(Path(a.query).read_bytes()))
    elif a.command=='plan':
        from custom_plan import compile_plan
        r=json.loads(Path(a.request).read_bytes());r['edge_ai']=dict(strategy=STRATEGY,model_file_sha256=model.file_sha256,max_extra_groups=1,allow_rule_fallback=True)
        v=compile_plan(r)
        if v['plan']:
            v['coverage']=[dict(condition_id=c['condition_id'],prediction=model.predict(from_condition(c,v['plan']['target']))) for c in v['plan']['conditions']]
            v['hardware_permission']=False;v['all_selected_configurations_are_learned']=all(x['prediction']['score'] is not None for x in v['coverage'])
        with Path(a.output).open('xb') as f:f.write(canonical(v)+b'\n')
        v={k:v[k] for k in ('status','errors','hardware_permission','all_selected_configurations_are_learned') if k in v}
    elif a.command=='suggest':
        from custom_refine import suggest
        from learning_domain import digest
        plan=json.loads(Path(a.plan).read_bytes());plan=plan.get('plan',plan);records=json.loads(Path(a.records).read_bytes())
        v=suggest(plan,records,a.session,plan['max_records']-len(records),confirmed_domain_sha256=digest(plan['conditions']))
    elif a.command=='collect':
        from feedback_oss import collect
        v=collect(a.session,a.output)
    else:
        from feedback_oss import prepare_snapshot
        v=prepare_snapshot(ROOT/'data',a.queue,a.approval,a.output)
    print(json.dumps(v,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
