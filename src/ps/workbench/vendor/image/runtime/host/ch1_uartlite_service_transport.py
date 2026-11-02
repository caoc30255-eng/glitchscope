"""Explicit persistent RX service; call start_receiver after board preflight.

The worker and exchange share one locked RX service; main exchanges own TX. Native error observations
are latched, file persistence is unchanged, ring overflow is a distinct fault.
"""
import ctypes as C
from ch1_uartlite_native_transport import NativeUARTLiteControlTransport

class BackgroundUARTLiteControlTransport(NativeUARTLiteControlTransport):
    collector_name='native_C_background'
    def __init__(self,uart,journal,*,library,**kwargs):
        super().__init__(uart,journal,library=library,**kwargs)
        self.context=None
        self._start=self.lib.uartlite_service_start
        self._start.argtypes=[C.c_void_p,C.c_uint32];self._start.restype=C.c_void_p
        self._pause=self.lib.uartlite_service_pause;self._pause.argtypes=[C.c_void_p]
        self._pause.restype=None
        self._close=self.lib.uartlite_service_close;self._close.argtypes=[C.c_void_p]
        self._close.restype=None
        self._snapshot=self.lib.uartlite_service_snapshot
        self._snapshot.argtypes=[C.c_void_p,C.c_void_p,C.c_uint32,C.c_void_p]
        self._snapshot.restype=C.c_uint32
        self._metrics=getattr(self.lib,'uartlite_service_metrics',None)
        if self._metrics is not None:
            self._metrics.argtypes=[C.c_void_p,C.c_void_p];self._metrics.restype=None
        self._exchange_metrics=getattr(self.lib,'uartlite_service_exchange_metrics',None)
        if self._exchange_metrics is not None:
            self._exchange_metrics.argtypes=[C.c_void_p,C.c_void_p]
            self._exchange_metrics.restype=None
        self._collect=self.lib.uartlite_service_collect
        self._collect.argtypes=self.collect.argtypes;self._collect.restype=C.c_int
        def collect(unused_array,*args):
            if not self.context:raise RuntimeError('Background RX service not started')
            return self._collect(self.context,*args)
        self.collect=collect
    def start_receiver(self,capacity=65536):
        if self.context or self.fault:raise RuntimeError('Fresh receiver required')
        if type(capacity) is not int or not 64<=capacity<=1048576:raise ValueError('Invalid bounded RX capacity')
        self.context=self._start(self.array.ctypes.data,capacity)
        if not self.context:raise RuntimeError('Cannot start native RX worker')
    def pending_snapshot(self,limit=4096):
        if type(limit) is not int or not 0<=limit<=1048576:raise ValueError('Invalid snapshot bound')
        if not self.context:raise RuntimeError('No receiver')
        words=(C.c_uint32*limit)();info=(C.c_uint32*5)()
        n=self._snapshot(self.context,words,limit,info)
        result={'buffered_words':list(words[:n]),'total_buffered':int(info[0]),
            'actual_UART_error_status':hex(info[1]),'collector_fault':int(info[2]),
            'receiver_running':bool(info[3]),'last_actual_UART_status':hex(info[4]),
            'valid_reply':False,'snapshot_truncated':n<info[0]}
        if self._metrics is not None:
            metrics=(C.c_uint64*4)();self._metrics(self.context,metrics)
            result['service_metrics']=dict(zip(
                ('max_service_gap_ns','worker_RX_words','exchange_RX_words','service_calls'),
                map(int,metrics)))
        if self._exchange_metrics is not None:
            metrics=(C.c_uint64*8)();self._exchange_metrics(self.context,metrics)
            result['exchange_metrics']=dict(zip(
                ('TX_register_writes','first_TX_write_ns','last_TX_write_ns',
                 'max_TX_write_gap_ns','max_gap_before_TX_word',
                 'worker_RX_words_since_exchange_start','exchange_RX_words_since_exchange_start',
                 'max_service_gap_during_exchange_ns'),map(int,metrics)))
        return result
    def pause_receiver(self):
        if self.context:self._pause(self.context)
        self.fault=True
    def _exchange(self,*args,**kwargs):
        try:return super()._exchange(*args,**kwargs)
        except BaseException:
            if self.context:
                self.pause_receiver()
                diagnostic=self.pending_snapshot()
                if self.last_trace is not None:self.last_trace['background_stop']=diagnostic
                if not self.journal.fault:
                    try:self.journal.record('background_RX_stopped',**diagnostic)
                    except Exception:pass
            raise
    def close(self):
        if self.busy:raise RuntimeError('Cannot close active exchange')
        if self.context:self._close(self.context);self.context=None
        self.fault=True
    def __del__(self):
        try:self.close()
        except Exception:pass
