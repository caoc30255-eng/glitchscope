import copy,json,sys,tempfile,types,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from contract import RegisterBank,SemanticBus,validate
import pynq_mmio_example as hw
class FieldTests(unittest.TestCase):
 def bank(self,change=None):
  c=json.loads((ROOT/'examples/mixed.json').read_text(encoding='utf-8'))
  if change:change(c)
  b=SemanticBus(c,{'0':'0x434e5431','8':'0xf','12':'0x55','16':'0xa5000f05'});return RegisterBank(b,c),b,c
 def test_ro_status_not_echoed_into_write(self):
  d,b,c=self.bank();d.update_bits('control_status',0xff,7);self.assertEqual(b.calls[-1],['write',16,7]);self.assertEqual(b.words[16],0xa5000f07)
 def test_w1c_clear_preserves_rw_and_ro(self):
  d,b,c=self.bank();d.write_fields('control_status',{'irq':2});self.assertEqual(b.words[16],0xa5000d05)
 def test_pulse_is_event_not_persistent_bit(self):
  d,b,c=self.bank();d.write_fields('control_status',{'trigger':1});self.assertEqual(len(b.pulses),1);self.assertEqual(b.words[16],0xa5000f05)
 def test_update_cannot_target_w1c(self):
  d,b,c=self.bank()
  with self.assertRaises(ValueError):d.update_bits('control_status',0x100,0x100)
  self.assertEqual(b.calls,[])
 def test_undocumented_ro_write_policy_rejected(self):
  c=json.loads((ROOT/'examples/mixed.json').read_text(encoding='utf-8'));c['registers'][-1]['fields'][-1].pop('write_value')
  with self.assertRaises(ValueError):validate(c)
 def test_overlapping_fields_rejected(self):
  c=json.loads((ROOT/'examples/mixed.json').read_text(encoding='utf-8'));c['registers'][-1]['fields'][0]['width']=10
  with self.assertRaises(ValueError):validate(c)
 def test_plain_rw_not_silently_masked(self):
  d,b,c=self.bank();b.words[4]=0x80000000
  with self.assertRaisesRegex(ValueError,'RESERVED'):d.update_bits('scratch',1,1)
 def test_read_clear_model_and_driver(self):
  d,b,c=self.bank()
  with self.assertRaises(ValueError):d.read('events')
  self.assertEqual(d.read('events',True),0x55);self.assertEqual(d.read('events',True),0)
 def test_register_w1c_model(self):
  d,b,c=self.bank();d.write('irq',5);self.assertEqual(b.words[8],0xa)
 def test_read_clear_mixed_needs_explicit_rw_values(self):
  def alter(c):c['registers'][-1]['fields'][-1]['read_effect']='clear'
  d,b,c=self.bank(alter)
  with self.assertRaises(ValueError):d.update_bits('control_status',0xff,9)
  d.write_fields('control_status',{'gain':9});self.assertFalse(any(x[0]=='read' for x in b.calls));self.assertEqual(b.words[16],0xa5000f09)
 def test_raw_mixed_write_checks_constant_policy(self):
  d,b,c=self.bank()
  with self.assertRaises(ValueError):d.write('control_status',0xa5000001)
 def test_real_mmio_example_with_fake_backend_no_implicit_write(self):
  c=json.loads((ROOT/'examples/counter.json').read_text(encoding='utf-8'));c['target_kind']='REAL_BOARD_CONTRACT';calls=[]
  class MMIO:
   def __init__(self,*a):calls.append('construct')
   def read(self,a):calls.append(('read',a));return 0x434e5431
   def write(self,a,v):calls.append(('write',a,v))
  fake=types.ModuleType('pynq');fake.MMIO=MMIO
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'a.hwh';p.write_text('<X><MEMRANGE INSTANCE="test" BASEVALUE="0x40000000" HIGHVALUE="0x40000fff"/></X>')
   with patch.dict(sys.modules,{'pynq':fake}):r=hw.run(c,p,'test',True)
  self.assertEqual(r['writes'],[]);self.assertEqual(calls,['construct',('read',0)])
if __name__=='__main__':unittest.main()
