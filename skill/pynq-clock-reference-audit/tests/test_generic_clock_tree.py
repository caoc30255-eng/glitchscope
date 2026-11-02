import copy,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from diagnose_clock_tree import diagnose
def case():
    return dict(schema='CLOCK_TREE_REFERENCE_SNAPSHOT_V1',device='Independent 24MHz-reference example (synthetic)',snapshot_stable=True,references=[dict(id='osc',hz=24000000,source='synthetic reference specification')],nodes=[dict(id='pll',parent='osc',numerator=125,denominator=3,kind='fractional_pll'),dict(id='bus',parent='pll',numerator=1,denominator=10,kind='divider')],clocks=[dict(id='bus',hardware_node='bus',enabled=True,software_reference_hz=24000000,reported_hz=100000000,requested_hz=100000000,declaration_hz=100000000,tolerance_ppm=1,tolerance_basis='synthetic exact-frequency arithmetic')])
class GenericTests(unittest.TestCase):
    def test_not_33_or50_reference_and_fractional_pll(self):
        v=diagnose(case());self.assertEqual(v['status'],'CONFIGURATION_AND_READBACK_CONSISTENT');self.assertEqual(v['clocks'][0]['register_tree_derived_hz'],100000000)
    def test_reference_mismatch(self):
        v=case();v['clocks'][0].update(software_reference_hz=48000000,reported_hz=200000000,requested_hz=200000000)
        r=diagnose(v)['clocks'][0];self.assertIn('SOFTWARE_REFERENCE_MISMATCH',r['issues']);self.assertNotIn('READBACK_OR_GETTER_MODEL_MISMATCH',r['issues'])
    def test_readback_not_explained_by_reference_model(self):
        v=case();v['clocks'][0]['reported_hz']=120000000
        self.assertIn('READBACK_OR_GETTER_MODEL_MISMATCH',diagnose(v)['clocks'][0]['issues'])
    def test_request_and_declaration_mismatch_diagnosed_separately(self):
        v=case();v['clocks'][0].update(requested_hz=99000000,declaration_hz=80000000)
        r=diagnose(v)['clocks'][0];self.assertIn('REQUEST_VS_READBACK_DIFFERENCE',r['issues']);self.assertIn('DECLARATION_VS_TREE_DIFFERENCE',r['issues']);self.assertNotIn('SOFTWARE_REFERENCE_MISMATCH',r['issues'])
    def test_disabled_not_reported_as_running(self):
        v=case();v['clocks'][0]['enabled']=False;r=diagnose(v)['clocks'][0]
        self.assertEqual(r['register_tree_derived_hz'],0);self.assertIn('CLOCK_DISABLED',r['issues'])
    def test_missing_reference_returns_evidence_request(self):
        v=case();v['references'][0]['hz']=None;r=diagnose(v)['clocks'][0]
        self.assertIsNone(r['register_tree_derived_hz']);self.assertIn('MISSING_BOARD_REFERENCE',r['issues']);self.assertTrue(r['next_actions'])
    def test_multiple_domains_and_source_selection_export(self):
        v=case();v['nodes'].append(dict(id='other',parent='pll',numerator=1,denominator=20));v['clocks'].append(dict(v['clocks'][0],id='other_domain',hardware_node='other',reported_hz=50000000,requested_hz=50000000,declaration_hz=50000000))
        r=diagnose(v);self.assertEqual(len(r['clocks']),2);self.assertEqual(r['status'],'CONFIGURATION_AND_READBACK_CONSISTENT')
    def test_device_getter_can_model_different_ratio(self):
        v=case();v['nodes'].append(dict(id='software_old',parent='osc',numerator=4,denominator=1));v['clocks'][0].update(software_node='software_old',reported_hz=96000000)
        r=diagnose(v)['clocks'][0];self.assertNotIn('READBACK_OR_GETTER_MODEL_MISMATCH',r['issues']);self.assertIn('REPORTED_VS_CONFIGURED_TREE_DIFFERENCE',r['issues'])
    def test_cycle_rejected_even_when_unused(self):
        v=case();v['nodes'].append(dict(id='bad',parent='bad',numerator=1,denominator=1))
        with self.assertRaisesRegex(ValueError,'CYCLE'):diagnose(v)
    def test_unknown_parent_rejected(self):
        v=case();v['nodes'][0]['parent']='unknown'
        with self.assertRaisesRegex(ValueError,'UNKNOWN_PARENT'):diagnose(v)
    def test_zero_negative_bool_ratio_rejected(self):
        for value in (0,-1,True):
            v=case();v['nodes'][0]['denominator']=value
            with self.subTest(value=value),self.assertRaises(ValueError):diagnose(v)
    def test_unstable_rejected(self):
        v=case();v['snapshot_stable']=False
        with self.assertRaisesRegex(ValueError,'UNSTABLE'):diagnose(v)
    def test_nan_and_unexplained_tolerance_rejected(self):
        for field,value in [('reported_hz',float('nan')),('tolerance_basis',''),('tolerance_ppm',20000)]:
            v=case();v['clocks'][0][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):diagnose(v)
    def test_duplicate_clock_id_rejected(self):
        v=case();v['clocks'].append(dict(v['clocks'][0]))
        with self.assertRaisesRegex(ValueError,'CLOCK_ID'):diagnose(v)
    def test_inputs_immutable_and_no_physical_claim(self):
        v=case();before=copy.deepcopy(v);r=diagnose(v);self.assertEqual(v,before);self.assertFalse(r['physical_measurement']);self.assertFalse(r['automatic_repair_performed'])
if __name__=='__main__':unittest.main()
