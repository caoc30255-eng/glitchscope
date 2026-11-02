"""Python3.8 standard-library deployment adapter; no training or device IO."""
import json, hashlib, math, copy
from pathlib import Path

TARGETS=('B_frame_correct','STM_payload_correct','STM_business_success')
SCHEMA='GLITCHSCOPE_OSS_FOREST_V1'
STRATEGY='EDGE_AI_OSS_ENTROPY_COVERAGE_V1'
FEATURES={t:(('d','s') if t==TARGETS[0] else ())+('byte','bit','phase','width','count','mode_code') for t in TARGETS}
MODES={'TYPE3A_SINGLE':1,'TYPE3C_CONTIGUOUS':2,'DISABLED':0}
def require(ok,reason):
    if not ok:raise ValueError(reason)
def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')
def digest(v):return hashlib.sha256(canonical(v)).hexdigest()
def validate(q):
    require(type(q) is dict and set(q)=={'schema','receiver_B','fault','payload_sha256','mode','route_mode','target'},'QUERY_FIELDS_NO_POSTMEASUREMENT_INPUTS')
    require(q['schema']=='EDGE_AI_QUERY_V1' and q['target'] in TARGETS and q['mode'] in MODES,'QUERY_SCHEMA_TARGET_MODE')
    b=q['receiver_B'];f=q['fault']
    require(type(b) is dict and set(b)=={'d','s'} and type(f) is dict and set(f)=={'byte','bit','phase','width','count'},'QUERY_PARAMETER_FIELDS')
    require(all(type(v) is int for v in list(b.values())+list(f.values())+[q['route_mode']]),'INTEGER_PARAMETERS_REQUIRED')
    require(b['d'] in (1,2,3,4) and -2<=b['s']<=3-b['d'],'ILLEGAL_DS')
    require(q['route_mode']==0,'ROUTE_ZERO_ONLY')
    require(20<=f['byte']<=275 and 0<=f['bit']<=7,'ILLEGAL_BYTE_BIT')
    require(5<=f['phase']<=44 and 1<=f['width']<=40 and f['phase']+f['width']<=45,'ILLEGAL_PHASE_WIDTH')
    require(0<=f['count']<=256 and f['byte']+f['count']<=276,'ILLEGAL_CONTIGUOUS_RANGE')
    require((q['mode']=='DISABLED' and f['count']==0) or (q['mode']=='TYPE3A_SINGLE' and f['count']==1) or (q['mode']=='TYPE3C_CONTIGUOUS' and f['count']>=1),'MODE_COUNT_MISMATCH')
    s=q['payload_sha256'];require(type(s) is str and len(s)==64 and all(c in '0123456789abcdef' for c in s),'PAYLOAD_SHA')
    return dict(b,**f,mode_code=MODES[q['mode']])
def context(q):
    validate(q)
    return dict(receiver_B=q['receiver_B'],payload_sha256=q['payload_sha256'],mode=q['mode'],route_mode=q['route_mode'],
        **{k:q['fault'][k] for k in ('byte','bit','count')})
def features(q):
    v=validate(q);return [v[k] for k in FEATURES[q['target']]]
def from_condition(c,target):
    return dict(schema='EDGE_AI_QUERY_V1',target=target,receiver_B=copy.deepcopy(c['receiver_B']),
        fault=dict(c['fault'],count=c['count']),mode=c['mode'],route_mode=c['route_mode'],payload_sha256=c['payload_sha256'])
def entropy(p):
    return 0.0 if p in (0.,1.) else -p*math.log(p,2)-(1-p)*math.log(1-p,2)
def tree_score(tree,x):
    while 'value' not in tree:tree=tree['left'] if x[tree['feature']]<=tree['threshold'] else tree['right']
    return tree['value']
def hull(points):
    p=sorted(set(tuple(x) for x in points))
    if len(p)<2:return p
    def cross(o,a,b):return (a[0]-o[0])*(b[1]-o[1])-(a[1]-o[1])*(b[0]-o[0])
    lo=[];hi=[]
    for x in p:
        while len(lo)>=2 and cross(lo[-2],lo[-1],x)<=0:lo.pop()
        lo.append(x)
    for x in reversed(p):
        while len(hi)>=2 and cross(hi[-2],hi[-1],x)<=0:hi.pop()
        hi.append(x)
    return lo[:-1]+hi[:-1]
def inside(p,poly):
    if len(poly)==1:return tuple(p)==tuple(poly[0])
    if len(poly)==2:
        a,b=poly
        return (b[0]-a[0])*(p[1]-a[1])==(b[1]-a[1])*(p[0]-a[0]) and all(min(a[i],b[i])<=p[i]<=max(a[i],b[i]) for i in (0,1))
    return bool(poly) and all((b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0])>=0 for a,b in zip(poly,poly[1:]+poly[:1]))
