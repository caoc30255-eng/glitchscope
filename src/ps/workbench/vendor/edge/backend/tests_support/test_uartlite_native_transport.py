"""Native C collector + scheduled C UART model + real fsync; no hardware."""
from pathlib import Path
import os,sys,uuid,unittest,ctypes as C
from unittest.mock import patch
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'host'))
from ch1_uartlite_native_transport import NativeUARTLiteControlTransport
from ch1_control_session import ApplicationJournal,frame

LIB=os.environ.get('UART_NATIVE_TEST_LIBRARY')
@unittest.skipUnless(LIB,'Native C fixture must be compiled for this host')
class NativeTests(unittest.TestCase):
    def setUp(self):
        directory=ROOT/'evidence/offline_native_tests'/uuid.uuid4().hex
        self.journal=ApplicationJournal(directory,1);self.addCleanup(self.journal.close)
        class Bus:
            array=np.zeros(4,dtype=np.uint32)
            def read(self,*args):raise AssertionError('slow access')
            def write(self,*args):raise AssertionError('slow access')
        self.request=frame(0x3b,bytes(32));self.reply=frame(0x7b,bytes(32))
        self.bus=Bus();self.fixture=C.CDLL(LIB)
        self.fixture.fixture_reset.argtypes=[C.c_void_p,C.c_uint32,C.c_uint32,C.c_uint32]
        self.adapter=NativeUARTLiteControlTransport(self.bus,self.journal,library=LIB,
            exclusive_owner=True,timeout=0.02,quiet_time=0.002,interbyte_timeout=0.004)
        self.reset(self.reply)
    def reset(self,raw,trigger=39,mode=0):
        buf=(C.c_uint8*len(raw)).from_buffer_copy(raw)
        self.fixture.fixture_reset(buf,len(raw),trigger,mode)
    def test_exact_39byte_reply_and_guard_once(self):
        calls=[]
        def guard():
            self.assertEqual(self.fixture.fixture_txcount(),0)
            self.assertIn('uart_byte_exchange_intent',self.journal.path.read_text())
            calls.append(1)
        self.assertEqual(self.adapter.exchange_checked(self.request,0x7b,guard),self.reply)
        self.assertEqual(calls,[1]);self.assertEqual(self.fixture.fixture_txcount(),39)
        self.assertEqual(self.adapter.last_trace['collector'],'native_C')
        self.assertIn(self.reply.hex(),self.journal.path.read_text())
    def test_overrun_stops_and_keeps_uncertain_prefix(self):
        self.reset(self.reply,mode=1)
        with self.assertRaises(RuntimeError):self.adapter.exchange(self.request,0x7b)
        self.assertEqual(self.fixture.fixture_rxreads(),22)
        self.assertEqual(self.adapter.last_trace['last_status'],'0x27')
        self.assertTrue(self.adapter.last_trace['request_effect_uncertain'])
        with self.assertRaises(RuntimeError):self.adapter.exchange(self.request,0x7b)
        self.assertEqual(self.fixture.fixture_txcount(),39)
    def test_bad_RX_DWORD_not_invented(self):
        self.reset(self.reply,mode=2)
        with self.assertRaises(ValueError):self.adapter.exchange(self.request,0x7b)
        self.assertEqual(self.adapter.last_trace['rx_hex'],'')
    def test_bad_CRC_retained(self):
        bad=self.reply[:-1]+bytes([self.reply[-1]^1]);self.reset(bad)
        with self.assertRaises(ValueError):self.adapter.exchange(self.request,0x7b)
        self.assertEqual(self.adapter.last_trace['rx_hex'],bad.hex())
    def test_partial_reply_retained(self):
        self.reset(self.reply[:-1])
        with self.assertRaises(TimeoutError):self.adapter.exchange(self.request,0x7b)
        self.assertEqual(self.adapter.last_trace['pending_hex'],self.reply[:-1].hex())
    def test_stale_reply_blocks_TX(self):
        self.reset(self.reply,trigger=0)
        with self.assertRaises(RuntimeError):self.adapter.exchange(self.request,0x7b)
        self.assertEqual(self.fixture.fixture_txcount(),0)
    def test_duplicate_reply_denied(self):
        self.reset(self.reply+self.reply)
        with self.assertRaises(RuntimeError):self.adapter.exchange(self.request,0x7b)
        self.assertEqual(self.adapter.last_trace['native_error'],8)
    def test_notification_and_reply_order_preserved(self):
        event=frame(0x31,bytes(32));self.reset(event+self.reply)
        self.assertEqual(self.adapter.exchange(self.request,0x7b),event+self.reply)
    def test_guard_failure_sends_nothing(self):
        def guard():raise RuntimeError('window expired')
        with self.assertRaisesRegex(RuntimeError,'window expired'):
            self.adapter.exchange_checked(self.request,0x7b,guard)
        self.assertEqual(self.fixture.fixture_txcount(),0)
    def test_disk_failure_before_TX_sends_nothing(self):
        with patch.object(self.journal,'record',side_effect=OSError('disk')):
            with self.assertRaises(OSError):self.adapter.exchange(self.request,0x7b)
        self.assertEqual(self.fixture.fixture_txcount(),0)
    def test_disk_failure_after_RX_returns_no_reply(self):
        record=self.journal.record
        def fail(event,**kw):
            if event=='uart_byte_exchange_saved':raise OSError('RX disk')
            return record(event,**kw)
        with patch.object(self.journal,'record',side_effect=fail):
            with self.assertRaises(OSError):self.adapter.exchange(self.request,0x7b)
        self.assertTrue(self.adapter.fault)
        self.assertEqual(self.adapter.last_trace['rx_hex'],self.reply.hex())
    def test_saved_capture_receipt_matches_exact_bytes_and_owned_journal(self):
        result=self.adapter.exchange(self.request,0x7b)
        self.assertTrue(self.adapter.capture_is_durable(self.request,result,self.journal))
        self.assertFalse(self.adapter.capture_is_durable(self.request,b'wrong',self.journal))
        self.journal.record('later')
        self.assertFalse(self.adapter.capture_is_durable(self.request,result,self.journal))
    def test_precommitted_exact_intent_is_not_fsynced_twice(self):
        self.journal.record('control_tx_intent',raw_hex=self.request.hex())
        before=self.journal.index
        self.adapter.exchange(self.request,0x7b)
        self.assertEqual(self.journal.index,before+1) # RX original saved once.
