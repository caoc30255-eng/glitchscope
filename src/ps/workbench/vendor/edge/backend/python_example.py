"""Preview by default. --run-model explicitly runs an isolated register model."""
import argparse,json
from pathlib import Path
from custom_plan import compile_plan

def example():
    return dict(receiver_B=dict(d=2,s=1),mode='TYPE3A_SINGLE',fault=dict(byte=24,bit=2,count=1),
        scan=dict(phase=dict(start=7,stop=11,step=4),width=[3,9]),repeats=1,max_records=8,target='B_frame_correct')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run-model',action='store_true');p.add_argument('--output');a=p.parse_args()
    preview=compile_plan(example());print(json.dumps(preview,indent=2))
    if a.run_model:
        if not a.output:raise ValueError('NEW_OUTPUT_DIRECTORY_REQUIRED')
        from custom_model import ModelHarness
        h=ModelHarness(preview['plan'],a.output)
        try:print(json.dumps(h.run(),indent=2));h.save()
        finally:h.close()
