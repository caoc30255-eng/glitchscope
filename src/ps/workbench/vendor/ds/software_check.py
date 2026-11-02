"""Target-compatible software-only check, without FPGA/native receiver imports."""
from pathlib import Path
import argparse,ast,json,sys,os,platform,struct,subprocess
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parent

def run(output,session=None,analysis=None):
    out=Path(output).resolve()
    if out==ROOT or ROOT in out.parents or out in ROOT.parents:raise ValueError('OUTPUT_OVERLAPS_PACKAGE')
    out.mkdir(parents=True,exist_ok=False)
    print('1/3 Package/model hashes and Python3.8 syntax',flush=True)
    from workbench import verify_package
    count=verify_package()
    for p in ROOT.glob('*.py'):ast.parse(p.read_text(encoding='utf-8'),feature_version=8)
    print('2/3 Software guards and optional historical evidence checks',flush=True)
    env=dict(os.environ);env['WORKBENCH_TEST_ROOT']=str(out/'synthetic_fixtures')
    if session:env['IMAGE64_EVIDENCE']=str(Path(session).resolve())
    else:env.pop('IMAGE64_EVIDENCE',None)
    if analysis:
        env['WORKBENCH_OUTPUT']=str(Path(analysis).resolve());env['IMAGE64_OUTPUT']=str(Path(analysis).resolve())
    else:
        env.pop('WORKBENCH_OUTPUT',None);env.pop('IMAGE64_OUTPUT',None)
    r=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s',str(ROOT),'-p','tests_*.py','-v'],env=env,capture_output=True)
    (out/'tests.log').write_bytes(r.stdout+r.stderr)
    print('3/3 Save software report (no physical START)',flush=True)
    result=dict(status='PASS_SOFTWARE_ONLY' if r.returncode==0 else 'FAIL_SOFTWARE_ONLY',fixed_files=count,
        python=sys.version,machine=platform.machine(),pointer_bits=struct.calcsize('P')*8,
        target_profile_match=platform.system()=='Linux' and platform.machine()=='armv7l' and struct.calcsize('P')==4 and sys.version_info[:2]==(3,8),
        tests_returncode=r.returncode,historical_checks_requested=bool(session),full_analysis_checks_requested=bool(analysis),
        hardware_access=False,new_STARTs=0,hardware_acceptance=False,
        test_scope='Synthetic failure copies and optional immutable historical records; inspect tests.log for skips')
    (out/'report.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result,indent=2),flush=True)
    if r.returncode:raise RuntimeError('SOFTWARE_CHECK_FAILED_RETAIN_OUTPUT')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--session');p.add_argument('--analysis')
    a=p.parse_args();run(a.output,a.session,a.analysis)
