import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'host'))
from ch0_registration_driver_v0_2 import CH0RegistrationDriverV2
IDENT=(7<<187)|(1<<155)|(101<<123)|(3<<88)
class Bus:
 def __init__(self):self.reg={};self.writes=[];self.bound=None;self.seq=0;self.words=None;self.clock=100000000;self.tick=120;self.flags=0x19;self.live=3;self.stale=False;self.wrong_record=False;self.old=False
 def write(self,a,v):
  self.writes.append((a,v));self.reg[a]=v
  if a==0x70:self.bound=[self.reg[0x30],self.reg[0x34],self.reg[0x38],self.reg[0x3c],*[self.reg[0x50+4*i] for i in range(8)],0,100,0,4100]
  if a==0x7c:
   self.seq+=not self.stale;self.words=[0,self.tick,self.reg[0x30],self.reg[0x48],self.reg[0x34]+int(self.wrong_record),self.seq,self.flags,self.clock]
 def read(self,a):
  if a==0:return 0x48305231 if self.old else 0x48305232
  if a==4:return 0x11 if self.bound else 8
  if a==0x18:return 0x1ffff
  if a==0x170:return self.reg[0x48]
  if 0x100<=a<0x140:return self.bound[(a-0x100)//4]
  if a==0x1a0:return self.live if self.words else 0
  if a==0x1a4:return 255
  if 0x180<=a<0x1a0:return self.words[(a-0x180)//4]
  raise AssertionError(a)
class Tests(unittest.TestCase):
 def prepare(self):
  b=Bus();d=CH0RegistrationDriverV2(b,expected_clock_hz=100000000)
  r=d.register(epoch=9,peer_epoch=101,record_id=2,kind=1,identity=IDENT,request_length=278,delay_ticks=4,duration_ticks=4000)
  return b,d,r
 def test_distinct_epochs_and_actual_clock(self):
  b,d,r=self.prepare();self.assertEqual((r['epoch'],r['peer_epoch']),(9,101));s=d.snapshot_window(r,minimum_remaining_ticks=100);self.assertTrue(s['window_open']);self.assertFalse(s['complete_START_admission'])
 def test_peer_identity_mismatch_no_writes(self):
  b=Bus();d=CH0RegistrationDriverV2(b,expected_clock_hz=100000000)
  with self.assertRaises(ValueError):d.register(epoch=9,peer_epoch=102,record_id=2,kind=1,identity=IDENT,request_length=278,delay_ticks=4,duration_ticks=4000)
  self.assertEqual(b.writes,[])
 def test_before_start(self):
  b,d,r=self.prepare();b.tick=99
  with self.assertRaises(RuntimeError):d.snapshot_window(r,minimum_remaining_ticks=1)
 def test_deadline_inclusive_rejected(self):
  b,d,r=self.prepare();b.tick=4000
  with self.assertRaises(RuntimeError):d.snapshot_window(r,minimum_remaining_ticks=100)
 def test_clock_rate_mismatch(self):
  b,d,r=self.prepare();b.clock=150000000
  with self.assertRaises(RuntimeError):d.snapshot_window(r,minimum_remaining_ticks=1)
 def test_received_or_faulted_snapshot(self):
  b,d,r=self.prepare();b.flags=5
  with self.assertRaises(RuntimeError):d.snapshot_window(r,minimum_remaining_ticks=1)
 def test_live_invalidated(self):
  b,d,r=self.prepare();b.live=1
  with self.assertRaises(RuntimeError):d.snapshot_window(r,minimum_remaining_ticks=1)
 def test_no_new_capture_sequence(self):
  b,d,r=self.prepare();d.snapshot_window(r,minimum_remaining_ticks=1);b.stale=True
  with self.assertRaises(RuntimeError):d.snapshot_window(r,minimum_remaining_ticks=1)
 def test_wrong_record(self):
  b,d,r=self.prepare();b.wrong_record=True
  with self.assertRaises(RuntimeError):d.snapshot_window(r,minimum_remaining_ticks=1)
 def test_old_ip_stop_no_writes(self):
  b=Bus();b.old=True
  with self.assertRaises(RuntimeError):CH0RegistrationDriverV2(b,expected_clock_hz=100000000)
  self.assertEqual(b.writes,[])
if __name__=='__main__':unittest.main(verbosity=2)
