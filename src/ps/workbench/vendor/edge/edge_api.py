"""Public EdgeAI software API. No board initialization or START entry point."""
from pathlib import Path
import sys,json,hashlib,copy
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parent;BACKEND=ROOT/'backend'
sys.path.insert(0,str(BACKEND))
from custom_ai_core import load_model,query,TARGETS,CONTEXT
from custom_ai_policy import VERSION,validate_policy

def default_model_sha():return json.loads((BACKEND/'models/default.json').read_bytes())['model_file_sha256']

class EdgeAI:
    def __init__(self,model_file_sha256=None):
        self.file_sha=model_file_sha256 or default_model_sha()
        self.model=load_model(BACKEND/'models'/(self.file_sha+'.json'),self.file_sha)
    def predict(self,request):return self.model.predict(request)
    def predict_many(self,requests):return [self.predict(q) for q in requests]
    def policy(self,max_extra_groups=1,allow_rule_fallback=True):
        p=dict(strategy=VERSION,model_file_sha256=self.file_sha,max_extra_groups=max_extra_groups,allow_rule_fallback=allow_rule_fallback)
        validate_policy(p);return p
    def compile(self,request):
        from custom_plan import compile_plan
        request=copy.deepcopy(request)
        if 'edge_ai' not in request:request['edge_ai']=self.policy()
        return compile_plan(request)
    def suggest(self,plan,checked_records,session):
        from custom_refine import suggest
        from learning_domain import digest
        return suggest(plan,checked_records,session,plan['max_records']-len(checked_records),confirmed_domain_sha256=digest(plan['conditions']))
    def capabilities(self):
        from custom_plan import capabilities
        return dict(software_version='1.0-candidate',scanner=capabilities(),model_sha256=self.model.model_sha256,model_file_sha256=self.file_sha,
            model_targets=list(TARGETS),model_context=CONTEXT,
            supported_profiles=sorted(self.model.snapshot['targets']['B_frame_correct']['support_polygons']),
            unsupported_context='Explicit rule fallback or abstention, not an invented model prediction',
            hardware_permission=False,real_AI_speedup_verified=False)

def example_request(target='B_frame_correct',d=3,s=-1,max_records=14,model_sha=None):
    from learning_domain import CELLS
    service=EdgeAI(model_sha)
    return dict(receiver_B=dict(d=d,s=s),mode='TYPE3A_SINGLE',fault=dict(byte=20,bit=0,count=1),
        scan=dict(points=[dict(phase=15,width=1),dict(phase=15,width=30)]),repeats=3,max_records=max_records,
        target=target,refinement=dict(enabled=True,confirmation_repeats=3,candidates=[dict(phase=c['phase'],width=c['width']) for c in CELLS]),
        edge_ai=service.policy(max_extra_groups=1))
