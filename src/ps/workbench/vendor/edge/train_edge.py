"""Reproducible local development training, no board IO or deployment."""
from pathlib import Path
import sys,json,argparse,hashlib
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT/'backend'))
from custom_ai_data import read_splits,normalize
from custom_ai_training import train_bundle
from custom_ai_evaluation import evaluate
from custom_ai_core import canonical

def run(data,output):
    data=Path(data).resolve();out=Path(output).resolve()
    if out==data or data in out.parents or out in data.parents:raise ValueError('OUTPUT_OVERLAPS_INPUT')
    out.mkdir(parents=True,exist_ok=False);original=read_splits(data)
    splits={k:normalize(v) if k!='controls_only' else v for k,v in original.items()}
    def progress(target,done,total):print('TRAIN_CV',target,done,'/',total,flush=True)
    bundle,oof=train_bundle(splits['train'],progress)
    report,predictions=evaluate(bundle,splits,oof)
    for name,value in [('model_bundle.json',bundle),('evaluation.json',report),('grouped_oof.json',oof)]:
        (out/name).write_bytes(canonical(value)+b'\n')
    for name,rows in predictions.items():(out/(name+'.jsonl')).write_bytes(b''.join(canonical(r)+b'\n' for r in rows))
    receipt=dict(status='TRAINED_AND_EVALUATED_OFFLINE_CANDIDATE',model_sha256=bundle['model_sha256'],
        model_file_sha256=hashlib.sha256((out/'model_bundle.json').read_bytes()).hexdigest(),
        source_data_manifest_sha256=hashlib.sha256((data/'data_sha256.json').read_bytes()).hexdigest(),
        raw_training_flags_rewritten=False,training_performed=True,
        training_context='User requested complete local EdgeAI software development; historical source flags preserved',
        hardware_access=False,new_STARTs=0,deployed=False,hardware_acceleration_accepted=False)
    (out/'training_receipt.json').write_bytes(canonical(receipt)+b'\n')
    print(json.dumps(receipt,indent=2),flush=True)
    for t,r in report['targets'].items():print(t,'CV',r['grouped_CV_raw'],'VALIDATION',r['validation']['selective'],flush=True)
    return bundle,report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data',default=str(ROOT/'data'));p.add_argument('--output',required=True);a=p.parse_args();run(a.data,a.output)
