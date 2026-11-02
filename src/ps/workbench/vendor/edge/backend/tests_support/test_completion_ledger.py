"""Raw H1 status register model and real durable journal; no board/RTL execution."""
from dataclasses import replace
from pathlib import Path
import struct, sys, unittest, uuid
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'host'),str(ROOT/'tests')]
import ch1_evidence_store as store
from ch1_completion_ledger import CompletionLedger,H1CompletionReader,_codec
from ch1_runtime_driver import Binding
from test_evidence_store import fixture


def reply(inner,state=0x81,session=0x10203040,seq=7,crc=None,code=0,credit=0):
    body=struct.pack('>BBIIHBB',1,state,session,seq,store.crc16(inner) if crc is None else crc,code,credit)
    return b'\xa6\x6a'+body+store.crc16(body).to_bytes(2,'big')


class StatusBus:
    def __init__(self,ledger):
        self.ledger=ledger; self.events=[]; self.held=False; self.ticket=0
        self.mask=0; self.writes=[]; self.lost_reply=False; self.bad_mask=False
        self.overflow=False; self.padding=b'\0\0'; self.meta=0x112
    def read(self,a):
        if a==0:return 0x48315431
        if a==4:return 1|(8 if self.events else 0)|(16 if self.held else 0)|(32 if self.overflow else 0)
        if a==0x40:self.mask|=1;return self.ticket
        if a==0x44:self.mask|=2;return self.meta
        if a in (0x48,0x4c,0x50,0x54,0x58):
            i=(a-0x48)//4;self.mask|=1<<(i+2)
            return int.from_bytes((self.events[0]+self.padding)[i*4:i*4+4],'big')
        if a==0x5c:return 63 if self.bad_mask else self.mask
        raise AssertionError(a)
    def write(self,a,v):
        self.writes.append((a,v))
        if a==0x30:self.held=True;self.ticket+=1;self.mask=0
        elif a==0x34:
            self.ledger.verify_journal()
            assert self.mask==127 and v==self.ticket
            records=[__import__('json').loads(x) for x in self.ledger.path.read_text().splitlines()]
            assert any(r['event']=='status_matched' and r['ticket']==v for r in records)
            if self.lost_reply:
                self.lost_reply=False;raise OSError('Reply lost before local release execution')
            self.events.pop(0);self.held=False
        else:raise AssertionError(a)


