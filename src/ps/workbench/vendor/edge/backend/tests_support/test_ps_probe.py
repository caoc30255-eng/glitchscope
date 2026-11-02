from pathlib import Path
import sys, unittest, uuid
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'host')]
from read_only_probe import probe
from ps_candidate_session import BANKS


class ProbeTests(unittest.TestCase):
    def test_reviewed_HWH_all_eight_actual_reads_and_zero_writes(self):
        calls = []
        class Bus:
            def __init__(self, base): self.base = base
            def read(self, a):
                calls.append((self.base, a))
                if a == 0: return next(i for b, _, i in BANKS.values() if b == self.base)
                if self.base == BANKS['SYS'][0] and a == 8: return 100000000
                return 0
            def write(self, a, v): raise AssertionError('Probe must never write')
        result = probe(lambda base, size: Bus(base), ROOT/'hardware/h1_7020_evidence_candidate_v0_1.hwh')
        self.assertTrue(result['all_IDs_match'])
        self.assertEqual(len(result['banks']), 8)
        self.assertEqual(result['hardware_writes'], 0)
        self.assertFalse(result['hardware_system_acceptance'])
    def test_wrong_HWH_rejected_before_MMIO(self):
        path = ROOT/'evidence'/('bad_hwh_'+uuid.uuid4().hex+'.xml')
        path.write_text('<MODULES/>')
        with self.assertRaises(ValueError):
            probe(lambda *args: self.fail('Unexpected device IO'), path)


if __name__ == '__main__': unittest.main()
