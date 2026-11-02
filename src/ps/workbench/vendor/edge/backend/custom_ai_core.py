"""Portable, immutable inference. Scores are not hardware reliability estimates."""
import json,hashlib,math,copy
from pathlib import Path

TARGETS=('B_frame_correct','STM_payload_correct','STM_business_success')
FEATURES={'B_frame_correct':('d','s','phase','width'),
          'STM_payload_correct':('phase','width'),'STM_business_success':('phase','width')}
CONTEXT=dict(mode='TYPE3A_SINGLE',route_mode=0,byte=20,bit=0,count=1,
    payload_sha256='40aff2e9d2d8922e47afd4648e6967497158785fbd1da870e7110266bf944880')
SCHEMA='GLITCHSCOPE_EDGE_AI_FOREST_V1'

def require(ok,reason):
    if not ok:raise ValueError(reason)
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')
def digest(value):return hashlib.sha256(canonical(value)).hexdigest()
def file_sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def pairs(values):
    out={}
    for k,v in values:require(k not in out,'DUPLICATE_JSON_KEY');out[k]=v
    return out
def load_json(path):
    raw=Path(path).read_bytes();require(len(raw)<=4*1024*1024,'JSON_SIZE_LIMIT')
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda v:(_ for _ in ()).throw(ValueError('NONFINITE_JSON')))

def hull(points):
    points=sorted(set(tuple(p) for p in points))
    if len(points)<=1:return points
    def cross(o,a,b):return (a[0]-o[0])*(b[1]-o[1])-(a[1]-o[1])*(b[0]-o[0])
    lo=[];hi=[]
    for p in points:
        while len(lo)>=2 and cross(lo[-2],lo[-1],p)<=0:lo.pop()
        lo.append(p)
    for p in reversed(points):
        while len(hi)>=2 and cross(hi[-2],hi[-1],p)<=0:hi.pop()
        hi.append(p)
    return lo[:-1]+hi[:-1]

def within_polygon(point,poly):
    if not poly:return False
    if len(poly)==1:return tuple(point)==tuple(poly[0])
    if len(poly)==2:
        a,b=poly;p=point
        return (b[0]-a[0])*(p[1]-a[1])==(b[1]-a[1])*(p[0]-a[0]) and all(min(a[i],b[i])<=p[i]<=max(a[i],b[i]) for i in (0,1))
    return all((b[0]-a[0])*(point[1]-a[1])-(b[1]-a[1])*(point[0]-a[0])>=0 for a,b in zip(poly,poly[1:]+poly[:1]))

def query(d=3,s=-1,phase=15,width=10,target='B_frame_correct',byte=20,bit=0,count=1,
          payload_sha256=CONTEXT['payload_sha256'],mode='TYPE3A_SINGLE',route_mode=0):
    return dict(schema='EDGE_AI_QUERY_V1',receiver_B=dict(d=d,s=s),fault=dict(byte=byte,bit=bit,count=count,phase=phase,width=width),
        payload_sha256=payload_sha256,mode=mode,route_mode=route_mode,target=target)

def validate_query(q):
    require(type(q) is dict and set(q)=={'schema','receiver_B','fault','payload_sha256','mode','route_mode','target'},'QUERY_FIELDS_NO_POSTMEASUREMENT_INPUTS')
    require(q['schema']=='EDGE_AI_QUERY_V1' and q['target'] in TARGETS,'QUERY_SCHEMA_OR_TARGET')
    b=q['receiver_B'];f=q['fault']
    require(type(b) is dict and set(b)=={'d','s'} and type(f) is dict and set(f)=={'byte','bit','count','phase','width'},'QUERY_PARAMETER_FIELDS')
    require(all(type(v) is int for v in list(b.values())+list(f.values())+[q['route_mode']]),'INTEGER_PARAMETERS_REQUIRED')
    require(b['d'] in (1,2,3,4) and -2<=b['s']<=3-b['d'],'ILLEGAL_DS')
    require(20<=f['byte']<=275 and 0<=f['bit']<=7 and 0<=f['count']<=256 and f['byte']+f['count']<=276,'ILLEGAL_POSITION_COUNT')
    require(5<=f['phase']<=44 and 1<=f['width']<=40 and f['phase']+f['width']<=45,'ILLEGAL_PHASE_WIDTH')
    require(type(q['payload_sha256']) is str and len(q['payload_sha256'])==64,'PAYLOAD_SHA')
    return dict(b,phase=f['phase'],width=f['width'])

