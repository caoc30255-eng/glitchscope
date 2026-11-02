"""Platform-neutral clock-tree diagnosis; normalized facts, never device addresses.

Device adapters supply a finite graph. Ratios are rational, allowing dividers,
MMCM chains and fractional PLLs without adopting any board's fixed reference.
"""
import argparse,json,math
from fractions import Fraction
from pathlib import Path
from audit_clock import load

def require(value,message):
    if not value:raise ValueError(message)
def finite(v,name,zero=False):
    require(type(v) in (int,float) and math.isfinite(v) and (v>=0 if zero else v>0),'INVALID_'+name)
    return float(v)
def integer(v,name):
    require(type(v) is int and 0<v<=2**64-1,'INVALID_'+name);return v
def close(a,b,ppm):return abs(a-b)<=max(abs(a),abs(b))*ppm/1e6
def diagnose(v):
    require(type(v) is dict and v.get('schema')=='CLOCK_TREE_REFERENCE_SNAPSHOT_V1','NORMALIZED_CLOCK_TREE_REQUIRED')
    require(v.get('snapshot_stable') is True,'UNSTABLE_SNAPSHOT')
    require(type(v.get('device')) is str and v['device'].strip(),'DEVICE_DESCRIPTION_REQUIRED')
    roots=v.get('references');nodes=v.get('nodes');clocks=v.get('clocks')
    require(type(roots) is list and 1<=len(roots)<=32,'REFERENCE_LIST_REQUIRED')
    require(type(nodes) is list and len(nodes)<=128,'NODE_LIMIT')
    require(type(clocks) is list and 1<=len(clocks)<=32,'CLOCK_LIST_REQUIRED')
    references={};graph={}
    for r in roots:
        require(type(r) is dict and set(r)<=set(('id','hz','source','confidence','note')),'REFERENCE_FIELDS')
        name=r.get('id');require(type(name) is str and bool(name) and name not in references,'REFERENCE_ID')
        require(type(r.get('source')) is str and bool(r['source'].strip()),'REFERENCE_SOURCE_REQUIRED')
        hz=r.get('hz')
        if hz is not None:finite(hz,'REFERENCE_HZ')
        references[name]=r
    for n in nodes:
        require(type(n) is dict and type(n.get('id')) is str,'NODE_ID')
        require(n['id'] not in references and n['id'] not in graph,'DUPLICATE_NODE')
        require(set(n)<=set(('id','parent','numerator','denominator','kind','note')),'NODE_FIELDS')
        require(type(n.get('parent')) is str,'NODE_PARENT')
        integer(n.get('numerator'),'RATIO_NUMERATOR');integer(n.get('denominator'),'RATIO_DENOMINATOR')
        graph[n['id']]=n
    def resolve(name,visiting=()):
        if name in references:return name,Fraction(1)
        require(name in graph,'UNKNOWN_PARENT:'+str(name));require(name not in visiting,'CLOCK_TREE_CYCLE')
        n=graph[name];source,factor=resolve(n['parent'],visiting+(name,))
        return source,factor*Fraction(n['numerator'],n['denominator'])
    # Validate even unused branches; do not hide malformed or cyclic input.
    for name in graph:resolve(name)
    results=[];seen=set()
    for c in clocks:
        require(type(c) is dict and set(c)<=set(('id','hardware_node','software_node','enabled','software_reference_hz','reported_hz','requested_hz','declaration_hz','tolerance_ppm','tolerance_basis')),'CLOCK_FIELDS')
        name=c.get('id');require(type(name) is str and bool(name) and name not in seen,'CLOCK_ID');seen.add(name)
        require(type(c.get('enabled')) is bool,'CLOCK_ENABLE_FACT_REQUIRED')
        ppm=finite(c.get('tolerance_ppm'),'TOLERANCE_PPM');require(ppm<=10000,'TOLERANCE_ABOVE_ONE_PERCENT_REQUIRES_SPECIALIZED_REVIEW')
        require(type(c.get('tolerance_basis')) is str and bool(c['tolerance_basis'].strip()),'TOLERANCE_BASIS_REQUIRED')
        source,hardware_ratio=resolve(c['hardware_node'])
        sw_source,software_ratio=resolve(c.get('software_node',c['hardware_node']))
        require(source==sw_source,'DIFFERENT_ROOTS_REQUIRE_DEVICE_SPECIFIC_GETTER_MODEL')
        r=references[source];ref=r.get('hz');reported=c.get('reported_hz');requested=c.get('requested_hz');declaration=c.get('declaration_hz');soft_ref=c.get('software_reference_hz')
        for value,label in [(reported,'REPORTED_HZ'),(requested,'REQUESTED_HZ'),(declaration,'DECLARATION_HZ')]:
            if value is not None:finite(value,label,True)
        if soft_ref is not None:finite(soft_ref,'SOFTWARE_REFERENCE')
        issues=[];actions=[]
        if ref is None:
            expected=None;issues.append('MISSING_BOARD_REFERENCE');actions.append('Obtain the reference frequency and provenance from this device schematic, clock chip configuration or an independent measurement.')
        else:expected=float(Fraction(str(ref))*hardware_ratio) if c['enabled'] else 0.0
        getter=float(Fraction(str(soft_ref))*software_ratio) if soft_ref is not None else None
        if not c['enabled']:
            issues.append('CLOCK_DISABLED');actions.append('Review the enable/gating state and downstream clock domain; changing a reference constant cannot enable a stopped clock.')
        if ref is not None and soft_ref is not None and not close(ref,soft_ref,ppm):
            issues.append('SOFTWARE_REFERENCE_MISMATCH');actions.append('Align the software frequency model with the documented device reference, preserving the intended divisor configuration; review every setter caller before any change.')
        if reported is not None and getter is not None and not close(reported,getter,ppm):
            issues.append('READBACK_OR_GETTER_MODEL_MISMATCH');actions.append('Inspect the installed getter, units, selected clock source and snapshot timing; do not infer a reference error alone.')
        if reported is not None and expected is not None and not close(reported,expected,ppm):issues.append('REPORTED_VS_CONFIGURED_TREE_DIFFERENCE')
        if requested is not None and reported is not None and not close(requested,reported,ppm):
            issues.append('REQUEST_VS_READBACK_DIFFERENCE');actions.append('Check available divisor quantization, Overlay/HWH reconfiguration order and whether the intended setter acted on this clock domain.')
        if declaration is not None and expected is not None and not close(declaration,expected,ppm):
            issues.append('DECLARATION_VS_TREE_DIFFERENCE');actions.append('Review HWH/device-tree clock declarations and whether the reference or source selection changed; declarations and kernel caches are not physical measurements.')
        status='REVIEW_REQUIRED' if issues else 'CONFIGURATION_AND_READBACK_CONSISTENT'
        results.append(dict(id=name,status=status,issues=issues,next_actions=actions,reference_id=source,reference_source=r['source'],reference_hz=ref,hardware_ratio=dict(numerator=hardware_ratio.numerator,denominator=hardware_ratio.denominator),software_ratio=dict(numerator=software_ratio.numerator,denominator=software_ratio.denominator),register_tree_derived_hz=expected,software_getter_expected_hz=getter,reported_hz=reported,requested_hz=requested,declaration_hz=declaration,tolerance_ppm=ppm,tolerance_basis=c['tolerance_basis'],physical_measurement=False))
    return dict(schema='CLOCK_TREE_DIAGNOSIS_V1',device=v['device'],status='REVIEW_REQUIRED' if any(c['issues'] for c in results) else 'CONFIGURATION_AND_READBACK_CONSISTENT',clocks=results,hardware_access=False,hardware_writes=0,automatic_repair_performed=False,physical_measurement=False,scope='Conditional diagnosis of user/adapter-supplied clock facts; the graph and reference provenance are not independently certified by this calculator')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--snapshot',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    require(Path(a.snapshot).stat().st_size<=2*1024*1024,'INPUT_TOO_LARGE')
    value=diagnose(load(a.snapshot))
    with Path(a.output).open('x',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,indent=2);f.write('\n')
    print(value['status'])
