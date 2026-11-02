"""Frozen 7010 control-frame adapter with durable RX before interpretation.

transport.exchange(request, expected_type) is an injected exclusive byte-I/O
adapter, not a UARTLite implementation. It returns complete captured bytes,
possibly including asynchronous lifecycle frames. No retries/reset/Clocks.
"""
from pathlib import Path
from collections import deque
import json,os,struct,hashlib
import ch1_evidence_store as store
from ch1_runtime_driver import unsigned


class ApplicationJournal:
    def __init__(self,root,epoch):
        unsigned(epoch,32,'journal epoch',1)
        root=Path(root);root.mkdir(parents=True,exist_ok=True)
        self.path=root/f'application_{epoch:08x}.jsonl'
        self.file=self.path.open('x',encoding='utf-8',newline='\n');self.digest='0'*64;self.index=0;self.fault=False
        self._content_hash=hashlib.sha256();self._owned_state=(self.digest,self.index)
        self._last_intent=None
        self.record('begin',epoch=epoch,scope='new application session; no automatic crash resume')
        store._sync_directory(root)
    def record(self,event,**fields):
        self.record_many([(event,fields)])
    def record_many(self,records):
        if self.fault:raise RuntimeError('Application journal locked')
        digest,index=self.digest,self.index;lines=[];last_intent=None
        for event,fields in records:
            if {'journal_index','previous','event','sha256'} & fields.keys():raise ValueError('Reserved application journal field')
            item={'journal_index':index,'previous':digest,'event':event,**fields}
            digest=store.sha(store._json(item));index+=1
            lines.append(json.dumps({**item,'sha256':digest},sort_keys=True)+'\n')
            last_intent=(fields.get('raw_hex'),index,digest) if event=='control_tx_intent' else None
        if not lines:return
        line=''.join(lines)
        try:
            self.file.write(line)
            self.file.flush();os.fsync(self.file.fileno())
        except Exception:self.fault=True;raise
        self.digest=digest;self.index=index
        self._content_hash.update(line.encode('utf-8'))
        self._owned_state=(self.digest,self.index)
        self._last_intent=last_intent
    def matches_intent(self,request):
        return self._last_intent==(bytes(request).hex(),self.index,self.digest)
    def verify(self):
        try:
            # This live journal was exclusively created with 'x'. Every line's
            # chain digest is constructed here and its exact bytes are fsynced
            # before updating the owned hash/state. Rehash ALL on-disk bytes,
            # never trust size/mtime or a tail-only check. Offline/imported logs
            # still use audit_application_journal's independent chain parser.
            if (hashlib.sha256(self.path.read_bytes()).digest()!=self._content_hash.digest() or
                    (self.digest,self.index)!=self._owned_state):
                raise ValueError('Application journal bytes/state altered or truncated')
        except Exception:self.fault=True;raise
    def close(self):self.file.close()


def frame(kind,payload):
    payload=bytes(payload);unsigned(kind,8,'control type')
    if len(payload)>32:raise ValueError('Control payload exceeds frozen 32-byte bound')
    body=bytes((1,kind,len(payload)))+payload
    return b'\xa5\x5a'+body+store.crc16(body).to_bytes(2,'big')


def audit_application_journal(path):
    """Read-only restart inspection; never grants resume, credit or START."""
    digest='0'*64;records=[]
    for line in Path(path).read_text().splitlines():
        item=json.loads(line);new=item.pop('sha256')
        if item['journal_index']!=len(records) or item['previous']!=digest or store.sha(store._json(item))!=new:
            raise ValueError('Application journal invalid/truncated record')
        records.append(item);digest=new
    if not records or records[0]['event']!='begin':raise ValueError('Missing application namespace begin')
    return {'epoch':records[0]['epoch'],'records':len(records),
            'start_intents':sum(r['event'] in ('start_intent','verified_start_intent') for r in records),
            'last_event':records[-1]['event'],'recorded_fault':any(r['event']=='owner_stop' for r in records),
            'automatic_resume_allowed':False,'scope':'hash-chain inspection; no live hardware inference'}


def decode_frame(raw):
    raw=bytes(raw)
    if len(raw)<7 or raw[:3]!=b'\xa5\x5a\x01' or raw[4]>32 or len(raw)!=raw[4]+7 or store.crc16(raw[2:-2])!=int.from_bytes(raw[-2:],'big'):
        raise ValueError('Control frame SOF/version/length/CRC')
    return raw[3],raw[5:-2]


def event_payload(identity,record_id):
    unsigned(identity,256,'identity');unsigned(record_id,32,'record ID')
    f=store._fields(identity,store.IDENTITY)
    if f['reserved'] or not f['session'] or not f['seq'] or f['route_mode']>1:
        raise ValueError('Invalid event identity')
    return struct.pack('>IIIBIIBHHBBI',f['session'],f['seq'],f['route_epoch'],f['slot'],
        f['generation'],f['run_id'],f['image_id'],f['trial_id'],f['item_index'],f['attempt_id'],f['route_mode'],record_id)