def tree_tuple(tree,nfeatures,depth=0):
    require(type(tree) is dict and depth<=8,'TREE_STRUCTURE')
    if 'value' in tree:
        require(set(tree)=={'n','successes','value'} and type(tree['n']) is int and tree['n']>0 and type(tree['successes']) is int and 0<=tree['successes']<=tree['n'],'LEAF_COUNTS')
        require(type(tree['value']) in (int,float) and math.isfinite(tree['value']) and abs(tree['value']-(tree['successes']+1)/(tree['n']+2))<1e-12,'LEAF_SCORE')
        return ('leaf',float(tree['value']))
    require(set(tree)=={'feature','threshold','left','right'} and type(tree['feature']) is int and 0<=tree['feature']<nfeatures and type(tree['threshold']) in (int,float) and math.isfinite(tree['threshold']),'TREE_SPLIT')
    return ('split',tree['feature'],tree['threshold'],tree_tuple(tree['left'],nfeatures,depth+1),tree_tuple(tree['right'],nfeatures,depth+1))

def tree_score(tree,x):
    while tree[0]!='leaf':tree=tree[3] if x[tree[1]]<=tree[2] else tree[4]
    return tree[1]

def interval(scores):
    s=sorted(scores);return s[int((len(s)-1)*.1)],s[int((len(s)-1)*.9)]

