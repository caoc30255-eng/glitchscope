"""Deterministic small forests. Group bagging and held-out coordinate CV."""
import hashlib,math,collections,copy
from custom_ai_core import FEATURES,TARGETS,CONTEXT,SCHEMA,canonical,digest,hull,within_polygon,tree_tuple,tree_score,interval,require

CONFIG=dict(trees=31,depth=4,min_leaf=3,seed=20261025,bootstrap_unit='phase_width_group')

class Draws:
    def __init__(self,seed):self.seed=seed;self.counter=0
    def below(self,n):
        require(type(n) is int and n>0,'DRAW_BOUND')
        limit=2**256-(2**256%n)
        while True:
            word=int.from_bytes(hashlib.sha256(('%d:%d'%(self.seed,self.counter)).encode('ascii')).digest(),'big');self.counter+=1
            if word<limit:return word%n
    def sample(self,n,k):
        pool=list(range(n));out=[]
        for unused in range(k):out.append(pool.pop(self.below(len(pool))))
        return sorted(out)

def fit_tree(rows,depth,min_leaf,rng,nfeatures):
    n=len(rows);y=sum(r[1] for r in rows);leaf=dict(n=n,successes=y,value=(y+1)/(n+2))
    if not depth or n<2*min_leaf or y in (0,n):return leaf
    best=None
    for feature in rng.sample(nfeatures,nfeatures if nfeatures<=2 else 3):
        values=sorted(set(r[0][feature] for r in rows))
        for a,b in zip(values,values[1:]):
            t=(a+b)/2;left=[r for r in rows if r[0][feature]<=t];right=[r for r in rows if r[0][feature]>t]
            if min(len(left),len(right))<min_leaf:continue
            loss=sum(2*sum(r[1] for r in side)*(len(side)-sum(r[1] for r in side))/len(side) for side in (left,right))/n
            rank=(round(loss,12),feature,t)
            if best is None or rank<best[0]:best=(rank,left,right)
    if best is None or best[0][0]>=2*y*(n-y)/(n*n)-1e-12:return leaf
    (_,feature,t),left,right=best
    return dict(feature=feature,threshold=t,left=fit_tree(left,depth-1,min_leaf,rng,nfeatures),right=fit_tree(right,depth-1,min_leaf,rng,nfeatures))

def fit(rows,target,seed):
    groups=collections.defaultdict(list)
    for r in rows:groups[r['cv_group']].append(([r['features'][k] for k in FEATURES[target]],int(r['labels'][target])))
    names=sorted(groups);rng=Draws(seed);trees=[]
    for unused in range(CONFIG['trees']):
        sample=[]
        for j in range(len(names)):sample.extend(groups[names[rng.below(len(names))]])
        trees.append(fit_tree(sample,CONFIG['depth'],CONFIG['min_leaf'],rng,len(FEATURES[target])))
    return trees

def support(rows):
    groups=collections.defaultdict(list)
    for r in rows:
        f=r['features'];groups['%d,%d'%(f['d'],f['s'])].append((f['phase'],f['width']))
    return {key:hull(points) for key,points in sorted(groups.items())}

def score_rows(trees,train,rows,target):
    compiled=[tree_tuple(t,len(FEATURES[target])) for t in trees];polygons=support(train);result=[]
    for r in rows:
        f=r['features'];poly=polygons.get('%d,%d'%(f['d'],f['s']),[])
        if not within_polygon((f['phase'],f['width']),poly):result.append(None);continue
        scores=[tree_score(t,[f[k] for k in FEATURES[target]]) for t in compiled];lo,hi=interval(scores)
        result.append(dict(score=sum(scores)/len(scores),lower=lo,upper=hi))
    return result

def screen(oof,target):
    available=[x for x in oof if x['estimate'] is not None]
    pass_cut=fail_cut=None
    for t in sorted({x['estimate']['lower'] for x in available}):
        selected=[x for x in available if x['estimate']['lower']>=t]
        if len({x['cv_group'] for x in selected})>=2 and all(x['label'] for x in selected):pass_cut=t;break
    for t in sorted({x['estimate']['upper'] for x in available},reverse=True):
        selected=[x for x in available if x['estimate']['upper']<=t]
        if len({x['cv_group'] for x in selected})>=2 and all(not x['label'] for x in selected):fail_cut=t;break
    return dict(pass_lower=pass_cut,fail_upper=fail_cut,
        method='Zero observed errors on training grouped-OOF screening subset, at least2 coordinate groups; not a population guarantee',
        thresholds_selected_on_train_OOF=True,selective_OOF_is_not_unbiased_test=True)

def train_bundle(rows,progress=None):
    require(rows and all(r['split']=='train' for r in rows),'ONLY_TRAIN_SPLIT_MAY_FIT')
    require(len({r['uid'] for r in rows})==len(rows),'DUPLICATE_TRAIN_UID')
    target_models={};fold_reports={};coordinates=sorted({r['cv_group'] for r in rows})
    for ti,target in enumerate(TARGETS):
        oof=[]
        for fold,group in enumerate(coordinates):
            train=[r for r in rows if r['cv_group']!=group];test=[r for r in rows if r['cv_group']==group]
            trees=fit(train,target,CONFIG['seed']+ti*1000+fold)
            estimates=score_rows(trees,train,test,target)
            oof.extend(dict(uid=r['uid'],cv_group=group,label=r['labels'][target],estimate=v,train_coordinate_groups=len(coordinates)-1) for r,v in zip(test,estimates))
            if progress:progress(target,fold+1,len(coordinates))
        counts=collections.defaultdict(lambda:[0,0])
        for r in rows:
            point=tuple(r['features'][k] for k in ('d','s','phase','width'));counts[point][0]+=1;counts[point][1]+=int(r['labels'][target])
        target_models[target]=dict(features=list(FEATURES[target]),trees=fit(rows,target,CONFIG['seed']+ti*1000+999),
            support_polygons=support(rows),cells=[dict(point=list(p),n=n,successes=y) for p,(n,y) in sorted(counts.items())],screen=screen(oof,target))
        fold_reports[target]=oof
    bundle=dict(schema=SCHEMA,version='1.0-candidate',context=CONTEXT,targets=target_models,configuration=CONFIG,
        train_rows=len(rows),train_coordinate_groups=len(coordinates),train_sessions=sorted({r['session'] for r in rows}),
        training_data_sha256=digest(rows),features_exclude_postmeasurement_values=True,
        STM_models_exclude_B_ds_features=True,calibrated_probability_claim=False,
        validation_used_for_fit=False,historical_used_for_fit=False,hardware_acceleration_accepted=False,
        disclosure='Public historical development data; model/thresholds use train only; grouped-CV raw estimates diagnostic, screened CV tuned on same train OOF')
    bundle['model_sha256']=digest(bundle)
    return bundle,fold_reports
