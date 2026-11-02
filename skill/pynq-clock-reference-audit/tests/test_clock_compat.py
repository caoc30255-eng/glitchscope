"""Class-shape regressions based on the official PYNQ2.4/2.7 implementation APIs."""
import sys,types,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from collect_clock import resolve_clock_api

class CompatTests(unittest.TestCase):
    def test_24_real_metaclass_shape_not_type_name(self):
        class _ClocksMeta(type):pass
        class _ClocksZynq(_ClocksMeta):DEFAULT_SRC_CLK_MHZ=50.0
        class Clocks(_ClocksZynq,metaclass=_ClocksMeta):pass
        self.assertEqual(type(Clocks).__name__,'_ClocksMeta')
        result=resolve_clock_api(Clocks,types.SimpleNamespace(_ClocksZynq=_ClocksZynq))
        self.assertIs(result[0],Clocks);self.assertEqual(result[1:3],('legacy_classmethod_api',50.0))
    def test_legacy_runtime_constant_override_is_read_not_assumed(self):
        class _ClocksMeta(type):pass
        class _ClocksZynq(_ClocksMeta):DEFAULT_SRC_CLK_MHZ=50.0
        class Clocks(_ClocksZynq,metaclass=_ClocksMeta):DEFAULT_SRC_CLK_MHZ=33.333333
        result=resolve_clock_api(Clocks,types.SimpleNamespace(_ClocksZynq=_ClocksZynq));self.assertEqual(result[2],33.333333)
    def test_27_instance_reference_not_default_is_used(self):
        class _ClocksZynq:
            DEFAULT_SRC_CLK_MHZ=50.0
            def __init__(self):self._ref_clk_mhz=33.333333
        instance=_ClocksZynq()
        class Meta(type):
            @property
            def _instance(cls):return instance
        class Clocks(metaclass=Meta):pass
        result=resolve_clock_api(Clocks,types.SimpleNamespace(_ClocksZynq=_ClocksZynq))
        self.assertIs(result[0],instance);self.assertEqual(result[1:3],('instance_api',33.333333))
    def test_foreign_same_named_instance_is_not_accepted(self):
        genuine=type('_ClocksZynq',(),{})
        foreign=type('_ClocksZynq',(),{})()
        clocks=types.SimpleNamespace(_instance=foreign)
        with self.assertRaisesRegex(RuntimeError,'UNSUPPORTED'):resolve_clock_api(clocks,types.SimpleNamespace(_ClocksZynq=genuine))
    def test_foreign_legacy_class_is_not_accepted(self):
        class Base:pass
        class Clocks:DEFAULT_SRC_CLK_MHZ=50.0
        with self.assertRaisesRegex(RuntimeError,'UNSUPPORTED'):resolve_clock_api(Clocks,types.SimpleNamespace(_ClocksZynq=Base))
    def test_missing_base_fails_without_guess(self):
        with self.assertRaisesRegex(RuntimeError,'BASE_UNAVAILABLE'):resolve_clock_api(object(),types.SimpleNamespace())
if __name__=='__main__':unittest.main()
