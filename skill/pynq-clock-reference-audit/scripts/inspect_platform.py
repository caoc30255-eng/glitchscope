"""Software-only discovery for an unknown PYNQ installation; does not import PYNQ."""
import argparse,ast,hashlib,importlib.util,json,platform
from pathlib import Path
def inspect_platform():
    value=dict(schema='PYNQ_PLATFORM_DISCOVERY_V1',machine=platform.machine(),python=platform.python_version(),pynq_imported=False,MMIO_mapped=False,hardware_writes=0,physical_measurement=False)
    for root in (Path('/sys/firmware/devicetree/base'),Path('/proc/device-tree')):
        if root.is_dir():
            value['device_tree_root']=str(root)
            for name in ('model','compatible'):
                p=root/name
                if p.is_file():value[name]=p.read_bytes().decode('utf-8','replace').strip('\x00').split('\x00')
            break
    try:spec=importlib.util.find_spec('pynq')
    except (ImportError,ValueError) as e:spec=None;value['discovery_error']=str(e)
    if spec and spec.origin:
        base=Path(spec.origin).parent;ps=base/'ps.py';value['pynq_package']=str(base)
        if ps.is_file() and ps.stat().st_size<=4*1024*1024:
            data=ps.read_bytes();value['ps_source_sha256']=hashlib.sha256(data).hexdigest();value['ps_source_file']=str(ps)
            try:
                tree=ast.parse(data.decode('utf-8'));constants=[]
                for cls in tree.body:
                    if isinstance(cls,ast.ClassDef):
                        for stmt in cls.body:
                            if isinstance(stmt,ast.Assign) and any(isinstance(n,ast.Name) and n.id=='DEFAULT_SRC_CLK_MHZ' for n in stmt.targets):
                                try:v=ast.literal_eval(stmt.value)
                                except (ValueError,TypeError):v='NON_LITERAL'
                                constants.append(dict(class_name=cls.name,declared_default_mhz=v))
                value['source_default_declarations_not_live_values']=constants
            except (SyntaxError,UnicodeError) as e:value['source_parse_error']=str(e)
    compatible=value.get('compatible',[])
    value['suggested_adapter']='zynq7000_readonly' if 'xlnx,zynq-7000' in compatible else ('normalized_clock_tree_profile_required' if 'xlnx,zynqmp' in compatible else 'device_specific_clock_profile_required')
    value['next_steps']=['Confirm the exact hardware model and reference clock from its documentation.','Choose a reviewed device-specific read-only adapter or export a normalized clock tree.','Do not infer the runtime reference from an on-disk default or OS device-tree declaration alone.']
    return value
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args()
    with Path(a.output).open('x',encoding='utf-8') as f:json.dump(inspect_platform(),f,ensure_ascii=False,indent=2);f.write('\n')