class EdgeModel:
    def __init__(self,envelope):
        require(type(envelope) is dict and envelope.get('schema')==SCHEMA,'MODEL_SCHEMA')
        require(envelope.get('model_sha256')==digest({k:v for k,v in envelope.items() if k!='model_sha256'}),'MODEL_SHA_MISMATCH')
        require(envelope['context']==CONTEXT and set(envelope['targets'])==set(TARGETS),'MODEL_CONTEXT_TARGETS')
        self.__raw=canonical(envelope);self.__sha=envelope['model_sha256'];self.__compiled={}
        for target,m in envelope['targets'].items():
            require(m['features']==list(FEATURES[target]) and 1<=len(m['trees'])<=64,'MODEL_FEATURES_OR_TREE_COUNT')
            trees=tuple(tree_tuple(t,len(m['features'])) for t in m['trees'])
            polygons=tuple((k,tuple(tuple(p) for p in v)) for k,v in sorted(m['support_polygons'].items()))
            cells=tuple((tuple(c['point']),c['n'],c['successes']) for c in m['cells'])
            require(len({p for p,n,y in cells})==len(cells) and bool(cells),'DUPLICATE_OR_EMPTY_CELLS')
            for point,n,y in cells:
                require(len(point)==4 and type(n) is int and type(y) is int and 0<=y<=n and n>0,'OBSERVED_COUNTS')
                validate_query(query(d=point[0],s=point[1],phase=point[2],width=point[3],target=target))
            expected_profiles={'%d,%d'%(p[0],p[1]) for p,n,y in cells}
            require({k for k,v in polygons}==expected_profiles,'SUPPORT_PROFILE_CELLS_MISMATCH')
            for key,poly in polygons:
                expected=hull([p[2:] for p,n,y in cells if '%d,%d'%(p[0],p[1])==key])
                require(poly==tuple(expected),'SUPPORT_HULL_CHANGED')
            for key in ('pass_lower','fail_upper'):
                v=m['screen'][key];require(v is None or type(v) in (int,float) and math.isfinite(v) and 0<=v<=1,'SCREEN_THRESHOLD')
            if m['screen']['pass_lower'] is not None and m['screen']['fail_upper'] is not None:
                require(m['screen']['pass_lower']>m['screen']['fail_upper'],'OVERLAPPING_SCREEN_THRESHOLDS')
            self.__compiled[target]=(trees,polygons,cells,m['screen']['pass_lower'],m['screen']['fail_upper'])
        self._state=tuple((k,v) for k,v in sorted(self.__compiled.items()));self.__original_state=self._state
        self.__original_identity=(self.__sha,self.__raw)

    @property
    def model_sha256(self):return self.__sha
    @property
    def snapshot(self):return json.loads(self.__raw)
    def integrity(self):return self._state is self.__original_state and (self.__sha,self.__raw)==self.__original_identity
    def predict(self,q):
        out=dict(schema='EDGE_AI_PREDICTION_V1',action='ABSTAIN',target=q.get('target') if type(q) is dict else None,
            prediction=None,score=None,score_type='NONE',model_sha256=self.__sha,measurement_claim=False,hardware_permission=False)
        if not self.integrity():return dict(out,reason='MODEL_RUNTIME_STATE_CHANGED')
        try:features=validate_query(q)
        except (ValueError,KeyError,TypeError) as e:return dict(out,reason=str(e))
        context=dict(mode=q['mode'],route_mode=q['route_mode'],payload_sha256=q['payload_sha256'],**{k:q['fault'][k] for k in ('byte','bit','count')})
        if context!=CONTEXT:return dict(out,reason='UNSUPPORTED_EXPERIMENT_CONTEXT')
        target=q['target'];trees,polygons,cells,pass_cut,fail_cut=dict(self._state)[target]
        polygon=dict(polygons).get('%d,%d'%(features['d'],features['s']))
        if not polygon:return dict(out,reason='UNSUPPORTED_RECEIVER_PROFILE')
        if not within_polygon((features['phase'],features['width']),list(polygon)):return dict(out,reason='OUTSIDE_TRAINING_CONDITION_HULL')
        x=[features[k] for k in FEATURES[target]];scores=[tree_score(t,x) for t in trees];lo,hi=interval(scores);score=sum(scores)/len(scores)
        key=tuple(features[k] for k in ('d','s','phase','width'));cell=next(((n,y) for p,n,y in cells if p==key),None)
        out.update(action='ESTIMATE',score=score,score_type='UNCALIBRATED_ENSEMBLE_SCORE',ensemble_interval=[lo,hi],
            interval_is_calibrated_confidence=False,training_observation=None if cell is None else dict(n=cell[0],successes=cell[1]),
            training_repeat_disagreement=0.0 if cell is None else 4*(cell[1]/cell[0])*(1-cell[1]/cell[0]),
            support='OBSERVED_TRAINING_CONDITION' if cell else 'UNSEEN_CONDITION_INSIDE_TRAINING_HULL',reason='UNCERTAIN_SCORE_REQUIRES_MEASUREMENT')
        if cell and 0<cell[1]<cell[0]:return dict(out,action='ABSTAIN',reason='TRAINING_REPEAT_CONFLICT')
        if pass_cut is not None and lo>=pass_cut:out.update(action='PREDICT',prediction=True,reason='TRAIN_OOF_SCREEN_ACCEPTED_PASS')
        elif fail_cut is not None and hi<=fail_cut:out.update(action='PREDICT',prediction=False,reason='TRAIN_OOF_SCREEN_ACCEPTED_FAIL')
        return out

def load_model(path,expected_file_sha=None):
    if expected_file_sha is not None:require(file_sha(path)==expected_file_sha,'MODEL_FILE_SHA_CHANGED')
    return EdgeModel(load_json(path))
