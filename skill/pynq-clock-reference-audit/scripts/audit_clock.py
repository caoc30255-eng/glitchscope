"""Offline, standard-library Zynq7000 reference-clock audit. No PYNQ dependency."""
import argparse,json,math
from pathlib import Path

SUPPORTED={'ZYNQ_CLOCK_REFERENCE_SNAPSHOT_V1','ZYNQ_CLOCK_READONLY_REFERENCE_AUDIT_V1','BOARD_CLOCK_REFERENCE_AUDIT_EXCERPT_V1'}
def require(value,message):
    if not value:raise ValueError(message)
def number(v,name):
    require(type(v) in (int,float) and math.isfinite(v) and v>0,'POSITIVE_FINITE_'+name)
    return float(v)
def u32(v):
    if type(v) is str:
        try:v=int(v,0)
        except ValueError:raise ValueError('INVALID_REGISTER_TEXT')
    require(type(v) is int and 0<=v<=0xffffffff,'REGISTER_MUST_BE_UINT32')
    return v
def unique(pairs):
    d={}
    for k,v in pairs:
        require(k not in d,'DUPLICATE_JSON_KEY:'+k);d[k]=v
    return d
def load(path):
    def nonfinite(v):raise ValueError('NONFINITE_JSON:'+v)
    return json.loads(Path(path).read_text(encoding='utf-8'),object_pairs_hook=unique,parse_constant=nonfinite)
def audit(snapshot,reference_mhz,reference_source):
    ref=number(reference_mhz,'REFERENCE')
    require(type(reference_source) is str and bool(reference_source.strip()),'REFERENCE_SOURCE_REQUIRED')
    require(type(snapshot) is dict and snapshot.get('schema') in SUPPORTED,'SUPPORTED_ZYNQ7000_SNAPSHOT_REQUIRED')
    require(snapshot.get('clock_class')=='_ClocksZynq','ZYNQ7000_CLOCK_CLASS_REQUIRED')
    require(snapshot.get('raw_second_read_matches') is True,'UNSTABLE_OR_UNCONFIRMED_SNAPSHOT')
    regs={k:u32(v) for k,v in snapshot['raw_registers'].items()}
    if 'raw_registers_second' in snapshot:
        second={k:u32(v) for k,v in snapshot['raw_registers_second'].items()}
        require(regs==second,'RAW_SNAPSHOTS_DIFFER')
    for k in ('ARM_PLL_CTRL','DDR_PLL_CTRL','IO_PLL_CTRL','PLL_STATUS','FPGA0_CLK_CTRL'):require(k in regs,'MISSING_REGISTER:'+k)
    clock=regs['FPGA0_CLK_CTRL'];source=(clock>>4)&3
    name=('IO_PLL_CTRL','IO_PLL_CTRL','ARM_PLL_CTRL','DDR_PLL_CTRL')[source]
    ctrl=regs[name];div0=(clock>>8)&63;div1=(clock>>20)&63;fbdiv=(ctrl>>12)&127
    require(div0!=0 and div1!=0,'ZERO_DIVISOR_UNSUPPORTED')
    lockbit={'ARM_PLL_CTRL':0,'DDR_PLL_CTRL':1,'IO_PLL_CTRL':2}[name]
    locked=bool((regs['PLL_STATUS']>>lockbit)&1)
    force=bool(ctrl&16);qual=bool(ctrl&8)
    require(not (ctrl&3),'PLL_RESET_OR_POWERDOWN_REQUIRES_REVIEW')
    if force:bypass=True
    elif qual:
        require('BOOT_MODE' in regs,'QUALIFIED_BYPASS_NEEDS_BOOT_MODE')
        bypass=bool(regs['BOOT_MODE']&16)
    else:bypass=False
    if not bypass:
        require(locked,'PLL_NOT_LOCKED');require(fbdiv!=0,'ZERO_PLL_MULTIPLIER')
    divisor=div0*div1;factor=1 if bypass else fbdiv
    derived=ref*factor/divisor
    runtime_ref=snapshot.get('pynq_instance_reference_mhz')
    reported=snapshot.get('reported_fclk0_mhz')
    if reported is not None:reported=number(reported,'PYNQ_REPORTED_FREQUENCY')
    if runtime_ref is None:
        status='REGISTER_RATE_DERIVED_PYNQ_REFERENCE_UNAVAILABLE';expected=None
    else:
        runtime_ref=number(runtime_ref,'PYNQ_REFERENCE')
        # PYNQ2.7's recorded getter multiplies FBDIV and does not implement bypass.
        expected=runtime_ref*fbdiv/divisor
        reported=number(reported,'PYNQ_REPORTED_FREQUENCY')
        require(math.isclose(reported,expected,rel_tol=1e-6,abs_tol=1e-5),'REPORTED_VALUE_DISAGREES_WITH_RECORDED_PYNQ_FORMULA')
        if bypass:status='PLL_BYPASS_REQUIRES_PYNQ_GETTER_REVIEW'
        elif math.isclose(ref,runtime_ref,rel_tol=1e-6):status='REFERENCE_CONSISTENT'
        else:status='PYNQ_REFERENCE_MISMATCH'
    declarations=[]
    for item in snapshot.get('device_tree_declarations',[]):
        hz=item.get('declared_hz');number(hz,'DEVICE_TREE_REFERENCE')
        declarations.append(dict(declared_hz=hz,agrees_with_selected_reference=math.isclose(hz/1e6,ref,rel_tol=1e-6),physical_measurement=False))
    if 'device_tree_ps_clk_frequency_hz' in snapshot:
        hz=snapshot['device_tree_ps_clk_frequency_hz'];number(hz,'DEVICE_TREE_REFERENCE')
        declarations.append(dict(declared_hz=hz,agrees_with_selected_reference=math.isclose(hz/1e6,ref,rel_tol=1e-6),physical_measurement=False))
    if any(not d['agrees_with_selected_reference'] for d in declarations):status='REFERENCE_EVIDENCE_CONFLICT'
    return dict(schema='ZYNQ_CLOCK_REFERENCE_RESULT_V1',status=status,reference_mhz=ref,reference_source=reference_source,pynq_reference_mhz=runtime_ref,reported_fclk0_mhz=snapshot.get('reported_fclk0_mhz'),expected_pynq_getter_mhz=expected,register_derived_fclk0_mhz=derived,source_selector=source,selected_pll=name,pll_fbdiv=fbdiv,pll_locked=locked,pll_bypass=bypass,divisor0=div0,divisor1=div1,formula='reference_mhz * (1 if bypass else PLL_FDIV) / DIVISOR0 / DIVISOR1',device_tree_comparisons=declarations,physical_measurement=False,hardware_access=False,hardware_writes=0,clock_configuration_changed=False,scope='Offline register/reference calculation, not frequency measurement, timing closure or board acceptance')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--snapshot',required=True);p.add_argument('--reference-mhz',required=True,type=float);p.add_argument('--reference-source',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    value=audit(load(a.snapshot),a.reference_mhz,a.reference_source)
    with Path(a.output).open('x',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,indent=2);f.write('\n')
    print(value['status'])
