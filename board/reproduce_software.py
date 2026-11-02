"""PYNQ software/native reproduction only; never map devices or start a receiver."""
import argparse,hashlib,json,os,platform,shutil,struct,subprocess,sys,time
from pathlib import Path
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def run(output):
    root=Path(__file__).resolve().parents[1];out=Path(output).resolve()
    if out==root or root in out.parents:raise ValueError('RESULT_MUST_BE_OUTSIDE_RELEASE')
    out.mkdir(parents=True,exist_ok=False)
    report=dict(schema='FRESH_TARGET_SOFTWARE_REPRODUCTION_V1',status='FAILED',source=str(root),python=sys.version,machine=platform.machine(),bits=struct.calcsize('P')*8,stages=[],hardware_access=False,receiver_started=False,new_STARTs=0,rebuilt_library_installed=False)
    env=dict(os.environ);env.update(TMPDIR=str(out),TEMP=str(out),TMP=str(out),PYTHONDONTWRITEBYTECODE='1')
    def stage(name,args):
        log=out/(name+'.log');start=time.monotonic()
        print('开始：'+name,flush=True)
        with log.open('wb') as f:
            p=subprocess.Popen(args,env=env,cwd=str(out),stdout=f,stderr=subprocess.STDOUT)
            while True:
                try:code=p.wait(timeout=15);break
                except subprocess.TimeoutExpired:print('仍在运行：%s，日志：%s'%(name,log),flush=True)
        report['stages'].append(dict(name=name,returncode=code,seconds=time.monotonic()-start,log=log.name))
        if code:raise RuntimeError('STAGE_FAILED:'+name)
    try:
        if platform.system()!='Linux' or platform.machine()!='armv7l' or struct.calcsize('P')!=4:raise RuntimeError('PYNQ_ARMV7L_32BIT_TARGET_REQUIRED')
        stage('release_check',[sys.executable,'-B',str(root/'build/verify_release.py')])
        code='import json,numpy,PIL;print(json.dumps(dict(numpy=numpy.__version__,pillow=PIL.__version__)))'
        stage('dependencies',[sys.executable,'-B','-c',code])
        stage('workbench_software',[sys.executable,'-B',str(root/'src/ps/workbench/software_check.py'),'--output',str(out/'software')])
        receipt=json.loads((out/'software/report.json').read_bytes())
        if receipt['status']!='PASS_TARGET_DEMO_SOFTWARE' or receipt['hardware_access'] is not False or receipt['new_STARTs']!=0:raise RuntimeError('EXACT_TARGET_SOFTWARE_PASS_REQUIRED')
        stage('compiler_version',['gcc','--version'])
        stage('native_build',['bash',str(root/'build/build_native.sh'),str(out/'native')])
        library=out/'native/libuartlite_service_v5_rt.so'
        expected=['uartlite_service_start','uartlite_service_start_rt','uartlite_service_scheduling','uartlite_service_pause','uartlite_service_close','uartlite_service_snapshot','uartlite_service_metrics','uartlite_service_exchange_metrics','uartlite_service_collect']
        code='import ctypes,sys,json;lib=ctypes.CDLL(sys.argv[1]);names=json.loads(sys.argv[2]);[getattr(lib,n) for n in names];print("PASS_EXPORTS_ONLY_NO_FUNCTIONS_CALLED")'
        stage('native_load',[sys.executable,'-B','-c',code,str(library),json.dumps(expected)])
        report.update(status='PASS_TARGET_SOFTWARE_AND_NATIVE_BUILD',native_sha256=hashlib.sha256(library.read_bytes()).hexdigest(),exports_checked=expected,hardware_acceptance=False)
    except Exception as e:report['error']=dict(type=type(e).__name__,message=str(e))
    finally:write(out/'report.json',report)
    print('结果：'+report['status']+'；完整报告：'+str(out/'report.json'),flush=True)
    return report['status']=='PASS_TARGET_SOFTWARE_AND_NATIVE_BUILD'
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();sys.exit(0 if run(a.output) else 2)
