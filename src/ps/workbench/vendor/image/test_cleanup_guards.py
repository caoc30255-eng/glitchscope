from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock,patch
import runpy,tempfile,unittest

ROOT=Path(__file__).resolve().parent


class Cleanup(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);session=self.root/'session_00000026';session.mkdir()
        self.session=NS(root=session,current=None,fault=False,journal=NS(record=Mock()),close=Mock())
        self.env=dict(board_session=self.session,image_web=NS(pilot=None),candidate=ROOT,
            control_uart=NS(context=True,fault=True,pending_snapshot=lambda **kw:{'buffered_words':[],'receiver_running':False}),
            buses={'SYS':NS(read=lambda offset:0)})
    def run_cleanup(self):
        # Windows cannot fsync directory descriptors; modeled IO only in this test.
        with patch('os.open',return_value=9876),patch('os.fsync'),patch('os.close'):
            return runpy.run_path(str(ROOT/'preserve_failure_close.py'),init_globals=self.env)
    def test_preserves_notebook_then_closes_idle_failed_session(self):
        self.run_cleanup();self.session.close.assert_called_once()
        self.assertEqual(len(list(self.session.root.glob('WEB_START_FAILURE_*/notebook_original.ipynb'))),1)
        self.assertEqual(len(list(self.session.root.glob('WEB_START_FAILURE_*/diagnostic.json'))),1)
    def test_active_image_plan_rejected_before_close(self):
        self.env['image_web'].pilot=NS()
        with self.assertRaises(AssertionError):self.run_cleanup()
        self.session.close.assert_not_called()
    def test_nonzero_physical_counters_rejected_before_close(self):
        self.env['buses']['SYS'].read=lambda offset:1
        with self.assertRaises(AssertionError):self.run_cleanup()
        self.session.close.assert_not_called()


if __name__=='__main__':unittest.main()
