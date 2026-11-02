"""Independent ready/valid accumulator reference: six 64-cycle scenarios."""
import csv,argparse,json
from pathlib import Path
def stimulus(case,k):
    reset=k<2 or (case==2 and k in (16,32)) or (case==5 and k==20)
    inv=(k+case)%3!=0
    ready=True
    if case==1:inv=True
    if case==3:ready=k%5 not in (0,1)
    if case in (4,5):ready=not 10<=k<30;inv=True
    value=(k*7+case*11)&255 if case!=1 else 250
    return reset,inv,ready,value
def generate(output):
    out=Path(output);out.mkdir()
    with (out/'reference.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.writer(f);w.writerow(['case','cycle','ready','valid','data','acc'])
        for case in range(6):
            acc=data=0;valid=False
            for k in range(64):
                reset,inv,ready,value=stimulus(case,k)
                accepting=(not valid) or ready
                if reset:acc=data=0;valid=False
                elif accepting:
                    valid=inv
                    if inv:acc=(acc+value)&255;data=acc
                w.writerow([case,k,int((not valid) or ready),int(valid),data,acc])
    (out/'spec.json').write_text(json.dumps(dict(schema=1,signals=dict(ready=1,valid=1,data=8,acc=8),expected_rows=384,expected_cases=6),indent=2),encoding='utf-8')
    return out
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();print(generate(a.output))
