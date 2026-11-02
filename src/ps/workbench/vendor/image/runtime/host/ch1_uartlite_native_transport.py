"""Native bounded byte collector; Python preserves exact bytes before use.

No import/constructor hardware access, no reset/IRQ/clock changes or retries.
Linux scheduling can still cause overrun: errors always stop the session.
"""
import ctypes as C
from pathlib import Path
from ch1_uartlite_transport import UARTLiteControlTransport, NOTIFICATIONS
from ch1_control_session import decode_frame

_GUARD = C.CFUNCTYPE(C.c_int)
_ERRORS = {1:'deadline',2:'partial frame interbyte deadline',3:'UART hardware error',
    4:'RX DWORD padding',5:'frame prefix/version/length',6:'frame CRC',
    7:'unexpected reply',8:'duplicate reply',9:'reply before complete TX',
    10:'operation/status budget',11:'raw capture bound',12:'first-TX guard',
    13:'stale reply before TX',14:'frame count bound',15:'invalid arguments/status'}

class NativeUARTLiteControlTransport(UARTLiteControlTransport):
    def __init__(self, uart, journal, *, library, **kwargs):
        super().__init__(uart,journal,**kwargs)
        if self.array is None or not hasattr(self.array,'ctypes'):
            raise ValueError('Native transport requires the live PYNQ uint32 MMIO array')
        self.lib=C.CDLL(str(Path(library).resolve()))
        self.collect=self.lib.uartlite_collect
        self.collect.argtypes=[C.c_void_p,C.c_void_p,C.c_uint32,C.c_int,_GUARD,
            C.c_void_p,C.c_uint32,C.c_void_p,C.c_uint32,C.c_void_p,
            C.c_uint64,C.c_uint64,C.c_uint64,C.c_uint32,C.c_uint32]
        self.collect.restype=C.c_int
        self._saved_capture=None

    def capture_is_durable(self,request,raw,journal):
        if journal is not self.journal:return False
        journal.verify()
        return self._saved_capture==(bytes(request),bytes(raw),journal.index,journal.digest)

    def _exchange(self,request,expected_type,*,before_first_tx=None):
        if self.fault or self.busy:raise RuntimeError('Native UART stopped/concurrent exchange; no further IO')
        request=bytes(request)
        if request:decode_frame(request)
        elif expected_type is not None:raise ValueError('Receive-only poll cannot expect command reply')
        if expected_type is not None and (type(expected_type) is not int or not 0<=expected_type<=255):
            raise ValueError('Invalid expected type')
        self.busy=True
        self.last_trace=None
        self._saved_capture=None
        collector=getattr(self,'collector_name','native_C')
        cap=39*(self.frame_limit+1)
        rawbuf=(C.c_uint8*cap)();tx=(C.c_uint8*max(1,len(request)))()
        if request:C.memmove(tx,request,len(request))
        statuses=(C.c_uint32*4096)();out=(C.c_uint32*12)();guard_error=[]
        def guard():
            try:
                if before_first_tx is not None:before_first_tx()
                return 0
            except BaseException as exc:
                guard_error.append(exc);return 1
        callback=_GUARD(guard)
        try:
            self.journal.verify()
            if not self.journal.matches_intent(request):
                self.journal.record('uart_byte_exchange_intent',request_hex=request.hex(),
                    expected_type=expected_type,collector=collector)
            rc=self.collect(self.array.ctypes.data,tx,len(request),
                -1 if expected_type is None else expected_type,callback,
                rawbuf,cap,statuses,4096,out,int(self.timeout*1e9),
                int(self.quiet*1e9),int(self.gap*1e9),self.poll_limit,self.frame_limit)
            raw=bytes(rawbuf[:out[0]])
            trace={'request_hex':request.hex(),'rx_hex':raw.hex(),
                'tx_bytes_confirmed':int(out[1]),'tx_write_attempts':int(out[2]),
                'status_transitions':list(statuses[:out[3]]),'pending_hex':raw[out[5]:].hex(),
                'frames':int(out[6]),'polls':int(out[4]),'bad_rx_word':int(out[7]) if rc==4 else None,
                'native_error':rc,'last_status':hex(out[9]),'collector':collector,
                'request_effect_uncertain':bool(out[2]),'guard_calls':int(out[11])}
            self.last_trace=trace
            if rc:
                if guard_error:raise guard_error[0]
                message='Native UART '+_ERRORS.get(rc,'unknown error')+'; retain evidence, no retry'
                if rc in (1,2,10):raise TimeoutError(message)
                if rc in (4,5,6):raise ValueError(message)
                raise RuntimeError(message)
            # Independent Python decode too; return original bytes only after fsync.
            pos=0;reply_count=0
            while pos<len(raw):
                size=raw[pos+4]+7;packet=raw[pos:pos+size]
                kind,_=decode_frame(packet)
                if kind not in NOTIFICATIONS and kind!=expected_type:
                    raise ValueError('Native collector returned unexpected frame')
                if expected_type is not None and kind==expected_type:reply_count+=1
                pos+=size
            if pos!=len(raw) or (expected_type is not None and reply_count!=1):
                raise ValueError('Native collector returned incomplete/duplicate reply')
            self.journal.record('uart_byte_exchange_saved',**trace)
            self._saved_capture=(request,raw,self.journal.index,self.journal.digest)
            return raw
        except BaseException as exc:
            self.fault=True
            if self.last_trace is None:
                self.last_trace={'request_hex':request.hex(),'rx_hex':'','collector':collector,
                    'tx_bytes_confirmed':0,'tx_write_attempts':0,'request_effect_uncertain':False}
            self.last_trace['reason']=str(exc)
            if not self.journal.fault:
                try:self.journal.record('uart_byte_exchange_stopped',**self.last_trace)
                except Exception:pass
            raise
        finally:self.busy=False
