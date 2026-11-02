import argparse,json,platform,sys,time,shutil
from pathlib import Path
from labutil import *
from scans import default_plan,make_plan
from learner import Estimator,evaluate,benchmark,synthetic_truth

def algorithm_demo(workspace):
    workspace=output_path(workspace);out=workspace/'algorithm';out.mkdir(parents=True,exist_ok=True)
    plan=make_plan(bytes(range(256)),list(range(5,41,5)),[1,5,10,15,20,25,30,35,40],repeats=1,budget=100)
    write(out/'evaluation_plan.json',plan)
    reports={}
    for target in ('B_frame_correct','STM_business_success'):
        reports[target]=evaluate(plan,target=target)
        cells=[c for c in plan['cells'] if c['legal']];samples=[dict(phase=c['phase'],width=c['width'],y=float(synthetic_truth(c,7,target)),origin='SIMULATED_DEVELOPMENT') for c in cells[::4]]
        model=Estimator(target).fit(samples,'SIMULATED_DEVELOPMENT');model.save(out/(target+'_model.json'))
        write(out/(target+'_predictions.json'),model.predict(cells))
    report=dict(origin='SIMULATED_DEVELOPMENT_ONLY',targets=reports,real_training_performed=False,real_AI_acceleration_accepted=False,
        actual_environment=dict(python=sys.version,machine=platform.machine(),platform=platform.platform()))
    write(out/'comparison.json',report);return report

def inference(model_path,plan_path,output):
    from scans import validate
    require(Path(output).resolve() not in (Path(model_path).resolve(),Path(plan_path).resolve()),'INFERENCE_MUST_NOT_OVERWRITE_INPUT')
    output_path(output)
    start=time.perf_counter();model=Estimator.load(model_path);load_seconds=time.perf_counter()-start
    plan=read(plan_path);validate(plan);cells=[c for c in plan['cells'] if c['legal']]
    b=benchmark(model,cells);b.update(python=sys.version,machine=platform.machine(),platform=platform.platform(),
        model_load_seconds=load_seconds,actual_ARM_run=platform.machine().lower().startswith(('arm','aarch')),
        dependencies='Python standard library; does not upgrade NumPy/PYNQ',real_training_performed=False)
    write(output,dict(benchmark=b,predictions=model.predict(cells)));return b

def cli():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
    a=sub.add_parser('prepare');a.add_argument('--baseline',required=True,type=Path);a.add_argument('--baseline-zip',required=True,type=Path)
    a.add_argument('--workspace',required=True,type=Path);a.add_argument('--temp-root',required=True,type=Path)
    a=sub.add_parser('algorithm-demo');a.add_argument('--workspace',required=True,type=Path)
    a=sub.add_parser('init-demo');a.add_argument('--workspace',required=True,type=Path)
    a=sub.add_parser('infer');a.add_argument('--model',required=True,type=Path);a.add_argument('--plan',required=True,type=Path);a.add_argument('--output',required=True,type=Path)
    a=sub.add_parser('serve');a.add_argument('--workspace',required=True,type=Path);a.add_argument('--port',type=int,default=8765)
    args=p.parse_args()
    if args.command=='prepare':
        from evidence import prepare
        result=prepare(args.baseline,args.baseline_zip,args.workspace,args.temp_root)
    elif args.command=='init-demo':
        from verify_delivery import verify
        verify(Path(__file__).resolve().parent)
        target=output_path(args.workspace);require(not target.exists(),'NEW_WORKSPACE_REQUIRED')
        origin=Path(__file__).resolve().parent/'results';require((origin/'prepared.json').is_file(),'BUNDLED_RESULTS_REQUIRED')
        shutil.copytree(origin,target,ignore=shutil.ignore_patterns('lab_state.sqlite','service.lock'))
        result=dict(status='COPIED_DEMO_TO_OWN_WORKSPACE',workspace=str(target),hardware_access=False)
    elif args.command=='algorithm-demo':result=algorithm_demo(args.workspace)
    elif args.command=='infer':result=inference(args.model,args.plan,args.output)
    else:
        from server import serve
        return serve(args.workspace,args.port)
    print(json.dumps(view(result),ensure_ascii=False,indent=2))

if __name__=='__main__':cli()
