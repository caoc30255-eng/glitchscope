"""Install immutable model versions; never silently replace the active default."""
from pathlib import Path
import json,sys,os,contextlib,hashlib
ROOT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT/'backend'))
from custom_ai_core import load_model,require,canonical

def install(training_output):
    folder=Path(training_output).resolve();model=folder/'model_bundle.json';receipt=json.loads((folder/'training_receipt.json').read_bytes())
    sha=hashlib.sha256(model.read_bytes()).hexdigest()
    require(sha==receipt['model_file_sha256'] and receipt['hardware_access'] is False,'TRAINING_RECEIPT_BINDING')
    loaded=load_model(model,sha);require(loaded.model_sha256==receipt['model_sha256'],'MODEL_SEMANTIC_SHA')
    evaluation=json.loads((folder/'evaluation.json').read_bytes())
    require(evaluation['validation_used_for_fit'] is False and evaluation['historical_used_for_fit'] is False,'EVALUATION_LEAK_DECLARATION')
    with contextlib.ExitStack() as stack:
        lock=ROOT.parent/'board_runs/exclusive.lock'
        if sys.platform.startswith('linux') and lock.is_file():
            import fcntl
            f=stack.enter_context(lock.open('rb'));fcntl.flock(f,fcntl.LOCK_SH|fcntl.LOCK_NB)
        target=ROOT/'backend/models'/(sha+'.json')
        if target.exists():require(target.read_bytes()==model.read_bytes(),'MODEL_VERSION_COLLISION')
        else:
            with target.open('xb') as f:f.write(model.read_bytes())
    return dict(status='MODEL_VERSION_REGISTERED',model_file_sha256=sha,model_sha256=loaded.model_sha256,
        default_model_changed=False,hardware_authorization_issued=False,
        note='Select this SHA explicitly in a NEW plan; old live plans retain their pinned model')
