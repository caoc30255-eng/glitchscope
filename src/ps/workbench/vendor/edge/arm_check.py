"""Software and inference timing only. No PYNQ, MMIO, UART, Overlay or START."""
from pathlib import Path
import sys,json,platform,struct,time,statistics,tracemalloc,subprocess,ast,argparse,collections
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parent
from edge_package import verify

def run(output,calls=300):
    out=Path(output).resolve()
    if out==ROOT or ROOT in out.parents or out in ROOT.parents:raise ValueError('OUTPUT_OVERLAPS_PACKAGE')
    if type(calls) is not int or not 60<=calls<=10000:raise ValueError('BENCHMARK_CALL_BOUND')
    out.mkdir(parents=True,exist_ok=False)
    print('1/4 Fixed files and Python3.8 syntax',flush=True);fixed=verify(notebooks=True)
    for p in ROOT.rglob('*.py'):
        if '__pycache__' not in p.parts:ast.parse(p.read_text(encoding='utf-8'),feature_version=8)
    print('2/4 Software contracts and synthetic register integration; no FPGA',flush=True)
    process=subprocess.run([sys.executable,'-B',str(ROOT/'run_software_tests.py'),'--output',str(out/'contracts')],capture_output=True)
    (out/'contracts_console.log').write_bytes(process.stdout+process.stderr)
    if process.returncode:raise RuntimeError('SOFTWARE_CONTRACTS_FAILED_RETAIN_OUTPUT')
    print('3/4 Query/inference timing only; no training or hardware session',flush=True)
    from edge_api import EdgeAI
    from custom_ai_core import query,TARGETS
    started=time.perf_counter();service=EdgeAI();load_seconds=time.perf_counter()-started
    qs=[query(phase=15,width=5),query(phase=15,width=10),query(phase=15,width=20),
        query(target=TARGETS[1],phase=15,width=5),query(target=TARGETS[2],phase=15,width=1),query(d=2,s=1)]
    golden=json.loads((ROOT/'golden_queries.json').read_bytes())
    for q,expected in zip(golden['queries'],golden['outputs']):
        actual=service.predict(q)
        for key in ('action','prediction','reason','score_type','support'):
            if actual.get(key)!=expected.get(key):raise ValueError('PORTABLE_QUERY_CHANGED:'+key)
        if actual['score'] is not None and abs(actual['score']-expected['score'])>1e-12:raise ValueError('PORTABLE_SCORE_CHANGED')
    timings=[];actions=collections.Counter()
    for i in range(calls):
        t=time.perf_counter();prediction=service.predict(qs[i%len(qs)]);timings.append(time.perf_counter()-t);actions[prediction['action']]+=1
    tracemalloc.start()
    for i in range(18):service.predict(qs[i%len(qs)])
    current,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
    rss=None
    if sys.platform.startswith('linux'):
        import resource
        rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    require_modules=('pynq','ch1_uartlite_realtime_transport','ch1_uartlite_native_transport')
    if any(n in sys.modules for n in require_modules):raise RuntimeError('DEVICE_MODULE_IMPORTED_IN_CHECK_PROCESS')
    target=platform.system()=='Linux' and platform.machine()=='armv7l' and struct.calcsize('P')==4 and sys.version_info[:2]==(3,8)
    report=dict(status='PASS_PYNQ_EDGE_AI_SOFTWARE' if target else 'PASS_HOST_SOFTWARE_TARGET_PENDING',fixed_files=fixed,
        python=sys.version,machine=platform.machine(),pointer_bits=struct.calcsize('P')*8,actual_ARM_run=target,
        model_sha256=service.model.model_sha256,model_file_sha256=service.file_sha,
        benchmark=dict(calls=calls,load_seconds=load_seconds,mean_seconds=sum(timings)/calls,median_seconds=statistics.median(timings),
            p95_seconds=sorted(timings)[int(.95*(calls-1))],max_seconds=max(timings),actions=dict(actions),
            python_traced_peak_bytes=peak,process_peak_RSS_KiB=rss,load_and_checks_excluded_from_inference_timing=True),
        training_performed=False,hardware_access=False,new_STARTs=0,board_session_created=False,AI_hardware_acceleration_accepted=False)
    (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('4/4 Saved',out/'report.json',flush=True);print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--calls',type=int,default=300);a=p.parse_args();run(a.output,a.calls)
