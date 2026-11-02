"""Bookkeeping model with synthetic DUT reports and real evidence files. No I/O."""
from pathlib import Path
from types import SimpleNamespace
import sys,unittest,uuid,hashlib
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'host'),str(ROOT/'tests')]
from ch1_image_attempt_ledger import ImageAttemptLedger
from ch1_runtime_driver import Binding
from ch1_completion_ledger import _codec
from test_evidence_store import packed
import ch1_evidence_store as store

class ImageTests(unittest.TestCase):
    def setUp(self):
        self.root=ROOT/'evidence/offline_image_ledger_tests'/('test_'+uuid.uuid4().hex)
        self.source=bytes(range(256))*64;self.codec=_codec()
        chunks=[self.source[i:i+256] for i in range(0,len(self.source),256)]
        self.config=self.codec.encode_config(1,2,128,128,len(self.source),64,256,hashlib.sha256(self.source).digest(),[store.crc16(x) for x in chunks])
        self.ledger=ImageAttemptLedger(self.root/'image',self.source,self.config,epoch=1,trial_registry=self.root/'global_trials')
        self.addCleanup(self.ledger.close)
        self.previous=self.owner(2,self.config,0,0,0,1)
        self.ledger.accept_config(self.previous)
    def owner(self,kind,inner,trial,index,attempt,generation):
        identity=int.from_bytes(packed([(37,0),(32,0x10203040),(32,generation),(32,1),(3,0),
            (32,generation),(32,1),(8,2),(16,trial),(16,index),(8,attempt),(8,0)]),'big')
        return SimpleNamespace(fault=False,phase='RETIRED',completion=SimpleNamespace(current=None),
            upload=SimpleNamespace(credit=1),journal=self.ledger.journal,
            binding=Binding(1,generation,kind,identity,50,800000),prepared_inner=inner,business_success=True,saved_proof=None)
    def finish(self,inner,trial,index,attempt,generation,bad=False):
        expected=self.ledger.chunks[index];actual=expected if not bad else bytes((expected[0]^1,))+expected[1:]
        report=self.codec.encode_report(1,2,trial,index,attempt,0,0,0,actual)
        owner=self.owner(1,inner,trial,index,attempt,generation)
        ticks=[100+1000*i for i in range(len(report))];close=ticks[-1]+2000
        d=packed([(32,1),(1,0),(256,owner.binding.identity),(32,generation),(2,1),(8,1),(16,len(report)),
            (64,50),(64,800000),(64,close),(1,1),(8,0),(8,0),(16,0),(32,0),(4,0),(64,0)])
        samples=b''.join(((b<<68)|t).to_bytes(10,'big') for b,t in zip(report,ticks))
        receipt=store.persist_record(self.root/'main',d,samples,store.crc16(d),store.crc16(samples),
            errors=[],orphans=[],watermark_tick=close+1,expected_payload=expected)
        owner.business_success=receipt['business_success'];owner.saved_proof=receipt
        result=self.ledger.record_attempt(owner);self.previous=owner
        return result
    def test_64_received_chunks_reconstruct_actual_image(self):
        for i in range(64):
            inner=self.ledger.prepare_item(i,0,i+1,self.previous)
            self.assertTrue(self.finish(inner,i+1,i,0,i+2)['business_success'])
        out=self.ledger.reconstruct()
        self.assertEqual(Path(out['received_path']).read_bytes(),self.source);self.assertEqual(out['items'],64)
    def test_bad_first_item_not_filled_then_exact_retry_recovers(self):
        for i in range(64):
            inner=self.ledger.prepare_item(i,0,i+1,self.previous)
            self.finish(inner,i+1,i,0,i+2,bad=(i==0))
        self.assertNotIn(0,self.ledger.received)
        with self.assertRaises(RuntimeError):self.ledger.reconstruct()
        inner=self.ledger.prepare_item(0,1,65,self.previous)
        self.finish(inner,65,0,1,66)
        self.assertEqual(Path(self.ledger.reconstruct()['received_path']).read_bytes(),self.source)
    def test_trial_reuse_denied_before_new_offer(self):
        inner=self.ledger.prepare_item(0,0,1,self.previous);self.finish(inner,1,0,0,2,bad=True)
        with self.assertRaises(FileExistsError):self.ledger.prepare_item(0,1,1,self.previous)
    def test_source_config_sha_mismatch_rejected(self):
        with self.assertRaises(ValueError):ImageAttemptLedger(self.root/'bad_source',b'bad',self.config,epoch=2,trial_registry=self.root/'global_trials')
    def test_not_retired_owner_cannot_prepare_next(self):
        self.previous.phase='STARTED'
        with self.assertRaises(RuntimeError):self.ledger.prepare_item(0,0,1,self.previous)
    def test_existing_image_session_cannot_silently_resume(self):
        with self.assertRaises(FileExistsError):ImageAttemptLedger(self.root/'image',self.source,self.config,epoch=1,trial_registry=self.root/'global_trials')

if __name__=='__main__':unittest.main(verbosity=2)
