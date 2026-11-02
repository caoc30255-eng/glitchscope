"""Partial admission source checks; modeled peer ACKs, real flight files."""
from pathlib import Path
from types import SimpleNamespace
import hashlib,sys,unittest,uuid
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'host'),str(ROOT/'tests'),str(ROOT/'host')]
from ch1_admission_parts import AdmissionParts
from ch1_control_session import ApplicationJournal,PeerControlSession,frame,event_payload,decode_event,decode_frame
from ch1_completion_ledger import _codec
from ch1_runtime_driver import Binding
from h1_upload_ledger import UploadLedger
from h1_protocol import Kind
from test_completion_ledger import reply
from test_evidence_store import fixture
import ch1_evidence_store as store

class ProfilePeer:
    def __init__(self,journal,session):self.journal=journal;self.session=session;self.commands=[];self.bad_ack=False
    def read(self,a):return {0:0x48354531,4:1,0x24:1,0x28:self.session,0x2c:0}[a]
    def request_profile_none(self,identity):
        class Wire:
            def __init__(self,parent):self.parent=parent
            def exchange(self,request,expected):
                kind,p=decode_frame(request);assert kind==0x3a
                self.parent.commands.append(request)
                return frame(0x7a,p if not self.parent.bad_ack else p[:-1]+b'\x01')
        return PeerControlSession(Wire(self),self.journal,0x75000001).request_profile_none(identity)

class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.root=ROOT/'evidence/offline_admission_tests'/('test_'+uuid.uuid4().hex)
        self.journal=ApplicationJournal(self.root/'journal',0x75000001);self.addCleanup(self.journal.close)
        self.upload=UploadLedger(self.root/'upload',0x10203040);self.addCleanup(self.upload.close)
        self.upload.prepare(Kind.HELLO);self.upload.observe(reply(b'',0x80,seq=0,crc=0,credit=1))
        self.upload.seq=1 # Explicit test fixture for previously retired CONFIG.
        self.payload=bytes(range(256));codec=_codec()
        self.inner=codec.encode_item(1,2,3,0,1,0,0,self.payload);self.upload.prepare(Kind.ITEM,self.inner)
        base=store.descriptor_decode(fixture()[0])['identity']
        self.identity=(base & ~((0xffffffff<<155)|(0xffffffff<<88)|(0xffff<<16)|(0xff<<8)))|(2<<155)|(2<<88)
        self.binding=Binding(1,18,1,self.identity,50,800000)
        cfg_identity=(self.identity & ~((0xffffffff<<155)|(0xffffffff<<88)))|(1<<155)|(1<<88)
        cfg=codec.encode_config(1,2,16,16,256,1,256,hashlib.sha256(self.payload).digest(),[store.crc16(self.payload)])
        ack=decode_event(frame(0x79,event_payload(cfg_identity,17)))
        self.journal.record('control_rx_stream',raw_hex=ack['raw_hex'])
        self.config_owner=SimpleNamespace(fault=False,phase='RETIRED',business_success=True,config_success_ack=ack,
            prepared_inner=cfg,binding=Binding(1,17,2,cfg_identity,50,800000),journal=self.journal)
        self.peer=ProfilePeer(self.journal,self.upload.session);self.factory=AdmissionParts(self.root/'flight',self.journal)
    def register(self):return self.factory.register(self.binding,self.upload,self.peer,config_owner=self.config_owner)
    def test_actual_namespace_policy_ack_and_flight_files_remain_partial(self):
        parts=self.register()
        self.assertTrue(parts['STM_expected_flight_registered'] and parts['policy_ready'])
        self.assertFalse(parts['CH0_registered'] or parts['generation_continuity_verified'] or parts['admission_complete'])
        self.assertEqual((Path(parts['flight_dir'])/'inner.bin').read_bytes(),self.inner)
        with self.assertRaises(RuntimeError):self.factory.require_complete(parts)
    def test_none_profile_matches_frozen_layout(self):
        parts=self.register();kind,p=decode_frame(bytes.fromhex(parts['policy_receipt']['request_hex']))
        context=event_payload(self.identity & ~(0xffffffff<<88),0)
        self.assertEqual(kind,0x3a);self.assertEqual(p,context[:12]+context[17:28]+bytes(9))
    def test_config_approval_missing_rejected_before_policy_command(self):
        self.config_owner.config_success_ack=None
        with self.assertRaises(RuntimeError):self.register()
        self.assertFalse(self.peer.commands)
    def test_wrong_source_crc_table_rejected(self):
        self.config_owner.prepared_inner=_codec().encode_config(1,2,16,16,256,1,256,bytes(32),[0x1234])
        with self.assertRaises(ValueError):self.register()
        self.assertFalse(self.peer.commands)
    def test_stale_config_namespace_rejected(self):
        self.config_owner.binding=Binding(2,17,2,self.config_owner.binding.identity,50,800000)
        with self.assertRaises(ValueError):self.register()
    def test_changed_profile_ack_does_not_produce_ready_parts(self):
        self.peer.bad_ack=True
        with self.assertRaises(ValueError):self.register()
        self.assertTrue(list((self.root/'flight').glob('*/committed.json')))
    def test_journal_disk_failure_prevents_profile_program(self):
        from unittest.mock import patch
        with patch.object(self.journal,'record',side_effect=OSError('flight journal failed')):
            with self.assertRaises(OSError):self.register()
        self.assertFalse(self.peer.commands)

    def native_config_capture(self, **overrides):
        journal=ApplicationJournal(self.root/'native_config',0x75000002)
        self.addCleanup(journal.close)
        self.config_owner.journal=journal
        fields=dict(collector='native_C_background',native_error=0,
                    bad_rx_word=None,pending_hex='',
                    rx_hex=self.config_owner.config_success_ack['raw_hex'])
        fields.update(overrides)
        journal.record('uart_byte_exchange_saved',**fields)

    def test_background_saved_capture_authorizes_exact_config(self):
        self.native_config_capture()
        self.assertTrue(self.register()['STM_expected_flight_registered'])

    def test_foreground_native_saved_capture_authorizes_exact_config(self):
        self.native_config_capture(collector='native_C')
        self.assertTrue(self.register()['STM_expected_flight_registered'])

    def test_native_hardware_error_is_not_config_evidence(self):
        self.native_config_capture(native_error=3)
        with self.assertRaises(ValueError):self.register()
        self.assertFalse(self.peer.commands)

    def test_native_partial_capture_is_not_config_evidence(self):
        self.native_config_capture(pending_hex='a55a')
        with self.assertRaises(ValueError):self.register()

    def test_native_unknown_collector_is_not_config_evidence(self):
        self.native_config_capture(collector='unverified')
        with self.assertRaises(ValueError):self.register()

    def test_native_missing_original_is_not_config_evidence(self):
        self.native_config_capture(rx_hex='')
        with self.assertRaises(ValueError):self.register()

    def test_native_other_valid_ack_cannot_authorize_config(self):
        other=frame(0x79,event_payload(self.config_owner.binding.identity,18))
        self.native_config_capture(rx_hex=other.hex())
        with self.assertRaises(ValueError):self.register()

    def test_native_matching_prefix_with_partial_tail_is_not_evidence(self):
        self.native_config_capture(rx_hex=self.config_owner.config_success_ack['raw_hex']+'a55a')
        with self.assertRaises(ValueError):self.register()

if __name__=='__main__':unittest.main(verbosity=2)
