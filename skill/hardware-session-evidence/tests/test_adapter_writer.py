import hashlib,json,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
import session_ledger as ledger
from device_lease import DeviceLease
from peer_read_adapter import read_request,frame,decode,verify,run_readonly
class AdapterTests(unittest.TestCase):
 def reply(self,request,value=7):
  _,p=decode(request);return frame(0x7b,p[:12]+bytes([0,0,1,0])+value.to_bytes(4,'big')+bytes(12))
 def test_actual_wire_contract(self):
  request=read_request(0x10000001,1,0x24);self.assertEqual(len(request),39);self.assertEqual(verify(request,self.reply(request)),7)
 def test_wrong_transaction_or_parameter_rejected(self):
  request=read_request(1,1,0)
  for other in [read_request(2,1,0),read_request(1,2,0),read_request(1,1,4)]:
   with self.assertRaises(ValueError):verify(request,self.reply(other))
 def test_crc_bad_or_partial_rejected(self):
  request=read_request(1,1,0);raw=self.reply(request)
  for bad in [raw[:-1],raw[:-1]+bytes([raw[-1]^1])]:
   with self.assertRaises(ValueError):verify(request,bad)
 def test_write_request_not_accepted(self):
  request=read_request(1,1,0);_,p=decode(request);p=p[:8]+bytes([1])+p[9:]
  with self.assertRaises(ValueError):verify(frame(0x3b,p),self.reply(request))
 def test_unknown_consumes_attempt_and_preserves_bytes(self):
  outer=self
  class T:
   calls=0
   def exchange(self,r,k):self.calls+=1;return outer.reply(r,value=99)
   def close(self):return True
  with tempfile.TemporaryDirectory() as t:
   tr=T();p=Path(t);r=run_readonly(tr,p/'s',p/'device.lock',1,1,[dict(address=0,expected=7,access='RO',read_effect='none')]*2,True)
   self.assertEqual(tr.calls,1);self.assertEqual(r['unknown_or_unresolved'],1);self.assertEqual(r['cancelled_unstarted'],1);self.assertTrue((p/'s/raw/read_0_rx.bin').is_file())
 def test_unknown_raw_capture_is_hash_bound(self):
  outer=self
  class T:
   def exchange(self,r,k):return outer.reply(r,value=99)
   def close(self):return True
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);run_readonly(T(),p/'s',p/'device.lock',1,1,[dict(address=0,expected=7,access='RO',read_effect='none')],True)
   (p/'s/raw/read_0_rx.bin').write_bytes(b'changed')
   with self.assertRaises(ValueError):ledger.audit(p/'s')
 def test_unconfirmed_close_quarantines_device(self):
  class T:
   def exchange(self,r,k):return b'bad'
   def close(self):return False
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);r=run_readonly(T(),p/'s',p/'device.lock',1,1,[dict(address=0,expected=7,access='RO',read_effect='none')]*2,True)
   self.assertTrue(r['device_quarantined']);self.assertEqual(r['reserved_unstarted'],1)
   with self.assertRaisesRegex(RuntimeError,'QUARANTINED'):
    with DeviceLease(p/'device.lock'):pass
 def test_cross_process_lease_and_persistent_inode(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'device.lock'
   code="import sys;sys.path.insert(0,"+repr(str(ROOT/'scripts'))+");from device_lease import DeviceLease\ntry:\n with DeviceLease(sys.argv[1]):pass\nexcept RuntimeError:sys.exit(2)\n"
   with DeviceLease(p):r=subprocess.run([sys.executable,'-B','-c',code,str(p)],capture_output=True);self.assertEqual(r.returncode,2,r.stderr)
   self.assertTrue(p.exists());r=subprocess.run([sys.executable,'-B','-c',code,str(p)],capture_output=True);self.assertEqual(r.returncode,0,r.stderr)
 def create(self,p,n):ledger.create(p,dict(max_records=n,record_ids=['r'+str(i) for i in range(n)],origin='SYNTHETIC'))
 def test_incremental_final_audit_visits_all_evidence(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t)/'s';self.create(root,5);orig=ledger.artifact;count=[0]
   def counted(*a,**k):count[0]+=1;return orig(*a,**k)
   with patch.object(ledger,'artifact',counted):
    with ledger.SessionWriter(root,incremental=True) as w:
     for i in range(5):
      n='r'+str(i);w.begin(n,{});p=root/'raw'/(n+'.bin');p.write_bytes(bytes([i]));w.complete(n,{p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()})
   self.assertEqual(count[0],10);self.assertEqual(w.final_report['recorded_completions'],5)
 def test_fast_writer_detects_raw_tampering_on_close(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t)/'s';self.create(root,1)
   with self.assertRaises(ValueError):
    with ledger.SessionWriter(root,incremental=True) as w:
     w.begin('r0',{});p=root/'raw/x';p.write_bytes(b'one');w.complete('r0',{'raw/x':hashlib.sha256(p.read_bytes()).hexdigest()});p.write_bytes(b'two')
   self.assertFalse((root/'writer.lock').exists())
 def test_fast_writer_external_append_blocks_next_event(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t)/'s';self.create(root,1)
   with self.assertRaises(ValueError):
    with ledger.SessionWriter(root,incremental=True) as w:
     with (root/'journal.jsonl').open('ab') as f:f.write(b'bad')
     w.begin('r0',{})
if __name__=='__main__':unittest.main()
