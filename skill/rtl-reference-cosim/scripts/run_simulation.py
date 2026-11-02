"""Run bundled behavioral demo; no synthesis, bitstream, hardware manager or FPGA access."""
import argparse,hashlib,json,os,platform,re,subprocess,sys,time
from pathlib import Path
from make_demo_reference import generate
from compare_trace import compare,check_log
def run(vivado,output,part='xc7z020clg400-1',inject=False,isolate=False):
    root=Path(__file__).resolve().parents[1];out=Path(output).resolve()
    tool=Path(vivado).resolve();tcl=root/'examples/run_vivado.tcl'
    if not tool.is_file() or not re.fullmatch(r'[a-zA-Z0-9_-]+',part):raise ValueError('TOOL_OR_PART')
    for p in [tool,tcl,out]:
        if not str(p).isascii() or any(c in str(p) for c in '&|<>^%!"\r\n'):raise ValueError('WINDOWS_SHELL_SPECIAL_PATH_NOT_SUPPORTED')
    out.mkdir();env=dict(os.environ);adjustments=[]
    if os.name=='nt' and not env.get('PROCESSOR_ARCHITECTURE'):
        machine=platform.machine().lower()
        if machine not in ('amd64','x86_64'):raise ValueError('VERIFY_NATIVE_WINDOWS_ARCHITECTURE')
        env['PROCESSOR_ARCHITECTURE']='AMD64';adjustments.append('PROCESSOR_ARCHITECTURE set from actual platform.machine')
    if isolate:
        for k in ['PYTHONHOME','PYTHONPATH','TCL_LIBRARY','TK_LIBRARY','QT_PLUGIN_PATH','QT_QPA_PLATFORM_PLUGIN_PATH']:
            if k in env:env.pop(k);adjustments.append('removed '+k)
        env['PATH']=os.pathsep.join(p for p in env.get('PATH','').split(os.pathsep) if 'anaconda' not in p.lower() and 'conda' not in p.lower())
        adjustments.append('removed conda entries from child PATH only')
    env.update(TEMP=str(out),TMP=str(out))
    args=['-mode','batch','-nojournal','-nolog','-source',str(tcl),'-tclargs',str(out/'project'),part]
    if inject:args.append('inject_stall_bug')
    if os.name=='nt' and tool.suffix.lower() in ('.bat','.cmd'):
        shim=out/'invoke.cmd'
        shim.write_text('@echo off\ncall "'+str(tool)+'" '+' '.join('"'+x+'"' for x in args)+'\nexit /b %errorlevel%\n',encoding='ascii')
        command=[os.environ.get('COMSPEC','cmd.exe'),'/d','/c',str(shim)]
    else:command=[str(tool)]+args
    source_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [tcl,root/'examples/accumulator.sv',root/'examples/tb_accumulator.sv']}
    start=time.perf_counter()
    try:
        result=subprocess.run(command,cwd=str(out),env=env,capture_output=True,timeout=180,creationflags=0x08000000 if os.name=='nt' else 0)
        log=result.stdout+result.stderr;returncode=result.returncode
    except subprocess.TimeoutExpired as e:log=(e.stdout or b'')+(e.stderr or b'');returncode=None
    console=out/'console.log';console.write_bytes(log)
    actual=out/'project/skill_demo.sim/sim_1/behav/xsim/actual.csv'
    generate(out/'reference');spec=json.loads((out/'reference/spec.json').read_text(encoding='utf-8'))
    report=dict(status='FAILED',returncode=returncode,process_wall_seconds=time.perf_counter()-start,injected_bug=inject,source_sha256=source_hashes,environment_adjustments=adjustments,
                hardware_access=False,scope='Behavioral simulation of bundled ready/valid accumulator, not implementation/timing/hardware proof')
    try:
        for p in [tcl,root/'examples/accumulator.sv',root/'examples/tb_accumulator.sv']:
            if hashlib.sha256(p.read_bytes()).hexdigest()!=source_hashes[p.name]:raise ValueError('SOURCES_CHANGED')
        if inject:
            text=log.decode('utf-8','replace')
            if 'SKILL_RTL_FAIL' not in text or 'SKILL_RTL_PASS cases=6 cycles=384' in text or not actual.is_file():raise ValueError('INJECTED_FAILURE_NOT_OBSERVED')
            try:comparison=compare(out/'reference/reference.csv',actual,spec)
            except ValueError as e:comparison=dict(passed=False,message=str(e))
            if comparison['passed']:raise ValueError('BUG_NOT_REJECTED_BY_COMPARATOR')
            report.update(status='PASS_INJECTED_FAILURE_DETECTED',comparison=comparison)
        else:
            if returncode!=0:raise ValueError('VIVADO_RETURN_CODE')
            check_log(console,'SKILL_RTL_PASS cases=6 cycles=384','SKILL_RTL_FAIL')
            comparison=compare(out/'reference/reference.csv',actual,spec)
            if not comparison['passed']:raise ValueError('REFERENCE_MISMATCH')
            report.update(status='PASS_VIVADO_AND_REFERENCE',comparison=comparison)
    except Exception as e:report['error']=str(e)
    (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(report['status']);return report
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--vivado',required=True);p.add_argument('--output',required=True);p.add_argument('--part',default='xc7z020clg400-1');p.add_argument('--inject-stall-bug',action='store_true');p.add_argument('--isolate-python-env',action='store_true');a=p.parse_args()
    r=run(a.vivado,a.output,a.part,a.inject_stall_bug,a.isolate_python_env);sys.exit(0 if r['status'].startswith('PASS_') else 2)
