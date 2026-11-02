import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class Layout(unittest.TestCase):
    def test_relocated_runtime_and_lazy_codec_use_packaged_sources(self):
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as t:
            output=Path(t)/'result.json'
            done=subprocess.run([sys.executable,'-B',str(root/'runtime_probe.py'),str(output)],capture_output=True)
            self.assertEqual(done.returncode,0,done.stderr.decode('utf-8',errors='replace'))
            result=json.loads(output.read_bytes())
            self.assertFalse(result['hardware_access'])
            self.assertEqual(result['ITEM_bytes'],278)


if __name__=='__main__':unittest.main()