def decode_event(raw):
    kind,p=decode_frame(raw);base=kind-0x40 if kind>=0x70 else kind
    if base not in range(0x30,0x3a) or len(p)!=32:raise ValueError('Unsupported lifecycle event')
    values=struct.unpack('>IIIBIIBHHBBI',p)
    session,seq,epoch,slot,generation,run,image,trial,item,attempt,route,record=values
    if not session or not seq or slot>7 or route>1 or (base==0x30 and (generation or record)) or (base!=0x30 and not generation) or (base<=0x33 and record) or (base>=0x34 and not record):
        raise ValueError('Lifecycle identity encoding')
    identity=0
    for value,width in zip(values[:-1],(32,32,32,3,32,32,8,16,16,8,8)):identity=(identity<<width)|value
    return {'type':kind,'identity':identity,'record_id':record,'payload_hex':p.hex(),'raw_hex':bytes(raw).hex()}


class PeerControlSession:
    def __init__(self,transport,journal,epoch,*,event_limit=64):
        self.transport=transport;self.journal=journal;self.epoch=unsigned(epoch,32,'control epoch',1)
        self.limit=unsigned(event_limit,32,'event limit',1)
        self.txn=1;self.events=deque();self.fault=False;self.in_exchange=False
    def _exchange(self,request,expected_type,*,before_send=None):
        if self.fault or self.in_exchange:raise RuntimeError('Control session fault/concurrent request')
        self.in_exchange=True
        try:
            self.journal.verify()
            if not request or not self.journal.matches_intent(request):
                self.journal.record('control_tx_intent' if request else 'control_poll_intent',raw_hex=request.hex())
            if before_send is not None:
                checked=getattr(self.transport,'exchange_checked',None)
                if not callable(checked):raise RuntimeError('Transport first-TX guard required')
                captured=bytes(checked(request,expected_type,before_send))
            else:captured=bytes(self.transport.exchange(request,expected_type))
            # Save entire captured stream, including malformed/truncated traffic.
            durable=getattr(self.transport,'capture_is_durable',None)
            if not callable(durable) or not durable(request,captured,self.journal):
                self.journal.record('control_rx_stream',raw_hex=captured.hex())
            replies=[];pos=0
            while pos<len(captured):
                if len(captured)-pos<5:raise ValueError('Partial control header; stop without retry')
                n=captured[pos+4]+7;raw=captured[pos:pos+n]
                kind,payload=decode_frame(raw);pos+=n
                if kind in (0x31,0x32,0x33,0x38):
                    event=decode_event(raw)
                    if len(self.events)>=self.limit:raise RuntimeError('Control event queue full; raw stream preserved')
                    self.events.append(event)
                elif kind==expected_type:replies.append((raw,payload))
                else:raise ValueError('Unexpected control reply type; no automatic discard')
            if expected_type is None:
                if replies:raise ValueError('Unexpected reply to event ACK')
                return None
            if len(replies)!=1:raise ValueError('Missing/duplicate control reply; stop without retry')
            return replies[0]
        except Exception:self.fault=True;raise
        finally:self.in_exchange=False
    def _mmio(self,op,address,value=0):
        unsigned(address,12,'peer register');unsigned(value,32,'peer value')
        if address&3 or self.txn==0xffffffff:raise ValueError('Unaligned MMIO or exhausted transaction namespace')
        txn=self.txn;self.txn+=1
        payload=struct.pack('>IIBBHI',self.epoch,txn,op,1,address,value)+bytes(16)
        raw,reply=self._exchange(frame(0x3b,payload),0x7b)
        expected_count=1 if op==0 else 0
        try:
            if len(reply)!=32 or reply[:12]!=payload[:12] or reply[12:16]!=bytes((0,0,expected_count,0)) or any(reply[20:] if op==0 else reply[16:]):
                raise ValueError('Peer MMIO response identity/status/count/padding mismatch')
            return int.from_bytes(reply[16:20],'big') if op==0 else 0
        except Exception:self.fault=True;raise
    def read(self,address):return self._mmio(0,address)
    def read_bytes(self,address,count):
        """Frozen executor OP2: 1..16 actual cache bytes, each from an AXI R."""
        unsigned(address,12,'peer cache address');unsigned(count,8,'byte count',1)
        if count>16 or address&3 or address<0x400 or address+4*(count-1)>0xc54 or self.txn==0xffffffff:
            raise ValueError('OP2 range/count/transaction invalid; no request sent')
        txn=self.txn;self.txn+=1
        payload=struct.pack('>IIBBHI',self.epoch,txn,2,count,address,0)+bytes(16)
        try:
            raw,reply=self._exchange(frame(0x3b,payload),0x7b)
            if (len(reply)!=32 or reply[:12]!=payload[:12] or
                    reply[12:16]!=bytes((0,0,count,0)) or any(reply[16+count:])):
                raise ValueError('Peer OP2 identity/status/count/padding mismatch')
            return bytes(reply[16:16+count])
        except Exception:self.fault=True;raise
    def write(self,address,value):return self._mmio(1,address,value)
    def poll_notifications(self):
        """Receive later lifecycle events; no command, ACK or fabricated effect."""
        self._exchange(b'',None)
        return len(self.events)
    def request_event(self,kind,identity,record_id):
        if kind not in (0x30,0x34,0x35,0x36,0x37,0x39):raise ValueError('Unsupported owner event command')
        request=frame(kind,event_payload(identity,record_id));decode_event(request)
        raw,payload=self._exchange(request,kind+0x40)
        if payload!=request[5:-2]:self.fault=True;raise ValueError('Peer event ACK changed exact tuple')
        return decode_event(raw)
    def start(self,identity):
        f=store._fields(identity,store.IDENTITY)
        # Invocation prerequisites belong to durable owner, not this byte adapter.
        request=frame(0x11,f['trial_id'].to_bytes(2,'little'))
        raw,p=self._exchange(request,0x80)
        if p!=bytes((0x11,))+f['trial_id'].to_bytes(2,'little')+b'\x01':
            self.fault=True;raise ValueError('Legacy START not accepted for exact trial')
        return raw
    def start_checked(self,identity,before_send):
        """Final LOCAL window check after TX intent fsync; no nested peer traffic."""
        if not callable(before_send):raise TypeError('Local pre-send guard required')
        f=store._fields(identity,store.IDENTITY)
        request=frame(0x11,f['trial_id'].to_bytes(2,'little'))
        raw,p=self._exchange(request,0x80,before_send=before_send)
        if p!=bytes((0x11,))+f['trial_id'].to_bytes(2,'little')+b'\x01':
            self.fault=True;raise ValueError('Legacy START not accepted for exact trial')
        return raw
    def request_profile_none(self,identity):
        """TYPE3A has its own layout. Exact ACK7A confirms a disabled ITEM policy."""
        f=store._fields(unsigned(identity,256,'profile identity'),store.IDENTITY)
        if f['reserved'] or f['slot']!=0 or not f['session'] or not f['seq'] or f['attempt_id']>3 or f['route_mode']>1:
            raise ValueError('Profile requires canonical one-slot pre-START context')
        window=identity & ~(0xffffffff<<88)
        context=event_payload(window,0)
        payload=context[:12]+context[17:28]+bytes(9)
        request=frame(0x3a,payload)
        raw,reply=self._exchange(request,0x7a)
        if reply!=payload:self.fault=True;raise ValueError('Profile ACK changed exact policy/context')
        return {'identity_without_generation':window,'request_hex':request.hex(),'ack_hex':raw.hex(),
                'injection_enable':False,'mark_required':False}
    def request_profile_fault(self,identity,profile,inner):
        from fault_profile import FaultProfile
        from multi_point_profile import MultiPointProfile
        if type(profile) is MultiPointProfile:
            monitor=getattr(self,'mpg1_monitor',None)
            if monitor is None or monitor.session.peer is not self:
                raise RuntimeError('TYPE3C requires the registered exclusive MPG1 trial monitor')
            monitor.authorize_multi_profile(identity,profile,inner)
            request=profile.build_request(identity,inner)
            raw,reply=self._exchange(request,0x7c)
            if reply!=decode_frame(request)[1]:
                self.fault=True
                raise ValueError('ACK7C changed exact multi-point context or range')
            return {'identity_without_generation':identity & ~(0xffffffff<<88),
                'request_hex':request.hex(),'ack_hex':raw.hex(),'injection_enable':True,
                'mark_required':True,'fault_profile':profile.validate(inner),
                'policy_type':'TYPE3C_CONTIGUOUS','first_mark_only':True}
        if type(profile) is not FaultProfile:raise TypeError('Typed fault profile required')
        coordinates=profile.validate(inner)
        f=store._fields(unsigned(identity,256,'profile identity'),store.IDENTITY)
        if f['reserved'] or f['slot']!=0 or not f['session'] or not f['seq'] or not f['generation'] or not f['route_epoch'] or f['attempt_id']>3 or f['route_mode']!=0:
            raise ValueError('Canonical Direct profile identity required')
        from ch1_completion_ledger import _codec
        decoded=_codec().decode_item(bytes(inner))
        if any(f[k]!=decoded[k] for k in ('run_id','image_id','trial_id','item_index','attempt_id','route_mode')):
            raise ValueError('Fault policy identity differs from original ITEM')
        window=identity & ~(0xffffffff<<88)
        context=event_payload(window,0)
        payload=context[:12]+context[17:28]+profile.wire_suffix()
        request=frame(0x3a,payload)
        raw,reply=self._exchange(request,0x7a)
        if reply!=payload:self.fault=True;raise ValueError('Profile ACK changed exact fault policy/context')
        return {'identity_without_generation':window,'request_hex':request.hex(),'ack_hex':raw.hex(),
                'injection_enable':True,'mark_required':True,'fault_profile':coordinates}
    def ack_notification(self,event):
        raw=bytes.fromhex(event['raw_hex']);decoded=decode_event(raw)
        if decoded!=event or decoded['type'] not in (0x31,0x32,0x33,0x38):raise ValueError('Not an exact peer notification')
        # Caller must first durably commit the semantic effect via owner.
        self._exchange(frame(decoded['type']+0x40,bytes.fromhex(decoded['payload_hex'])),None)
