"""Full collector/UNKNOWN/ledger integration with real H5E1 bytes in a local emulator.
Requires the explicitly supplied sibling ledger scripts. Never opens physical UART.
"""
import argparse,hashlib,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from campaign import run_policy,coverage
from benchmark import digest
def demo(output,ledger_scripts,unknown_at=0):
    sys.path.insert(0,str(Path(ledger_scripts).resolve()))
    import session_ledger as ledger
    from device_lease import DeviceLease
    from peer_read_adapter import frame,decode,read_request,verify,durable_bytes
    out=Path(output);out.mkdir();session=out/'session';words={0:0x48354531,4:0x20,0x24:0,0x28:0}
    class Transport:
        n=0
        def exchange(self,request,expected):
            self.n+=1;kind,p=decode(request);address=int.from_bytes(p[10:12],'big')
            reply=frame(0x7b,p[:12]+bytes([0,0,1,0])+words[address].to_bytes(4,'big')+bytes(12))
            if self.n==unknown_at:reply=reply[:-1]+bytes([reply[-1]^1])
            return reply
        def close(self):return True
    transport=Transport();epoch=0x10000001
    plan=dict(context=dict(protocol='H5E1_READ32',epoch=epoch,source='LOCAL_EMULATOR_NOT_BOARD'),domain=[dict(id='a',coordinates=[0x24]),dict(id='b',coordinates=[0x28])],budget=8,setup_records=2,repeats=3,max_groups_per_point=1)
    ledger.create(session,dict(record_ids=['r%05d'%i for i in range(8)],max_records=8,origin='ADAPTER_REPORTED',target='LOCAL_EMULATOR'))
    def expected(req):
        address=[0,4][req['repeat_index']] if req['kind']=='SETUP' else {'a':0x24,'b':0x28}[req['point_id']]
        txn=int(req['record_id'][1:])+1;return address,read_request(epoch,txn,address)
    def collect(req):
        address,tx=expected(req);txp=session/'raw'/(req['record_id']+'_tx.bin');rxp=session/'raw'/(req['record_id']+'_rx.bin')
        durable_bytes(txp,tx);rx=transport.exchange(tx,0x7b);durable_bytes(rxp,rx)
        return dict(record_id=req['record_id'],request_sha256=digest(req),status='VALID',outcome=None if req['kind']=='SETUP' else True,
                    evidence_files={p.relative_to(session).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in [txp,rxp]},tx_path=txp.relative_to(session).as_posix(),rx_path=rxp.relative_to(session).as_posix())
    def verify_raw(req,reply):
        address,tx=expected(req);actual=(session/reply['tx_path']).read_bytes()
        if actual!=tx:raise ValueError('REQUEST_ECHO')
        return verify(actual,(session/reply['rx_path']).read_bytes())==words[address]
    with DeviceLease(out/'device.lock') as lease:
        with ledger.SessionWriter(session,incremental=True) as writer:
            def before(req):writer.begin(req['record_id'],req)
            def after(req,row):
                if row['status']=='VALID':writer.complete(req['record_id'],row['receipt']['evidence_files'])
                else:
                    candidates=[session/'raw'/(req['record_id']+suffix) for suffix in ['_tx.bin','_rx.bin']]
                    writer.unknown(req['record_id'],row['error'],{p.relative_to(session).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in candidates if p.exists()})
            run=run_policy(plan,coverage,collect,'local_read32','ADAPTER_REPORTED',before,verify_raw,after)
            if writer.state['state'] in ('READY','RUNNING'):writer.stop('policy_finished')
        closed=transport.close()
    ledger.cleanup(session,closed,lease.released)
    report=dict(run=run,ledger=ledger.audit(session),source='LOCAL_EMULATOR_REAL_WIRE_FORMAT_NOT_BOARD',hardware_access=False,physical_STARTs=0)
    if report['ledger']['occupied']!=run['occupied']:raise ValueError('LEDGER_COUNTER_DIVERGENCE')
    if unknown_at and run['terminal']!='BLOCKED_UNKNOWN':raise ValueError('UNKNOWN_FIXTURE_NOT_BLOCKED')
    (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print('PASS_LEDGER_COLLECTOR_BRIDGE',run['occupied'],run['unknown_records']);return report
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--ledger-scripts',required=True);p.add_argument('--unknown-at',type=int,default=0);a=p.parse_args();demo(a.output,a.ledger_scripts,a.unknown_at)
