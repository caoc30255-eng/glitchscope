import copy,json,sys,tempfile,subprocess,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from contract import RegisterBank,FakeBus,validate
from generate_driver import generate
class ContractTests(unittest.TestCase):
 def setup_bank(self,n='counter'):
  c=json.loads((ROOT/'examples'/(n+'.json')).read_text(encoding='utf-8'));b=FakeBus(json.loads((ROOT/'examples'/(n+'_words.json')).read_text(encoding='utf-8')));return RegisterBank(b,c),b,c
 def test_offset_bank(self):
  d,b,c=self.setup_bank();self.assertTrue(d.identities()[0]['matched']);self.assertEqual(b.calls[0],['read',0])
 def test_absolute_other_ip(self):
  d,b,c=self.setup_bank('fir');self.assertTrue(d.identities()[0]['matched']);self.assertEqual(b.calls[0],['read',int(c['base'],0)])
 def test_constructor_does_not_touch_bus(self):self.assertEqual(self.setup_bank()[1].calls,[])
 def test_contract_snapshot_isolation(self):
  c=json.loads((ROOT/'examples/counter.json').read_text(encoding='utf-8'));b=FakeBus({'0':'0x434e5431'});d=RegisterBank(b,c);c['registers'][0]['access']='RW';c['base']='0x60000000'
  with self.assertRaises(ValueError):d.write('identity',0)
  self.assertTrue(d.identities()[0]['matched'])
 def test_read32_binding(self):
  class Bus:
   def read32(self,a):return 9
   def write32(self,a,v):self.last=(a,v)
  c=self.setup_bank()[2];c.pop('read_method');c.pop('write_method');b=Bus();d=RegisterBank(b,c);d.write('scratch',5);self.assertEqual(d.read('scratch'),9)
 def test_ambiguous_binding_refused(self):
  class Bus(FakeBus):
   def read32(self,a):return self.read(a)
  c=self.setup_bank()[2];c.pop('read_method')
  with self.assertRaises(ValueError):RegisterBank(Bus({}),c)
 def test_reserved_write_bits(self):
  d,b,c=self.setup_bank()
  with self.assertRaisesRegex(ValueError,'RESERVED'):d.write('scratch',256)
  self.assertEqual(b.calls,[])
 def test_read_only_write(self):
  with self.assertRaises(ValueError):self.setup_bank()[0].write('identity',0)
 def test_clear_requires_intent(self):
  d,b,c=self.setup_bank()
  with self.assertRaises(ValueError):d.read('events')
  self.assertEqual(d.read('events',allow_clear=True),0)
 def test_w1c_is_not_read_modify_write(self):
  d,b,c=self.setup_bank()
  with self.assertRaises(ValueError):d.update_bits('irq',1,1)
  d.write('irq',1);self.assertEqual(b.calls,[['write',8,1]])
 def test_bool_is_not_integer_data(self):
  with self.assertRaises(ValueError):self.setup_bank()[0].write('scratch',True)
 def test_duplicate_offset(self):
  c=self.setup_bank()[2];c['registers'][1]['offset']=0
  with self.assertRaises(ValueError):validate(c)
 def test_identity_mismatch_is_not_success(self):
  d,b,c=self.setup_bank();b.words[0]=0;self.assertFalse(d.identities()[0]['matched'])
 def test_generated_alternate_bus_names(self):
  with tempfile.TemporaryDirectory() as t:
   c=json.loads((ROOT/'examples/fir.json').read_text(encoding='utf-8'));c.update(read_method='read32',write_method='write32');p=Path(t)/'contract.json';p.write_text(json.dumps(c))
   out=generate(p,Path(t)/'generated');r=subprocess.run([sys.executable,'-B',str(out/'test_generated.py')],capture_output=True)
   self.assertEqual(r.returncode,0,r.stderr)
 def test_generator_refuses_vacuous_identity_test(self):
  with tempfile.TemporaryDirectory() as t:
   c=json.loads((ROOT/'examples/fir.json').read_text(encoding='utf-8'));c['registers'][0].pop('expected');p=Path(t)/'contract.json';p.write_text(json.dumps(c))
   with self.assertRaises(ValueError):generate(p,Path(t)/'generated')
 def test_generated_driver_runs_and_refuses_overwrite(self):
  with tempfile.TemporaryDirectory() as t:
   out=generate(ROOT/'examples/fir.json',Path(t)/'generated')
   p=subprocess.run([sys.executable,'-B',str(out/'test_generated.py')],capture_output=True)
   self.assertEqual(p.returncode,0,p.stderr)
   with self.assertRaises(FileExistsError):generate(ROOT/'examples/fir.json',out)
 def test_schema_and_word_width_types(self):
  c=self.setup_bank()[2];c['word_bits']=32.0
  with self.assertRaises(ValueError):validate(c)
if __name__=='__main__':unittest.main()
