"""Explicit real-MMIO example. Default is identity reads; no Overlay/clock/reset calls."""
import argparse,json,hashlib,sys
import xml.etree.ElementTree as ET
from pathlib import Path
from contract import RegisterBank,uint,read_effect
def run(contract,hwh,ip_name,target_confirmed=False,scratch=None,value=None,allow_write=False,restore=False,report=None):
    r=report if report is not None else {};r.update(status='BLOCKED',reads=[],writes=[],overlay_loaded=False,physical_trials=0)
    if not target_confirmed or contract.get('target_kind')!='REAL_BOARD_CONTRACT':raise ValueError('EXPLICIT_TARGET_CONTRACT_AND_INTENT_REQUIRED')
    raw=Path(hwh).read_bytes()
    if len(raw)>64*1024*1024 or b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():raise ValueError('HWH_FORMAT')
    ranges=set()
    for e in ET.fromstring(raw).iter():
        if e.tag.rsplit('}',1)[-1]=='MEMRANGE' and e.get('INSTANCE')==ip_name and e.get('MEMTYPE','REGISTER')=='REGISTER':ranges.add((uint(e.get('BASEVALUE')),uint(e.get('HIGHVALUE'))))
    if len(ranges)!=1:raise ValueError('HWH_IP_MISSING_OR_AMBIGUOUS')
    base,high=next(iter(ranges))
    if uint(contract['base'])!=base or base+uint(contract['span'])-1>high:raise ValueError('HWH_BANK_MISMATCH')
    r['hwh_sha256']=hashlib.sha256(raw).hexdigest()
    if scratch:
        reg=next((x for x in contract['registers'] if x['name']==scratch),None)
        if not allow_write or reg is None or reg['access']!='RW' or read_effect(reg) or reg.get('write_safety')!='scratch' or uint(reg.get('write_mask',0xffffffff))!=0xffffffff:raise ValueError('FULL_WIDTH_SAFE_SCRATCH_AND_WRITE_INTENT_REQUIRED')
        uint(value)
    from pynq import MMIO
    mmio=MMIO(base,uint(contract['span']))
    class Bus:
        def offset(self,a):return a-base if contract['addressing']=='absolute' else a
        def read(self,a):v=mmio.read(self.offset(a));r['reads'].append(dict(address=a,value=v));return v
        def write(self,a,v):r['writes'].append(dict(address=a,value=v,attempted=True));mmio.write(self.offset(a),v)
        read32=read;write32=write
    bank=RegisterBank(Bus(),contract);identities=bank.identities();r['identities']=identities
    if not identities or not all(x['matched'] for x in identities):raise ValueError('IDENTITY_MISMATCH')
    if scratch:
        previous=bank.read(scratch);bank.write(scratch,value)
        if bank.read(scratch)!=uint(value):raise ValueError('SCRATCH_READBACK')
        if restore:bank.write(scratch,previous)
    r.update(status='PASS_EXPLICIT_MMIO_EXAMPLE',scope='HWH-bound MMIO and declared identities; does not prove exact loaded bitstream or analog behavior');return r
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--contract',required=True);p.add_argument('--hwh',required=True);p.add_argument('--ip-name',required=True);p.add_argument('--output',required=True);p.add_argument('--target-confirmed',action='store_true');p.add_argument('--scratch');p.add_argument('--value');p.add_argument('--allow-scratch-write',action='store_true');p.add_argument('--restore',action='store_true');a=p.parse_args()
    with Path(a.output).open('x',encoding='utf-8') as f:
        report={}
        try:run(json.loads(Path(a.contract).read_text(encoding='utf-8')),a.hwh,a.ip_name,a.target_confirmed,a.scratch,a.value,a.allow_scratch_write,a.restore,report)
        except Exception as e:report.update(status='BLOCKED',error=str(e))
        json.dump(report,f,indent=2)
    print(json.dumps(report));sys.exit(0 if report['status'].startswith('PASS_') else 2)
