"""Fresh-installation identity and filesystem registries. No device imports or grants."""
import json,os,re,uuid
from pathlib import Path
from common import ROOT,require,sha,digest,write
MARKER='fresh_installation.json'
CLOCK_PROFILE=dict(name='navigator7020_pynq27_nominal150_derived100',pynq_major_minor='2.7',pynq_reference_mhz=50.0,device_tree_ps_reference_hz=33333333,nominal_fclk0_mhz=150.0,derived_fclk0_mhz_approx=100.0)
CONFIRMATION='创建全新安装，不导入旧会话或额度'

def validate_registries(runs,identity=None):
    runs=Path(runs);registry=runs/'namespace_allocations.jsonl';trials=runs/'trial_registry'
    require(registry.is_file() and not registry.is_symlink() and trials.is_dir() and not trials.is_symlink(),'REGISTRIES_REQUIRED')
    rows=[json.loads(line) for line in registry.read_text(encoding='utf-8').splitlines() if line.strip()]
    for i,row in enumerate(rows,1):
        require(type(row) is dict and type(row.get('number')) is int and row['number']==i,'NAMESPACE_HISTORY_CHANGED')
        if identity:require(set(row)=={'number','installation_id'} and row['installation_id']==identity['id'],'FRESH_NAMESPACE_ORIGIN_CHANGED')
    files=list(trials.iterdir()) if identity else list(trials.glob('trial_*.json'));ids=[]
    for p in files:
        require(p.is_file() and not p.is_symlink() and re.fullmatch(r'trial_[0-9a-f]{4}\.json',p.name),'TRIAL_REGISTRY_ENTRY_CHANGED')
        v=json.loads(p.read_bytes());n=int(p.stem.split('_')[1],16)
        require(type(v.get('trial_id')) is int and v['trial_id']==n,'TRIAL_ID_CHANGED');ids.append(n)
    require(sorted(ids)==list(range(1,len(ids)+1)) and len(ids)<65535,'TRIAL_HISTORY_CHANGED')
    return rows

def fresh_identity(config,validate=True):
    runs=Path(config['runs']).resolve();path=runs/MARKER;mode=config.get('installation_mode','legacy')
    if not path.exists():
        require(mode=='legacy','FRESH_INSTALLATION_MARKER_REQUIRED');return None
    require(not path.is_symlink() and mode=='fresh','FRESH_BINDING_REQUIRED')
    require(config.get('fresh_installation_sha256')==sha(path),'FRESH_INSTALLATION_BINDING_CHANGED')
    value=json.loads(path.read_bytes());body={k:v for k,v in value.items() if k!='sha256'}
    require(value.get('sha256')==digest(body) and value.get('schema')=='GLITCHSCOPE_FRESH_INSTALLATION_V1','FRESH_MARKER_INTEGRITY')
    require(re.fullmatch('[0-9a-f]{32}',value.get('id','')) and value.get('runs')==str(runs),'FRESH_INSTALLATION_ID_OR_PATH')
    require(value.get('asset_sha256')=={k:sha(p) for k,p in config['assets'].items()},'FRESH_ASSETS_CHANGED')
    require(all(type(value.get(k)) is int and value[k]==0 for k in ('initial_namespaces','initial_trials','initial_budget')),'FRESH_INITIAL_STATE_CHANGED')
    require(value.get('clock_profile')==CLOCK_PROFILE,'FRESH_CLOCK_PROFILE_CHANGED')
    require(not (runs/'unified_ui_approval_consumed').exists(),'LEGACY_ACCOUNTING_IN_FRESH_ROOT')
    if validate:validate_registries(runs,value)
    return value

def installed_config(runs,installation):
    result=dict(runs=str(Path(runs).resolve()),assets=installation['assets'],software_receipt=installation['software_receipt'])
    for name in ('installation_mode','fresh_installation_sha256'):
        if name in installation:result[name]=installation[name]
    return result

def create_fresh(runs,assets,receipt,confirmation):
    require(confirmation==CONFIRMATION,'FRESH_INSTALLATION_CONFIRMATION_REQUIRED')
    runs=Path(runs).resolve();require(runs!=ROOT and ROOT not in runs.parents,'RUNS_OUTSIDE_SOURCE_REQUIRED')
    require(not runs.exists(),'NEW_RUNS_DIRECTORY_REQUIRED')
    for parent in runs.parents:require(not (parent/'namespace_allocations.jsonl').exists(),'DO_NOT_NEST_INSIDE_OLD_RUNS')
    assets={k:str(Path(p).resolve()) for k,p in assets.items()};receipt=Path(receipt).resolve()
    require(set(assets)=={'bit','hwh','native'} and receipt.is_file(),'ASSETS_AND_RECEIPT_REQUIRED')
    for p in assets.values():require(Path(p).is_file(),'ASSET_MISSING')
    body=dict(schema='GLITCHSCOPE_FRESH_INSTALLATION_V1',id=uuid.uuid4().hex,runs=str(runs),asset_sha256={k:sha(p) for k,p in assets.items()},created_with_ui_manifest_sha256=sha(ROOT/'manifest.json'),created_with_software_receipt_sha256=sha(receipt),initial_namespaces=0,initial_trials=0,initial_budget=0,clock_profile=CLOCK_PROFILE,hardware_access=False,new_STARTs=0)
    runs.mkdir(parents=False,exist_ok=False)
    # Partial setup is kept if interrupted. Never delete or reuse that directory.
    (runs/'namespace_allocations.jsonl').open('x',encoding='utf-8').close();(runs/'trial_registry').mkdir()
    marker=dict(body,sha256=digest(body));write(runs/MARKER,marker)
    config=dict(runs=str(runs),assets=assets,software_receipt=str(receipt),installation_mode='fresh',fresh_installation_sha256=sha(runs/MARKER))
    write(runs/'live_config.json',config)
    fresh_identity(config)
    return config

def check_clock_environment(clocks,version,dt_root='/sys/firmware/devicetree/base'):
    require(str(version).split('.')[:2]==['2','7'],'VALIDATED_PYNQ27_ENVIRONMENT_REQUIRED')
    instance=getattr(clocks,'_instance',None)
    require(instance is not None and type(instance).__name__=='_ClocksZynq','ZYNQ7000_CLOCK_IMPLEMENTATION_REQUIRED')
    require(getattr(instance,'_ref_clk_mhz',None)==50.0,'CLOCK_REFERENCE_ENVIRONMENT_CHANGED_NO_SETTER_CALLED')
    files=list(Path(dt_root).rglob('ps-clk-frequency'));require(len(files)==1,'UNIQUE_PS_REFERENCE_DECLARATION_REQUIRED')
    data=files[0].read_bytes();require(len(data)==4 and int.from_bytes(data,'big')==33333333,'BOARD_PS_REFERENCE_PROFILE_CHANGED')
    return dict(profile=CLOCK_PROFILE,clock_setter_called=False,scope='Read-only validation of accepted environment before any Overlay or clock writes')
