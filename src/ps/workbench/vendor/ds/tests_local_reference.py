import unittest,copy
from tests_offline import all64,window
from image64 import summarize
from workbench import add_regions

class LocalReferenceTests(unittest.TestCase):
    def test_dynamic_nonzero_coverage(self):
        for count in [1,2,7,20,32,63]:
            with self.subTest(count=count):
                windows=all64()
                for w in windows[count:]:w['state']='UNALIGNED';w['profiles']=[]
                s=summarize(windows);p=s['local_reference']
                self.assertEqual(p['covered_windows'],count);self.assertTrue(p['candidate_set'])
                self.assertEqual(len(p['excluded_items']),64-count)
                self.assertFalse(s['global_minimax_candidate_set']);self.assertFalse(p['full64_recommendation'])
                self.assertFalse(p['per_ITEM_ds_selection_allowed'])
    def test_zero_no_candidate(self):
        windows=all64()
        for w in windows:w['state']='UNALIGNED';w['profiles']=[]
        s=summarize(windows);self.assertFalse(s['local_reference']['candidate_set'])
        self.assertEqual(s['local_reference']['state'],'NO_COMMON_USABLE_WINDOWS')
    def test_full64_ranking_unchanged(self):
        s=summarize(all64())
        self.assertTrue(s['global_minimax_candidate_set'])
        self.assertEqual(s['local_reference']['candidate_set'],s['global_minimax_candidate_set'])
    def test_different_coverage_cannot_bias_ranking(self):
        windows=all64();windows[0]['profiles'][0]['scenarios'][0]['aligned']=False
        p=summarize(windows)['local_reference'];self.assertEqual(p['covered_windows'],63)
        self.assertTrue(all(r['evaluated_windows']==63 and r['compared_local_bits']==63*16 for r in p['profiles']))
        self.assertNotIn(2,p['included_record_ids'])
    def test_bit_coverage_must_match(self):
        windows=all64();windows[0]['profiles'][0]['compared_bits']=8
        p=summarize(windows)['local_reference'];self.assertEqual(p['covered_windows'],63)
    def test_integrity_and_contradiction_suppress_partial(self):
        for state in ['INTEGRITY_ERROR','MODEL_CONTRADICTED','UNKNOWN_OR_UNRETIRED','ANALYSIS_CANCELLED']:
            windows=all64();windows[-1]['state']=state;windows[-1]['profiles']=[]
            p=summarize(windows)['local_reference'];self.assertEqual(p['state'],'BLOCKED_EVIDENCE');self.assertFalse(p['candidate_set'])
    def test_outer_integrity_block_withdraws_partial(self):
        s=summarize(all64());add_regions(s,0,0,True)
        self.assertFalse(s['local_reference']['candidate_set']);self.assertEqual(s['local_reference']['state'],'BLOCKED_EVIDENCE')
    def test_input_not_modified_and_ties_retained(self):
        windows=all64();before=copy.deepcopy(windows);s=summarize(windows)
        self.assertEqual(windows,before);self.assertGreater(len(s['local_reference']['candidate_set']),1)
    def test_partial_list_enumerates_missing_windows(self):
        p=summarize([window(2)])['local_reference'];self.assertEqual(p['covered_windows'],1)
        self.assertEqual(len(p['excluded_items']),63)
if __name__=='__main__':unittest.main(verbosity=2)
