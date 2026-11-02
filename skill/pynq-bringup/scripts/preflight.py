"""Staged PYNQ preflight with HWH range binding and explicit clock-effect scope."""
import argparse,hashlib,json,math,platform,re,struct,sys
import xml.etree.ElementTree as ET
from pathlib import Path

def uint(value,bits=32):
    if isinstance(value,bool):raise ValueError('BOOL_NOT_INTEGER')
    n=int(value,0) if isinstance(value,str) else value
    if type(n) is not int or not 0<=n<2**bits:raise ValueError('INTEGER_RANGE')
    return n

def hwh_map(path):
    p=Path(path)
    if p.stat().st_size>64*1024*1024:raise ValueError('HWH_TOO_LARGE')
    raw=p.read_bytes()
    if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():raise ValueError('HWH_DTD_NOT_ALLOWED')
    root=ET.fromstring(raw);ranges=[];seen=set();system={}
    for e in root.iter():
        tag=e.tag.rsplit('}',1)[-1]
        if tag=='SYSTEMINFO':system=dict(e.attrib)
        if tag!='MEMRANGE' or e.get('MEMTYPE','REGISTER')!='REGISTER':continue
        a=e.attrib;ip=a.get('INSTANCE');interface=a.get('SLAVEBUSINTERFACE','')
        if not ip or 'BASEVALUE' not in a or 'HIGHVALUE' not in a:continue
        base,high=uint(a['BASEVALUE']),uint(a['HIGHVALUE'])
        if high<base:raise ValueError('HWH_REVERSED_RANGE')
        key=(ip,interface,base,high)
        if key not in seen:ranges.append(dict(ip_name=ip,interface=interface,base=base,span=high-base+1));seen.add(key)
    if not ranges:raise ValueError('HWH_REGISTER_MAP_EMPTY')
    return dict(system=system,ranges=ranges)

def validate(profile,root):
    if type(profile.get('schema')) is not int or profile['schema']!=1:raise ValueError('PROFILE_SCHEMA')
    assets={}
    for role in ('bit','hwh'):
        item=profile['assets'][role];p=(root/item['path']).resolve()
        if not p.is_file():raise ValueError('ASSET_MISSING:'+role)
        if hashlib.sha256(p.read_bytes()).hexdigest()!=item['sha256']:raise ValueError('ASSET_HASH:'+role)
        assets[role]=str(p)
    if Path(assets['bit']).with_suffix('.hwh')!=Path(assets['hwh']):raise ValueError('BIT_HWH_BASENAME_PAIR_REQUIRED')
    mapping=hwh_map(assets['hwh'])
    if profile.get('expected_hwh_device') and mapping['system'].get('DEVICE')!=profile['expected_hwh_device']:raise ValueError('HWH_DEVICE_MISMATCH')
    regs=profile.get('registers')
    if not isinstance(regs,list) or not regs:raise ValueError('IDENTITY_REGISTERS_REQUIRED')
    seen=set()
    for reg in regs:
        base,span,offset=uint(reg['base']),uint(reg['span']),uint(reg['offset'])
        if base%4 or offset%4 or span<4 or offset+4>span or base+span>2**32:raise ValueError('REGISTER_RANGE')
        if reg['name'] in seen:raise ValueError('DUPLICATE_REGISTER')
        seen.add(reg['name'])
        if reg.get('access')!='RO' or reg.get('read_effect')!='none':raise ValueError('PREFLIGHT_ONLY_SIDE_EFFECT_FREE_RO')
        uint(reg['expected'])
        if uint(reg.get('mask',0xffffffff))==0:raise ValueError('ZERO_IDENTITY_MASK')
        matches=[x for x in mapping['ranges'] if x['ip_name']==reg.get('ip_name') and (not reg.get('hwh_interface') or x['interface']==reg['hwh_interface'])]
        if len(matches)!=1:raise ValueError('HWH_IP_MISSING_OR_AMBIGUOUS:'+reg['name'])
        bank=matches[0]
        if base!=bank['base'] or span>bank['span'] or offset+4>bank['span']:raise ValueError('HWH_ADDRESS_MISMATCH:'+reg['name'])
    clock=profile.get('clock')
    if clock:
        if not re.fullmatch(r'fclk[0-3]_mhz',clock['attribute']):raise ValueError('CLOCK_ATTRIBUTE')
        for key in ('expected_mhz','tolerance_mhz','configure_mhz'):
            if key in clock and (type(clock[key]) not in (int,float) or not math.isfinite(clock[key]) or not 0<=clock[key]<10000):raise ValueError('CLOCK_VALUE')
        if 'configure_mhz' in clock and clock['configure_mhz']<=0:raise ValueError('CLOCK_CONFIG_MUST_BE_POSITIVE')
    return assets

def board_metadata():
    result=dict(machine=platform.machine(),python=platform.python_version(),pointer_bits=struct.calcsize('P')*8,kernel=platform.release())
    for name in ('model','compatible'):
        p=Path('/sys/firmware/devicetree/base')/name
        result['device_tree_'+name]=p.read_bytes().decode('utf-8','replace').rstrip('\x00').replace('\x00',',') if p.is_file() else None
    return result

