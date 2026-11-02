import copy,json,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from images import Assembler,repair,crc
from scans import make_plan,aggregate,propose,TARGETS

ROOT=Path(__file__).resolve().parents[1]
def js(p):return json.loads(p.read_bytes())
class ReviewFixes(unittest.TestCase):
    def setUp(self):
        self.config=js(ROOT/'results/image_repair/config.json')
        self.bad=next(e for e in js(ROOT/'results/image_repair/a_blocks.json')['blocks'] if not e['packet']['payload_crc_ok'])
        self.index=self.bad['packet']['item_index'];self.start=self.index*self.config['chunk_size'];self.end=self.start+self.config['chunk_size']
    def lanes(self):
        B=Assembler(self.config,'B');A=Assembler(self.config,'A')
        for e in js(ROOT/'results/image_repair/b_blocks.json')['blocks']:
            if e['packet']['item_index']!=self.index:B.add(e['packet'],e['reference'])
        B.mark_unknown(self.index,'capture missing');A.add(self.bad['packet'],self.bad['reference']);return dict(B=B,A=A)
    def test_missing_bad_alternate_and_empty_candidates(self):
        for method in ('crc_select','crc_burst_multi'):
            with patch('images.burst_candidates',return_value=[]):value=repair(self.config,self.lanes(),method)
            self.assertTrue(all(value['missing'][self.start:self.end]));self.assertTrue(all(value['original_B_missing'][self.start:self.end]))
            self.assertEqual(value['metadata']['blocks'][self.index]['selection'],'MISSING_NO_ACCEPTED_SOURCE')
            self.assertFalse(any(value['estimated'][self.start:self.end]))
    def test_every_lane_missing(self):
        for method in ('crc_select','crc_burst_B','crc_burst_multi','visual_median_B'):
            value=repair(self.config,{'B':Assembler(self.config,'B')},method)
            self.assertTrue(all(value['missing']));self.assertFalse(value['metadata']['whole_received_config_SHA_verified'])
    def test_good_alternate_has_separate_original_missing(self):
        config=copy.deepcopy(self.config);lanes=self.lanes();packet=copy.deepcopy(self.bad['packet'])
        config['item_crcs'][self.index]=crc(bytes.fromhex(packet['payload_hex']))
        value=repair(config,lanes,'crc_select')
        self.assertFalse(any(value['missing'][self.start:self.end]));self.assertTrue(all(value['original_B_missing'][self.start:self.end]))
        self.assertEqual(value['data'][self.start:self.end],bytes.fromhex(packet['payload_hex']))
    def test_generated_estimate_preserves_original_missing(self):
        value=repair(self.config,self.lanes(),'crc_burst_multi')
        self.assertTrue(all(value['missing'][self.start:self.end]));self.assertTrue(all(value['estimated'][self.start:self.end]))
        self.assertTrue(all(value['original_B_missing'][self.start:self.end]))
    def records(self,n,unknown=False):
        p=make_plan(bytes(range(256)),[15],[20],d=4,repeats=3,budget=5)
        r=next(r for r in js(ROOT/'results/real_records.json') if r.get('kind')=='ITEM' and r.get('condition',{}) and r['condition'].get('d')==4)
        rows=[]
        for i in range(n):
            a=copy.deepcopy(r);a.update(uid='test-'+str(i),identity_hex=('%064x'%(i+1)));rows.append(a)
        if unknown:rows[-1].update(status='UNKNOWN',labels={t:None for t in TARGETS})
        return p,rows
    def test_repetition_insufficient_exact_and_excess(self):
        for n,complete in ((0,False),(1,False),(2,False),(3,True),(4,False)):
            p,rows=self.records(n);result=aggregate(p,rows)
            self.assertEqual(result['real_hardware_complete'],complete)
            self.assertEqual(result['execution_coverage_complete'],complete)
            self.assertEqual(result['valid_measurements_sufficient'],complete)
        p,rows=self.records(3);result=aggregate(p,rows+[rows[0]])
        self.assertTrue(result['real_hardware_complete']);self.assertEqual(len(result['cells'][0]['measurements']),3)
    def test_unknown_occupies_but_does_not_fill_valid_repeats(self):
        p,rows=self.records(3,True);result=aggregate(p,rows)
        self.assertTrue(result['execution_coverage_complete']);self.assertFalse(result['valid_measurements_sufficient']);self.assertFalse(result['real_hardware_complete'])
    def test_different_UID_cannot_duplicate_identity(self):
        p,rows=self.records(3);rows[1]['identity_hex']=rows[0]['identity_hex']
        with self.assertRaises(ValueError):aggregate(p,rows)
    def history(self):
        p=make_plan(bytes(range(256)),[15],[20],repeats=1,budget=3)
        return p,dict(request_index=0,plan_sha256=p['plan_sha256'],identity_hex='1'*64,status='VALID',result_sha256='a'*64,origin='AUDITED_MEASUREMENT')
    def test_identity_forms_digests_and_status_strict(self):
        for identity in (1,'1','A'*64,'g'*64):
            p,h=self.history();h['identity_hex']=identity
            with self.assertRaises(ValueError):propose(p,[h])
        p,h=self.history();second=dict(h,request_index=1)
        with self.assertRaises(ValueError):propose(p,[h,second])
        second['identity_hex']=1
        with self.assertRaises(ValueError):propose(p,[h,second])
        for field,value in (('result_sha256','z'*64),('status','DONE')):
            p,h=self.history();h[field]=value
            with self.assertRaises(ValueError):propose(p,[h])
    def test_unknown_null_or_missing_result_and_no_followup(self):
        for supplied in (False,True):
            p,h=self.history();h.update(status='UNKNOWN',diagnostic_sha256='b'*64,diagnostic_reference='diagnostic.json');h.pop('result_sha256')
            if supplied:h['result_sha256']=None
            value=propose(p,[h]);self.assertEqual(value['reason'],'UNKNOWN_BLOCKED');self.assertIsNone(value['after_result_sha256']);self.assertEqual(value['after_diagnostic_sha256'],'b'*64)
            self.assertEqual(value['after_diagnostic_reference'],'diagnostic.json')
            second=dict(h,request_index=1,identity_hex='2'*64)
            with self.assertRaises(ValueError):propose(p,[h,second])
    def test_current_profile_all_boundaries(self):
        for d in range(1,5):
            for s in range(-2,4-d):make_plan(bytes(range(256)),[15],[20],d=d,s=s,repeats=1,budget=3)
            for s in (-3,4-d,127):
                with self.assertRaises(ValueError):make_plan(bytes(range(256)),[15],[20],d=d,s=s,repeats=1,budget=3)
        for d in (0,5,255,True):
            with self.assertRaises(ValueError):make_plan(bytes(range(256)),[15],[20],d=d,repeats=1,budget=3)

if __name__=='__main__':unittest.main()
