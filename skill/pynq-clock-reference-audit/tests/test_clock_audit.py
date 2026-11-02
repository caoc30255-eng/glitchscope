import copy,importlib.util,json,math,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from audit_clock import audit,load
from collect_clock import collect,OFFSETS
def sample():return json.loads((ROOT/'examples/navigator_snapshot.json').read_bytes())
def run(s=None,ref=33.333333):return audit(sample() if s is None else s,ref,'documented schematic PS_CLK')
class ClockTests(unittest.TestCase):
    def test_actual_case_recomputed_not_measured(self):
        v=run();self.assertEqual(v['status'],'PYNQ_REFERENCE_MISMATCH');self.assertAlmostEqual(v['register_derived_fclk0_mhz'],100,places=5);self.assertFalse(v['physical_measurement']);self.assertFalse(v['clock_configuration_changed'])
    def test_all_source_selectors(self):
        for selector,name,mult in [(0,'IO_PLL_CTRL',30),(1,'IO_PLL_CTRL',30),(2,'ARM_PLL_CTRL',46),(3,'DDR_PLL_CTRL',32)]:
            with self.subTest(selector=selector):
                s=sample();s['raw_registers']['FPGA0_CLK_CTRL']=hex(0x200500|(selector<<4));s['reported_fclk0_mhz']=50*mult/10
                v=run(s);self.assertEqual(v['selected_pll'],name);self.assertAlmostEqual(v['register_derived_fclk0_mhz'],33.333333*mult/10)
    def test_native50_reference_is_not_universally_wrong(self):
        s=sample();s.pop('device_tree_ps_clk_frequency_hz');v=run(s,50);self.assertEqual(v['status'],'REFERENCE_CONSISTENT');self.assertEqual(v['register_derived_fclk0_mhz'],150)
    def test_reference_evidence_conflict(self):self.assertEqual(run(ref=50)['status'],'REFERENCE_EVIDENCE_CONFLICT')
    def test_reported_rate_not_rewritten_to_fit(self):
        s=sample();s['reported_fclk0_mhz']=100
        with self.assertRaisesRegex(ValueError,'REPORTED_VALUE'):run(s)
    def test_unstable_flag(self):
        s=sample();s['raw_second_read_matches']=False
        with self.assertRaisesRegex(ValueError,'UNSTABLE'):run(s)
    def test_raw_second_snapshot_overrides_false_stability_claim(self):
        s=sample();s['raw_registers_second']=dict(s['raw_registers']);s['raw_registers_second']['FPGA0_CLK_CTRL']='0x200600'
        with self.assertRaisesRegex(ValueError,'RAW_SNAPSHOTS'):run(s)
    def test_zero_divisors_rejected(self):
        for raw in (0x200000,0x500):
            s=sample();s['raw_registers']['FPGA0_CLK_CTRL']=hex(raw)
            with self.subTest(raw=raw),self.assertRaisesRegex(ValueError,'ZERO_DIVISOR'):run(s)
    def test_reset_and_powerdown_rejected(self):
        for flag in (1,2):
            s=sample();s['raw_registers']['IO_PLL_CTRL']=hex(0x1e000|flag)
            with self.subTest(flag=flag),self.assertRaisesRegex(ValueError,'RESET_OR_POWERDOWN'):run(s)
    def test_stable_bit_is_not_lock_bit(self):
        s=sample();s['raw_registers']['PLL_STATUS']='0x20'
        with self.assertRaisesRegex(ValueError,'PLL_NOT_LOCKED'):run(s)
    def test_forced_bypass_uses_reference_not_multiplied_rate(self):
        s=sample();s['raw_registers']['IO_PLL_CTRL']='0x1e010';s['raw_registers']['PLL_STATUS']='0'
        v=run(s);self.assertTrue(v['pll_bypass']);self.assertAlmostEqual(v['register_derived_fclk0_mhz'],3.3333333);self.assertEqual(v['status'],'PLL_BYPASS_REQUIRES_PYNQ_GETTER_REVIEW')
    def test_qualified_bypass_requires_boot_strap_not_lock_guess(self):
        s=sample();s['raw_registers']['IO_PLL_CTRL']='0x1e008'
        with self.assertRaisesRegex(ValueError,'BOOT_MODE'):run(s)
        s['raw_registers']['BOOT_MODE']='0';self.assertFalse(run(s)['pll_bypass'])
        s['raw_registers']['BOOT_MODE']='0x10';self.assertTrue(run(s)['pll_bypass'])
    def test_unknown_pynq_reference_remains_unknown(self):
        s=sample();s['pynq_instance_reference_mhz']=None
        v=run(s);self.assertEqual(v['status'],'REGISTER_RATE_DERIVED_PYNQ_REFERENCE_UNAVAILABLE');self.assertIsNone(v['expected_pynq_getter_mhz'])
    def test_nonfinite_bool_and_nonpositive_reference_rejected(self):
        for ref in (float('nan'),float('inf'),True,0,-33):
            with self.subTest(ref=ref),self.assertRaises(ValueError):run(ref=ref)
    def test_invalid_register_and_wrong_architecture_rejected(self):
        for bad in (True,-1,0x100000000,1.5,'invalid'):
            s=sample();s['raw_registers']['PLL_STATUS']=bad
            with self.subTest(bad=bad),self.assertRaises(ValueError):run(s)
        s=sample();s['clock_class']='_ClocksUltrascale'
        with self.assertRaisesRegex(ValueError,'ZYNQ7000'):run(s)
    def test_json_duplicate_and_nan_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'bad.json'
            for text in ('{"a":1,"a":2}','{"a":NaN}'):
                p.write_text(text,encoding='utf-8')
                with self.assertRaises(ValueError):load(p)
    def test_collector_reads_only_declared_registers_twice(self):
        s=sample();regs={o:int(s['raw_registers'].get(k,'0'),0) for k,o in OFFSETS.items()};calls=[]
        def read(o):calls.append(o);return regs[o]
        v=collect(read,lambda:dict(clock_class='_ClocksZynq',pynq_instance_reference_mhz=50,reported_fclk0_mhz=150))
        self.assertEqual(calls,list(OFFSETS.values())*2);self.assertEqual(v['hardware_register_writes'],0);self.assertTrue(v['raw_second_read_matches']);self.assertAlmostEqual(run(v)['register_derived_fclk0_mhz'],100,places=5)
    def test_change_during_metadata_collection_detected(self):
        s=sample();regs={o:int(s['raw_registers'].get(k,'0'),0) for k,o in OFFSETS.items()}
        def meta():regs[0x170]=0x200600;return dict(clock_class='_ClocksZynq')
        v=collect(regs.__getitem__,meta);self.assertFalse(v['raw_second_read_matches'])
        with self.assertRaisesRegex(ValueError,'UNSTABLE'):run(v)
    def test_cli_does_not_overwrite_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'result.json';p.write_text('original',encoding='utf-8')
            args=[sys.executable,'-B',str(ROOT/'scripts/audit_clock.py'),'--snapshot',str(ROOT/'examples/navigator_snapshot.json'),'--reference-mhz','33.333333','--reference-source','schematic','--output',str(p)]
            result=subprocess.run(args,capture_output=True)
            self.assertNotEqual(result.returncode,0);self.assertEqual(p.read_text(),'original')
if __name__=='__main__':unittest.main()
