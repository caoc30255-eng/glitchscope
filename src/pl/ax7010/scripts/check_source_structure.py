"""Static text/port checks, not an HDL compiler, elaborator or simulator."""
from pathlib import Path
import re,json,hashlib
ROOT=Path(__file__).resolve().parents[1]
def clean(s):return re.sub(r'/\*.*?\*/|//[^\n]*','',s,flags=re.S)
def balanced(s,p):
    assert s[p]=='('
    depth=1;i=p+1
    while depth:
        assert i<len(s),'Unbalanced parentheses'
        depth+=(s[i]=='(')-(s[i]==')');i+=1
    return s[p+1:i-1],i
names=(ROOT/'rtl/sources.txt').read_text(encoding='utf-8').split()
assert len(names)==len(set(names))==49
texts={name:clean((ROOT/'rtl'/name).read_bytes().decode('latin1')) for name in names}
goldens={p.name:clean(p.read_bytes().decode('latin1')) for p in (ROOT/'sim/golden').glob('*.v')}
modules={};module_files={}
for name,s in {**texts,**goldens}.items():
    for m in re.finditer(r'\bmodule\s+(\w+)\s*',s):
        p=m.end()
        if s[p]=='#':_,p=balanced(s,s.index('(',p))
        p=s.index('(',p);header,end=balanced(s,p)
        bare=re.sub(r'\[[^]]*\]','',header)
        ports=set(re.findall(r'\b\w+\b',bare))-set('input output inout wire reg signed unsigned integer logic'.split())
        assert m.group(1) not in modules
        modules[m.group(1)]=ports
        module_files[m.group(1)]=name
        # Bracket pairing text check only; do not claim HDL validity.
        for left,right in (('(',')'),('[',']'),('{','}')):
            assert s.count(left)==s.count(right),(name,left,right)
instances=0;dependencies={}
test_texts={p.name:clean(p.read_bytes().decode('latin1')) for p in (ROOT/'sim').glob('*.v')}
for name,s in {**texts,**goldens,**test_texts}.items():
    for module,ports in modules.items():
        for m in re.finditer(r'\b'+re.escape(module)+r'\b\s*',s):
            if re.search(r'\bmodule\s*$',s[:m.start()]):continue
            p=m.end()
            if p<len(s) and s[p]=='#':_,p=balanced(s,s.index('(',p))
            im=re.match(r'\s*(\w+)\s*\(',s[p:])
            if not im:continue
            dependencies.setdefault(name,set()).add(module)
            body,end=balanced(s,p+im.end()-1)
            connected=re.findall(r'\.([A-Za-z_]\w*)\s*\(',body)
            assert len(connected)==len(set(connected)),(name,module,'duplicate port')
            assert set(connected)<=ports,(name,module,set(connected)-ports)
            required={
                'h1_item_profile_owner_v0_1':{'event_type'},
                'h1_payload_fault_overlay_v0_1':{'target_count'},
                'h1_w19_profile_owner_core_bram_v0_5':{'injection_count'},
                'h1_7010_prestart_observer_axi_v0_1':{'mp_expected','mp_emitted','mp_identity','mp_done'},
            }.get(module,set())
            assert required<=set(connected),(name,module,'missing new input')
            instances+=1
top=modules['h1_ax7010_uart_cdc_sync_board_top_v0_7']
assert top=={'pl_clk_50m','key_n','h1_rx_pin','ctrl_rx_pin','h1_tx_pin','ctrl_tx_pin','w19_tx','fault_mark'}
tcl=(ROOT/'scripts/run_multipoint_component_sim.tcl').read_text(encoding='utf-8')
groups=re.findall(r'set mp_names \{([^}]+)\}',tcl)
assert len(groups)==2
for group,tb in zip(groups,('tb_multipoint_owner_sender_v0_11.v','tb_multipoint_control_profile_v0_11.v')):
    supplied=set(group.split())|{tb}
    for name in supplied:
        for module in dependencies.get(name,set()):
            assert module_files[module] in supplied,(tb,name,'missing dependency',module_files[module])
supplied={'h1_board_reset_handoff_golden_v0_2.v','h1_board_reset_handoff_v0_2.v','tb_reset_ready_registered_v0_12.v'}
for name in supplied:
    for module in dependencies.get(name,set()):
        assert module_files[module] in supplied,(name,'reset component dependency missing',module)
report={'status':'PASS_STATIC_TEXT_AND_PORT_CHECKS_ONLY','RTL_files':len(names),'modules':len(modules),
        'named_instances_checked':instances,'HDL_compilation':False,'HDL_simulation':False,
        'component_source_lists_closed':True,'top_physical_ports_unchanged':True}
(ROOT/'evidence/static_structure_check.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,indent=2))
