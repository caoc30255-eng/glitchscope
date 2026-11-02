"""Explicit read-only target collection. Never call a clock setter or device write."""
import argparse,inspect,json,platform
from pathlib import Path
OFFSETS={'ARM_PLL_CTRL':0x100,'DDR_PLL_CTRL':0x104,'IO_PLL_CTRL':0x108,'PLL_STATUS':0x10c,'ARM_CLK_CTRL':0x120,'FPGA0_CLK_CTRL':0x170,'BOOT_MODE':0x25c}

def resolve_clock_api(clocks,ps):
    """Resolve actual class ancestry, not a display-name substitution.

    PYNQ2.4 Clocks inherits the Zynq metaclass implementation; PYNQ2.7
    delegates to a cached _ClocksZynq instance. Neither path sets clocks.
    """
    base=getattr(ps,'_ClocksZynq',None)
    if not isinstance(base,type):raise RuntimeError('ZYNQ_CLOCK_BASE_UNAVAILABLE')
    instance=getattr(clocks,'_instance',None)
    if instance is not None:
        if isinstance(instance,type) or not isinstance(instance,base):raise RuntimeError('UNSUPPORTED_CLOCK_IMPLEMENTATION')
        return instance,'instance_api',getattr(instance,'_ref_clk_mhz',None),'instance._ref_clk_mhz'
    if isinstance(clocks,type) and issubclass(clocks,base):
        return clocks,'legacy_classmethod_api',getattr(clocks,'DEFAULT_SRC_CLK_MHZ',None),'Clocks.DEFAULT_SRC_CLK_MHZ'
    raise RuntimeError('UNSUPPORTED_CLOCK_IMPLEMENTATION')
def collect(read32,metadata):
    first={k:int(read32(o)) for k,o in OFFSETS.items()}
    details=metadata()
    second={k:int(read32(o)) for k,o in OFFSETS.items()}
    return dict(details,schema='ZYNQ_CLOCK_REFERENCE_SNAPSHOT_V1',raw_registers={k:hex(v) for k,v in first.items()},raw_registers_second={k:hex(v) for k,v in second.items()},raw_second_read_matches=first==second,hardware_register_writes=0,Overlay_loaded=False,clock_setter_called=False,new_STARTs=0,physical_measurement=False)
def main():
    p=argparse.ArgumentParser();p.add_argument('--allow-register-read',action='store_true');a=p.parse_args()
    if not a.allow_register_read:raise SystemExit('Explicit read-only target collection flag required')
    if platform.machine()!='armv7l':raise SystemExit('Zynq7000 armv7l target required; no PYNQ imported')
    import pynq
    from pynq import Clocks,MMIO
    import pynq.ps as ps
    implementation,style,reference,origin=resolve_clock_api(Clocks,ps)
    def metadata():
        dt=[];base=Path('/sys/firmware/devicetree/base')
        if base.is_dir():
            for path in base.rglob('ps-clk-frequency'):
                b=path.read_bytes()
                if len(b)!=4:raise ValueError('UNEXPECTED_DT_REFERENCE_WIDTH')
                dt.append(dict(path=str(path),declared_hz=int.from_bytes(b,'big')))
        code={}
        for name in ('get_pll_mhz','get_pl_clk'):
            try:code[name]=inspect.getsource(getattr(implementation,name))
            except (OSError,TypeError,AttributeError):code[name]='SOURCE_UNAVAILABLE'
        return dict(pynq_version=getattr(pynq,'__version__',None),ps_module=str(ps.__file__),clock_class=ps._ClocksZynq.__name__,clock_api_style=style,clock_api_type=type(Clocks).__name__,clock_implementation_type=type(implementation).__name__,clock_reference_origin=origin,pynq_instance_reference_mhz=reference,reported_fclk0_mhz=float(Clocks.fclk0_mhz),reported_cpu_mhz=float(Clocks.cpu_mhz),device_tree_declarations=dt,clock_implementation_source=code)
    regs=MMIO(0xf8000000,0x300)
    print(json.dumps(collect(regs.read,metadata),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
