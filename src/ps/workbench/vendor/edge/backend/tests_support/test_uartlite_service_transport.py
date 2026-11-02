"""Persistent C pthread RX across Python/disk pauses; no real UART hardware."""
from pathlib import Path
import sys,os,uuid,ctypes as C,time,unittest,threading
from unittest.mock import patch
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'host'))
from ch1_uartlite_service_transport import BackgroundUARTLiteControlTransport
from ch1_control_session import ApplicationJournal,frame
LIB=os.environ.get('UART_SERVICE_TEST_LIBRARY')
@unittest.skipUnless(LIB,'Service fixture must be compiled for host')
class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.j=ApplicationJournal(ROOT/'evidence/offline_RX_service_tests'/uuid.uuid4().hex,1)
        self.addCleanup(self.j.close)
        class Bus:
            array=np.zeros(4,dtype=np.uint32)
        self.lib=C.CDLL(LIB)
        self.lib.fixture_reset.argtypes=[C.c_void_p,C.c_uint32,C.c_uint32]
        self.lib.fixture_error.argtypes=[C.c_uint32]
        self.lib.fixture_parser_stall.argtypes=[C.c_uint32]
        self.lib.fixture_wire_gap.argtypes=[C.c_uint32,C.c_uint32]
        self.lib.fixture_finite_fifo.argtypes=[C.c_uint32]
        self.lib.fixture_hold_worker.argtypes=[C.c_uint32]
        self.lib.fixture_TX_pause.argtypes=[C.c_uint32,C.c_uint32,C.c_uint32]
        self.request=frame(0x3b,bytes(32));self.reply=frame(0x7b,bytes(32));self.event=frame(0x31,bytes(32))
        self.reset(self.reply,39)
        self.a=BackgroundUARTLiteControlTransport(Bus(),self.j,library=LIB,
            exclusive_owner=True,timeout=0.5,interbyte_timeout=0.1,quiet_time=0.002,poll_limit=10000000)
        self.addCleanup(self.a.close)
        self.addCleanup(lambda:self.lib.fixture_hold_worker(0))
    def reset(self,raw,trigger):
        buf=(C.c_uint8*len(raw)).from_buffer_copy(raw)
        self.lib.fixture_reset(buf,len(raw),trigger)
    def wait_buffer(self,count):
        deadline=time.monotonic()+1
        while self.a.pending_snapshot()['total_buffered']<count:
            if time.monotonic()>deadline:self.fail('worker did not collect')
            time.sleep(0.001)
    def test_explicit_start_required(self):
        self.assertIsNone(self.a.context)
        with self.assertRaises(RuntimeError):self.a.exchange(self.request,0x7b)
        self.assertEqual(self.lib.fixture_txcount(),0)
    def test_notification_collected_while_Python_pauses(self):
        self.reset(self.event,0);self.a.start_receiver()
        time.sleep(0.03);self.wait_buffer(39)
        snapshot=self.a.pending_snapshot()
        self.assertEqual(bytes(snapshot['buffered_words']),self.event)
        self.assertEqual(self.a.exchange(b'',None),self.event)
        self.assertEqual(self.lib.fixture_txcount(),0)
    def test_notifications_collected_during_actual_journal_commit_delay(self):
        self.reset(self.event,0);self.a.start_receiver()
        original=self.j.record
        def slow(event,**kw):
            if event=='uart_byte_exchange_intent':time.sleep(0.03)
            return original(event,**kw)
        with patch.object(self.j,'record',side_effect=slow):
            self.assertEqual(self.a.exchange(b'',None),self.event)
        self.assertEqual(self.a.last_trace['collector'],'native_C_background')
    def test_exact_response_and_first_TX_guard(self):
        self.a.start_receiver();calls=[]
        def guard():
            self.assertEqual(self.lib.fixture_txcount(),0);calls.append(1)
        self.assertEqual(self.a.exchange_checked(self.request,0x7b,guard),self.reply)
        self.assertEqual(calls,[1]);self.assertEqual(self.lib.fixture_txcount(),39)
    def test_event_ACK_after_durable_effect_delay_has_no_receive_gap(self):
        self.a.start_receiver()
        self.assertEqual(self.a.exchange(self.request,0x7b),self.reply)
        self.reset(self.event,0)
        self.j.record('synthetic_saved_START_effect')
        time.sleep(0.03);self.wait_buffer(39)
        ack=frame(0x71,self.event[5:-2])
        self.assertEqual(self.a.exchange(ack,None),self.event)
        self.assertEqual(self.lib.fixture_txcount(),39)
    def test_bad_CRC_pauses_preserving_failure(self):
        self.reset(self.reply[:-1]+bytes([self.reply[-1]^1]),39);self.a.start_receiver()
        with self.assertRaises(ValueError):self.a.exchange(self.request,0x7b)
        self.assertFalse(self.a.pending_snapshot()['receiver_running'])
        self.assertTrue(self.a.fault)
    def test_clear_on_read_HW_error_is_latched_even_before_exchange(self):
        self.a.start_receiver();self.lib.fixture_error(0x20);time.sleep(0.01)
        with self.assertRaises(RuntimeError):self.a.exchange(self.request,0x7b)
        self.assertEqual(self.a.pending_snapshot()['actual_UART_error_status'],'0x24')
        self.assertEqual(self.lib.fixture_txcount(),0)
    def test_ring_overflow_is_separate_from_hardware_overrun(self):
        self.reset(self.event*3,0);self.a.start_receiver(capacity=64)
        time.sleep(0.03)
        with self.assertRaises(RuntimeError):self.a.exchange(b'',None)
        info=self.a.pending_snapshot();self.assertEqual(info['total_buffered'],64)
        self.assertEqual(info['collector_fault'],1)
        self.assertEqual(info['actual_UART_error_status'],'0x0')
    def test_parser_stall_with_complete_buffered_reply_not_wire_timeout(self):
        self.lib.fixture_parser_stall(30);self.a.gap=0.01
        self.a.start_receiver()
        self.assertEqual(self.a.exchange(self.request,0x7b),self.reply)
        self.assertEqual(self.a.last_trace['native_error'],0)
    def test_real_capture_gap_rejected_even_when_complete_reply_is_buffered(self):
        self.lib.fixture_wire_gap(1,25);self.lib.fixture_parser_stall(50)
        self.a.gap=0.01;self.a.start_receiver()
        with self.assertRaises(TimeoutError):self.a.exchange(self.request,0x7b)
        self.assertEqual(self.a.last_trace['native_error'],2)
        self.assertEqual(self.a.last_trace['rx_hex'],self.reply[:2].hex())
        self.assertEqual(self.a.pending_snapshot()['actual_UART_error_status'],'0x0')
    def test_transaction_services_finite_FIFO_with_worker_unscheduled(self):
        # 500us/byte is a deterministic host scheduling model, not board baud proof.
        self.lib.fixture_finite_fifo(500000)
        self.lib.fixture_hold_worker(1)
        watchdog=threading.Timer(1.0,lambda:self.lib.fixture_hold_worker(0))
        watchdog.start()
        self.addCleanup(watchdog.cancel)
        self.a.start_receiver()
        self.assertEqual(self.a.exchange(self.request,0x7b),self.reply)
        info=self.a.pending_snapshot()
        self.assertEqual(info['service_metrics']['exchange_RX_words'],39)
        self.assertEqual(info['service_metrics']['worker_RX_words'],0)
        self.assertEqual(info['actual_UART_error_status'],'0x0')
        self.assertEqual(self.lib.fixture_lost_words(),0)
    def test_real_finite_FIFO_loss_is_latched_and_unread_prefix_preserved(self):
        self.reset(self.event,0)
        self.lib.fixture_hold_worker(1)
        self.lib.fixture_finite_fifo(43400)
        self.a.start_receiver()
        time.sleep(0.03)
        self.lib.fixture_hold_worker(0)
        deadline=time.monotonic()+1
        while self.a.pending_snapshot()['receiver_running']:
            if time.monotonic()>deadline:self.fail('FIFO overrun not latched')
            time.sleep(0.001)
        with self.assertRaises(RuntimeError):self.a.exchange(self.request,0x7b)
        info=self.a.pending_snapshot()
        self.assertEqual(info['actual_UART_error_status'],'0x27')
        self.assertEqual(info['collector_fault'],0)
        self.assertEqual(info['total_buffered'],0)
        self.assertEqual(self.lib.fixture_hardware_words(),16)
        self.assertEqual(self.lib.fixture_lost_words(),23)
        self.assertEqual(self.lib.fixture_txcount(),0)
    def test_exchange_metrics_are_per_transaction_and_actual_register_writes(self):
        self.a.start_receiver()
        for _ in range(2):
            self.assertEqual(self.a.exchange(self.request,0x7b),self.reply)
            metrics=self.a.pending_snapshot()['exchange_metrics']
            self.assertEqual(metrics['TX_register_writes'],39)
            self.assertGreater(metrics['first_TX_write_ns'],0)
            self.assertGreaterEqual(metrics['last_TX_write_ns'],metrics['first_TX_write_ns'])
            self.assertEqual(metrics['worker_RX_words_since_exchange_start']+
                metrics['exchange_RX_words_since_exchange_start'],39)
            self.reset(self.reply,39)
    def test_model_peer_discards_gapped_request_even_after_39_TX_writes(self):
        # Simplified peer model: no physical TX FIFO timing/7010 proof claimed.
        self.lib.fixture_TX_pause(17,25,10)
        self.a.start_receiver()
        with self.assertRaises(TimeoutError):self.a.exchange(self.request,0x7b)
        info=self.a.pending_snapshot();metrics=info['exchange_metrics']
        self.assertEqual(self.lib.fixture_peer_discarded(),1)
        self.assertEqual(self.a.last_trace['native_error'],1)
        self.assertEqual(self.a.last_trace['rx_hex'],'')
        self.assertEqual(metrics['TX_register_writes'],39)
        self.assertEqual(metrics['max_gap_before_TX_word'],17)
        self.assertGreaterEqual(metrics['max_TX_write_gap_ns'],20000000)
        self.assertEqual(info['actual_UART_error_status'],'0x0')
