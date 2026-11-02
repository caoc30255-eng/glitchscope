from pathlib import Path
import argparse
from run_rtl_cosim import generate
p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args()
root=Path(__file__).resolve().parent;out=Path(a.output).resolve()
if root==out or root in out.parents:raise ValueError('Output must be outside generator directory')
out.mkdir(parents=True,exist_ok=False)
count,cycles=generate(root,out)
print('Prepared cases=%d cycles=%d; no simulator or hardware access'%(count,cycles))
