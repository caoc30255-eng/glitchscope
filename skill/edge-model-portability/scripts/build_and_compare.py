"""Compile and run C99, compare to a separately loaded Python implementation."""
import argparse,hashlib,json,os,platform,shutil,subprocess,sys,time
from pathlib import Path
from inference_bench import load_runner
from golden_check import compare
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def find_compiler(explicit=None):
    if explicit:
        p=shutil.which(explicit) or explicit
        if not Path(p).is_file():raise ValueError('COMPILER_NOT_FOUND')
        return str(Path(p).resolve())
    for name in ['gcc','clang','cc']:
        p=shutil.which(name)
        if p:return p
    raise ValueError('Provide --compiler pointing to GCC/Clang; tool never downloads a compiler')
def build(compiler,output,model=None):
    root=Path(__file__).resolve().parents[1];out=Path(output);out.mkdir()
    model=Path(model or root/'examples/weights.txt').resolve();before=sha(model)
    compiler=find_compiler(compiler);binary=out/('demo_model.exe' if os.name=='nt' else 'demo_model')
    env=dict(os.environ);env['PATH']=str(Path(compiler).parent)+os.pathsep+env.get('PATH','')
    version=subprocess.run([compiler,'--version'],capture_output=True,env=env,timeout=20)
    (out/'compiler.log').write_bytes(version.stdout+version.stderr)
    command=[compiler,'-std=c99','-O2',str(root/'examples/demo_model.c'),'-o',str(binary),'-lm']
    if os.name=='nt':command.insert(2,'-static-libgcc')
    p=subprocess.run(command,capture_output=True,env=env,timeout=60);(out/'compile.log').write_bytes(p.stdout+p.stderr)
    if p.returncode or not binary.is_file():raise ValueError('C_COMPILE_FAILED')
    base=[dict(width=x,gap=y) for x in [0,1,7,8,9,16,31,32,33] for y in [0,15,16,17,32]]
    base+= [dict(width=True,gap=1),dict(width=1.5,gap=2)]
    queries=base*10
    predict,receipt=load_runner(root/'examples/demo_runner.py',model)
    expected=dict(schema=1,model_sha256=before,queries=[dict(id='q'+str(i),input=q,result=predict(q)) for i,q in enumerate(queries)])
    def token(v):return str(v) if type(v) is int else 'INVALID'
    raw=''.join('q%d %s %s\n'%(i,token(q['width']),token(q['gap'])) for i,q in enumerate(queries)).encode('ascii')
    t=time.perf_counter();p=subprocess.run([str(binary.resolve()),str(model)],input=raw,capture_output=True,env=env,timeout=30);elapsed=time.perf_counter()-t
    (out/'c_stdout.jsonl').write_bytes(p.stdout);(out/'c_stderr.log').write_bytes(p.stderr)
    if p.returncode:raise ValueError('C_RUN_FAILED')
    lines=[json.loads(line) for line in p.stdout.decode('ascii').splitlines()]
    if len(lines)!=len(queries):raise ValueError('C_QUERY_COUNT')
    actual=dict(schema=1,model_sha256=before,queries=[dict(id=x['id'],input=q,result=x['result']) for x,q in zip(lines,queries)])
    if sha(model)!=before:raise ValueError('MODEL_CHANGED_DURING_RUN')
    spec=json.loads((root/'examples/tolerance_c.json').read_text(encoding='utf-8'));comparison=compare(expected,actual,spec)
    (out/'python.json').write_text(json.dumps(expected,indent=2),encoding='utf-8');(out/'c.json').write_text(json.dumps(actual,indent=2),encoding='utf-8')
    report=dict(status='PASS_NATIVE_PYTHON_C' if comparison['passed'] else 'FAILED_COMPARISON',comparison=comparison,queries=len(queries),compiler=compiler,compile_command=command,
                compiler_version_returncode=version.returncode,c_source_sha256=sha(root/'examples/demo_model.c'),binary_sha256=sha(binary),model_sha256=before,python_loader_receipt=receipt,
                machine=platform.machine(),python=platform.python_version(),c_process_wall_seconds=elapsed,c_time_includes_startup_and_io=True,hardware_access=False,new_STARTs=0,
                actual_ARM_run=platform.machine().lower() in ('armv7l','aarch64','arm64'),scope='Real compiled C example on this host; synthetic model, not accuracy or physical scan speedup')
    (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(report['status'],len(queries),'queries');return report
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--compiler');p.add_argument('--output',required=True);p.add_argument('--model');a=p.parse_args()
    r=build(a.compiler,a.output,a.model);sys.exit(0 if r['status'].startswith('PASS_') else 2)
