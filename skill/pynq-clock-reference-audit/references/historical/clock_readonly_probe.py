"""Zynq7000 reference-clock audit. Reads only; no Overlay or clock setter."""
import inspect,json,platform,struct,sys
from pathlib import Path
def main():
    if platform.machine()!='armv7l':raise SystemExit('Run on the Zynq7000/PYNQ target; no host MMIO attempted')
    import pynq
    from pynq import Clocks,MMIO
    import pynq.ps as ps
    instance=getattr(Clocks,'_instance',Clocks)
    regs=MMIO(0xf8000000,0x200)
    offsets={'ARM_PLL_CTRL':0x100,'DDR_PLL_CTRL':0x104,'IO_PLL_CTRL':0x108,'PLL_STATUS':0x10c,'ARM_CLK_CTRL':0x120,'FPGA0_CLK_CTRL':0x170}
    first={k:int(regs.read(o)) for k,o in offsets.items()}
    second={k:int(regs.read(o)) for k,o in offsets.items()}
    stable=first==second
    fclk=first['FPGA0_CLK_CTRL'];source=(fclk>>4)&3;div0=(fclk>>8)&63;div1=(fclk>>20)&63
    pll_name=['IO_PLL_CTRL','IO_PLL_CTRL','ARM_PLL_CTRL','DDR_PLL_CTRL'][source]
    ctrl=first[pll_name];fbdiv=(ctrl>>12)&127
    lockbit={'ARM_PLL_CTRL':0,'DDR_PLL_CTRL':1,'IO_PLL_CTRL':2}[pll_name]
    locked=bool((first['PLL_STATUS']>>lockbit)&1)
    bypass=bool(ctrl&16) or (bool(ctrl&8) and not locked)
    candidates=[]
    for ref in (33.333333,50.0):
        hz=None
        if stable and div0 and div1 and not (ctrl&3):hz=ref*(1 if bypass else fbdiv)/(div0*div1)
        candidates.append(dict(assumed_ps_reference_mhz=ref,register_derived_fclk0_mhz=hz,physical_measurement=False))
    dt=[]
    base=Path('/sys/firmware/devicetree/base')
    if base.is_dir():
        for p in base.rglob('ps-clk-frequency'):
            b=p.read_bytes()
            dt.append(dict(path=str(p),declared_hz=int.from_bytes(b,'big'),physical_measurement=False))
    ref=getattr(instance,'_ref_clk_mhz',None)
    sources={}
    for method in ('get_pll_mhz','get_pl_clk'):
        try:sources[method]=inspect.getsource(getattr(type(instance),method))
        except (TypeError,OSError,AttributeError):sources[method]='SOURCE_UNAVAILABLE'
    value=dict(schema='ZYNQ_CLOCK_READONLY_REFERENCE_AUDIT_V1',pynq_version=getattr(pynq,'__version__',None),ps_module=str(ps.__file__),clock_class=type(instance).__name__,pynq_instance_reference_mhz=ref,default_reference_mhz=getattr(type(instance),'DEFAULT_SRC_CLK_MHZ',None),reported_fclk0_mhz=float(Clocks.fclk0_mhz),reported_cpu_mhz=float(Clocks.cpu_mhz),raw_registers={k:hex(v) for k,v in first.items()},raw_second_read_matches=stable,fclk_source_selector=source,selected_pll=pll_name,pll_fbdiv=fbdiv,pll_locked=locked,pll_bypass=bypass,divisor0=div0,divisor1=div1,candidate_calculations=candidates,device_tree_declarations=dt,clock_implementation_source=sources,hardware_register_writes=0,Overlay_loaded=False,clock_setter_called=False,new_STARTs=0,scope='Read-only configuration calculation with two reference hypotheses; not oscilloscope/frequency-counter measurement')
    print(json.dumps(value,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
