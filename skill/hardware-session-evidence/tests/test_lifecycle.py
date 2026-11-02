import struct,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from peer_read_adapter import frame
from verify_lifecycle import verify_frames,NAMES,FORMAT
class LifecycleTests(unittest.TestCase):
 def fixture(self,mark=False):
  identity=dict(zip(NAMES,[1,2,3,0,4,5,1,9,8,0,0]));frames=[frame(0x80,b'\x11\x09\x00\x01')]
  for kind in [0x31]+([0x33] if mark else [])+[0x32,0x38]:frames.append(frame(kind,struct.pack(FORMAT,*[identity[k] for k in NAMES],7 if kind==0x38 else 0)))
  return identity,frames
 def test_complete_peer_sequence(self):
  i,f=self.fixture();r=verify_frames(f,i,7);self.assertEqual(r['status'],'PEER_LIFECYCLE_SEQUENCE_PASS');self.assertFalse(r['strict_local_retirement_verified'])
 def test_start_ack_is_not_done(self):
  i,f=self.fixture();r=verify_frames(f[:1],i,7);self.assertEqual(r['status'],'INCOMPLETE_UNKNOWN');self.assertFalse(r['physical_done_notification'])
 def test_missing_retired_is_unknown(self):
  i,f=self.fixture();self.assertEqual(verify_frames(f[:-1],i,7)['status'],'INCOMPLETE_UNKNOWN')
 def test_wrong_identity_rejected(self):
  i,f=self.fixture();i['seq']=99
  with self.assertRaises(ValueError):verify_frames(f,i,7)
 def test_done_before_start_rejected(self):
  i,f=self.fixture();f[1],f[2]=f[2],f[1]
  with self.assertRaises(ValueError):verify_frames(f,i,7)
 def test_required_mark_and_disabled_mark(self):
  i,f=self.fixture(True);self.assertEqual(verify_frames(f,i,7,True)['status'],'PEER_LIFECYCLE_SEQUENCE_PASS')
  with self.assertRaises(ValueError):verify_frames(f,i,7,False)
 def test_wrong_retirement_record_rejected(self):
  i,f=self.fixture()
  with self.assertRaises(ValueError):verify_frames(f,i,8)
if __name__=='__main__':unittest.main()
