"""Generate a portable driver bundle and an identity-test skeleton from a contract."""
import argparse,json,shutil
from pathlib import Path
from contract import validate
def generate(contract_path,output):
    c=validate(json.loads(Path(contract_path).read_text(encoding='utf-8')))
    if not any('expected' in r for r in c['registers']):raise ValueError('IDENTITY_EXPECTATION_REQUIRED_FOR_TEST_SKELETON')
    out=Path(output);out.mkdir() # Refuse existing output; preserve earlier generated code.
    shutil.copy2(Path(__file__).with_name('contract.py'),out/'contract.py')
    (out/'registers.json').write_text(json.dumps(c,indent=2),encoding='utf-8')
    (out/'driver.py').write_text('''import json
from pathlib import Path
from contract import RegisterBank
def connect(bus):
    contract=json.loads(Path(__file__).with_name('registers.json').read_text(encoding='utf-8'))
    return RegisterBank(bus,contract)
''',encoding='utf-8')
    (out/'test_generated.py').write_text('''import json,unittest
from pathlib import Path
from contract import FakeBus
from driver import connect
class TestGenerated(unittest.TestCase):
    def test_identity_and_no_construction_writes(self):
        c=json.loads(Path(__file__).with_name('registers.json').read_text(encoding='utf-8'))
        words={str(int(r['offset'],0) if isinstance(r['offset'],str) else r['offset']):r['expected'] for r in c['registers'] if 'expected' in r}
        if c['addressing']=='absolute':
            base=int(c['base'],0) if isinstance(c['base'],str) else c['base']
            words={str(int(k)+base):v for k,v in words.items()}
        bus=FakeBus(words)
        for key,fallback in [('read_method',bus.read),('write_method',bus.write)]:
            if c.get(key) and not hasattr(bus,c[key]):setattr(bus,c[key],fallback)
        bank=connect(bus)
        self.assertEqual(bus.calls,[])
        self.assertTrue(all(i['matched'] for i in bank.identities()))
        self.assertTrue(all(i[0]=='read' for i in bus.calls))
if __name__=='__main__':unittest.main()
''',encoding='utf-8')
    return out
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--contract',required=True);p.add_argument('--output',required=True);a=p.parse_args();print(generate(a.contract,a.output))
