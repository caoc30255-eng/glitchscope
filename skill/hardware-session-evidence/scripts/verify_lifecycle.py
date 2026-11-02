"""Read-only verification of the project's actual peer lifecycle notification format.
Peer notifications alone do not prove local archives, strict retirement or physical authenticity.
"""
import argparse,json,struct,sys
from pathlib import Path
from peer_read_adapter import decode
from session_ledger import file_sha
NAMES=['session','seq','route_epoch','slot','generation','run_id','image_id','trial_id','item_index','attempt_id','route_mode']
FORMAT='>IIIBIIBHHBBI'
def verify_frames(frames,expected,record_id,mark_required=False):
    seen=[];ack=False
    if set(expected)!=set(NAMES) or any(type(v) is not int or v<0 for v in expected.values()):raise ValueError('EXPECTED_IDENTITY')
    if expected['slot']>7 or expected['route_mode']>1:raise ValueError('IDENTITY_SLOT_OR_ROUTE_RANGE')
    if not all(expected[n] for n in ['session','seq','route_epoch','generation']):raise ValueError('FRESH_NONZERO_IDENTITY_REQUIRED')
    if type(record_id) is not int or not 0<record_id<2**32:raise ValueError('RECORD_ID')
    for raw in frames:
        kind,p=decode(raw)
        if kind==0x80:
            if ack or p!=bytes([0x11])+expected['trial_id'].to_bytes(2,'little')+b'\x01':raise ValueError('START_ACK_IDENTITY')
            ack=True;continue
        if kind not in (0x31,0x32,0x33,0x38) or len(p)!=32:raise ValueError('NOT_A_LIFECYCLE_ONLY_CAPTURE')
        values=struct.unpack(FORMAT,p);identity=dict(zip(NAMES,values[:-1]))
        if identity!=expected or values[-1]!=(record_id if kind==0x38 else 0):raise ValueError('PEER_EVENT_IDENTITY')
        sequence=[0x31]+([0x33] if mark_required else [])+[0x32,0x38]
        if len(seen)>=len(sequence) or kind!=sequence[len(seen)]:raise ValueError('PEER_EVENT_ORDER_OR_DUPLICATE')
        seen.append(kind)
    required=[0x31]+([0x33] if mark_required else [])+[0x32,0x38]
    missing=[hex(k) for k in required if k not in seen]+([] if ack else ['START_COMMAND_ACK'])
    return dict(status='PEER_LIFECYCLE_SEQUENCE_PASS' if not missing else 'INCOMPLETE_UNKNOWN',start_command_ack=ack,start_accept=0x31 in seen,physical_done_notification=0x32 in seen,peer_retired_notification=0x38 in seen,missing=missing,
                strict_local_retirement_verified=False,hardware_authenticity_verified=False,scope='Actual peer frame format/identity/order only; original owner must still verify local TX_DONE, archives, READY and authorization')
def read_frames(path):
    with Path(path).open('rb') as f:
        while True:
            header=f.read(5)
            if not header:break
            if len(header)!=5 or header[4]>32:raise ValueError('TRUNCATED_HEADER')
            rest=f.read(header[4]+2)
            if len(rest)!=header[4]+2:raise ValueError('TRUNCATED_FRAME')
            yield header+rest
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--capture',required=True);p.add_argument('--expected',required=True);p.add_argument('--record-id',type=int,required=True);p.add_argument('--mark-required',action='store_true');p.add_argument('--output',required=True);a=p.parse_args()
    with Path(a.output).open('x',encoding='utf-8') as f:
        try:r=verify_frames(read_frames(a.capture),json.loads(Path(a.expected).read_text(encoding='utf-8')),a.record_id,a.mark_required)
        except Exception as e:r=dict(status='BLOCKED_UNKNOWN',error=str(e))
        r['capture_sha256']=file_sha(a.capture);json.dump(r,f,indent=2)
    print(json.dumps(r));sys.exit(0 if r['status']=='PEER_LIFECYCLE_SEQUENCE_PASS' else 2)
