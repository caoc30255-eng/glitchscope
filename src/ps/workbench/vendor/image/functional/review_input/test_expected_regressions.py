"""Desired behavior regression tests, currently red on Functional Delivery v0.1."""
import argparse,json,sys,unittest
from pathlib import Path

parser=argparse.ArgumentParser()
parser.add_argument('--package',type=Path,required=True)
args,remaining=parser.parse_known_args()
P=args.package.resolve();sys.path.insert(0,str(P))
from scans import make_plan,aggregate,propose
from images import Assembler,repair
js=lambda p:json.loads(p.read_bytes())

class ExpectedBehavior(unittest.TestCase):
    def test_unavailable_B_and_bad_A_must_not_become_known_zero_block(self):
        config=js(P/'results/image_repair/config.json')
        entry=next(e for e in js(P/'results/image_repair/a_blocks.json')['blocks'] if not e['packet']['payload_crc_ok'])
        index=entry['packet']['item_index'];B=Assembler(config,'B');A=Assembler(config,'A')
        for e in js(P/'results/image_repair/b_blocks.json')['blocks']:
            if e['packet']['item_index']!=index:B.add(e['packet'],e['reference'])
        B.mark_unknown(index,'Missing B block');A.add(entry['packet'],entry['reference'])
        value=repair(config,dict(A=A,B=B),'crc_select')
        start=index*config['chunk_size'];end=start+len(bytes.fromhex(entry['packet']['payload_hex']))
        remains_missing=all(value['missing'][start:end])
        selected_actual_A=value['data'][start:end]==bytes.fromhex(entry['packet']['payload_hex'])
        self.assertTrue(remains_missing or selected_actual_A,
            'A missing B block must remain missing or retain actual alternate observed data; zero placeholders are not received pixels')
    def test_one_audited_measurement_is_not_three_repetitions_complete(self):
        plan=make_plan(bytes(range(256)),[15],[20],d=4,s=-1,repeats=3,budget=5)
        result=aggregate(plan,js(P/'results/real_records.json'))
        self.assertEqual(result['cells'][0]['targets']['B_frame_correct']['valid'],1)
        self.assertFalse(result['real_hardware_complete'])
    def test_duplicate_identity_cannot_advance_schedule(self):
        plan=make_plan(bytes(range(256)),[15],[20],repeats=1,budget=3)
        history=[dict(request_index=i,plan_sha256=plan['plan_sha256'],identity_hex=1,
            status='VALID',result_sha256='a'*64,origin='AUDITED_MEASUREMENT') for i in (0,1)]
        with self.assertRaises(ValueError):propose(plan,history)
    def test_diagnostic_only_unknown_returns_structured_stop(self):
        plan=make_plan(bytes(range(256)),[15],[20],repeats=1,budget=3)
        h=dict(request_index=0,plan_sha256=plan['plan_sha256'],identity_hex='1'*64,
            status='UNKNOWN',diagnostic_sha256='a'*64,origin='AUDITED_MEASUREMENT')
        result=propose(plan,[h])
        self.assertEqual(result['action'],'STOP');self.assertEqual(result['reason'],'UNKNOWN_BLOCKED')
        self.assertIsNone(result['after_result_sha256'])
    def test_current_receiver_illegal_profile_rejected(self):
        with self.assertRaises(ValueError):
            make_plan(bytes(range(256)),[15],[20],d=0,s=127,repeats=1,budget=3)

if __name__=='__main__':unittest.main(argv=[sys.argv[0]]+remaining)
