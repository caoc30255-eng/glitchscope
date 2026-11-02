"""Python/JSON command entrypoints, deliberately no actual-hardware command."""
import argparse,json
from pathlib import Path
from custom_plan import capabilities,compile_plan,raw,require

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['capabilities','compile','run-model']);p.add_argument('--input');p.add_argument('--output',required=True)
    a=p.parse_args();out=Path(a.output).resolve();require(not out.exists(),'NEW_OUTPUT_REQUIRED')
    if a.action=='capabilities':result=capabilities()
    else:
        require(a.input is not None,'INPUT_JSON_REQUIRED');data=Path(a.input).read_bytes();require(len(data)<=256*1024,'INPUT_TOO_LARGE')
        request=json.loads(data);result=compile_plan(request)
        if a.action=='run-model':
            require(result['status']=='ACCEPTED','REJECTED_PLAN_NOT_EXECUTABLE')
            from custom_model import ModelHarness
            h=ModelHarness(result['plan'],out)
            try:
                result=h.run()
                # Refinement always waits for an explicit caller selection; CLI
                # does not silently allocate or consume it.
                if result['state']=='AWAITING_SELECTION':h.owner.request_stop();result=h.owner.status()
                h.save()
                (out/'run_result.json').write_bytes(raw(result)+b'\n')
            finally:h.close()
            print(json.dumps(result,indent=2));raise SystemExit(2 if result['state'].startswith('BLOCKED') else 0)
    with out.open('xb') as f:f.write(raw(result)+b'\n')
    print(json.dumps(result,indent=2))
    if result.get('status')=='REJECTED':raise SystemExit(2)
