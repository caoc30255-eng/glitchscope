"""Explicit new filesystem installation; zero registrations, grants and hardware calls."""
import argparse,json,platform,struct,sys
from pathlib import Path
from common import ROOT,verify,sha,require
from demo_authority import ASSETS
from installation_state import create_fresh,CONFIRMATION

def run(runs,assets_dir,receipt,confirmation):
    verify();receipt=Path(receipt).resolve();v=json.loads(receipt.read_bytes())
    require(v.get('status')=='PASS_TARGET_DEMO_SOFTWARE' and v.get('ui_manifest_sha256')==sha(ROOT/'manifest.json') and v.get('hardware_access') is False and v.get('new_STARTs')==0,'CURRENT_TARGET_SOFTWARE_PASS_REQUIRED')
    require(platform.system()=='Linux' and platform.machine()=='armv7l' and struct.calcsize('P')==4,'TARGET_ARM32_REQUIRED')
    base=Path(assets_dir).resolve();assets=dict(bit=str(base/'ax7020/h1_7020_evidence_candidate_v0_1.bit'),hwh=str(base/'ax7020/h1_7020_evidence_candidate_v0_1.hwh'),native=str(base/'native/libuartlite_service_v5_rt.so'))
    require({k:sha(p) for k,p in assets.items()}==ASSETS,'ORIGINAL_ASSETS_REQUIRED')
    config=create_fresh(runs,assets,receipt,confirmation)
    result=dict(status='FRESH_FILESYSTEM_INSTALLATION_CREATED',runs=config['runs'],config=str(Path(config['runs'])/'live_config.json'),namespace_records=0,trial_records=0,approved_budget=0,hardware_access=False,new_STARTs=0,scope='Filesystem setup only, not proof of a newly flashed SD or hardware acceptance')
    print(json.dumps(result,ensure_ascii=False,indent=2));return result
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--runs',required=True);p.add_argument('--assets',required=True);p.add_argument('--receipt',required=True);p.add_argument('--confirm',required=True);a=p.parse_args();run(a.runs,a.assets,a.receipt,a.confirm)
