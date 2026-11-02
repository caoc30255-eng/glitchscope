"""Host filesystem benchmark: strict pre-event audit versus owned incremental writer."""
import argparse,hashlib,json,time
from pathlib import Path
import session_ledger as ledger
def measure(output,records=50):
    if type(records) is not int or not 1<=records<=2000:raise ValueError('RECORDS_RANGE')
    out=Path(output);out.mkdir();results={}
    for fast in [False,True]:
        root=out/('incremental' if fast else 'strict');ledger.create(root,dict(max_records=records,record_ids=['r'+str(i) for i in range(records)],origin='SYNTHETIC'))
        original=ledger.artifact;calls=[0]
        def counted(*a,**k):calls[0]+=1;return original(*a,**k)
        ledger.artifact=counted;t=time.perf_counter()
        try:
            with ledger.SessionWriter(root,incremental=fast) as w:
                for i in range(records):
                    name='r'+str(i);w.begin(name,dict(index=i));p=root/'raw'/(name+'.bin');p.write_bytes(bytes([i%256])*256)
                    w.complete(name,{p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()})
            results['incremental' if fast else 'strict']=dict(wall_seconds=time.perf_counter()-t,artifact_verification_calls=calls[0],final_audit=w.final_report)
        finally:ledger.artifact=original
    report=dict(records=records,results=results,scope='Measured host temporary-file IO; incremental assumes owned immutable evidence and checks whole history on close. Not hardware speedup or adversarial anti-tamper proof',hardware_access=False)
    (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps({n:r['artifact_verification_calls'] for n,r in results.items()}));return report
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--records',type=int,default=50);a=p.parse_args();measure(a.output,a.records)
