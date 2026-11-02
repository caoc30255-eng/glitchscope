import copy,json,sys,tempfile,types,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
import preflight as p
class HardeningTests(unittest.TestCase):
 def profile(self):
  f=ROOT/'examples/counter/profile.json';c=json.loads(f.read_text(encoding='utf-8'))
  for a in c['assets'].values():a['path']=str((f.parent/a['path']).resolve())
  return f,c
 def test_zero_mask_rejected(self):
  f,c=self.profile();c['registers'][0]['mask']=0
  with self.assertRaisesRegex(ValueError,'ZERO_IDENTITY'):p.validate(c,f.parent)
 def test_hwh_wrong_address_rejected(self):
  f,c=self.profile();c['registers'][0]['base']='0x40000004'
  with self.assertRaisesRegex(ValueError,'HWH_ADDRESS'):p.validate(c,f.parent)
 def test_hwh_wrong_span_rejected(self):
  f,c=self.profile();c['registers'][0]['span']=8192
  with self.assertRaisesRegex(ValueError,'HWH_ADDRESS'):p.validate(c,f.parent)
 def test_wrong_ip_rejected(self):
  f,c=self.profile();c['registers'][0]['ip_name']='wrong'
  with self.assertRaisesRegex(ValueError,'HWH_IP'):p.validate(c,f.parent)
 def test_xml_entities_rejected(self):
  with tempfile.TemporaryDirectory() as t:
   f=Path(t)/'x.hwh';f.write_text('<!DOCTYPE x [<!ENTITY e "xx">]><x/>')
   with self.assertRaisesRegex(ValueError,'DTD'):p.hwh_map(f)
 def test_zero_clock_config_rejected(self):
  f,c=self.profile();c['clock']['configure_mhz']=0
  with self.assertRaises(ValueError):p.validate(c,f.parent)
 def target(self,throw=False):
  f,c=self.profile();c['asset_kind']='REAL_BOARD_ASSET';c['clock']['expected_mhz']=125
  fake=types.ModuleType('pynq');fake.__version__='FAKE_TEST';fake.Clocks=types.SimpleNamespace(fclk0_mhz=100)
  class Bus:
   def __init__(self,*a):pass
   def read(self,*a):return int(c['registers'][0]['expected'],0)
  fake.MMIO=Bus
  def overlay(*a,**k):
   fake.Clocks.fclk0_mhz=125
   if throw:raise RuntimeError('FAKE_FAILED_AFTER_CLOCK')
  fake.Overlay=overlay;server=types.ModuleType('pynq.pl_server');server.Device=types.SimpleNamespace(devices=['FAKE'])
  return c,{'pynq':fake,'pynq.pl_server':server}
 def test_implicit_clock_never_reported_false(self):
  c,modules=self.target()
  with tempfile.TemporaryDirectory() as t:
   f=Path(t)/'p.json';f.write_text(json.dumps(c))
   with patch.dict(sys.modules,modules):r=p.run(f,'load',True,True)
   self.assertTrue(r['overlay_clock_configuration_possible']);self.assertIsNone(r['clock_write_attempted']);self.assertFalse(r['explicit_clock_write_attempted']);self.assertEqual(r['clock_after']['fclk0_mhz'],125)
 def test_all_downloads_need_clock_effect_scope(self):
  c,modules=self.target();c.pop('clock')
  with tempfile.TemporaryDirectory() as t:
   f=Path(t)/'p.json';f.write_text(json.dumps(c))
   with self.assertRaisesRegex(ValueError,'CLOCK_WRITE_FLAG'):p.run(f,'load',True,False)
 def test_failure_after_implicit_clock_preserved(self):
  c,modules=self.target(True);report={}
  with tempfile.TemporaryDirectory() as t:
   f=Path(t)/'p.json';f.write_text(json.dumps(c))
   with patch.dict(sys.modules,modules):
    with self.assertRaises(RuntimeError):p.run(f,'load',True,True,report)
   self.assertFalse(report['overlay_download_completed']);self.assertTrue(report['overlay_clock_configuration_possible']);self.assertEqual(report['clock_after_overlay']['fclk0_mhz'],125)
 def test_explicit_clock_setter_partial_failure_preserved(self):
  c,modules=self.target();c['clock']['configure_mhz']=150;report={}
  class Clock:
   value=100
   @property
   def fclk0_mhz(self):return self.value
   @fclk0_mhz.setter
   def fclk0_mhz(self,v):self.value=v;raise RuntimeError('PARTIAL_SET')
  modules['pynq'].Clocks=Clock();modules['pynq'].Overlay=lambda *a,**k:None
  with tempfile.TemporaryDirectory() as t:
   f=Path(t)/'p.json';f.write_text(json.dumps(c))
   with patch.dict(sys.modules,modules):
    with self.assertRaises(RuntimeError):p.run(f,'load',True,True,report)
   self.assertTrue(report['explicit_clock_write_attempted']);self.assertEqual(report['clock_after_explicit_write']['fclk0_mhz'],150)
 def test_clock_mismatch_blocks_before_mmio(self):
  c,modules=self.target();c['clock']['expected_mhz']=999;called=[]
  modules['pynq'].MMIO=lambda *a:called.append(a)
  with tempfile.TemporaryDirectory() as t:
   f=Path(t)/'p.json';f.write_text(json.dumps(c))
   with patch.dict(sys.modules,modules):
    with self.assertRaisesRegex(ValueError,'BEFORE_MMIO'):p.run(f,'inspect')
   self.assertEqual(called,[])
 def test_board_model_mismatch_before_mmio(self):
  c,modules=self.target();c['expected_board_model']='wanted'
  with tempfile.TemporaryDirectory() as t:
   f=Path(t)/'p.json';f.write_text(json.dumps(c))
   with patch.object(p,'board_metadata',return_value={'device_tree_model':'other'}):
    with self.assertRaisesRegex(ValueError,'BOARD_MODEL'):p.run(f,'inspect')
if __name__=='__main__':unittest.main()
