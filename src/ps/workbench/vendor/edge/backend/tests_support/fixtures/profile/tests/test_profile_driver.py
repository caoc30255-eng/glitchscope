import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'host'))
from ch0_rx_profile_driver import CH0RXProfileDriver
class Bus:
 def __init__(self):self.writes=[];self.seq=0;self.applied=False;self.d=0;self.s=0;self.stale=False;self.bad=False;self.busy=False;self.mask=0
 def read(self,a):
  if a==0:return 0x48525031
  if a==4:return 0x14 if self.busy else 7 if self.applied else 4
  if a==8:return self.seq
  if a==0x10:self.mask|=1;return self.d
  if a==0x14:self.mask|=2;return self.s
  if a==0x4c:return self.mask|4
  raise AssertionError(a)
 def write(self,a,v):
  self.writes.append((a,v))
  if a==0x30:self.d=v
  elif a==0x34:self.s=v
  elif a==0x38:
   self.applied=True;self.seq+=not self.stale;self.mask=0
   if self.bad:self.s=9
class Tests(unittest.TestCase):
 def test_signed_profile(self):
  b=Bus();r=CH0RXProfileDriver(b).apply(d=4,s=-1);self.assertEqual(r['s'],-1);self.assertFalse(r['complete_START_admission']);self.assertEqual(b.s,0xffffffff)
 def test_next_apply(self):
  b=Bus();d=CH0RXProfileDriver(b);d.apply(d=2,s=0);r=d.apply(d=1,s=2);self.assertEqual(r['profile_seq'],2)
 def test_illegal_no_writes(self):
  b=Bus();d=CH0RXProfileDriver(b)
  with self.assertRaises(ValueError):d.apply(d=4,s=0)
  self.assertEqual(b.writes,[])
 def test_held_no_writes(self):
  b=Bus();d=CH0RXProfileDriver(b);b.busy=True
  with self.assertRaises(RuntimeError):d.apply(d=1,s=0)
  self.assertEqual(b.writes,[])
 def test_rejected_same_profile_old_sequence(self):
  b=Bus();d=CH0RXProfileDriver(b);d.apply(d=1,s=0);fresh=CH0RXProfileDriver(b);b.stale=True
  with self.assertRaises(RuntimeError):fresh.apply(d=1,s=0)
 def test_readback_mismatch(self):
  b=Bus();b.bad=True
  with self.assertRaises(RuntimeError):CH0RXProfileDriver(b).apply(d=1,s=0)
if __name__=='__main__':unittest.main(verbosity=2)
