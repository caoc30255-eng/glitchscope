"""File-only target setup after software PASS. No consent, MMIO, reset or START."""
import argparse,json,os
from pathlib import Path
from common import ROOT,verify,sha,require
from demo_authority import Authority,ASSETS
def run(path):
    verify();config=json.loads(Path(path).read_bytes());runs=Path(config['runs']).resolve()
    receipt=json.loads(Path(config['software_receipt']).read_bytes())
    require(receipt['status']=='PASS_TARGET_DEMO_SOFTWARE' and receipt['ui_manifest_sha256']==sha(ROOT/'manifest.json') and receipt['hardware_access'] is False and receipt['new_STARTs']==0,'TARGET_SOFTWARE_PASS_REQUIRED')
    require({k:sha(p) for k,p in config['assets'].items()}==ASSETS,'ORIGINAL_ASSETS_REQUIRED')
    registry=runs/'namespace_allocations.jsonl';require(registry.is_file() and (runs/'trial_registry').is_dir(),'EXISTING_REGISTRIES_REQUIRED_NO_REBUILD')
    from installation_state import fresh_identity,validate_registries
    origin=fresh_identity(config)
    rows=validate_registries(runs,origin);numbers=[x['number'] for x in rows]
    if origin is None:require(len(numbers)>=79,'ORIGINAL_NAMESPACE_HISTORY_REQUIRED')
    authority=Authority.for_live(config);status=authority.status();active=status['active_round']
    if active is not None:
        tasks=[t for t in authority._load()[1]['tasks'].values() if t['round_id']==active['id']]
        require(active['state']=='BLOCKED' and tasks and all(t['terminal'] and t.get('cleanup_confirmed') and t.get('audit_reference') and t['attempts']==t['retired'] for t in tasks),'存在未核对或未清理任务，不能更换执行版本')
        print('仅更新修复软件：原轮次保持阻断；须由操作者在网页结束旧轮次并重新确认。',flush=True)
    binding=dict(schema='DEMO_INSTALLATION_V1',software_receipt=str(Path(config['software_receipt']).resolve()),assets={k:str(Path(p).resolve()) for k,p in config['assets'].items()},ui_manifest_sha256=sha(ROOT/'manifest.json'),hardware_access=False,new_STARTs=0)
    binding['installation_mode']=config.get('installation_mode','legacy')
    if origin:binding['fresh_installation_sha256']=config['fresh_installation_sha256']
    target=authority.root/'installation.json';pending=authority.root/'installation.json.pending'
    with pending.open('w',encoding='utf-8') as f:json.dump(binding,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
    os.replace(pending,target)
    print(json.dumps(dict(status='INSTALLATION_READY_NO_ROUND_GRANTED',namespace_count_read_only=len(numbers),software_receipt=binding['software_receipt'],approved_new_records=0,hardware_access=False,new_STARTs=0),indent=2),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);run(p.parse_args().config)
