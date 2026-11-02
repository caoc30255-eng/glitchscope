import copy,json,sys,tempfile,types,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
import preflight as p
from check_notebook import compare
class BringupTests(unittest.TestCase):
 def profile(self,name='counter'):
  f=ROOT/'examples'/name/'profile.json';return f,json.loads(f.read_text(encoding='utf-8'))
 def test_two_ip_profiles_offline(self):
  for n in ['counter','fir']:self.assertEqual(p.run(self.profile(n)[0])['status'],'PASS_OFFLINE_PROFILE')
 def test_offline_never_imports_pynq(self):
  with patch.dict(sys.modules,{'pynq':None}):self.assertEqual(p.run(self.profile()[0])['mmio_reads'],[])
 def test_tampered_asset_rejected(self):
  f,c=self.profile();c['assets']['bit']['sha256']='0'*64
  with self.assertRaisesRegex(ValueError,'ASSET_HASH'):p.validate(c,f.parent)
 def test_offset_alignment_rejected(self):
  f,c=self.profile();c['registers'][0]['offset']=3
  with self.assertRaisesRegex(ValueError,'REGISTER_RANGE'):p.validate(c,f.parent)
 def test_read_clear_cannot_enter_preflight(self):
  f,c=self.profile();c['registers'][0]['read_effect']='clear'
  with self.assertRaises(ValueError):p.validate(c,f.parent)
 def test_mock_cannot_be_loaded(self):
  with self.assertRaisesRegex(ValueError,'MOCK_ASSET'):p.run(self.profile()[0],'load',True,True)
 def test_empty_identity_list_rejected(self):
  f,c=self.profile();c['registers']=[]
  with self.assertRaises(ValueError):p.validate(c,f.parent)
 def test_bool_word_rejected(self):
  with self.assertRaises(ValueError):p.uint(True)
 def test_notebook_format_only(self):
  a=json.loads((ROOT/'examples/reference.ipynb').read_text(encoding='utf-8'));b=json.loads((ROOT/'examples/reformatted.ipynb').read_text(encoding='utf-8'));self.assertTrue(compare(a,b)['passed'])
 def test_notebook_value_change(self):
  a=json.loads((ROOT/'examples/reference.ipynb').read_text(encoding='utf-8'));b=copy.deepcopy(a);b['cells'][0]['source']=['x=4\nprint(x)'];self.assertFalse(compare(a,b)['passed'])
 def test_notebook_added_code_cell(self):
  a=json.loads((ROOT/'examples/reference.ipynb').read_text(encoding='utf-8'));b=copy.deepcopy(a);b['cells'].append(copy.deepcopy(b['cells'][0]));self.assertFalse(compare(a,b)['passed'])
 def test_all_flags_checked_before_fake_download(self):
  f,c=self.profile();c['asset_kind']='REAL_BOARD_ASSET';c['clock']['configure_mhz']=150
  with tempfile.TemporaryDirectory() as t:
   # Absolute asset paths preserve source fixtures while testing configuration guards.
   for item in c['assets'].values():item['path']=str((f.parent/item['path']).resolve())
   q=Path(t)/'p.json';q.write_text(json.dumps(c))
   with patch.dict(sys.modules,{'pynq':None}):
    with self.assertRaisesRegex(ValueError,'CLOCK_WRITE_FLAG'):p.run(q,'load',True,False)
 def test_fake_target_records_effects_and_readback_scope(self):
  f,c=self.profile();c['asset_kind']='REAL_BOARD_ASSET';c['clock'].update(configure_mhz=150,expected_mhz=150)
  with tempfile.TemporaryDirectory() as t:
   for item in c['assets'].values():item['path']=str((f.parent/item['path']).resolve())
   q=Path(t)/'p.json';q.write_text(json.dumps(c));calls=[]
   class Bus:
    def __init__(self,*a):pass
    def read(self,*a):return int(c['registers'][0]['expected'],0)
   fake=types.ModuleType('pynq');fake.MMIO=Bus;fake.Clocks=types.SimpleNamespace(fclk0_mhz=100);fake.Overlay=lambda *a,**k:calls.append((a,k))
   server=types.ModuleType('pynq.pl_server');server.Device=types.SimpleNamespace(devices=['FAKE_DEVICE'])
   with patch.dict(sys.modules,{'pynq':fake,'pynq.pl_server':server}):r=p.run(q,'load',True,True)
   self.assertEqual(len(calls),1);self.assertTrue(r['clock_write_attempted']);self.assertFalse(r['exact_loaded_bitstream_identity_verified']);self.assertEqual(r['status'],'PASS_TARGET_READBACK_ONLY')
 def test_schema_bool_refused(self):
  f,c=self.profile();c['schema']=True
  with self.assertRaises(ValueError):p.validate(c,f.parent)
if __name__=='__main__':unittest.main()