def clock_snapshot(clocks):
    result={}
    for i in range(4):
        key='fclk%d_mhz'%i
        try:
            value=float(getattr(clocks,key));result[key]=value if math.isfinite(value) else None
        except Exception:result[key]=None
    return result

def run(profile_path,stage='offline',allow_download=False,allow_clock=False,report=None):
    report=report if report is not None else {}
    report.update(schema=2,stage=stage,status='BLOCKED',overlay_download_attempted=False,overlay_download_completed=False,
        explicit_clock_write_attempted=False,overlay_clock_configuration_possible=False,clock_write_attempted=False,
        clock_side_effect_observed_by_instrumentation=False,mmio_reads=[],physical_frequency_measured=False,
        exact_loaded_bitstream_identity_verified=False,physical_trials=0)
    p=Path(profile_path).resolve();profile=json.loads(p.read_text(encoding='utf-8'));assets=validate(profile,p.parent)
    report.update(asset_hashes_verified=True,hwh_address_crosscheck=True,hwh_metadata=hwh_map(assets['hwh']))
    if stage not in ('offline','inspect','load'):raise ValueError('STAGE')
    if stage=='offline':report['status']='PASS_OFFLINE_PROFILE';return report
    if profile.get('asset_kind')!='REAL_BOARD_ASSET':raise ValueError('MOCK_ASSET_CANNOT_REACH_HARDWARE')
    if profile.get('expected_machine') and profile['expected_machine']!=platform.machine():raise ValueError('TARGET_MACHINE_MISMATCH')
    # Overlay(download=True) may apply HWH clocks BEFORE programming. Both scopes are required.
    if stage=='load' and not allow_download:raise ValueError('DOWNLOAD_FLAG_REQUIRED')
    if stage=='load' and not allow_clock:raise ValueError('CLOCK_WRITE_FLAG_REQUIRED_FOR_OVERLAY_HWH')
    report['environment']=board_metadata()
    if profile.get('expected_board_model') and report['environment']['device_tree_model']!=profile['expected_board_model']:raise ValueError('BOARD_MODEL_MISMATCH')
    import pynq
    from pynq import MMIO,Clocks
    from pynq.pl_server import Device
    report['environment']['pynq_version']=getattr(pynq,'__version__','unavailable')
    devices=Device.devices;report['devices_found']=len(devices);report['device_classes']=[type(x).__name__ for x in devices]
    if not devices:raise RuntimeError('NO_PYNQ_DEVICE_CHECK_SAME_SHELL_ENVIRONMENT')
    report['clock_before']=clock_snapshot(Clocks);clock=profile.get('clock')
    if stage=='load':
        report.update(overlay_download_attempted=True,overlay_clock_configuration_possible=True,clock_write_attempted=None,
                      clock_effect_scope='Overlay may apply HWH clocks even if download later fails; internal writes are not instrumented')
        try:pynq.Overlay(assets['bit'],download=True);report['overlay_download_completed']=True
        finally:report['clock_after_overlay']=clock_snapshot(Clocks)
        if clock and 'configure_mhz' in clock:
            report['explicit_clock_write_attempted']=True;report['clock_write_attempted']=True
            try:setattr(Clocks,clock['attribute'],clock['configure_mhz'])
            finally:report['clock_after_explicit_write']=clock_snapshot(Clocks)
    report['clock_after']=clock_snapshot(Clocks)
    if clock:
        configured=report['clock_after'][clock['attribute']];report['clock_configuration_readback_mhz']=configured
        if configured is None or abs(configured-clock['expected_mhz'])>clock['tolerance_mhz']:raise ValueError('CLOCK_CONFIGURATION_MISMATCH_BEFORE_MMIO')
    mismatches=[]
    for reg in profile['registers']:
        value=uint(MMIO(uint(reg['base']),uint(reg['span'])).read(uint(reg['offset'])));mask=uint(reg.get('mask',0xffffffff))
        matched=value&mask==uint(reg['expected'])&mask;report['mmio_reads'].append(dict(name=reg['name'],actual=value,mask=mask,matched=matched))
        if not matched:mismatches.append(reg['name'])
    report['clock_after']=clock_snapshot(Clocks)
    if clock:
        value=report['clock_after'][clock['attribute']];report['clock_configuration_readback_mhz']=value
        if value is None or abs(value-clock['expected_mhz'])>clock['tolerance_mhz']:mismatches.append('clock')
    if mismatches:raise ValueError('READBACK_MISMATCH:'+','.join(mismatches))
    report['status']='PASS_TARGET_READBACK_ONLY';return report

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--profile',required=True);p.add_argument('--output',required=True)
    p.add_argument('--stage',choices=['offline','inspect','load'],default='offline');p.add_argument('--allow-overlay-download',action='store_true');p.add_argument('--allow-clock-write',action='store_true');a=p.parse_args()
    with Path(a.output).open('x',encoding='utf-8') as f:
        r={}
        try:run(a.profile,a.stage,a.allow_overlay_download,a.allow_clock_write,r)
        except Exception as e:r.update(status='BLOCKED',error=type(e).__name__,message=str(e))
        json.dump(r,f,indent=2,ensure_ascii=False,allow_nan=False)
    print(json.dumps(r,ensure_ascii=False,allow_nan=False));return 0 if r['status'].startswith('PASS_') else 2
if __name__=='__main__':sys.exit(main())
