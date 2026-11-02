"""Software peer/control models, actual local persistence. No device/RTL execution."""
from pathlib import Path
from collections import deque
from dataclasses import replace
from unittest.mock import patch
import json,struct,sys,unittest,uuid
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'host'),str(ROOT/'tests'),str(ROOT/'host')]
import ch1_evidence_store as store
from ch1_control_session import ApplicationJournal,PeerControlSession,frame,decode_frame,event_payload,decode_event,audit_application_journal
from ch1_peer_archive_driver import AXPeerArchiveDriver
from ch1_item_owner import SingleItemOwner
from ch1_completion_ledger import CompletionLedger,H1CompletionReader,_codec
from ch1_runtime_driver import Binding
from h1_upload_ledger import UploadLedger
from h1_protocol import Kind
from test_completion_ledger import reply,StatusBus
from test_evidence_store import fixture

class PeerCache:
    def __init__(self,root,upload,epoch=1):
        kind,seq,inner,packet=upload.current
        self.root=root;self.upload=upload;self.inner=bytes(inner);self.sealed=True;self.mask=set();self.coverage=set()
        self.meta=[int(kind),epoch,upload.session,seq,91,len(inner),store.crc16(inner),12]
        self.stage={};self.writes=[];self.last_id=0;self.last_ticket=0;self.bad=False;self.lost=False
    def read(self,a):
        if a==0:return 0x48354531
        if a==4:return 1|(6 if self.sealed else 0)
        if a in (0x24,0x28,0x2c):return {0x24:self.meta[1],0x28:self.upload.session,0x2c:0}[a]
        if 0x100<=a<=0x11c:
            self.mask.add(a);return self.meta[(a-0x100)//4]
        if a>=0x400:
            i=(a-0x400)//4;self.coverage.add(i);return self.inner[i]^(1 if self.bad and i==0 else 0)
        if a==0x30:return len(self.coverage)
        if a==0x34:return 255 if len(self.mask)==8 else 0
        if a==0x68:return self.last_id
        if a==0x6c:return self.last_ticket
        raise AssertionError(a)
    def write(self,a,v):
        self.writes.append((a,v))
        if a!=0x64:self.stage[a]=v;return
        directory=self.root/f'epoch_{self.meta[1]:08x}_session_{self.upload.session:08x}_seq_{self.meta[3]:08x}'
        assert (directory/'committed.json').is_file() and (directory/'inner.bin').read_bytes()==self.inner
        assert len(self.coverage)==len(self.inner) and len(self.mask)==8
        expected=dict(zip((0x44,0x40,0x48,0x4c,0x50,0x54,0x58,0x60),self.meta))
        assert all(self.stage[k]==v for k,v in expected.items()) and self.stage[0x5c]!=0
        self.last_id=self.stage[0x5c];self.last_ticket=91;self.sealed=False
        if self.lost:self.lost=False;raise OSError('Lost proof reply after actual take')

class WirePeer:
    def __init__(self,cache,identity):
        self.cache=cache;self.identity=identity;self.requests=[];self.inject=b'';self.bad_reply=False;self.start_done=True
    def exchange(self,request,expected_type):
        self.requests.append(request)
        if not request:
            data=self.inject;self.inject=b'';return data
        typ,p=decode_frame(request)
        if typ==0x3b:
            epoch,txn,op,count,a,v=struct.unpack('>IIBBHI',p[:16])
            if op==2:
                values=[self.cache.read(a+4*i) for i in range(count)]
                assert all(0<=value<=255 for value in values)
                result=p[:12]+bytes((0,0,count,0))+bytes(values)+bytes(16-count)
            else:
                value=self.cache.read(a) if op==0 else (self.cache.write(a,v) or 0)
                result=p[:12]+bytes((0,0,1 if op==0 else 0,0))+value.to_bytes(4,'big')+bytes(12)
            raw=frame(0x7b,result)
            if self.bad_reply:raw=raw[:-1]+bytes((raw[-1]^1,))
            prefix=self.inject;self.inject=b'';return prefix+raw
        if typ==0x11:
            started=frame(0x31,event_payload(self.identity,0))
            done=frame(0x32,event_payload(self.identity,0)) if self.start_done else b''
            return started+frame(0x80,bytes((0x11,))+p+b'\x01')+done
        if typ in (0x30,0x34,0x35,0x36,0x37,0x39):
            retired=frame(0x38,p) if typ==0x37 else b''
            return retired+frame(typ+0x40,p)
        if typ in (0x71,0x72,0x73,0x78):return b''
        raise AssertionError(typ)

class AppTests(unittest.TestCase):
    def setUp(self):
        self.root=ROOT/'evidence/offline_application_tests'/('test_'+uuid.uuid4().hex)
        self.journal=ApplicationJournal(self.root/'journal',0x73000001);self.addCleanup(self.journal.close)
        self.upload=UploadLedger(self.root/'upload',0x10203040);self.addCleanup(self.upload.close)
        self.upload.prepare(Kind.HELLO);self.upload.observe(reply(b'',0x80,seq=0,crc=0,credit=1))
        self.inner=_codec().encode_config(1,2,16,16,256,1,256,bytes(32),[0x1234])
        self.upload.prepare(Kind.CONFIG,self.inner)
        self.identity=store.descriptor_decode(fixture()[0])['identity']
        self.identity=(self.identity & ~(0xffffffff<<155))|(1<<155)
        self.binding=Binding(1,17,2,self.identity,50,800000)
        self.cache=PeerCache(self.root/'peer',self.upload)
        self.wire=WirePeer(self.cache,self.identity);self.peer=PeerControlSession(self.wire,self.journal,0x73000001)
        self.driver=AXPeerArchiveDriver(self.peer,self.root/'peer',poll_limit=3)
    def archive(self):return self.driver.archive_prepared(self.upload,peer_epoch=1,record_id=101,route=0)
    def test_event_effect_fsync_failure_sends_no_ACK(self):
        owner,reader,bus,receipt,runtime,admission=self.owner_setup()
        owner.phase='START_REQUESTED'
        raw=frame(0x31,event_payload(owner.binding.identity,0))
        self.peer.events.append(decode_event(raw));before=len(self.wire.requests)
        with patch('ch1_control_session.os.fsync',side_effect=OSError('disk')):
            with self.assertRaises(OSError):owner.drain_notifications(self.peer)
        self.assertEqual(len(self.wire.requests),before)
        self.assertFalse(owner.started)
    def owner_setup(self):
        receipt=self.archive()
        c=CompletionLedger(self.root/'completion',local_epoch=1,peer_epoch=1,session=self.upload.session)
        self.addCleanup(c.close);status_bus=StatusBus(c);reader=H1CompletionReader(status_bus,c)
        reader.bind_prepared(self.binding,self.upload);status_bus.events=[reply(self.inner,seq=1)]
        reader.read_and_preserve()
        owner=SingleItemOwner(self.journal,self.binding,self.upload,c)
        binding=self.binding
        class Runtime:
            def binding(self):return binding
            def snapshot(self):return {'epoch':1,'tick':100,'seq':1}
        admission={'identity':self.identity,'local_epoch':1,'peer_epoch':1,'CH0_registered':True,
                   'STM_expected_flight_registered':True,'policy_ready':True,
                   'generation_continuity_verified':True,'mark_required':False}
        return owner,reader,status_bus,receipt,Runtime(),admission
    def saved_main(self):
        d,s,raw,w=fixture('config_ack',kind=2)
        value=int.from_bytes(d,'big');value=(value & ~(((1<<256)-1)<<383))|(self.identity<<383)
        d=value.to_bytes(84,'big')
        result=store.persist_record(self.root/'main',d,s,store.crc16(d),store.crc16(s),errors=[],orphans=[],watermark_tick=w)
        return {**result,'hardware_retirement_verified':True,'mapping_retirement_verified':True}
    def test_peer_archive_full_reads_and_real_commit_before_proof(self):
        result=self.archive();self.assertTrue(result['peer_store_verified'])
        self.assertEqual(len(self.cache.coverage),len(self.inner));self.assertFalse(self.cache.sealed)
        self.assertEqual(result['capture_generation'],12)
        self.assertEqual((Path(result['directory'])/'inner.bin').read_bytes(),self.inner)
    def test_OP2_archive_exact_tail_and_full_actual_read_coverage(self):
        result=self.archive()
        payloads=[decode_frame(request)[1] for request in self.wire.requests]
        bursts=[p for p in payloads if p[8]==2]
        self.assertEqual(len(bursts),(len(self.inner)+15)//16)
        self.assertEqual(sum(p[9] for p in bursts),len(self.inner))
        self.assertEqual(bursts[-1][9],len(self.inner)%16 or 16)
        self.assertEqual(self.cache.coverage,set(range(len(self.inner))))
        self.assertTrue(result['peer_store_verified'])
    def test_OP2_bad_range_count_alignment_sends_nothing(self):
        before=list(self.wire.requests);txn=self.peer.txn
        for address,count in ((0x400,0),(0x400,17),(0x401,1),(0x3fc,1),(0xc54,2)):
            with self.assertRaises(ValueError):self.peer.read_bytes(address,count)
        self.assertEqual(self.wire.requests,before);self.assertEqual(self.peer.txn,txn)
    def test_OP2_wrong_return_count_locks_control(self):
        original=self.wire.exchange
        def changed(request,kind):
            raw=original(request,kind);typ,p=decode_frame(raw);p=bytearray(p);p[14]^=1
            return frame(typ,p)
        self.wire.exchange=changed
        with self.assertRaises(ValueError):self.peer.read_bytes(0x400,16)
        self.assertTrue(self.peer.fault);self.assertFalse(self.cache.writes)
    def test_OP2_nonzero_tail_padding_locks_control(self):
        original=self.wire.exchange
        def changed(request,kind):
            raw=original(request,kind);typ,p=decode_frame(raw);p=bytearray(p);p[31]=1
            return frame(typ,p)
        self.wire.exchange=changed
        with self.assertRaises(ValueError):self.peer.read_bytes(0x400,1)
        self.assertTrue(self.peer.fault);self.assertFalse(self.cache.writes)
    def test_peer_wrong_actual_bytes_preserved_without_proof(self):
        self.cache.bad=True
        with self.assertRaises(ValueError):self.archive()
        self.assertFalse(self.cache.writes);self.assertTrue(list((self.root/'peer').glob('failed_*/actual.bin')))
    def test_peer_archive_disk_failure_withholds_proof(self):
        with patch('ch1_peer_archive_driver.store._write',side_effect=OSError('disk failure')):
            with self.assertRaises(OSError):self.archive()
        self.assertFalse(self.cache.writes)
    def test_peer_lost_confirmation_uses_actual_last_take(self):
        self.cache.lost=True
        with self.assertRaises(OSError):self.archive()
        self.assertTrue(self.peer.fault) # Original control session remains stopped.
        fresh=ApplicationJournal(self.root/'journal',0x73000002);self.addCleanup(fresh.close)
        control=PeerControlSession(self.wire,fresh,0x73000002)
        recovered=AXPeerArchiveDriver(control,self.root/'peer',poll_limit=3)
        count=len(self.cache.writes)
        r=recovered.archive_prepared(self.upload,peer_epoch=1,record_id=101,route=0)
        self.assertTrue(r['cached']);self.assertEqual(count,len(self.cache.writes))
    def test_peer_cached_tamper_no_confirmation(self):
        r=self.archive();(Path(r['directory'])/'inner.bin').write_bytes(b'bad')
        with self.assertRaises(ValueError):self.archive()
    def test_control_mixed_notification_and_mmio_preserves_both(self):
        self.wire.inject=frame(0x31,event_payload(self.identity,0))
        self.assertEqual(self.peer.read(0),0x48354531)
        self.assertEqual(self.peer.events[0]['identity'],self.identity)
        self.assertIn(self.wire.requests[-1].hex(),self.journal.path.read_text())
    def test_bad_control_crc_faults_and_no_retry(self):
        self.wire.bad_reply=True
        with self.assertRaises(ValueError):self.peer.read(0)
        count=len(self.wire.requests)
        with self.assertRaises(RuntimeError):self.peer.read(0)
        self.assertEqual(count,len(self.wire.requests))
    def test_control_event_identity_roundtrip_and_window_generation_zero(self):
        identity=self.identity & ~(0xffffffff<<88)
        self.assertEqual(decode_event(frame(0x30,event_payload(identity,0)))['identity'],identity)
        self.assertEqual(self.peer.request_event(0x30,identity,0)['type'],0x70)
    def test_control_event_queue_overflow_stops_with_raw(self):
        self.peer.limit=1;raw=frame(0x31,event_payload(self.identity,0));self.wire.inject=raw+raw
        with self.assertRaises(RuntimeError):self.peer.read(0)
        self.assertIn((raw+raw).hex(),self.journal.path.read_text())
    def test_missing_start_admission_no_control_request(self):
        owner,reader,bus,receipt,runtime,admission=self.owner_setup();admission['CH0_registered']=False
        n=len(self.wire.requests)
        with self.assertRaises(RuntimeError):owner.start(self.peer,runtime,receipt,admission,minimum_remaining_ticks=1000)
        self.assertEqual(n,len(self.wire.requests));self.assertTrue(owner.fault)
    def test_real_control_start_and_done_both_saved_before_event_ack(self):
        owner,reader,bus,receipt,runtime,admission=self.owner_setup()
        r=owner.start(self.peer,runtime,receipt,admission,minimum_remaining_ticks=1000)
        self.assertTrue(r['physical_start_confirmed'] and r['physical_done_confirmed'])
        self.assertTrue(any(decode_frame(raw)[0]==0x11 for raw in self.wire.requests))
        records=[json.loads(x) for x in self.journal.path.read_text().splitlines()]
        effect=[i for i,x in enumerate(records) if x['event']=='peer_event_effect']
        ack=[i for i,x in enumerate(records) if x['event']=='control_tx_intent' and decode_frame(bytes.fromhex(x['raw_hex']))[0] in (0x71,0x72)]
        self.assertTrue(effect[0]<ack[0] and effect[1]<ack[1])
    def test_wrong_actual_start_generation_locks_owner(self):
        owner,reader,bus,receipt,runtime,admission=self.owner_setup()
        self.wire.identity=self.identity^(3<<88)
        with self.assertRaises(ValueError):owner.start(self.peer,runtime,receipt,admission,minimum_remaining_ticks=1000)
        self.assertTrue(owner.fault);self.assertFalse(owner.started)
    def test_full_peer_retirement_and_saved_ready_allow_one_next_upload(self):
        owner,reader,bus,receipt,runtime,admission=self.owner_setup()
        owner.start(self.peer,runtime,receipt,admission,minimum_remaining_ticks=1000)
        bus.events=[reply(self.inner,0x83,seq=1)];reader.read_and_preserve()
        owner.retire_peer(self.peer,self.saved_main());self.assertTrue(owner.peer_retired)
        bus.events=[reply(self.inner,0x80,seq=1,credit=1)];ready=reader.read_and_preserve()
        self.assertTrue(owner.accept_ready(ready)['next_item_allowed'])
        packet=self.upload.prepare(Kind.CLEANUP,_codec().encode_cleanup(1,2))
        self.assertEqual(int.from_bytes(packet[8:12],'big'),2)
    def test_ready_credit0_does_not_allow_next_item(self):
        owner,reader,bus,receipt,runtime,admission=self.owner_setup()
        owner.start(self.peer,runtime,receipt,admission,minimum_remaining_ticks=1000)
        bus.events=[reply(self.inner,0x83,seq=1)];reader.read_and_preserve();owner.retire_peer(self.peer,self.saved_main())
        bus.events=[reply(self.inner,0x80,seq=1,credit=0)];ready=reader.read_and_preserve()
        with self.assertRaises(ValueError):owner.accept_ready(ready)
        self.assertEqual(self.upload.credit,0)
    def test_only_one_retirement_never_unlocks_upload(self):
        owner,reader,bus,receipt,runtime,admission=self.owner_setup()
        bus.events=[reply(self.inner,0x80,seq=1,credit=1)];ready=reader.read_and_preserve()
        with self.assertRaises(RuntimeError):owner.accept_ready(ready)
        self.assertIsNotNone(self.upload.current)
    def test_uncertain_start_is_never_automatically_repeated(self):
        owner,reader,bus,receipt,runtime,admission=self.owner_setup()
        def failed(request,expected):raise OSError('Lost START or window ACK')
        self.wire.exchange=failed
        with self.assertRaises(OSError):owner.start(self.peer,runtime,receipt,admission,minimum_remaining_ticks=1000)
        with self.assertRaises(RuntimeError):owner.start(self.peer,runtime,receipt,admission,minimum_remaining_ticks=1000)
    def test_journal_reopen_and_tamper_denied(self):
        with self.assertRaises(FileExistsError):ApplicationJournal(self.root/'journal',0x73000001)
        self.journal.path.write_text(self.journal.path.read_text().replace('begin','altered'))
        with self.assertRaises(ValueError):self.journal.verify()

    def test_maximum_peer_raw_frame_exact_534_bytes(self):
        upload=UploadLedger(self.root/'max_upload',99);self.addCleanup(upload.close)
        upload.prepare(Kind.HELLO);upload.observe(reply(b'',0x80,session=99,seq=0,crc=0,credit=1))
        inner=_codec().encode_item(1,2,3,4,64,1,0,bytes(range(256))*2);upload.prepare(Kind.ITEM,inner)
        cache=PeerCache(self.root/'max_peer',upload);driver=AXPeerArchiveDriver(cache,self.root/'max_peer',poll_limit=3)
        result=driver.archive_prepared(upload,peer_epoch=1,record_id=102,route=0)
        self.assertEqual(result['len'],534);self.assertEqual(len(cache.coverage),534)

    def test_zero_length_hello_peer_evidence_is_not_invented(self):
        upload=UploadLedger(self.root/'hello_upload',99);self.addCleanup(upload.close)
        upload.prepare(Kind.HELLO)
        cache=PeerCache(self.root/'hello_peer',upload);driver=AXPeerArchiveDriver(cache,self.root/'hello_peer',poll_limit=3)
        result=driver.archive_prepared(upload,peer_epoch=1,record_id=102,route=0)
        self.assertEqual(result['len'],0);self.assertEqual(result['crc'],0xffff);self.assertFalse(cache.coverage)

    def test_peer_lifecycle_done_cannot_substitute_for_saved_h1_done(self):
        owner,reader,bus,receipt,runtime,admission=self.owner_setup()
        owner.start(self.peer,runtime,receipt,admission,minimum_remaining_ticks=1000)
        count=len(self.wire.requests)
        with self.assertRaises(RuntimeError):owner.retire_peer(self.peer,self.saved_main())
        self.assertEqual(count,len(self.wire.requests))

    def test_restart_inspection_never_authorizes_resume(self):
        result=audit_application_journal(self.journal.path)
        self.assertFalse(result['automatic_resume_allowed'])

    def test_start_journal_failure_never_sends_window_or_start(self):
        owner,reader,bus,receipt,runtime,admission=self.owner_setup();count=len(self.wire.requests)
        with patch.object(self.journal,'record',side_effect=OSError('application fsync failed')):
            with self.assertRaises(OSError):owner.start(self.peer,runtime,receipt,admission,minimum_remaining_ticks=1000)
        self.assertEqual(count,len(self.wire.requests));self.assertTrue(owner.fault)

    def test_delayed_w19_done_requires_receive_only_poll(self):
        owner,reader,bus,receipt,runtime,admission=self.owner_setup();self.wire.start_done=False
        result=owner.start(self.peer,runtime,receipt,admission,minimum_remaining_ticks=1000)
        self.assertFalse(result['physical_done_confirmed'])
        self.wire.inject=frame(0x32,event_payload(self.identity,0))
        self.assertTrue(owner.poll_lifecycle(self.peer)['physical_done_confirmed'])

    def test_actual_peer_session_ready_seq0_crc0_unlocks_only_after_retirement(self):
        owner,reader,bus,receipt,runtime,admission=self.owner_setup()
        owner.start(self.peer,runtime,receipt,admission,minimum_remaining_ticks=1000)
        bus.events=[reply(self.inner,0x83,seq=1)];reader.read_and_preserve()
        owner.retire_peer(self.peer,self.saved_main())
        bus.events=[reply(self.inner,0x80,seq=0,crc=0,credit=1)]
        result=reader.read_and_preserve()
        self.assertTrue(result['session_ready']);self.assertEqual(self.upload.credit,0)
        self.assertTrue(owner.accept_ready(result)['next_item_allowed'])

    def test_session_ready_before_actual_local_retirement_is_not_accepted(self):
        owner,reader,bus,receipt,runtime,admission=self.owner_setup()
        bus.events=[reply(self.inner,0x83,seq=1)];reader.read_and_preserve()
        bus.events=[reply(self.inner,0x80,seq=0,crc=0,credit=1)]
        with self.assertRaises(ValueError):reader.read_and_preserve()
        self.assertTrue(bus.held);self.assertEqual(self.upload.credit,0)

if __name__=='__main__':unittest.main(verbosity=2)
