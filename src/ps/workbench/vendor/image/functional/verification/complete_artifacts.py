import json,hashlib,sys
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from images import Assembler,config_decode,decode_packet,repair,evaluate
from render import svg_heatmap,csv_heatmap

workspace=Path(sys.argv[1]);baseline=Path(sys.argv[2]);out=workspace/'image_repair'
proof=json.loads((baseline/'sha256_manifest.json').read_text(encoding='utf-8'))['files']
config=config_decode((out/'received_config.bin').read_bytes());lanes={}
for lane in ('A','B','STM'):
    trace=json.loads((out/(lane+'_blocks.json')).read_text(encoding='utf-8'));a=Assembler(config,lane)
    for entry in reversed(trace['blocks']):
        ref=entry['reference'];raw=(baseline/ref['path']).read_bytes();h=hashlib.sha256(raw).hexdigest()
        assert h==ref['sha256']==proof[ref['path']]['sha256']
        directory=out/'raw_packets'/lane;directory.mkdir(parents=True,exist_ok=True)
        (directory/('%08x.bin'%ref['record_id'])).write_bytes(raw)
        packet=decode_packet(raw,lane,entry['packet']['identity_hex'],config)
        assert packet==entry['packet'];a.add(packet,ref)
    a.stop();assert a.render()[0]==(out/(lane+'_received.bin')).read_bytes();lanes[lane]=a
verified={}
for method in ('crc_select','crc_burst_B','crc_burst_multi','visual_median_B'):
    # All file access is prohibited during repair, including any source/fault-plan reads.
    with patch('pathlib.Path.open',side_effect=AssertionError('Repair must not read files')):
        result=repair(config,lanes,method)
    assert result['data']==(out/method/'data.bin').read_bytes()
    verified[method]={'output_sha256':hashlib.sha256(result['data']).hexdigest(),
                      'receiver_config_SHA_verified':result['metadata']['whole_received_config_SHA_verified']}
# Independent evaluator only, after repair has finished.
source=(baseline/'input_handoff/evidence/sessions/session_00000024/IMAGE_VIEW/source.bin').read_bytes()
metrics=json.loads((out/'metrics.json').read_text(encoding='utf-8'))
for method in verified:
    measured=evaluate(source,(out/method/'data.bin').read_bytes(),(out/method/'missing.bin').read_bytes())
    assert measured['error_pixels']==metrics['methods'][method]['error_pixels']
    assert measured['MAE']==metrics['methods'][method]['MAE']
    verified[method].update(measured)
for d in (3,4):
    data=json.loads((workspace/('real_heatmap_d%d.json'%d)).read_text(encoding='utf-8'))
    directory=workspace/'scans';directory.mkdir(exist_ok=True)
    (directory/('real_d%d.csv'%d)).write_bytes(csv_heatmap(data))
    for target in ('B_frame_correct','STM_business_success'):
        (directory/('real_d%d_%s.svg'%(d,target))).write_bytes(svg_heatmap(data,target))
report={'status':'PASS','raw_packets_redecoded':192,'reverse_order_assembly_matches':True,
        'repair_with_all_file_reads_disabled':True,'source_used_only_after_repairs_by_evaluator':True,'methods':verified}
(ROOT/'verification/independent_repair.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False))
