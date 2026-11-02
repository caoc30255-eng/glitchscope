import copy,json,hashlib,unittest,os
from pathlib import Path
from image64 import summarize,PROFILES,warm_analyze,evaluate_window,load_record,verify_cycle_model

def window(rid=2):
    return dict(record_id=rid,session='synthetic_not_hardware',state='LOCAL_ENVELOPE_AVAILABLE',
        actual_profile=dict(d=3,s=-1),profiles=[dict(d=d,s=s,compared_bits=16,
        scenarios=[dict(aligned=True,phase=0,bit_errors=0,framing_errors=0),dict(aligned=True,phase=1,bit_errors=1 if d==1 else 0,framing_errors=0)]) for d,s in PROFILES])
def all64():return [window(i) for i in range(2,66)]

class GlobalTests(unittest.TestCase):
    def test_01_model_hash_matches_reviewed_RTL_receipt(self):self.assertEqual(verify_cycle_model()['cases'],1125)
    def test_02_incomplete64_cannot_recommend(self):
        self.assertEqual(summarize(all64()[:-1])['global_minimax_candidate_set'],[])
    def test_03_one_global_choice_no_per_item_optimization(self):
        w=all64()
        # Each item has some ideal profile, but no profile can change by item.
        for i,item in enumerate(w):
            for p in item['profiles']:
                for s in p['scenarios']:s['bit_errors']=0 if (p['d'],p['s'])==PROFILES[i%14] else 3
        r=summarize(w)
        self.assertFalse(r['per_ITEM_ds_selection_allowed']);self.assertFalse(r['robust_zero_candidate_set'])
        self.assertGreater(min(p['bit_errors_upper_bound'] for p in r['profiles']),0)
    def test_04_ties_are_preserved(self):self.assertGreater(len(summarize(all64())['global_minimax_candidate_set']),1)
    def test_05_any_unaligned_window_blocks_whole64_claim(self):
        w=all64();w[-1]['state']='UNALIGNED'
        self.assertEqual(summarize(w)['global_minimax_candidate_set'],[])
    def test_06_model_contradiction_not_dropped(self):
        w=all64();w[-1]['state']='MODEL_CONTRADICTED'
        self.assertEqual(summarize(w)['profiles'][0]['unresolved_windows'],1)
        self.assertFalse(summarize(w)['global_minimax_candidate_set'])
    def test_07_candidate_unaligned_in_one_phase_not_ranked(self):
        w=all64();w[0]['profiles'][0]['scenarios'][0]['aligned']=False
        r=summarize(w);self.assertFalse(r['profiles'][0]['eligible_for_global_software_ranking'])
    def test_08_duplicate_record_rejected(self):
        w=all64();w[-1]['record_id']=2
        with self.assertRaisesRegex(ValueError,'DUPLICATE'):summarize(w)
    def test_09_cross_session_pooling_rejected(self):
        w=all64();w[-1]['session']='other'
        with self.assertRaisesRegex(ValueError,'CROSS_SESSION'):summarize(w)
    def test_10_different_actual_ds_per_item_rejected(self):
        w=all64();w[-1]['actual_profile']['d']=4
        with self.assertRaisesRegex(ValueError,'ONE_GLOBAL_DS'):summarize(w)
    def test_11_duplicate_profile_not_treated_as_domain(self):
        w=all64();w[0]['profiles'][0]=copy.deepcopy(w[0]['profiles'][1])
        with self.assertRaisesRegex(ValueError,'UNIQUE14'):summarize(w)
    def test_12_bit_error_bounds_sum_conservatively(self):
        r=summarize(all64());self.assertEqual((r['profiles'][0]['bit_errors_lower_bound'],r['profiles'][0]['bit_errors_upper_bound']),(0,64))
    def test_13_local_results_never_claim_full_frame(self):
        r=summarize(all64());self.assertFalse(r['full_ITEM_BER_evaluated']);self.assertFalse(r['hardware_verified_recommendation'])
    def test_14_framing_error_precedes_bit_error_in_declared_rank(self):
        w=all64()
        for item in w:
            for p in item['profiles']:
                for s in p['scenarios']:
                    s['framing_errors']=0 if (p['d'],p['s'])==(4,-2) else 1
                    s['bit_errors']=10 if (p['d'],p['s'])==(4,-2) else 0
        self.assertEqual(summarize(w)['global_minimax_candidate_set'],[dict(d=4,s=-2)])

class HistoricalChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root=Path(os.environ.get('IMAGE64_EVIDENCE','__missing__'))
        if not cls.root.is_dir():raise unittest.SkipTest('Historical checks need --session; synthetic checks are not hardware')
        cls.record=load_record(cls.root,4)
    def test_15_warm_prefix_does_not_modify_original_record(self):
        before=copy.deepcopy(self.record);r=warm_analyze(self.record)
        self.assertEqual(self.record,before);self.assertTrue(r['warmup']['prefix_before_first_scheduled_fault'])
        self.assertFalse(r['warmup']['prefix_in_scoring'])
    def test_16_target_reference_value_never_filters_phase(self):
        before=warm_analyze(self.record);changed=copy.deepcopy(self.record)
        target=changed['context']['arm']['profile']['first_byte'];source=bytearray(changed['source']);source[target]^=255;changed['source']=bytes(source)
        after=warm_analyze(changed)
        self.assertEqual(before['matching_NCO_accumulators'],after['matching_NCO_accumulators'])
        self.assertEqual(before['warmup']['prefix_sha256'],after['warmup']['prefix_sha256'])
    def test_17_actual_local_error_inside_current_profile_envelope(self):
        r,b=evaluate_window(self.record);p=next(x for x in r['profiles'] if (x['d'],x['s'])==(3,-1))
        self.assertLessEqual(p['bit_errors_min'],r['actual_local_bit_errors']);self.assertGreaterEqual(p['bit_errors_max'],r['actual_local_bit_errors'])
    def test_18_all64_per_item_extrema_match_global_totals(self):
        output=Path(os.environ.get('IMAGE64_OUTPUT','__missing__'))
        if not (output/'summary.json').exists():self.skipTest('Need saved full analysis')
        s=json.loads((output/'summary.json').read_bytes())
        w=[json.loads(p.read_bytes()) for p in sorted(output.glob('items/item_*/envelope.json'))]
        again=summarize(w)
        self.assertEqual(s['profiles'],again['profiles']);self.assertEqual(s['global_minimax_candidate_set'],again['global_minimax_candidate_set'])
        current=next(p for p in s['profiles'] if (p['d'],p['s'])==(3,-1))
        measured=sum(p['actual_local_bit_errors'] for p in w)
        self.assertLessEqual(current['bit_errors_lower_bound'],measured);self.assertGreaterEqual(current['bit_errors_upper_bound'],measured)

if __name__=='__main__':unittest.main(verbosity=2)
