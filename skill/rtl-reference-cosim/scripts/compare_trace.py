"""Streaming cycle-by-cycle CSV comparison, including hold values when valid=0."""
import argparse,csv,hashlib,itertools,json,re,sys
from pathlib import Path
def file_sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()
def integer(s):
    s=s.strip()
    if not re.fullmatch(r'(?:0[xX][0-9a-fA-F]+|[0-9]+)',s):raise ValueError('NON_INTEGER_TRACE_VALUE:'+s)
    return int(s,16 if s.lower().startswith('0x') else 10)
def rows(path,signals):
    with Path(path).open(newline='',encoding='utf-8') as f:
        r=csv.DictReader(f)
        required=['case','cycle']+list(signals)
        if r.fieldnames!=required:raise ValueError('TRACE_COLUMNS')
        last_case=-1;last_cycle=-1
        for row in r:
            if None in row or any(v is None for v in row.values()):raise ValueError('TRACE_COLUMN_COUNT')
            values={k:integer(v) for k,v in row.items()};case,cycle=values['case'],values['cycle']
            if case==last_case:
                if cycle!=last_cycle+1:raise ValueError('MISSING_OR_DUPLICATE_CYCLE')
            elif case!=last_case+1 or cycle!=0:raise ValueError('CASE_ORDER_OR_INITIAL_CYCLE')
            for key,bits in signals.items():
                if type(bits) is not int or not 1<=bits<=64 or values[key]>=2**bits:raise ValueError('SIGNAL_WIDTH:'+key)
            last_case,last_cycle=case,cycle
            yield values
def compare(reference,actual,spec):
    if type(spec.get('schema')) is not int or spec.get('schema')!=1:raise ValueError('TRACE_SPEC_SCHEMA')
    signals=spec['signals']
    if not isinstance(signals,dict) or not signals or any(k in ('case','cycle') or not re.fullmatch(r'[a-zA-Z_][a-zA-Z0-9_]*',k) for k in signals):raise ValueError('SIGNAL_SPEC')
    count=0;bad=0;details=[];cases=0;last_case=-1
    for a,b in itertools.zip_longest(rows(reference,signals),rows(actual,signals)):
        if a is None or b is None:raise ValueError('TRACE_LENGTH_MISMATCH')
        count+=1
        if a['case']!=last_case:cases+=1;last_case=a['case']
        if a!=b:
            bad+=1
            if len(details)<20:details.append(dict(row=count,expected=a,actual=b))
    if count==0:raise ValueError('EMPTY_TRACE')
    if spec.get('expected_rows') is not None and count!=spec['expected_rows']:raise ValueError('EXPECTED_ROW_COUNT')
    if spec.get('expected_cases') is not None and cases!=spec['expected_cases']:raise ValueError('EXPECTED_CASE_COUNT')
    return dict(passed=bad==0,compared_cycles=count,cases=cases,mismatched_cycles=bad,first_mismatches=details,
                reference_sha256=file_sha(reference),actual_sha256=file_sha(actual),
                scope='Finite digital traces, not formal proof, timing signoff or hardware acceptance')
def check_log(path,pass_marker,fail_marker):
    lines=Path(path).read_text(encoding='utf-8',errors='replace').splitlines()
    if any(fail_marker in s for s in lines):raise ValueError('SIMULATOR_FAILURE_MARKER')
    if lines.count(pass_marker)!=1:raise ValueError('EXACT_PASS_MARKER_MISSING_OR_DUPLICATE')
def main():
    p=argparse.ArgumentParser();p.add_argument('--reference',required=True);p.add_argument('--actual',required=True);p.add_argument('--spec',required=True);p.add_argument('--output',required=True)
    p.add_argument('--log');p.add_argument('--pass-marker');p.add_argument('--fail-marker',default='SKILL_RTL_FAIL')
    a=p.parse_args()
    with Path(a.output).open('x',encoding='utf-8') as f:
        try:
            if a.log:
                if not a.pass_marker:raise ValueError('PASS_MARKER_REQUIRED')
                check_log(a.log,a.pass_marker,a.fail_marker)
            r=compare(a.reference,a.actual,json.loads(Path(a.spec).read_text(encoding='utf-8')))
        except Exception as e:r=dict(passed=False,error=type(e).__name__,message=str(e))
        json.dump(r,f,indent=2)
    print(json.dumps(r));return 0 if r['passed'] else 2
if __name__=='__main__':sys.exit(main())
