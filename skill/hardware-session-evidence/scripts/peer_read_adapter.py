"""Actual project's H5E1 READ32 frame contract, coupled to ledger and device lease.
Transport is injected; no native UART is auto-opened, no writes/START/reset op exists here.
"""
import binascii,hashlib,json,struct,os
from pathlib import Path
import session_ledger as ledger
from device_lease import DeviceLease
def frame(kind,payload):
    body=bytes([1,kind,len(payload)])+bytes(payload)
    if len(payload)>32:raise ValueError('FRAME_PAYLOAD')
    return b'\xa5\x5a'+body+binascii.crc_hqx(body,0xffff).to_bytes(2,'big')
def decode(raw):
    if len(raw)<7 or raw[:3]!=b'\xa5\x5a\x01' or raw[4]>32 or len(raw)!=raw[4]+7 or binascii.crc_hqx(raw[2:-2],0xffff)!=int.from_bytes(raw[-2:],'big'):raise ValueError('SOF_VERSION_LENGTH_CRC')
    return raw[3],raw[5:-2]
def read_request(epoch,txn,address):
    if type(epoch) is not int or type(txn) is not int or not 0<epoch<2**32 or not 0<txn<0xffffffff:raise ValueError('EPOCH_TRANSACTION')
    if type(address) is not int or not 0<=address<4096 or address%4:raise ValueError('READ32_ADDRESS')
    return frame(0x3b,struct.pack('>IIBBHI',epoch,txn,0,1,address,0)+bytes(16))
def verify(request,captured):
    kind,payload=decode(request)
    if kind!=0x3b or len(payload)!=32 or payload[8:10]!=bytes([0,1]) or any(payload[12:]):raise ValueError('READ_ONLY_REQUEST_REQUIRED')
    epoch,txn,op,count,address,value=struct.unpack('>IIBBHI',payload[:16])
    if read_request(epoch,txn,address)!=request:raise ValueError('NONCANONICAL_READ_REQUEST')
    kind,reply=decode(captured)
    # A busy peer may interleave lifecycle frames. This idle READ32 example rejects rather than discards them.
    if kind!=0x7b or len(reply)!=32 or reply[:12]!=payload[:12] or reply[12:16]!=bytes([0,0,1,0]) or any(reply[20:]):raise ValueError('REPLY_IDENTITY_STATUS_COUNT_PADDING')
    return int.from_bytes(reply[16:20],'big')
def durable_bytes(path,data):
    with Path(path).open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
def run_readonly(transport,root,lease_path,epoch,first_txn,reads,incremental=False):
    """reads = [{address,expected,read_effect:'none',access:'RO'}]. Caller owns real namespace allocation."""
    if not reads:raise ValueError('READS_REQUIRED')
    requests=[]
    for i,r in enumerate(reads):
        if r.get('access')!='RO' or r.get('read_effect')!='none' or type(r['expected']) is not int or not 0<=r['expected']<2**32:raise ValueError('SIDE_EFFECT_FREE_IDENTITY_READS_ONLY')
        requests.append(read_request(epoch,first_txn+i,r['address']))
    root=Path(root);lease=DeviceLease(lease_path);closed=False
    with lease:
        ledger.create(root,dict(max_records=len(reads),record_ids=['read_'+str(i) for i in range(len(reads))],origin='ADAPTER_REPORTED',protocol='H5E1_READ32',epoch=epoch))
        try:
            with ledger.SessionWriter(root,incremental=incremental) as w:
                for i,(r,request) in enumerate(zip(reads,requests)):
                    record='read_'+str(i);w.begin(record,dict(epoch=epoch,txn=first_txn+i,address=r['address'],expected=r['expected'],operation='READ32'))
                    tx=root/'raw'/(record+'_tx.bin');rx=root/'raw'/(record+'_rx.bin');durable_bytes(tx,request)
                    try:
                        captured=bytes(transport.exchange(request,0x7b));durable_bytes(rx,captured)
                        value=verify(request,captured)
                        if value!=r['expected']:raise ValueError('IDENTITY_VALUE_MISMATCH')
                        w.complete(record,{p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in [tx,rx]})
                    except Exception as e:
                        # Preserve available partial transport bytes; never retry or label it DUT failure.
                        if not rx.exists():durable_bytes(rx,bytes(getattr(e,'captured',b'')))
                        w.unknown(record,str(e),{p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in [tx,rx] if p.exists()});break
        finally:
            # A close return is adapter-reported, not a universal proof of native UART thread exit.
            try:closed=transport.close() is True
            except Exception:closed=False
            if not closed:lease.quarantine('TRANSPORT_RELEASE_UNCONFIRMED')
    if closed:ledger.cleanup(root,True,lease.released)
    report=ledger.audit(root);report.update(protocol='H5E1_READ32',physical_START_commands_sent=0,transport_close_reported=closed,device_quarantined=lease.quarantine_path.exists(),
        scope='Actual frozen READ32 wire contract plus local OS cooperative lease; transport/caller owns board, epoch and transaction namespace; no independent board acceptance')
    (root/'adapter_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8');return report
