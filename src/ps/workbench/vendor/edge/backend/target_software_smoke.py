"""Pure software report; no actual device services, MMIO, serial, Overlay or trials."""
import hashlib
import json
import platform
import struct
import subprocess
import sys
from pathlib import Path


def run(directory):
    root=Path(__file__).resolve().parent;out=Path(directory);out.mkdir(parents=True,exist_ok=False)
    from custom_real import environment
    env=environment();logs=[]
    for test in ('tests_backend.py','tests_v02.py','tests_mmio_binding.py'):
        p=subprocess.run([sys.executable,'-B',str(root/test)],cwd=root,capture_output=True,text=True)
        (out/(test+'.log')).write_text(p.stdout+p.stderr,encoding='utf-8')
        logs.append(dict(test=test,returncode=p.returncode))
    target=platform.system()=='Linux' and platform.machine()=='armv7l' and struct.calcsize('P')==4 and sys.version_info[:3]==(3,8,2)
    passed=all(p['returncode']==0 for p in logs)
    report=dict(schema='SCAN_SOFTWARE_SMOKE_V0_2',environment=env,platform_role='TARGET_PYNQ_SOFTWARE' if target else 'HOST_ONLY',
                status='PASS' if passed else 'FAIL',target_status='PASS' if target and passed else 'FAIL' if target else 'PENDING_TARGET',
                tests=logs,hardware_status='PENDING_HARDWARE',physical_STARTs=0,device_services_started=False,
                code_sha256={p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*.py') if '__pycache__' not in p.parts})
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='code_sha256'},indent=2))
    return 0 if passed else 2


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);sys.exit(run(p.parse_args().output))