class CompletionTests(unittest.TestCase):
    def setUp(self):
        self.root=ROOT/'evidence/offline_completion_tests'/('test_'+uuid.uuid4().hex)
        self.ledger=CompletionLedger(self.root,local_epoch=1,peer_epoch=1,session=0x10203040)
        self.addCleanup(self.ledger.close)
        d,_,_,_=fixture();identity=store.descriptor_decode(d)['identity']
        self.bound=Binding(1,17,1,identity,50,800000)
        self.inner=_codec().encode_item(1,2,3,4,64,1,0,bytes(range(256))*2)
        self.bus=StatusBus(self.ledger);self.reader=H1CompletionReader(self.bus,self.ledger)
        self.packet=self.reader.bind(self.bound,self.inner)
    def observe(self,raw,ticket=1,epoch=1,meta=0x112):
        return self.ledger.observe_snapshot(source_epoch=epoch,ticket=ticket,meta=meta,packed=raw+b'\0\0')
    def accepted(self):self.observe(reply(self.inner))

    def test_full_packet_matches_prepared_frame_and_binding(self):
        self.assertEqual(len(self.packet),550);self.assertEqual(self.packet[14:-2],self.inner)
        self.assertEqual(store.crc16(self.packet[2:-2]),int.from_bytes(self.packet[-2:],'big'))
        self.assertIn(self.inner.hex(),self.ledger.path.read_text())

    def test_matching_done_after_saved_accepted_returns_full_receipt(self):
        self.accepted();self.observe(reply(self.inner,0x83),2)
        r=self.ledger.completion_receipt()
        self.assertEqual(r['binding']['identity'],self.bound.identity)
        self.assertFalse(r['hardware_physical_done_published'])
        r['binding']['identity']=0
        self.assertEqual(self.ledger.completion_receipt()['binding']['identity'],self.bound.identity)

    def test_missing_done_ready_is_only_advisory(self):
        self.accepted();r=self.observe(reply(self.inner,0x80,credit=1),2)
        self.assertFalse(r['completion_seen'])
        with self.assertRaises(RuntimeError):self.ledger.completion_receipt()

    def test_done_before_accepted_faults_and_keeps_raw(self):
        raw=reply(self.inner,0x83)
        with self.assertRaises(ValueError):self.observe(raw)
        self.assertTrue(self.ledger.fault);self.assertIn(raw.hex(),self.ledger.path.read_text())

    def test_wrong_session_denied(self):
        with self.assertRaises(ValueError):self.observe(reply(self.inner,session=42))

    def test_wrong_sequence_denied(self):
        with self.assertRaises(ValueError):self.observe(reply(self.inner,seq=8))

    def test_wrong_local_epoch_denied(self):
        with self.assertRaises(ValueError):self.observe(reply(self.inner),epoch=2)

    def test_wrong_inner_crc_denied(self):
        with self.assertRaises(ValueError):self.observe(reply(self.inner,crc=0))

    def test_bad_frame_crc_denied(self):
        raw=bytearray(reply(self.inner));raw[-1]^=1
        with self.assertRaises(ValueError):self.observe(raw)

    def test_uart_error_reason_denied(self):
        with self.assertRaises(ValueError):self.observe(reply(self.inner),meta=0x412)

    def test_rejected_status_locks(self):
        with self.assertRaises(ValueError):self.observe(reply(self.inner,0x82,code=3))

    def test_duplicate_done_no_second_completion(self):
        self.accepted();raw=reply(self.inner,0x83)
        self.assertTrue(self.observe(raw,2)['new_completion'])
        self.assertFalse(self.observe(raw,3)['new_completion'])

    def test_exact_held_snapshot_retry_allowed(self):
        raw=reply(self.inner);self.observe(raw)
        self.assertFalse(self.observe(raw)['new_completion']);self.assertFalse(self.ledger.fault)

    def test_ticket_changed_bytes_denied(self):
        self.accepted()
        with self.assertRaises(ValueError):self.observe(reply(self.inner,0x80))

    def test_regressed_ticket_denied(self):
        self.observe(reply(self.inner),2)
        with self.assertRaises(ValueError):self.observe(reply(self.inner),1)

    def test_status_regression_after_done_denied(self):
        self.accepted();self.observe(reply(self.inner,0x83),2)
        with self.assertRaises(ValueError):self.observe(reply(self.inner),3)

    def test_session_reuse_across_epochs_denied(self):
        with self.assertRaises(FileExistsError):CompletionLedger(self.root,local_epoch=2,peer_epoch=2,session=0x10203040)

    def test_new_record_blocked_without_retirement_owner(self):
        self.accepted();self.observe(reply(self.inner,0x83),2)
        with self.assertRaises(RuntimeError):self.ledger.bind(replace(self.bound,record_id=18),self.inner)

    def test_prepared_inner_identity_mismatch_denied(self):
        other=CompletionLedger(self.root/'other',local_epoch=1,peer_epoch=1,session=0x10203040)
        self.addCleanup(other.close)
        with self.assertRaises(ValueError):other.bind(replace(self.bound,identity=self.bound.identity^(1<<8)),self.inner)

    def test_peer_epoch_identity_mismatch_denied(self):
        other=CompletionLedger(self.root/'other',local_epoch=1,peer_epoch=2,session=0x10203040)
        self.addCleanup(other.close)
        with self.assertRaises(ValueError):other.bind(self.bound,self.inner)

    def test_journal_tamper_withholds_receipt(self):
        self.accepted();self.observe(reply(self.inner,0x83),2)
        self.ledger.path.write_text(self.ledger.path.read_text().replace('status_matched','status_changed'))
        with self.assertRaises(ValueError):self.ledger.completion_receipt()

    def test_real_snapshot_reads_and_persistence_before_pop(self):
        self.bus.events=[reply(self.inner),reply(self.inner,0x83)]
        self.reader.read_and_preserve();r=self.reader.read_and_preserve()
        self.assertTrue(r['new_completion']);self.assertFalse(self.bus.events)
        self.assertEqual(sum(a==0x34 for a,v in self.bus.writes),2)

    def test_failed_fsync_never_pops_or_authorizes(self):
        self.bus.events=[reply(self.inner)]
        with patch('ch1_completion_ledger.os.fsync',side_effect=OSError('disk unavailable')):
            with self.assertRaises(OSError):self.reader.read_and_preserve()
        self.assertFalse(any(a==0x34 for a,v in self.bus.writes));self.assertTrue(self.bus.held)
        with self.assertRaises(RuntimeError):self.ledger.completion_receipt()

    def test_lost_pop_reply_retry_does_not_restage_snapshot(self):
        self.bus.events=[reply(self.inner)];self.bus.lost_reply=True
        with self.assertRaises(OSError):self.reader.read_and_preserve()
        self.reader.read_and_preserve()
        self.assertEqual(sum(a==0x30 for a,v in self.bus.writes),1)
        self.assertEqual(sum(a==0x34 for a,v in self.bus.writes),2)

    def test_missing_read_coverage_blocks_pop_and_receipt(self):
        self.bus.events=[reply(self.inner)];self.bus.bad_mask=True
        with self.assertRaises(RuntimeError):self.reader.read_and_preserve()
        self.assertFalse(any(a==0x34 for a,v in self.bus.writes));self.assertTrue(self.ledger.fault)

    def test_nonzero_packed_padding_blocks_pop(self):
        self.bus.events=[reply(self.inner)];self.bus.padding=b'\0\1'
        with self.assertRaises(ValueError):self.reader.read_and_preserve()
        self.assertFalse(any(a==0x34 for a,v in self.bus.writes))

    def test_transport_overflow_revokes_existing_receipt(self):
        self.accepted();self.observe(reply(self.inner,0x83),2);self.bus.overflow=True
        with self.assertRaises(RuntimeError):self.reader.read_and_preserve()
        with self.assertRaises(RuntimeError):self.ledger.completion_receipt()

    def test_management_bindings_keep_local_trial_fields_without_wire_echo(self):
        codec=_codec()
        frames=[(2,codec.encode_config(1,2,16,16,256,1,256,bytes(32),[0x1234]),2),
                (3,codec.encode_cleanup(1,2),4)]
        for kind,inner,wire_kind in frames:
            other=CompletionLedger(self.root/f'management_{kind}',local_epoch=1,peer_epoch=1,session=0x10203040)
            self.addCleanup(other.close)
            packet=other.bind(replace(self.bound,kind=kind),inner)
            self.assertEqual(packet[3],wire_kind)
            other.observe_snapshot(source_epoch=1,ticket=1,meta=0x112,packed=reply(inner)+b'\0\0')
            other.observe_snapshot(source_epoch=1,ticket=2,meta=0x112,packed=reply(inner,0x83)+b'\0\0')
            self.assertEqual(other.completion_receipt()['binding']['identity'],self.bound.identity)

    def test_existing_upload_ledger_prepared_binding_and_status_join(self):
        sender=ROOT
        sys.path.insert(0,str(sender/'host'))
        from h1_upload_ledger import UploadLedger
        from h1_protocol import Kind
        upload=UploadLedger(self.root/'upload',0x10203040);self.addCleanup(upload.close)
        upload.prepare(Kind.HELLO);upload.observe(reply(b'',0x80,seq=0,crc=0,credit=1))
        inner=_codec().encode_config(1,2,16,16,256,1,256,bytes(32),[0x1234])
        original=upload.prepare(Kind.CONFIG,inner)
        other=CompletionLedger(self.root/'join',local_epoch=1,peer_epoch=1,session=0x10203040)
        self.addCleanup(other.close)
        bus=StatusBus(other);reader=H1CompletionReader(bus,other)
        identity=(self.bound.identity & ~(0xffffffff<<155)) | (1<<155)
        bound=replace(self.bound,kind=2,identity=identity)
        self.assertEqual(reader.bind_prepared(bound,upload),original)
        self.assertFalse(upload.transport_offered)
        bus.events=[reply(inner,seq=1),reply(inner,0x83,seq=1)]
        reader.read_and_preserve();reader.read_and_preserve()
        self.assertTrue(upload.accepted and upload.done)
        self.assertEqual(other.completion_receipt()['seq'],1)


if __name__=='__main__':unittest.main(verbosity=2)
