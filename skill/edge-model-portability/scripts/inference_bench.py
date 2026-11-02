"""Run a user-selected local predict(query) module. Timing and memory probes are separate."""
import argparse,hashlib,importlib.util,json,math,platform,time,tracemalloc,sys
from pathlib import Path
def load_runner(path,model_artifact=None):
    p=Path(path).resolve();spec=importlib.util.spec_from_file_location('skill_local_runner',str(p));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    source_sha=hashlib.sha256(p.read_bytes()).hexdigest();model=None
    if model_artifact:
        if not callable(getattr(m,'load_model',None)):raise ValueError('RUNNER_LOAD_HOOK_REQUIRED')
        artifact=Path(model_artifact).resolve();before=hashlib.sha256(artifact.read_bytes()).hexdigest();model=m.load_model(artifact)
    elif getattr(m,'DEFAULT_MODEL',None) is not None:
        model=m.DEFAULT_MODEL;artifact=Path(model.loaded_path).resolve();before=hashlib.sha256(artifact.read_bytes()).hexdigest()
    if model is not None:
        if Path(model.loaded_path).resolve()!=artifact or model.loaded_sha256!=before or hashlib.sha256(artifact.read_bytes()).hexdigest()!=before:raise ValueError('MODEL_LOADER_BINDING_MISMATCH')
        predict=model.predict;identity=before;scope='FILE_LOAD_HOOK_AND_HASH_CHECK_NOT_MEMORY_ATTESTATION'
    else:predict=getattr(m,'predict',None);identity=source_sha;scope='RUNNER_SOURCE_ONLY_NO_WEIGHT_BINDING'
    if not callable(predict):raise ValueError('PREDICT_FUNCTION_REQUIRED')
    return predict,dict(runner_source_sha256=source_sha,model_sha256=identity,model_load_hook_verified=model is not None,binding_scope=scope)
def get_runner(path,model_artifact=None):
    predict,receipt=load_runner(path,model_artifact);return predict,receipt['model_sha256']
def bench(predict,queries,calls=200,warmup=10,memory_probes=16):
    if not queries or any(type(n) is not int or n<0 for n in [calls,warmup,memory_probes]) or calls<1:raise ValueError('BENCH_ARGUMENTS')
    for i in range(warmup):predict(queries[i%len(queries)])
    timings=[]
    for i in range(calls):
        start=time.perf_counter();result=predict(queries[i%len(queries)]);elapsed=time.perf_counter()-start
        json.dumps(result,allow_nan=False);timings.append(elapsed)
    peak=None
    if memory_probes:
        tracemalloc.start()
        try:
            for i in range(memory_probes):predict(queries[i%len(queries)])
            peak=tracemalloc.get_traced_memory()[1]
        finally:tracemalloc.stop()
    ordered=sorted(timings)
    return dict(calls=calls,warmup_excluded=warmup,mean_seconds=math.fsum(timings)/calls,p95_seconds=ordered[max(0,math.ceil(.95*calls)-1)],
                p95_method='nearest rank',min_seconds=ordered[0],max_seconds=ordered[-1],separate_memory_probe_calls=memory_probes,python_traced_peak_bytes=peak,
                RSS_measured=False,inference_only=False,timing_scope="predict_call_elapsed",external_model_loading_and_serialization_excluded=True,runner_internal_io_excluded=False,hardware_time_measured=False,machine=platform.machine(),python=platform.python_version())
def main():
    p=argparse.ArgumentParser();p.add_argument('--runner',required=True);p.add_argument('--queries',required=True);p.add_argument('--calls',type=int,default=200);p.add_argument('--output',required=True);p.add_argument('--model-artifact');a=p.parse_args()
    with Path(a.output).open('x',encoding='utf-8') as f:
        predict,receipt=load_runner(a.runner,a.model_artifact);queries=json.loads(Path(a.queries).read_text(encoding='utf-8'))
        r=bench(predict,queries,a.calls);r['runner_receipt']=receipt
        json.dump(r,f,indent=2)
    print(json.dumps(r))
if __name__=='__main__':main()
