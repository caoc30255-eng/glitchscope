"""Rebuild source into a NEW short external directory, report actual timing; no bitgen."""
import argparse,json,os,platform,re,subprocess,sys,time
from pathlib import Path
def timing_table(path):
    lines=Path(path).read_text(encoding='utf-8',errors='replace').splitlines()
    for i,line in enumerate(lines):
        if all(k in line for k in ('WNS(ns)','TNS(ns)','WHS(ns)','WPWS(ns)')):
            for row in lines[i+1:i+6]:
                numbers=re.findall(r'-?\d+(?:\.\d+)?',row)
                if len(numbers)==12:return dict(zip(('wns_ns','tns_ns','setup_failing','setup_total','whs_ns','ths_ns','hold_failing','hold_total','wpws_ns','tpws_ns','pulse_failing','pulse_total'),map(float,numbers)))
    raise ValueError('TIMING_TABLE_NOT_FOUND')
def run(board,vivado,output):
    root=Path(__file__).resolve().parents[1];out=Path(output).resolve();tool=Path(vivado).resolve()
    if board not in ('ax7010','ax7020'):raise ValueError('BOARD')
    if not tool.is_file():raise ValueError('VIVADO_NOT_FOUND')
    if out==root or root in out.parents:raise ValueError('EXTERNAL_OUTPUT_REQUIRED')
    if os.name=='nt' and (len(str(out))>65 or not str(out).isascii()):raise ValueError('USE_SHORT_ASCII_OUTPUT_PATH_MAX65_CHARS')
    for p in (tool,out,root):
        if any(c in str(p) for c in '&|<>^%!"\r\n'):raise ValueError('UNSUPPORTED_SHELL_PATH_CHARACTER')
    out.mkdir(parents=True,exist_ok=False)
    env=dict(os.environ);env.update(GLITCHSCOPE_BUILD_OUTPUT=str(out/'project'),TEMP=str(out),TMP=str(out))
    if os.name=='nt':
        if platform.machine().lower() not in ('amd64','x86_64'):raise ValueError('WINDOWS_ARCHITECTURE')
        env['PROCESSOR_ARCHITECTURE']='AMD64'
    for k in ('PYTHONHOME','PYTHONPATH','TCL_LIBRARY','TK_LIBRARY','QT_PLUGIN_PATH','QT_QPA_PLATFORM_PLUGIN_PATH'):env.pop(k,None)
    env['PATH']=os.pathsep.join(p for p in env.get('PATH','').split(os.pathsep) if 'conda' not in p.lower())
    tcl=root/'build'/('rebuild_'+board+'.tcl')
    args=['-mode','batch','-nojournal','-log',str(out/'vivado.log'),'-source',str(tcl)]
    if os.name=='nt' and tool.suffix.lower() in ('.bat','.cmd'):
        shim=out/'invoke.cmd';shim.write_text('@echo off\ncall "'+str(tool)+'" '+' '.join('"'+a+'"' for a in args)+'\nexit /b %errorlevel%\n',encoding='utf-8')
        command=[os.environ.get('COMSPEC','cmd.exe'),'/d','/c',str(shim)]
    else:command=[str(tool)]+args
    start=time.monotonic()
    report=dict(status='FAILED',board=board,source=str(root),output=str(out),hardware_access=False,bitstream_generated=False)
    try:
        with (out/'console.log').open('wb') as f:
            p=subprocess.Popen(command,cwd=str(out),env=env,stdout=f,stderr=subprocess.STDOUT,creationflags=0x08000000 if os.name=='nt' else 0)
            while True:
                try:code=p.wait(timeout=30);break
                except subprocess.TimeoutExpired:print('Vivado运行中；日志：'+str(out/'console.log'),flush=True)
        text=(out/'console.log').read_text(encoding='utf-8',errors='replace')
        marker='BUILD_REPORTS_ONLY_REVIEW_REQUIRED_NO_BITSTREAM_NO_DOWNLOAD' if board=='ax7010' else 'BUILD_REPORTS_ONLY_REVIEW_REQUIRED_NO_HARDWARE'
        if code!=0 or marker not in text:raise RuntimeError('BUILD_INCOMPLETE_RETAIN_LOGS')
        timing=out/'project/reports/timing_route.txt' if board=='ax7010' else next((out/'project').glob('qualified_controlled_route_*/03_clock_clean_route_timing.txt'))
        values=timing_table(timing)
        ok=all(values[k]>=0 for k in ('wns_ns','whs_ns','wpws_ns')) and all(values[k]==0 for k in ('tns_ns','ths_ns','tpws_ns','setup_failing','hold_failing','pulse_failing'))
        report.update(status='PASS_TIMING_NUMBERS_REVIEW_DRC_AND_COVERAGE' if ok else 'FAILED_TIMING',timing=values,timing_report=str(timing),clock_scope='100MHz PS FCLK0 for ax7020; original MMCM clocks for ax7010',automatic_hardware_acceptance=False)
    except Exception as e:report['error']=dict(type=type(e).__name__,message=str(e))
    report['wall_seconds']=time.monotonic()-start
    (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(report['status'],flush=True);return report['status']=='PASS_TIMING_NUMBERS_REVIEW_DRC_AND_COVERAGE'
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--board',required=True,choices=['ax7010','ax7020']);p.add_argument('--vivado',required=True);p.add_argument('--output',required=True);a=p.parse_args();sys.exit(0 if run(a.board,a.vivado,a.output) else 2)
