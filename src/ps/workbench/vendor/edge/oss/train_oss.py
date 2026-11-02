"""PC offline train84/evaluate40+30; actual sklearn, scikit-activeml, emlearn."""
from pathlib import Path
import sys,json,hashlib,collections,shutil,argparse,copy,math
from importlib.metadata import version,distribution
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'oss')]
from feedback_oss import load_splits
from portable import TARGETS,FEATURES,SCHEMA,canonical,digest,context,features,hull,inside
from upstream import fit,CONFIG
import emlearn

def query_row(r,target):
    if 'oss_query' in r:return dict(r['oss_query'],target=target)
    return dict(schema='EDGE_AI_QUERY_V1',target=target,receiver_B={k:r['features'][k] for k in ('d','s')},
        fault=dict(byte=r['byte'],bit=r['bit'],count=r['count'],**{k:r['features'][k] for k in ('phase','width')}),
        payload_sha256=r['payload_sha256'],route_mode=r['route_mode'],mode='TYPE3A_SINGLE')
def support(rows,target):
    groups={}
    for r in rows:
        q=query_row(r,target);ctx=context(q);key=digest(ctx)
        groups.setdefault(key,dict(context=ctx,points=[]))['points'].append([q['fault']['phase'],q['fault']['width']])
    for s in groups.values():
        s['points']=sorted({tuple(p) for p in s['points']});s['points']=[list(p) for p in s['points']]
        s['hull']=[list(p) for p in hull(s['points'])]
    return groups
def tree_json(tree,i=0):
    if tree.children_left[i]<0:return dict(value=float(tree.value[i,0,0]))
    return dict(feature=int(tree.feature[i]),threshold=float(tree.threshold[i]),left=tree_json(tree,int(tree.children_left[i])),right=tree_json(tree,int(tree.children_right[i])))
def metrics(rows):
    valid=[r for r in rows if r['supported']]
    return dict(total=len(rows),supported=len(valid),coverage=len(valid)/len(rows) if rows else None,
        accuracy_at_half=sum((r['score']>.5)==r['label'] for r in valid)/len(valid) if valid else None,
        brier=sum((r['score']-r['label'])**2 for r in valid)/len(valid) if valid else None,
        false_PASS=sum((r['score']>.5) and not r['label'] for r in valid),
        scores_are_uncalibrated=True,threshold_is_diagnostic_not_execution_permission=True)
def evaluate(clf,train,test,target):
    ss=support(train,target);out=[]
    qs=[query_row(r,target) for r in test];scores=clf.predict_proba([features(q) for q in qs])[:,1]
    for r,q,p in zip(test,qs,scores):
        s=ss.get(digest(context(q)));out.append(dict(uid=r['uid'],cv_group=r['cv_group'],label=r['labels'][target],score=float(p),
            supported=s is not None and inside((q['fault']['phase'],q['fault']['width']),s['hull'])))
    return out
def run(output,data=None):
    out=Path(output).resolve();data=(Path(data) if data else ROOT/'data').resolve()
    for source in (ROOT,data):
        if out==source or source in out.parents or out in source.parents:raise ValueError('OUTPUT_OVERLAPS_INPUT_OR_PACKAGE')
    splits=load_splits(data);out.mkdir(parents=True,exist_ok=False)
    train=splits['train'];models={};evaluations={};versions={k:version(k) for k in ('scikit-learn','scikit-activeml','emlearn','makefun','numpy','scipy')}
    for ti,target in enumerate(TARGETS):
        print('TRAIN_OSS',target,flush=True);seed=CONFIG['random_state']+ti*1000
        clf=fit([features(query_row(r,target)) for r in train],[int(r['labels'][target]) for r in train],seed)
        reg=clf.estimator_.regressor_;trees=[tree_json(t.tree_) for t in reg.estimators_]
        models[target]=dict(features=list(FEATURES[target]),trees=trees,support=support(train,target))
        cv=[]
        for i,g in enumerate(sorted({r['cv_group'] for r in train})):
            a=[r for r in train if r['cv_group']!=g];b=[r for r in train if r['cv_group']==g]
            c=fit([features(query_row(r,target)) for r in a],[int(r['labels'][target]) for r in a],seed)
            cv.extend(evaluate(c,a,b,target))
        evaluation=dict(grouped_CV=metrics(cv),validation=metrics(evaluate(clf,train,splits['validation'],target)),
            historical=metrics(evaluate(clf,train,splits['historical_test'],target)))
        evaluations[target]=evaluation
        (out/(target+'_grouped_CV.json')).write_bytes(canonical(cv)+b'\n')
        # Regressor output preserves leaf proportions; no silent conversion
        # from sklearn soft probabilities to a majority-voting classifier.
        # emlearn inline uses '<', sklearn uses '<='. All our features are
        # validated integers. A k+0.5 cut preserves sklearn's partition on
        # this integer domain, including queries exactly at a training cut.
        c_reg=copy.deepcopy(reg)
        for estimator in c_reg.estimators_:
            tr=estimator.tree_
            for i in range(tr.node_count):
                if tr.children_left[i]>=0:tr.threshold[i]=math.floor(tr.threshold[i])+.5
        exported=emlearn.convert(c_reg,method='inline',dtype='float')
        exported.save(name='oss_'+target.lower(),file=str(out/('oss_'+target.lower()+'.h')))
        print(json.dumps(evaluation),flush=True)
    bundle=dict(schema=SCHEMA,version='1.1-oss-candidate',targets=models,configuration=CONFIG,
        upstream_versions=versions,train_rows=len(train),train_sessions=sorted({r['session'] for r in train}),
        data_manifest_sha256=hashlib.sha256((data/('OSS_DATASET.json' if (data/'OSS_DATASET.json').exists() else 'data_sha256.json')).read_bytes()).hexdigest(),
        validation_used_for_fit=False,historical_used_for_fit=False,calibrated_probability_claim=False,
        all_configurations_trained=False,hardware_speedup_accepted=False,
        C_export_threshold_adapter='integer features only: sklearn <=t becomes emlearn <floor(t)+0.5',
        C_float_score_tolerance=0.000002)
    bundle['model_sha256']=digest(bundle);raw=canonical(bundle)+b'\n';sha=hashlib.sha256(raw).hexdigest()
    (out/'model_bundle.json').write_bytes(raw)
    (out/'evaluation.json').write_bytes(canonical(dict(targets=evaluations,validation_used_for_fit=False,historical_used_for_fit=False,upstream_versions=versions))+b'\n')
    (out/'training_receipt.json').write_bytes(canonical(dict(status='TRAINED_OSS_OFFLINE_CANDIDATE',model_sha256=bundle['model_sha256'],
        model_file_sha256=sha,training_rows=len(train),hardware_access=False,new_STARTs=0,training_performed=True,
        source_flags_rewritten=False,source='Reviewed immutable training split only; validation and history excluded'))+b'\n')
    # Redistribute the exact required C runtime and licensing notices.
    third=out/'third_party';third.mkdir()
    runtime=Path(emlearn.__file__).parent
    for p in runtime.glob('*.h'):shutil.copy2(p,third/p.name)
    for package in ('emlearn','scikit-activeml','scikit-learn','makefun'):
        dist=distribution(package)
        for p in dist.files or []:
            if any(s in str(p).lower() for s in ('license','copying')) and Path(dist.locate_file(p)).is_file():
                dst=third/package/str(p).replace('../','_parent_/');dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(dist.locate_file(p),dst)
    (out/'versions.json').write_bytes(canonical(versions)+b'\n')
    print('OSS_TRAINED',sha,flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--data');a=p.parse_args();run(a.output,a.data)
