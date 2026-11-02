"""Independent behavioral probes. No product source modifications or hardware IO."""
from pathlib import Path
import argparse,json,sys

R=Path(__file__).resolve().parent
parser=argparse.ArgumentParser()
parser.add_argument('--package',type=Path,default=R/'work')
parser.add_argument('--output',type=Path,default=R/'reviewer_adversarial_results.json')
args=parser.parse_args()
P=args.package.resolve()
sys.path.insert(0,str(P))
from scans import make_plan,validate,aggregate,propose
from images import Assembler,repair,evaluate
load=lambda p:json.loads(p.read_bytes())
results={}

plan=make_plan(bytes(range(256)),[15],[20],d=4,s=-1,repeats=3,budget=5)
actual=load(P/'results/real_records.json')
grid=aggregate(plan,actual)
stats=grid['cells'][0]['targets']['B_frame_correct']
assert stats['valid']==1 and grid['real_hardware_complete'] is True
results['premature_real_grid_completion']=dict(reproduced=True,planned_repetitions=3,
    valid_audited_measurements=stats['valid'],reported_real_hardware_complete=grid['real_hardware_complete'],
    data_source='Supplied audited real_records.json; d4 p15 w20 has one real observation')

bad_profile=make_plan(bytes(range(256)),[15],[20],d=0,s=127,repeats=1,budget=3)
assert validate(bad_profile)
results['unsupported_current_receiver_profile']=dict(reproduced=True,d=0,s=127,
    plan_validation_passed=True,current_hardware_rule='d in 1..4 and -2 <= s <= 3-d')

history=[dict(request_index=i,plan_sha256=plan['plan_sha256'],identity_hex=1,status='VALID',
              result_sha256='a'*64,origin='AUDITED_MEASUREMENT') for i in (0,1)]
proposal=propose(plan,history)
assert proposal['action']=='CONTINUE_PREDECLARED'
results['duplicate_integer_identity_accepted']=dict(reproduced=True,identical_identity=1,
    history_records=2,action=proposal['action'],next_request=proposal['request'])

unknown=dict(request_index=0,plan_sha256=plan['plan_sha256'],identity_hex='1'*64,status='UNKNOWN',
             diagnostic_sha256='a'*64,origin='AUDITED_MEASUREMENT')
try:propose(plan,[unknown])
except KeyError as exc:results['unknown_without_result_file']=dict(reproduced=True,error=repr(exc))
else:raise AssertionError('Expected current diagnostic-only UNKNOWN handling to fail')

config=load(P/'results/image_repair/config.json')
trace=load(P/'results/image_repair/a_blocks.json')
entry=next(e for e in trace['blocks'] if not e['packet']['payload_crc_ok'])
index=entry['packet']['item_index'];B=Assembler(config,'B');A=Assembler(config,'A')
for other in load(P/'results/image_repair/b_blocks.json')['blocks']:
    if other['packet']['item_index']!=index:B.add(other['packet'],other['reference'])
B.mark_unknown(index,'B observation missing in independent test')
A.add(entry['packet'],entry['reference'])
before_data,before_missing,_=B.render()
repaired=repair(config,dict(A=A,B=B),method='crc_select')
offset=index*config['chunk_size'];end=offset+len(bytes.fromhex(entry['packet']['payload_hex']))
note=next(n for n in repaired['metadata']['blocks'] if n['item_index']==index)
assert all(before_missing[offset:end]) and not any(repaired['missing'][offset:end])
assert repaired['data'][offset:end]==bytes(end-offset)
assert bytes.fromhex(entry['packet']['payload_hex'])!=bytes(end-offset)
assert note['selection']=='B_UNREPAIRED' and note['candidate_count']==0
results['missing_block_cleared_without_data']=dict(reproduced=True,item_index=index,
    actual_A_raw_packet_sha256=entry['packet']['raw_sha256'],B_blocks_received=len(B.blocks),A_payload_crc_ok=False,
    original_missing_pixels=sum(bool(v) for v in before_missing),
    reported_missing_pixels=sum(bool(v) for v in repaired['missing']),
    falsely_known_zero_pixels=end-offset,repair_note=note,
    explanation='No B block and no CRC-valid A block; crc_select emits B placeholders but clears their missing mask')

args.output.write_bytes((json.dumps(results,indent=2)+'\n').encode('utf-8'))
print(json.dumps(results,indent=2))
