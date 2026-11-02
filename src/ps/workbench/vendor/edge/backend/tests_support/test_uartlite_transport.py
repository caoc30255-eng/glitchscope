"""Scheduled UARTLite register model + actual journal; no physical UART."""
from pathlib import Path
from collections import deque
from types import SimpleNamespace
from unittest.mock import patch
import sys,unittest,uuid
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'host'),str(ROOT/'tests')]
from ch1_uartlite_transport import UARTLiteControlTransport
from ch1_control_session import ApplicationJournal,PeerControlSession,frame,decode_frame,event_payload
from test_evidence_store import fixture
import ch1_evidence_store as store

class Clock:
    def __init__(self):self.t=0
    def __call__(self):self.t+=0.00001;return self.t

class UARTModel:
    def __init__(self,clock,response):
        self.clock=clock;self.response=response;self.rx=deque();self.schedule=[]
        self.tx=bytearray();self.requests=[];self.writes=[];self.reads=[]
        self.errors=0;self.full_until=0;self.stuck_full=False;self.respond=True
        self.split_interval=0.00004;self.lost_write=False;self.bad_word=False
    def queue(self,data,*,delay=0,spacing=0.00004):
        for i,b in enumerate(data):self.schedule.append((self.clock.t+delay+i*spacing,b))
        self.schedule.sort(key=lambda item:item[0])
    def read(self,a):
        self.reads.append(a)
        while self.schedule and self.schedule[0][0]<=self.clock.t:
            byte=self.schedule.pop(0)[1]
            if len(self.rx)>=16:self.errors|=0x20
            else:self.rx.append(byte)
        if a==8:
            full=self.stuck_full or self.clock.t<self.full_until
            return (1 if self.rx else 0)|(2 if len(self.rx)==16 else 0)|(8 if full else 4)|self.errors
        if a==0:
            value=self.rx.popleft();return value|(0x100 if self.bad_word else 0)
        raise AssertionError('Adapter touched non-status/RX register')
    def write(self,a,v):
        assert a==4 and 0<=v<=255
        self.writes.append((a,v));self.tx.append(v)
        if self.lost_write:self.lost_write=False;raise OSError('Executed TX write lost reply')
        if len(self.tx)>=5 and len(self.tx)==self.tx[4]+7:
            packet=bytes(self.tx);decode_frame(packet);self.requests.append(packet);self.tx.clear()
            if self.respond:self.queue(self.response(packet),delay=0.00005,spacing=self.split_interval)

