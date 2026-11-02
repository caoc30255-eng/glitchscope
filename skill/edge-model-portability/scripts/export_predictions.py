"""Execute the selected runner; never read or copy golden results."""
import argparse,hashlib,json
from pathlib import Path
from inference_bench import load_runner
def main():
    p=argparse.ArgumentParser();p.add_argument('--runner',required=True);p.add_argument('--queries',required=True);p.add_argument('--output',required=True);p.add_argument('--model-artifact');a=p.parse_args()
    # Reserve output before loading executable runner code.
    with Path(a.output).open('x',encoding='utf-8') as f:
        predict,receipt=load_runner(a.runner,a.model_artifact);sha=receipt['model_sha256']
        queries=json.loads(Path(a.queries).read_text(encoding='utf-8'))
        result=dict(schema=1,model_sha256=sha,queries=[dict(id='q'+str(i),input=q,result=predict(q)) for i,q in enumerate(queries)])
        json.dump(result,f,indent=2,allow_nan=False)
    print('PREDICTIONS_EXPORTED',len(queries),'MODEL_OR_RUNNER_IDENTITY_SHA256',sha)
if __name__=='__main__':main()
