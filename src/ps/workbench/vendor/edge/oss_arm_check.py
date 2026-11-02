"""Standard-library Python/C deployment check only; never starts devices."""
from pathlib import Path
import sys,json,platform,struct,time,statistics,ast,subprocess,shutil,argparse,hashlib
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT/'oss'))
from portable import load_default,features,TARGETS
from edge_package import verify
def run(output,compiler=None):
    out=Path(output).resolve()
    if out==ROOT or ROOT in out.parents or out in ROOT.parents:raise ValueError('OUTPUT_OVERLAPS_PACKAGE')
    out.mkdir(parents=True,exist_ok=False)
    print('1/4 Fixed files, Notebook code and Python3.8 syntax',flush=True);fixed=verify(notebooks=True)
    for p in ROOT.rglob('*.py'):
        if '__pycache__' not in p.parts:ast.parse(p.read_text(encoding='utf-8'),feature_version=8)
    print('2/4 Software contracts, synthetic models only; no FPGA',flush=True)
    r=subprocess.run([sys.executable,'-B',str(ROOT/'run_software_tests.py'),'--output',str(out/'contracts')],capture_output=True)
    (out/'contracts_console.log').write_bytes(r.stdout+r.stderr);r.check_returncode()
    print('3/4 Portable OSS model golden queries and inference-only timing',flush=True)
    m=load_default();gold=json.loads((ROOT/'oss/golden.json').read_bytes());qs=gold['queries'];timings=[]
    for q,e in zip(qs,gold['outputs']):
        a=m.predict(q)
        if a!=e:raise ValueError('OSS_GOLDEN_QUERY_CHANGED')
    for i in range(300):
        t=time.perf_counter();m.predict(qs[i%len(qs)]);timings.append(time.perf_counter()-t)
    print('4/4 Compile exported emlearn C when a compiler is available; no hardware IO',flush=True)
    compiler=compiler or shutil.which('cc') or shutil.which('gcc');c_check=dict(status='PENDING_NO_C_COMPILER')
    if compiler:
        code='#include <stdio.h>\n'+''.join('#include "oss_'+t.lower()+'.h"\n' for t in TARGETS)
        code+='int main(void){int t;float x[8];while(scanf("%d",&t)==1){if(t<0||t>2)return 3;int n=t==0?8:6;for(int i=0;i<n;i++)if(scanf("%f",&x[i])!=1)return 4;float p=0;'
        for ti,target in enumerate(TARGETS):code+='if(t=='+str(ti)+')p=oss_'+target.lower()+'_predict(x,n);'
        code+='printf("%.9g\\n",p);}return 0;}\n'
        src=out/'C_probe.c';src.write_text(code,encoding='ascii');exe=out/('C_probe.exe' if sys.platform=='win32' else 'C_probe')
        r=subprocess.run([compiler,'-std=c99','-O2','-I',str(ROOT/'oss'),str(src),'-o',str(exe)],capture_output=True)
        (out/'C_compile.log').write_bytes(r.stdout+r.stderr);r.check_returncode()
        checks=qs*10
        stdin=''.join(str(TARGETS.index(q['target']))+' '+' '.join(map(str,features(q)))+'\n' for q in checks).encode('ascii')
        t=time.perf_counter();r=subprocess.run([str(exe)],input=stdin,capture_output=True,check=True);seconds=time.perf_counter()-t
        scores=[float(v) for v in r.stdout.splitlines()]
        if len(scores)!=len(checks):raise ValueError('C_OUTPUT_LENGTH')
        diff=max(abs(a-m.raw_score(q)) for a,q in zip(scores,checks))
        if diff>2e-6:raise ValueError('C_PORTABLE_SCORE_MISMATCH')
        c_check=dict(status='PASS_EMLEARN_C_MATCH',queries=len(checks),max_abs_error=diff,total_process_seconds=seconds,
            time_includes_process_start_and_IO=True,binary_sha256=hashlib.sha256(exe.read_bytes()).hexdigest())
    if any(n in sys.modules for n in ('pynq','sklearn','skactiveml','emlearn','ch1_uartlite_native_transport')):raise ValueError('UNEXPECTED_DEVICE_OR_PC_TRAINING_IMPORT')
    target=platform.system()=='Linux' and platform.machine()=='armv7l' and struct.calcsize('P')==4 and sys.version_info[:2]==(3,8)
    report=dict(status=('PASS_ARM_OSS_PYTHON_AND_C_SOFTWARE' if compiler else 'PASS_ARM_OSS_PYTHON_C_PENDING') if target else 'PASS_HOST_OSS_SOFTWARE_ARM_PENDING',
        fixed_files=fixed,actual_ARM_run=target,python=sys.version,machine=platform.machine(),pointer_bits=struct.calcsize('P')*8,
        model_sha256=m.model_sha256,model_file_sha256=m.file_sha256,golden_queries=len(qs),
        benchmark=dict(calls=300,mean_seconds=sum(timings)/300,p95_seconds=sorted(timings)[284],inference_only=True),
        C_check=c_check,training_performed=False,hardware_access=False,new_STARTs=0,
        board_session_created=False,real_scan_speedup_accepted=False)
    (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)
    return report
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--compiler');a=p.parse_args();run(a.output,a.compiler)
