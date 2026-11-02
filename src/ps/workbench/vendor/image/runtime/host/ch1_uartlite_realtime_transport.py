"""Opt-in Linux worker scheduling; no silent ordinary-scheduler fallback.
No hardware resets, baud changes, retries, or evidence-format changes.
"""
import ctypes as C
import os
from ch1_uartlite_service_transport import BackgroundUARTLiteControlTransport

class RealtimeUARTLiteControlTransport(BackgroundUARTLiteControlTransport):
    def __init__(self, *args, receiver_cpu=1, receiver_priority=10,
                 receiver_idle_ns=50000, **kwargs):
        if type(receiver_cpu) is not int or not 0<=receiver_cpu<1024:
            raise ValueError('Invalid receiver CPU')
        if type(receiver_priority) is not int or not 1<=receiver_priority<=20:
            raise ValueError('Receiver priority must be 1..20')
        if type(receiver_idle_ns) is not int or not 20000<=receiver_idle_ns<=100000:
            raise ValueError('Receiver rest must be 20000..100000ns')
        super().__init__(*args, **kwargs)
        self.receiver_settings=(receiver_cpu,receiver_priority,receiver_idle_ns)
        self._start_rt=self.lib.uartlite_service_start_rt
        self._start_rt.argtypes=[C.c_void_p,C.c_uint32,C.c_int,C.c_int,C.c_uint32,C.POINTER(C.c_int)]
        self._start_rt.restype=C.c_void_p
        self._scheduling=self.lib.uartlite_service_scheduling
        self._scheduling.argtypes=[C.c_void_p,C.c_void_p];self._scheduling.restype=None

    def start_receiver(self, capacity=65536):
        if self.context or self.fault:raise RuntimeError('Fresh receiver required')
        if type(capacity) is not int or not 64<=capacity<=1048576:
            raise ValueError('Invalid bounded RX capacity')
        cpu,priority,idle_ns=self.receiver_settings
        if cpu not in os.sched_getaffinity(0):
            self.fault=True
            raise RuntimeError('Requested CPU outside caller affinity; no receiver started')
        error=C.c_int()
        self.context=self._start_rt(self.array.ctypes.data,capacity,cpu,priority,idle_ns,C.byref(error))
        if not self.context:
            self.fault=True
            raise RuntimeError('RT receiver setup failed errno=%d (%s); no fallback' %
                               (error.value,os.strerror(error.value)))
        scheduling=self.scheduling_snapshot()
        if (scheduling['version']!=5 or scheduling['cpu']!=cpu or
                scheduling['policy']!=os.SCHED_RR or scheduling['priority']!=priority or
                scheduling['affinity_verified']!=1 or scheduling['priority_inheritance']!=1 or
                scheduling['idle_ns']!=idle_ns or not scheduling['thread_id']):
            self.close()
            raise RuntimeError('RT receiver readback mismatch; stopped')
        try:self.journal.record('RX_worker_scheduling_verified',**scheduling)
        except BaseException:
            self.close()
            raise

    def scheduling_snapshot(self):
        if not self.context:raise RuntimeError('No receiver')
        values=(C.c_uint32*8)();self._scheduling(self.context,values)
        return dict(zip(('version','cpu','policy','priority','affinity_verified',
                         'priority_inheritance','idle_ns','thread_id'),map(int,values)))

    def pending_snapshot(self, limit=4096):
        result=super().pending_snapshot(limit=limit)
        result['receiver_scheduling']=self.scheduling_snapshot()
        return result
