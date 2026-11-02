"""Execution-bound refinement gates on new isolated register models."""
import argparse,copy,json
from pathlib import Path
from custom_plan import compile_plan,raw,require
from custom_model import ModelHarness
from tests_backend import request

def run(output):
    output=Path(output);output.mkdir(parents=True,exist_ok=False);all_results=[]
    for name,limit in [('insufficient_confirmation_budget',6),('changed_selection_before_effect',7)]:
        r=request(repeats=3,limit=limit,refine=True);p=compile_plan(r)['plan'];h=ModelHarness(p,output/name);h.mixed_faults=True
        try:
            result=h.run()
            if name=='insufficient_confirmation_budget':require(result['state']=='STOPPED_BUDGET' and result['attempts']==5,'NO_PARTIAL_CONFIRMATION_ALLOWED')
            else:
                require(result['state']=='AWAITING_SELECTION','EXPECTED_BOUNDARY_WAIT')
                proposal=h.owner.next_suggestion();proposal['condition']['fault']['width']=4
                result=h.step('changed_selection_0001',proposal)
                require(result['state']=='BLOCKED_INPUT' and result['attempts']==5,'CHANGED_SELECTION_MUST_NOT_START')
            h.save();(output/name/'result.json').write_bytes(raw(result)+b'\n');all_results.append(dict(case=name,**result))
            print(name,result['state'],result['attempts'],flush=True)
        finally:h.close()
    (output/'summary.json').write_bytes(raw(all_results)+b'\n')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();run(a.output)
