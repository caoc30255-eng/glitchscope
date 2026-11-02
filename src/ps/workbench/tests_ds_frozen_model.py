"""Regression checks for the web analysis deployment's inner frozen-model receipt."""
import unittest,sys,subprocess,tempfile,shutil,json,hashlib,os
from pathlib import Path
ROOT=Path(__file__).resolve().parent
DS=ROOT/'vendor/ds'
class FrozenModelTests(unittest.TestCase):
    def run_ds(self,folder,code,ok=True):
        env=dict(os.environ);env['PYTHONDONTWRITEBYTECODE']='1'
        r=subprocess.run([sys.executable,'-B','-c',code],cwd=str(folder),env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        if ok:self.assertEqual(r.returncode,0,(r.stdout+r.stderr).decode(errors='replace'))
        else:self.assertNotEqual(r.returncode,0)
        return r
    def test_web_package_and_original_receipt_agree(self):
        self.run_ds(DS,'from workbench import verify_package; verify_package()')
        b=(DS/'b_receiver.py').read_bytes();r=json.loads((DS/'rtl_cosim_receipt.json').read_bytes())
        self.assertNotIn(b'\r\n',b);self.assertEqual(hashlib.sha256(b).hexdigest(),r['model_sha256'])
        self.assertEqual(r['cases'],1125)
    def test_local_reference_contracts(self):
        self.run_ds(DS,'import unittest; r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.discover(".",pattern="tests_local_reference.py")); raise SystemExit(not r.wasSuccessful())')
    def test_crlf_regression_is_still_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            d=Path(t)/'ds';shutil.copytree(DS,d)
            p=d/'b_receiver.py';p.write_bytes(p.read_bytes().replace(b'\n',b'\r\n'))
            r=self.run_ds(d,'from image64 import verify_cycle_model; verify_cycle_model()',False)
            self.assertIn(b'FROZEN_CYCLE_MODEL_CHANGED',r.stderr)
    def test_model_edit_is_still_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            d=Path(t)/'ds';shutil.copytree(DS,d)
            p=d/'b_receiver.py';p.write_bytes(p.read_bytes()+b'\n# modified\n')
            r=self.run_ds(d,'from image64 import verify_cycle_model; verify_cycle_model()',False)
            self.assertIn(b'FROZEN_CYCLE_MODEL_CHANGED',r.stderr)
if __name__=='__main__':unittest.main(verbosity=2)
