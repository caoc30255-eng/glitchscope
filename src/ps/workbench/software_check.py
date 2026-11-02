"""Software/preview-model checks only. No actual board consent or FPGA access."""
import argparse,ast,json,platform,struct,subprocess,sys
from pathlib import Path
from common import ROOT,verify,write,require,sha
def run(output):
    out=Path(output).resolve();require(out!=ROOT and ROOT not in out.parents,'OUTPUT_OUTSIDE_DELIVERY_REQUIRED');out.mkdir(parents=True,exist_ok=False)
    print('1/8 Fixed code and Python3.8 syntax',flush=True);count=verify()
    for p in ROOT.glob('*.py'):ast.parse(p.read_text(encoding='utf-8'),feature_version=(3,8))
    results=[];tests=['tests_feedback_fix.py','tests_demo_authority.py','tests_live_accounting_models.py','tests_integration.py','test_forwarded_host.py','tests_fresh_install.py']
    tests.append('tests_ds_frozen_model.py')
    for i,name in enumerate(tests,2):
        print('%d/8 %s (temporary PREVIEW state/models only; no FPGA)'%(i,name),flush=True)
        with (out/(name+'.log')).open('wb') as f:r=subprocess.run([sys.executable,'-B',str(ROOT/name)],stdout=f,stderr=subprocess.STDOUT)
        results.append(dict(test=name,returncode=r.returncode))
        if r.returncode:break
    passed=len(results)==len(tests) and all(r['returncode']==0 for r in results)
    target=platform.system()=='Linux' and platform.machine()=='armv7l' and struct.calcsize('P')==4
    report=dict(status=('PASS_TARGET_DEMO_SOFTWARE' if target else 'PASS_LOCAL_DEMO_SOFTWARE') if passed else 'FAILED_DEMO_SOFTWARE',fixed_files=count,tests=results,ui_manifest_sha256=sha(ROOT/'manifest.json'),python=sys.version,machine=platform.machine(),bits=struct.calcsize('P')*8,hardware_access=False,new_STARTs=0,real_demo_consent_created=False,training_performed=False,browser_automation_used=False,new_UI_hardware_acceptance=False,test_scope='Synthetic PREVIEW ledgers, fake devices and local HTTP contracts; not physical measurements')
    write(out/'report.json',report);print(json.dumps(report,ensure_ascii=False,indent=2),flush=True);require(passed,'TESTS_FAILED_RETAIN_LOGS')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);run(p.parse_args().output)