class UARTTests(unittest.TestCase):
    def setUp(self):
        self.root=ROOT/'evidence/offline_uartlite_tests'/('test_'+uuid.uuid4().hex)
        self.journal=ApplicationJournal(self.root,0x74000001);self.addCleanup(self.journal.close)
        self.clock=Clock();self.identity=store.descriptor_decode(fixture()[0])['identity']
        self.request=frame(0x11,b'\x03\0');self.reply=frame(0x80,b'\x11\x03\0\x01')
        self.uart=UARTModel(self.clock,lambda request:self.reply)
        self.adapter=UARTLiteControlTransport(self.uart,self.journal,exclusive_owner=True,
            timeout=0.1,quiet_time=0.0003,interbyte_timeout=0.003,poll_limit=20000,clock=self.clock)
    def test_checked_guard_once_after_adapter_intent_before_first_fifo_write(self):
        calls=[]
        def guard():
            self.assertFalse(self.uart.writes)
            self.assertIn('uart_byte_exchange_intent',self.journal.path.read_text())
            calls.append(True)
        self.assertEqual(self.adapter.exchange_checked(self.request,0x80,guard),self.reply)
        self.assertEqual(calls,[True])
    def test_checked_guard_failure_no_fifo_write_or_uncertain_execution(self):
        def guard():raise RuntimeError('actual local window expired')
        with self.assertRaises(RuntimeError):self.adapter.exchange_checked(self.request,0x80,guard)
        self.assertFalse(self.uart.writes)
        self.assertFalse(self.adapter.last_trace['request_effect_uncertain'])
    def test_adapter_intent_fsync_expiry_seen_by_first_tx_guard(self):
        expired=[False];original=self.journal.record
        def delayed(event,**fields):
            result=original(event,**fields)
            if event=='uart_byte_exchange_intent':expired[0]=True
            return result
        def guard():
            if expired[0]:raise RuntimeError('window expired during adapter intent')
        with patch.object(self.journal,'record',side_effect=delayed):
            with self.assertRaises(RuntimeError):self.adapter.exchange_checked(self.request,0x80,guard)
        self.assertFalse(self.uart.writes)
    def test_constructor_and_import_perform_no_io(self):
        self.assertFalse(self.uart.reads or self.uart.writes)

    def enable_direct_mapping(self):
        read, write = self.uart.read, self.uart.write
        class Mapping:
            ndim=1;size=4;dtype=SimpleNamespace(kind='u',itemsize=4)
            def __getitem__(self,index):
                assert index in (0,2)
                return read(index*4)
            def __setitem__(self,index,value):
                assert index==1
                write(index*4,value)
        self.uart.array=Mapping()
        self.uart.read=lambda _: self.fail('Slow MMIO.read used in fast path')
        self.uart.write=lambda *_: self.fail('Slow MMIO.write used in fast path')
        self.adapter=UARTLiteControlTransport(self.uart,self.journal,exclusive_owner=True,
            timeout=0.1,quiet_time=0.0003,interbyte_timeout=0.003,clock=self.clock)

    def test_live_DWORD_mapping_exact_reply_without_slow_access(self):
        self.enable_direct_mapping()
        self.assertFalse(self.uart.reads or self.uart.writes)
        self.assertEqual(self.adapter.exchange(self.request,0x80),self.reply)
        self.assertTrue(self.adapter.last_trace['direct_mmio'])
        self.assertEqual(self.adapter.last_trace['receive_mode'],'fifo_first')

    def test_live_mapping_overrun_stops_without_fifo_pop_or_reset(self):
        self.enable_direct_mapping();self.uart.errors=0x20
        with self.assertRaises(RuntimeError):self.adapter.exchange(self.request,0x80)
        self.assertEqual(self.uart.reads,[8]);self.assertFalse(self.uart.writes)

    def test_live_mapping_rejects_invalid_RX_DWORD(self):
        self.enable_direct_mapping();self.uart.bad_word=True
        with self.assertRaises(ValueError):self.adapter.exchange(self.request,0x80)
        self.assertEqual(self.adapter.last_trace['rx_hex'],'')

    def test_live_mapping_lost_TX_write_preserves_uncertain_effect(self):
        self.enable_direct_mapping();self.uart.lost_write=True
        with self.assertRaises(OSError):self.adapter.exchange(self.request,0x80)
        self.assertEqual(self.adapter.last_trace['tx_write_attempts'],1)
        self.assertEqual(self.adapter.last_trace['tx_bytes_confirmed'],0)

    def test_full_FIFO_drain_precedes_received_frame_parsing(self):
        event=frame(0x31,event_payload(self.identity,0))
        self.uart.queue(event[:16],spacing=0)
        self.uart.queue(event[16:],delay=0.0001,spacing=0.00004)
        original=decode_frame
        def checked(packet):
            if packet==event:
                self.assertFalse(self.uart.rx)
            return original(packet)
        with patch('ch1_uartlite_transport.decode_frame',side_effect=checked):
            self.assertEqual(self.adapter.exchange(self.request,0x80),event+self.reply)

    def test_invalid_direct_mapping_denied_without_IO(self):
        self.uart.array=SimpleNamespace(ndim=1,size=4,
            dtype=SimpleNamespace(kind='u',itemsize=8))
        with self.assertRaises(ValueError):
            UARTLiteControlTransport(self.uart,self.journal,exclusive_owner=True)
        self.assertFalse(self.uart.reads or self.uart.writes)
    def test_exclusive_owner_required_before_io(self):
        with self.assertRaises(ValueError):UARTLiteControlTransport(self.uart,self.journal)
        self.assertFalse(self.uart.reads or self.uart.writes)
    def test_split_reply_exact_bytes_and_tx_fifo_only(self):
        self.uart.split_interval=0.00008
        self.assertEqual(self.adapter.exchange(self.request,0x80),self.reply)
        self.assertEqual(bytes(v for a,v in self.uart.writes),self.request)
        self.assertTrue(all(a==4 for a,v in self.uart.writes))
        self.assertIn(self.reply.hex(),self.journal.path.read_text())
    def test_mixed_notification_before_and_after_expected_reply(self):
        event=frame(0x31,event_payload(self.identity,0));done=frame(0x32,event_payload(self.identity,0))
        self.uart.response=lambda request:event+self.reply+done
        self.uart.split_interval=0.00004
        out=self.adapter.exchange(self.request,0x80)
        self.assertEqual(out,event+self.reply+done)
    def test_preexisting_notification_preserved_and_returned(self):
        event=frame(0x31,event_payload(self.identity,0));self.uart.queue(event)
        self.assertEqual(self.adapter.exchange(self.request,0x80),event+self.reply)
    def test_stale_reply_blocks_new_tx(self):
        self.uart.queue(self.reply)
        with self.assertRaises(RuntimeError):self.adapter.exchange(self.request,0x80)
        self.assertFalse(self.uart.writes);self.assertEqual(self.adapter.last_trace['rx_hex'],self.reply.hex())
    def test_tx_backpressure_drains_pending_notifications(self):
        event=frame(0x31,event_payload(self.identity,0));self.uart.queue(event,spacing=0.00002)
        self.uart.full_until=0.002
        out=self.adapter.exchange(self.request,0x80)
        self.assertEqual(out,event+self.reply)
    def test_uart_error_retains_state_and_never_clears_fifo(self):
        self.uart.errors=0x20
        with self.assertRaises(RuntimeError):self.adapter.exchange(self.request,0x80)
        self.assertFalse(self.uart.writes);self.assertIn(0x24,self.adapter.last_trace['status_transitions'])
    def test_timeout_uncertain_execution_never_retransmits(self):
        self.uart.respond=False
        with self.assertRaises(TimeoutError):self.adapter.exchange(self.request,0x80)
        count=len(self.uart.writes)
        self.assertTrue(self.adapter.last_trace['request_effect_uncertain'])
        with self.assertRaises(RuntimeError):self.adapter.exchange(self.request,0x80)
        self.assertEqual(len(self.uart.writes),count)
    def test_partial_frame_stops_and_retains_all_received_prefix(self):
        self.uart.response=lambda request:self.reply[:-2]
        with self.assertRaises(TimeoutError):self.adapter.exchange(self.request,0x80)
        self.assertEqual(self.adapter.last_trace['pending_hex'],self.reply[:-2].hex())
    def test_bad_crc_stops_without_resynchronizing(self):
        self.uart.response=lambda request:self.reply[:-1]+bytes((self.reply[-1]^1,))
        with self.assertRaises(ValueError):self.adapter.exchange(self.request,0x80)
        self.assertTrue(self.adapter.fault)
    def test_duplicate_reply_denied(self):
        self.uart.response=lambda request:self.reply+self.reply
        with self.assertRaises(RuntimeError):self.adapter.exchange(self.request,0x80)
    def test_rx_upper_bits_do_not_invent_byte(self):
        self.uart.bad_word=True
        with self.assertRaises(ValueError):self.adapter.exchange(self.request,0x80)
        self.assertEqual(self.adapter.last_trace['rx_hex'],'')
    def test_lost_tx_write_stops_with_uncertain_prefix(self):
        self.uart.lost_write=True
        with self.assertRaises(OSError):self.adapter.exchange(self.request,0x80)
        self.assertEqual(self.adapter.last_trace['tx_write_attempts'],1)
        self.assertEqual(self.adapter.last_trace['tx_bytes_confirmed'],0)
    def test_disk_failure_before_tx_sends_nothing(self):
        with patch.object(self.journal,'record',side_effect=OSError('disk failed')):
            with self.assertRaises(OSError):self.adapter.exchange(self.request,0x80)
        self.assertFalse(self.uart.writes)
    def test_receive_only_poll_and_ack_without_command_reply(self):
        event=frame(0x32,event_payload(self.identity,0));self.uart.queue(event,delay=0.0001)
        self.assertEqual(self.adapter.exchange(b'',None),event)
        self.assertFalse(self.uart.writes)
        self.uart.response=lambda request:b''
        self.assertEqual(self.adapter.exchange(frame(0x72,event[5:-2]),None),b'')
    def test_control_session_mmio_and_delayed_notification_integration(self):
        def response(request):
            kind,p=decode_frame(request)
            if kind==0x3b:return frame(0x7b,p[:12]+bytes((0,0,1,0))+bytes.fromhex('48354531')+bytes(12))
            return b''
        self.uart.response=response;self.uart.split_interval=0.00005
        peer=PeerControlSession(self.adapter,self.journal,0x74000001)
        self.assertEqual(peer.read(0),0x48354531)
        event=frame(0x32,event_payload(self.identity,0));self.uart.queue(event,delay=0.0001)
        self.assertEqual(peer.poll_notifications(),1)
        self.assertEqual(peer.events[0]['identity'],self.identity)

    def test_early_reply_during_tx_stops_remaining_packet(self):
        original=self.uart.write
        def write(a,v):
            original(a,v)
            if len(self.uart.writes)==1:self.uart.queue(self.reply,spacing=0)
        self.uart.write=write
        with self.assertRaises(RuntimeError):self.adapter.exchange(self.request,0x80)
        self.assertLess(len(self.uart.writes),len(self.request))
    def test_finite_rx_fifo_overrun_does_not_clear_original_bytes(self):
        self.uart.queue(bytes((0xa5,))*17,spacing=0)
        with self.assertRaises(RuntimeError):self.adapter.exchange(self.request,0x80)
        self.assertEqual(len(self.uart.rx),16);self.assertFalse(self.uart.writes)
    def test_complete_rx_fsync_failure_returns_no_frames(self):
        original=self.journal.record
        def record(event,**fields):
            if event=='uart_byte_exchange_saved':raise OSError('RX commit failed')
            return original(event,**fields)
        with patch.object(self.journal,'record',side_effect=record):
            with self.assertRaises(OSError):self.adapter.exchange(self.request,0x80)
        self.assertTrue(self.adapter.fault);self.assertEqual(self.adapter.last_trace['rx_hex'],self.reply.hex())

if __name__=='__main__':unittest.main(verbosity=2)
