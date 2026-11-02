"""Mapping register model + existing durable upload/completion ledgers; no RTL."""
from pathlib import Path
from dataclasses import replace
from unittest.mock import patch
import sys,unittest,uuid,json
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'host'),str(ROOT/'tests'),str(ROOT/'host')]
from ch1_mapping_driver import CH1MappingDriver
from ch1_completion_ledger import CompletionLedger,H1CompletionReader,_codec
from ch1_runtime_driver import Binding
from h1_upload_ledger import UploadLedger
from h1_protocol import Kind
from test_completion_ledger import reply,StatusBus
from test_evidence_store import fixture
import ch1_evidence_store as store

class MappingModel:
    def __init__(self,upload):
        self.upload=upload;self.stage={};self.writes=[];self.state=0;self.fault=False
        self.busy=False;self.pending=False;self.epoch=1;self.live=[0]*12;self.retired=0
        self.reject=False;self.lost=False;self.effects=0
    def read(self,a):
        if a==0:return 0x48314d31
        if a==4:return self.state|(4 if self.fault else 0)|(8 if self.busy else 0)|(16 if self.pending else 0)
        if a==8:return self.epoch
        if a==12:return 1
        if a==0x18:return self.retired
        if 0x100<=a<=0x12c:return self.live[(a-0x100)//4]
        raise AssertionError(a)
    def write(self,a,v):
        self.writes.append((a,v))
        if a==0x60:
            lines=[json.loads(x) for x in self.upload.path.read_text().splitlines()]
            assert any(x['event']=='mapping_intent' for x in lines)
            assert len(self.stage)==12
            if self.reject:return
            self.live=[self.stage[a] for a in range(0x30,0x60,4)]
            self.state=1;self.effects+=1
            if self.lost:self.lost=False;raise OSError('Lost mapping commit reply after execution')
        else:
            assert self.state==0,'Immutable mapping restaged'
            self.stage[a]=v

class MappingTests(unittest.TestCase):
    def setUp(self):
        self.root=ROOT/'evidence/offline_mapping_tests'/('test_'+uuid.uuid4().hex)
        self.upload=UploadLedger(self.root/'upload',0x10203040);self.addCleanup(self.upload.close)
        self.upload.prepare(Kind.HELLO);self.upload.observe(reply(b'',0x80,seq=0,crc=0,credit=1))
        self.inner=_codec().encode_config(1,2,16,16,256,1,256,bytes(32),[0x1234])
        self.upload.prepare(Kind.CONFIG,self.inner)
        identity=store.descriptor_decode(fixture()[0])['identity']
        self.identity=(identity & ~(0xffffffff<<155))|(1<<155)
        self.args=dict(epoch=1,peer_epoch=1,record_id=17,kind=2,identity=self.identity)
        self.bus=MappingModel(self.upload);self.driver=CH1MappingDriver(self.bus)
    def test_wrong_ip_no_writes(self):
        self.bus.read=lambda a:0
        with self.assertRaises(RuntimeError):CH1MappingDriver(self.bus)
        self.assertFalse(self.bus.writes)
    def test_twelve_fields_durable_intent_before_commit(self):
        out=self.driver.prepare(self.upload,**self.args)
        self.assertEqual(len(self.bus.stage),12);self.assertEqual(out['inner_crc'],store.crc16(self.inner))
        self.assertEqual(self.driver.mapping(),out);self.assertFalse(self.upload.transport_offered)
    def test_lost_commit_recovers_readonly_ready(self):
        self.bus.lost=True
        with self.assertRaises(OSError):self.driver.prepare(self.upload,**self.args)
        n=len(self.bus.writes);self.driver.prepare(self.upload,**self.args)
        self.assertEqual(n,len(self.bus.writes));self.assertEqual(self.bus.effects,1)
    def test_wrong_peer_identity_no_writes(self):
        args={**self.args,'peer_epoch':2}
        with self.assertRaises(ValueError):self.driver.prepare(self.upload,**args)
        self.assertFalse(self.bus.writes)
    def test_durable_intent_failure_no_writes(self):
        with patch.object(self.upload,'record',side_effect=OSError('fsync failed')):
            with self.assertRaises(OSError):self.driver.prepare(self.upload,**self.args)
        self.assertFalse(self.bus.writes)
    def test_pending_status_no_writes(self):
        self.bus.pending=True
        with self.assertRaises(RuntimeError):self.driver.prepare(self.upload,**self.args)
        self.assertFalse(self.bus.writes)
    def test_rejected_commit_never_arms(self):
        self.bus.reject=True
        with self.assertRaises(RuntimeError):self.driver.prepare(self.upload,**self.args)
    def test_consumed_mapping_never_reprepares(self):
        self.driver.prepare(self.upload,**self.args);self.bus.state=2
        n=len(self.bus.writes)
        with self.assertRaises(RuntimeError):self.driver.prepare(self.upload,**self.args)
        self.assertEqual(n,len(self.bus.writes))
    def test_full_durable_binding_join_after_actual_arm(self):
        ledger=CompletionLedger(self.root/'completion',local_epoch=1,peer_epoch=1,session=self.upload.session)
        self.addCleanup(ledger.close);reader=H1CompletionReader(StatusBus(ledger),ledger)
        bus=self.bus;identity=self.identity
        class Runtime:
            def arm(self,**kwargs):
                assert bus.state==1 and kwargs['identity']==identity
                bus.state=2
                return Binding(1,17,2,identity,500,800000)
            def snapshot(self):return {'epoch':1,'tick':499,'seq':1}
        bound=self.driver.arm_prepared(Runtime(),reader,self.upload,**self.args,delay_ticks=500,duration_ticks=799500)
        self.assertEqual(ledger.current['binding']['start'],bound.start)
        self.assertFalse(self.upload.transport_offered)
    def test_no_actual_consume_prevents_completion_binding(self):
        ledger=CompletionLedger(self.root/'completion',local_epoch=1,peer_epoch=1,session=self.upload.session)
        self.addCleanup(ledger.close);reader=H1CompletionReader(StatusBus(ledger),ledger)
        identity=self.identity
        class Runtime:
            def arm(self,**kwargs):return Binding(1,17,2,identity,500,800000)
        with self.assertRaises(RuntimeError):self.driver.arm_prepared(Runtime(),reader,self.upload,**self.args,delay_ticks=500,duration_ticks=799500)
        self.assertIsNone(ledger.current);self.assertFalse(self.upload.transport_offered)

    def completed_reader(self):
        self.driver.prepare(self.upload,**self.args);self.bus.state=2
        ledger=CompletionLedger(self.root/'completion',local_epoch=1,peer_epoch=1,session=self.upload.session)
        self.addCleanup(ledger.close);bus=StatusBus(ledger);reader=H1CompletionReader(bus,ledger)
        reader.bind_prepared(Binding(1,17,2,self.identity,500,800000),self.upload)
        bus.events=[reply(self.inner,seq=1),reply(self.inner,0x83,seq=1)]
        reader.read_and_preserve();reader.read_and_preserve()
        return reader

    def test_retirement_requires_runtime_and_mapping_feedback(self):
        reader=self.completed_reader();bus=self.bus
        class Runtime:
            def archive_and_request_release(self,archive,**kwargs):
                assert reader.ledger.done
                return {'business_success':False,'hardware_retirement_verified':False},'ticket'
            def wait_retirement(self,ticket,**kwargs):
                assert ticket=='ticket';bus.state=0;bus.retired=1
                return {'hardware_retirement_verified':True,'retire_count':1}
        class Archive:
            def drain_aux(self):pass
        out=self.driver.archive_and_retire(Runtime(),reader,Archive())
        self.assertTrue(out['mapping_retirement_verified']);self.assertFalse(out['business_success'])

    def test_runtime_only_retirement_never_claims_mapping_retired(self):
        reader=self.completed_reader()
        class Runtime:
            def archive_and_request_release(self,archive,**kwargs):return {},'ticket'
            def wait_retirement(self,ticket,**kwargs):return {'hardware_retirement_verified':True}
        class Archive:
            def drain_aux(self):pass
        with self.assertRaises(RuntimeError):self.driver.archive_and_retire(Runtime(),reader,Archive())

    def test_different_ready_mapping_cannot_be_overwritten(self):
        self.driver.prepare(self.upload,**self.args);self.bus.live[2]=18
        n=len(self.bus.writes)
        with self.assertRaises(RuntimeError):self.driver.prepare(self.upload,**self.args)
        self.assertEqual(len(self.bus.writes),n)

    def test_durable_binding_overruns_start_never_offers_packet(self):
        ledger=CompletionLedger(self.root/'completion',local_epoch=1,peer_epoch=1,session=self.upload.session)
        self.addCleanup(ledger.close);reader=H1CompletionReader(StatusBus(ledger),ledger)
        bus=self.bus;identity=self.identity
        class Runtime:
            def arm(self,**kwargs):
                bus.state=2;return Binding(1,17,2,identity,500,800000)
            def snapshot(self):return {'epoch':1,'tick':500,'seq':1}
        with self.assertRaises(RuntimeError):self.driver.arm_prepared(Runtime(),reader,self.upload,**self.args,delay_ticks=500,duration_ticks=799500)
        self.assertFalse(self.upload.transport_offered);self.assertIsNotNone(ledger.current)

if __name__=='__main__':unittest.main(verbosity=2)
