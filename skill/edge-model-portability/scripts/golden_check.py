"""Only explicitly declared FLOAT result paths receive an absolute tolerance."""
import argparse,json,math,re,sys
from pathlib import Path
def pairs(items):
    d={}
    for k,v in items:
        if k in d:raise ValueError('DUPLICATE_JSON_KEY')
        d[k]=v
    return d
def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'),object_pairs_hook=pairs,
                      parse_constant=lambda x:(_ for _ in ()).throw(ValueError('NONFINITE_JSON:'+x)))
def walk(expected,actual,paths,tolerance,path=''):
    errors=[];drift=[]
    if type(expected) is not type(actual):return ['TYPE:'+path],drift
    if isinstance(expected,float):
        if not math.isfinite(expected) or not math.isfinite(actual):return ['NONFINITE:'+path],drift
        if expected!=actual:
            difference=abs(expected-actual)
            policy=paths.get(path) if isinstance(paths,dict) else dict(abs=tolerance,rel=0) if path in paths else None
            allowed=max(policy['abs'],policy.get('rel',0)*max(abs(expected),abs(actual))) if policy else 0
            if policy and difference<=allowed:drift.append(dict(path=path,expected=expected,actual=actual,abs_difference=difference,allowed_error=allowed))
            else:errors.append('VALUE:'+path)
    elif isinstance(expected,dict):
        if set(expected)!=set(actual):errors.append('KEYS:'+path)
        for k in expected.keys() & actual.keys():
            e,d=walk(expected[k],actual[k],paths,tolerance,path+'/'+k.replace('~','~0').replace('/','~1'));errors+=e;drift+=d
    elif isinstance(expected,list):
        if len(expected)!=len(actual):errors.append('LENGTH:'+path)
        for i,(a,b) in enumerate(zip(expected,actual)):
            e,d=walk(a,b,paths,tolerance,path+'/'+str(i));errors+=e;drift+=d
    elif expected!=actual:errors.append('VALUE:'+path)
    return errors,drift
def compare(expected,actual,spec):
    if 'fields' in spec:
        paths=spec['fields'];tolerance=None
        if not isinstance(paths,dict):raise ValueError('FIELD_TOLERANCE_MAP')
        for pointer,p in paths.items():
            if not isinstance(pointer,str) or not pointer.startswith('/') or pointer.rsplit('/',1)[-1] in ('action','execution_allowed','status','state','class','budget','remaining','model_sha256'):raise ValueError('EXACT_FIELD_CANNOT_HAVE_TOLERANCE')
            if not isinstance(p,dict) or set(p)-{'abs','rel','unit','rationale'} or not ({'abs','rel'}&set(p)):raise ValueError('FIELD_TOLERANCE_KEYS')
            if type(p.get('unit')) is not str or not p['unit'].strip() or type(p.get('rationale')) is not str or not p['rationale'].strip():raise ValueError('TOLERANCE_UNIT_AND_RATIONALE_REQUIRED')
            for key in ('abs','rel'):
                v=p.get(key,0)
                if type(v) not in (int,float) or not math.isfinite(v) or v<0:raise ValueError('FIELD_TOLERANCE_VALUE')
            if 'abs' not in p:p=dict(p,abs=0);paths=dict(paths);paths[pointer]=p
    else:
        tolerance=spec['absolute_tolerance'];paths=spec['float_result_paths']
        if type(tolerance) not in (int,float) or not math.isfinite(tolerance) or not 0<=tolerance<=1e-4:raise ValueError('INVALID_LEGACY_TOLERANCE')
        if len(set(paths))!=len(paths) or any(not isinstance(p,str) or not p.startswith('/') for p in paths):raise ValueError('NUMERIC_PATHS')
        if any(p.rsplit('/',1)[-1] in ('action','execution_allowed','status','state','class','budget','remaining','model_sha256') for p in paths):raise ValueError('EXACT_FIELD_CANNOT_HAVE_TOLERANCE')
    errors=[];changes=[]
    for k in ['schema','model_sha256']:
        if k not in expected or k not in actual or type(expected[k]) is not type(actual[k]) or expected[k]!=actual[k]:errors.append('METADATA:'+k)
    if not re.fullmatch('[0-9a-f]{64}',expected.get('model_sha256','')):errors.append('MODEL_SHA_FORMAT')
    if set(expected)!=set(actual):errors.append('TOP_LEVEL_KEYS')
    if set(expected)!={'schema','model_sha256','queries'}:errors.append('SCHEMA_KEYS')
    if expected.get('schema')!=1 or type(expected.get('schema')) is not int:errors.append('SCHEMA_VERSION')
    a,b=expected['queries'],actual['queries']
    if not a or len(a)!=len(b):errors.append('QUERY_COUNT')
    seen=set()
    for index,(x,y) in enumerate(zip(a,b)):
        if set(x)!={'id','input','result'} or set(y)!={'id','input','result'}:errors.append('QUERY_KEYS:'+str(index));continue
        if type(x['id']) is not str or x['id'] in seen:errors.append('QUERY_ID:'+str(index))
        seen.add(x['id'])
        e,_=walk(dict(id=x['id'],input=x['input']),dict(id=y['id'],input=y['input']),[],0)
        errors.extend('INPUT:'+str(index)+':'+s for s in e)
        e,d=walk(x['result'],y['result'],paths,tolerance)
        errors.extend('RESULT:'+str(index)+':'+s for s in e)
        if d:changes.append(dict(index=index,numeric_differences=d))
    return dict(passed=not errors,errors=errors,changed_queries=changes,queries=len(a),absolute_tolerance=tolerance,relative_tolerance=0 if tolerance is not None else 'per_field',field_policy=paths if isinstance(paths,dict) else None,
                scope='Declared finite outputs only; not model accuracy, calibration, target identity or hardware speedup acceptance')
def main():
    p=argparse.ArgumentParser();p.add_argument('--golden',required=True);p.add_argument('--actual',required=True);p.add_argument('--spec',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    with Path(a.output).open('x',encoding='utf-8') as f:
        try:r=compare(load(a.golden),load(a.actual),load(a.spec))
        except Exception as e:r=dict(passed=False,error=type(e).__name__,message=str(e))
        json.dump(r,f,indent=2,allow_nan=False)
    print(json.dumps(r));return 0 if r['passed'] else 2
if __name__=='__main__':sys.exit(main())