def check_tree(t,n,depth=0):
    require(type(t) is dict and depth<=10,'TREE_DEPTH')
    if 'value' in t:
        require(set(t)=={'value'} and type(t['value']) in (float,int) and math.isfinite(t['value']) and 0<=t['value']<=1,'TREE_LEAF')
    else:
        require(set(t)=={'feature','threshold','left','right'} and type(t['feature']) is int and 0<=t['feature']<n and type(t['threshold']) in (float,int) and math.isfinite(t['threshold']),'TREE_SPLIT')
        check_tree(t['left'],n,depth+1);check_tree(t['right'],n,depth+1)

class PortableForest:
    def __init__(self,path,expected_sha):
        raw=Path(path).read_bytes();require(hashlib.sha256(raw).hexdigest()==expected_sha,'OSS_MODEL_FILE_SHA')
        value=json.loads(raw);require(value['schema']==SCHEMA,'OSS_MODEL_SCHEMA')
        require(value['model_sha256']==digest({k:v for k,v in value.items() if k!='model_sha256'}),'OSS_MODEL_SEMANTIC_SHA')
        require(set(value['targets'])==set(TARGETS),'OSS_TARGETS')
        for target,m in value['targets'].items():
            require(m['features']==list(FEATURES[target]) and 1<=len(m['trees'])<=64,'OSS_FEATURES_TREES')
            for tree in m['trees']:check_tree(tree,len(FEATURES[target]))
            require(bool(m['support']),'EMPTY_SUPPORT')
            for key,s in m['support'].items():
                require(key==digest(s['context']) and s['hull']==[list(p) for p in hull(s['points'])],'SUPPORT_HULL')
        self.__raw=canonical(value);self.model_sha256=value['model_sha256'];self.file_sha256=expected_sha
    @property
    def snapshot(self):return json.loads(self.__raw)
    def raw_score(self,q):
        x=features(q);trees=json.loads(self.__raw)['targets'][q['target']]['trees']
        return sum(tree_score(t,x) for t in trees)/len(trees)
    def predict(self,q):
        out=dict(schema='EDGE_AI_OSS_PREDICTION_V1',action='ABSTAIN',prediction=None,score=None,
            model_sha256=self.model_sha256,score_type='NONE',measurement_claim=False,hardware_permission=False)
        try:
            validate(q);m=json.loads(self.__raw)['targets'][q['target']];support=m['support'].get(digest(context(q)))
            if support is None:return dict(out,reason='UNLEARNED_CONFIGURATION_REQUIRES_SAMPLING')
            if not inside((q['fault']['phase'],q['fault']['width']),support['hull']):return dict(out,reason='OUTSIDE_LEARNED_COORDINATE_HULL')
            score=self.raw_score(q)
            return dict(out,action='ESTIMATE',score=score,score_type='UNCALIBRATED_SKLEARN_FOREST_SCORE',
                reason='MEASUREMENT_REQUIRED',support='EXACT_CONTEXT_COORDINATE_HULL',uncertainty_entropy=entropy(score))
        except (ValueError,KeyError,TypeError) as e:return dict(out,reason=str(e))

def rank(cells,target,model,need,max_extra_groups):
    measured=[x for x in cells if x['per_target'][target]['valid']]
    ranked=[]
    for row in cells:
        c=row['condition'];v=row['per_target'][target];n=v['valid'];y=v['success']
        if n>=max(need,v['required'])*(1+max_extra_groups):continue
        pred=model.predict(from_condition(c,target));p=pred['score']
        if n and v['state']!='MIXED' and (p is None or abs(y/n-p)<=.5):continue
        posterior=(2*p+y)/(2+n) if p is not None else ((y+1)/(n+2) if n else .5)
        novelty=min((sum(abs(c['fault'][k]-m['condition']['fault'][k])/scale for k,scale in [('phase',40.),('width',40.),('byte',256.),('bit',8.)])+abs(c['count']-m['condition']['count'])/256. for m in measured),default=1.)
        novelty=min(1.,novelty)
        # Binary entropy in bits equals upstream's entropy/natural-log(2).
        # Keep exploration for unlearned contexts; don't create model scores.
        priority=(.7*entropy(posterior)+.3*novelty)/(1+.5*n/need)
        ranked.append(dict(condition=c,condition_id=c['condition_id'],priority=round(priority,12),
            model_prediction=pred,model_used=p is not None,current_valid=n,current_success=y,
            reason='MODEL_ENTROPY_AND_COVERAGE' if p is not None else 'UNLEARNED_CONFIGURATION_EXPLORATION'))
    phases={m['condition']['fault']['phase'] for m in measured}
    if len(measured)>=3 and len(phases)==1:
        outside=[r for r in ranked if r['condition']['fault']['phase'] not in phases]
        if outside:ranked=outside
    return sorted(ranked,key=lambda r:(-r['priority'],r['condition_id']))

def load_default():
    folder=Path(__file__).resolve().parent/'models';v=json.loads((folder/'default.json').read_bytes())
    return PortableForest(folder/(v['model_file_sha256']+'.json'),v['model_file_sha256'])
