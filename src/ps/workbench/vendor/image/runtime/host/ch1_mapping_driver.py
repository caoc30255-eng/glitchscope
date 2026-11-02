"""H1M1 staged owner mapping + durable UploadLedger/runtime/completion join.

No START, reset, Overlay or board addresses. Exclusive ordered MMIO required.
Transport must propagate AXI errors. Existing sessions do not auto-resume.
"""
import ch1_evidence_store as store
from ch1_completion_ledger import _codec
from ch1_runtime_driver import unsigned


class CH1MappingDriver:
    def __init__(self, mmio):
        self.bus=mmio
        if self.read(0)!=0x48314d31:
            raise RuntimeError('Requires H1M1; no writes performed')
        self.expected=None;self.retire_before=None

    def read(self,a):return unsigned(self.bus.read(a),32,'mapping DWORD')
    def write(self,a,v):self.bus.write(a,unsigned(v,32,'mapping DWORD'))
    def status(self):
        s=self.read(4)
        if s&4:raise RuntimeError(f'Mapping fault {self.read(12)}; evidence retained')
        return s
    def mapping(self):
        s=self.status()
        identity=0
        for a in range(0x110,0x130,4):identity=(identity<<32)|self.read(a)
        out={'epoch':self.read(0x100),'peer_epoch':self.read(0x104),
             'record_id':self.read(0x108),'inner_crc':self.read(0x10c),'identity':identity}
        if self.status()&3 != s&3:raise RuntimeError('Mapping changed during read')
        return out

    def prepare(self,upload,*,epoch,peer_epoch,record_id,kind,identity):
        unsigned(epoch,32,'epoch',1);unsigned(peer_epoch,32,'peer_epoch',1)
        unsigned(record_id,32,'record_id',1);unsigned(identity,256,'identity')
        unsigned(kind,2,'kind',1)
        if upload.fault or upload.current is None or upload.transport_offered:
            raise RuntimeError('Requires durable unoffered upload')
        packet_kind,seq,inner,packet=upload.current
        fields=store._fields(identity,store.IDENTITY)
        if fields['reserved'] or not fields['generation'] or fields['route_epoch']!=peer_epoch or fields['route_mode']>1 or seq==0xffffffff or not seq or (upload.session,seq,int(packet_kind))!=(fields['session'],fields['seq'],{1:3,2:2,3:4}.get(kind)):
            raise ValueError('Upload and mapping identity differ')
        codec=_codec();decoder={1:codec.decode_item,2:codec.decode_config,3:codec.decode_cleanup}[kind]
        decoded=decoder(inner)
        keys=('run_id','image_id','trial_id','item_index','attempt_id','route_mode') if kind==1 else ('run_id','image_id')
        if not decoded['valid'] or any(decoded[k]!=fields[k] for k in keys):
            raise ValueError('Inner bytes differ from mapping identity')
        expected={'epoch':epoch,'peer_epoch':peer_epoch,'record_id':record_id,
                  'identity':identity,'inner_crc':store.crc16(inner)}
        status=self.status()
        if status&2:raise RuntimeError('Mapping already consumed; inspect runtime before any retry')
        if status&1:
            if self.mapping()!=expected:raise RuntimeError('Another immutable mapping is READY')
            # Read-only recovery of an uncertain commit; no staging writes.
            self.expected=expected;self.retire_before=self.read(0x18)
            return dict(expected)
        if status&24 or self.read(8)!=epoch:
            raise RuntimeError('Mapping requires current epoch, idle core and empty H1 status')
        # Caller ledger must fsync this intent before any hardware write.
        upload.record('mapping_intent',**expected,kind=kind,outer_sha256=store.sha(packet))
        self.retire_before=self.read(0x18)
        for a,key in ((0x30,'epoch'),(0x34,'peer_epoch'),(0x38,'record_id'),(0x3c,'inner_crc')):
            self.write(a,expected[key])
        for i in range(8):self.write(0x40+4*i,(identity>>(224-32*i))&0xffffffff)
        self.write(0x60,1)
        if self.status()&3!=1 or self.mapping()!=expected:
            raise RuntimeError('Mapping commit not confirmed; no ARM or send')
        upload.record('mapping_commit_verified',**expected)
        self.expected=expected
        return dict(expected)

    def arm_prepared(self,runtime,reader,upload,*,epoch,peer_epoch,record_id,kind,identity,delay_ticks,duration_ticks):
        """Prepare -> actual ARM -> readback -> durable binding, with no send."""
        if (reader.ledger.local_epoch,reader.ledger.peer_epoch,reader.ledger.session)!=(epoch,peer_epoch,upload.session):
            raise ValueError('Completion ledger namespace differs from requested mapping')
        expected=self.prepare(upload,epoch=epoch,peer_epoch=peer_epoch,record_id=record_id,kind=kind,identity=identity)
        bound=runtime.arm(kind=kind,record_id=record_id,identity=identity,
                          delay_ticks=delay_ticks,duration_ticks=duration_ticks)
        if bound.epoch!=epoch or self.status()&3!=2 or self.mapping()!=expected:
            raise RuntimeError('Actual ARM did not consume exact mapping; no packet offer')
        reader.bind_prepared(bound,upload)
        upload.record('mapping_arm_verified',epoch=epoch,record_id=record_id,identity=identity,
                      actual_start=bound.start,actual_deadline=bound.deadline)
        snap=runtime.snapshot()
        if snap['epoch']!=epoch or snap['tick']>=bound.start:
            raise RuntimeError('ARM start already reached after durable binding; no offer, preserve record')
        return bound

    def archive_and_retire(self,runtime,reader,archive,*,expected_payload=None):
        receipt=reader.ledger.completion_receipt()
        if self.expected is None or (receipt['binding']['epoch'],receipt['binding']['record_id'],receipt['binding']['identity'])!=(self.expected['epoch'],self.expected['record_id'],self.expected['identity']):
            raise RuntimeError('No saved matching completion receipt')
        saved,ticket=runtime.archive_and_request_release(archive,expected_payload=expected_payload)
        retired=runtime.wait_retirement(ticket,drain_aux=archive.drain_aux)
        if self.status()&3 or self.retire_before is None or (self.read(0x18)-self.retire_before)&0xffffffff!=1:
            raise RuntimeError('Runtime retired but mapping retirement not confirmed')
        reader.ledger.record('actual_mapping_retired',**retired)
        return {**saved,**retired,'mapping_retirement_verified':True}
