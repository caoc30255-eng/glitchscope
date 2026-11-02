"""Mocked RT start policy; no real OS scheduling or FPGA accesses."""
from pathlib import Path
import sys,ctypes as C,unittest
from unittest.mock import Mock,patch
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'host'))
from ch1_uartlite_realtime_transport import RealtimeUARTLiteControlTransport as T
class RealtimeTests(unittest.TestCase):
 def make(self,values=None,error=0):
  a=T.__new__(T);a.context=None;a.fault=False;a.receiver_settings=(1,10,50000)
  a.array=np.zeros(4,dtype=np.uint32);a.journal=Mock()
  a.close=Mock(side_effect=lambda:setattr(a,'fault',True))
  def start(*args):
   C.cast(args[-1],C.POINTER(C.c_int))[0]=error
   return 0 if error else 123
  a._start_rt=Mock(side_effect=start)
  def readback(ptr,out):
   for i,v in enumerate(values or [5,1,2,10,1,1,50000,321]):out[i]=v
  a._scheduling=readback;return a
 def start(self,a):
  with patch('os.sched_getaffinity',return_value={0,1},create=True),patch('os.SCHED_RR',2,create=True):a.start_receiver()
 def test_success_saved(self):
  a=self.make();self.start(a);self.assertEqual(a.context,123)
  a.journal.record.assert_called_once();self.assertEqual(a.journal.record.call_args.args[0],'RX_worker_scheduling_verified')
 def test_permission_no_fallback(self):
  a=self.make(error=1)
  with self.assertRaisesRegex(RuntimeError,'no fallback'):self.start(a)
  self.assertTrue(a.fault);self.assertFalse(a.context);a.journal.record.assert_not_called()
 def test_affinity_rejects_before_native(self):
  a=self.make()
  with patch('os.sched_getaffinity',return_value={0},create=True):
   with self.assertRaises(RuntimeError):a.start_receiver()
  a._start_rt.assert_not_called()
 def test_wrong_policy_stops(self):
  a=self.make(values=[5,1,0,10,1,1,50000,321])
  with self.assertRaises(RuntimeError):self.start(a)
  a.close.assert_called_once();a.journal.record.assert_not_called()
 def test_missing_PI_stops(self):
  a=self.make(values=[5,1,2,10,1,0,50000,321])
  with self.assertRaises(RuntimeError):self.start(a)
  a.close.assert_called_once()
 def test_persistence_failure_stops(self):
  a=self.make();a.journal.record.side_effect=OSError('disk full')
  with self.assertRaises(OSError):self.start(a)
  a.close.assert_called_once()
 def test_capacity_before_start(self):
  a=self.make()
  with self.assertRaises(ValueError):a.start_receiver(capacity=1)
  a._start_rt.assert_not_called()
 def test_repeat_denied(self):
  a=self.make();self.start(a)
  with self.assertRaises(RuntimeError):self.start(a)
  self.assertEqual(a._start_rt.call_count,1)
 def test_bounds_before_library(self):
  for kw in ({'receiver_priority':99},{'receiver_idle_ns':0},{'receiver_cpu':-1}):
   with self.assertRaises(ValueError):T(None,None,library='unused',**kw)
