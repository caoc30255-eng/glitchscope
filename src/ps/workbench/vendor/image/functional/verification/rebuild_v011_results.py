import sys,json,time,shutil
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from images import Assembler,repair,config_decode,png
from labutil import read,write,sha
from scans import default_plan,aggregate
from render import svg_heatmap,csv_heatmap

preview=ROOT.parent/'functional_v011_preview_2026-10-19';assert not preview.exists()
shutil.copytree(ROOT/'results',preview,ignore=shutil.ignore_patterns('lab_state.sqlite','service.lock'))
out=preview/'image_repair';config=config_decode((out/'received_config.bin').read_bytes());lanes={}
for name in ('A','B','STM'):
    a=Assembler(config,name)
    for entry in reversed(read(out/(name+'_blocks.json'))['blocks']):a.add(entry['packet'],entry['reference'])
    a.stop();lanes[name]=a
report={}
for method in ('crc_select','crc_burst_B','crc_burst_multi','visual_median_B'):
    start=time.perf_counter()
    with patch('builtins.open',side_effect=AssertionError('No IO in repair')),patch('pathlib.Path.open',side_effect=AssertionError('No IO in repair')):
        value=repair(config,lanes,method)
    elapsed=time.perf_counter()-start
    directory=out/method
    for key in ('data','missing','modified','uncertain'):
        assert value[key]==(directory/(key+'.bin')).read_bytes(),method+': old successful full-image output changed'
    for key in ('original_B_missing','estimated'):
        (directory/(key+'.bin')).write_bytes(value[key]);png(directory/(key+'.png'),value[key],config['width'],config['height'])
    value['metadata']['actual_compute_seconds_current_host']=elapsed;write(directory/'algorithm.json',value['metadata'])
    report[method]={'original_four_outputs_unchanged':True,'output_sha256':sha(value['data']),'repair_file_IO_disabled':True}
records=read(preview/'real_records.json')
for d in (3,4):
    result=aggregate(default_plan(d),records);write(preview/('real_heatmap_d%d.json'%d),result)
    scans=preview/'scans';(scans/('real_d%d.csv'%d)).write_bytes(csv_heatmap(result))
    for target in ('B_frame_correct','STM_business_success'):(scans/('real_d%d_%s.svg'%(d,target))).write_bytes(svg_heatmap(result,target))
(ROOT/'verification/v011_existing_results_preserved.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
# Build step copies generated artifacts into the candidate bundle; product output guards remain unchanged.
shutil.copytree(preview,ROOT/'results',dirs_exist_ok=True)
print('Recomputed completion flags; original image outputs unchanged; new preview workspace ready')
