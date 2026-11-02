"""Compile exported emlearn C, compare integer-domain predictions offline."""
from pathlib import Path
import sys,json,subprocess,hashlib,argparse,random,math
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'oss')]
from portable import PortableForest,TARGETS,features,canonical,entropy
from train_oss import query_row
from feedback_oss import load_splits
from upstream import fit,utilities,CONFIG
PAYLOAD=hashlib.sha256(bytes(range(256))).hexdigest()
def run(training,output,compiler):
    training=Path(training).resolve();out=Path(output).resolve()
    for source in (ROOT,training):
        if out==source or source in out.parents or out in source.parents:raise ValueError('OUTPUT_OVERLAPS_INPUT_OR_PACKAGE')
    out.mkdir(parents=True,exist_ok=False)
    modelpath=training/'model_bundle.json';sha=hashlib.sha256(modelpath.read_bytes()).hexdigest();model=PortableForest(modelpath,sha)
    source='#include <stdio.h>\n'+''.join('#include "'+str((training/('oss_'+t.lower()+'.h')).resolve()).replace('\\','/')+'"\n' for t in TARGETS)
    source+='int main(void){int t;float x[8];while(scanf("%d",&t)==1){if(t<0||t>2)return 3;int n=t==0?8:6;for(int i=0;i<n;i++){if(scanf("%f",&x[i])!=1)return 4;}float p=0;'
    for ti,target in enumerate(TARGETS):source+='if(t=='+str(ti)+')p=oss_'+target.lower()+'_predict(x,n);'
    source+='printf("%.9g\\n",p);}return 0;}\n'
    c=out/'probe.c';c.write_text(source,encoding='ascii');exe=out/('probe.exe' if sys.platform=='win32' else 'probe')
    result=subprocess.run([compiler,'-std=c99','-O2',str(c),'-o',str(exe)],capture_output=True)
    (out/'compiler.log').write_bytes(result.stdout+result.stderr);result.check_returncode()
    vectors=[]
    for d in range(1,5):
        for s in range(-2,4-d):
            for p in range(5,45):
                for w in range(1,41):
                    if p+w>45:continue
                    for target in TARGETS:vectors.append(dict(schema='EDGE_AI_QUERY_V1',target=target,receiver_B=dict(d=d,s=s),fault=dict(byte=20,bit=0,count=1,phase=p,width=w),mode='TYPE3A_SINGLE',route_mode=0,payload_sha256=PAYLOAD))
    rng=random.Random(20261026)
    for i in range(1000):
        d=rng.randint(1,4);s=rng.randint(-2,3-d);p=rng.randint(5,44);w=rng.randint(1,min(40,45-p));byte=rng.randint(20,275);mode=rng.choice(['TYPE3A_SINGLE','TYPE3C_CONTIGUOUS','DISABLED']);count=0 if mode=='DISABLED' else 1 if mode=='TYPE3A_SINGLE' else rng.randint(1,276-byte)
        for target in TARGETS:vectors.append(dict(schema='EDGE_AI_QUERY_V1',target=target,receiver_B=dict(d=d,s=s),fault=dict(byte=byte,bit=rng.randint(0,7),count=count,phase=p,width=w),mode=mode,route_mode=0,payload_sha256=PAYLOAD))
    stdin=''.join(str(TARGETS.index(q['target']))+' '+' '.join(map(str,features(q)))+'\n' for q in vectors).encode('ascii')
    result=subprocess.run([str(exe)],input=stdin,capture_output=True,check=True);cscores=[float(x) for x in result.stdout.splitlines()]
    assert len(cscores)==len(vectors)
    py=[model.raw_score(q) for q in vectors];diff=max(abs(a-b) for a,b in zip(py,cscores));assert diff<=2e-6,diff
    # Compare actual upstream sklearn fitted estimators to portable output,
    # and actual skactiveml entropy to stdlib entropy (normalized to bits).
    splits=load_splits(ROOT/'data');train=splits['train'];skdiff=entdiff=0.;checks=0
    for ti,target in enumerate(TARGETS):
        qs=[query_row(r,target) for r in train];X=[features(q) for q in qs];y=[int(r['labels'][target]) for r in train]
        clf=fit(X,y,CONFIG['random_state']+ti*1000)
        candidates=[features(q) for q in vectors[ti::3]]
        ss=clf.predict_proba(candidates)[:,1];expected=py[ti::3]
        skdiff=max(skdiff,max(abs(float(a)-b) for a,b in zip(ss,expected)))
        _,u=utilities(clf,X,y,candidates)
        entdiff=max(entdiff,max(abs(float(a)/math.log(2)-entropy(float(p))) for a,p in zip(u,ss)))
        checks+=len(candidates)
    assert skdiff<=1e-12 and entdiff<=1e-12,(skdiff,entdiff)
    report=dict(status='PASS_SKLEARN_PORTABLE_EMLEARN_C_AND_UPSTREAM_ENTROPY',integer_domain_queries=len(vectors),
        C_max_abs_score_error=diff,sklearn_max_abs_score_error=skdiff,entropy_max_abs_error=entdiff,
        compiled_export_sha256=hashlib.sha256(exe.read_bytes()).hexdigest(),compiler=compiler,
        sklearn_entropy_checks=checks,upstream_directly_imported=True,
        C_cross_compiled_for_ARM=False,actual_ARM_run=False,hardware_access=False,new_STARTs=0,
        unsupported_raw_score_test_is_not_prediction_permission=True)
    (out/'report.json').write_bytes(canonical(report)+b'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--training',required=True);p.add_argument('--output',required=True);p.add_argument('--compiler',required=True);a=p.parse_args();run(a.training,a.output,a.compiler)
