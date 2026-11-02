"""Approved v0.6 public-source review bridge. No private catalogue injection."""
import json,os,subprocess,sys,zipfile,time
from pathlib import Path
from labutil import *
from images import *
from scans import default_plan,aggregate

BASELINE_SHA='89c72cd1b8bbb8b84f61584c5b13fea762db5fa97b6154870870fd350aeffa17'

def prepare(baseline,baseline_zip,workspace,temp_root):
    baseline=Path(baseline).resolve();workspace=output_path(workspace);temp_root=output_path(temp_root)
    require(baseline not in workspace.parents and workspace!=baseline and not workspace.exists(),'NEW_SEPARATE_WORKSPACE')
    require(baseline not in temp_root.parents and baseline!=temp_root,'TEMP_NOT_IN_EVIDENCE')
    require(sha(Path(baseline_zip).read_bytes())==BASELINE_SHA,'APPROVED_V06_ZIP_REQUIRED')
    with zipfile.ZipFile(baseline_zip) as z:
        expected=z.read('return_shared_integration_v0_6_2026-10-18/sha256_manifest.json')
    require((baseline/'sha256_manifest.json').read_bytes()==expected,'BASELINE_MANIFEST_CHANGED')
    manifest=json.loads(expected)['files']
    for name,p in manifest.items():
        raw=(baseline/name).read_bytes();require((len(raw),sha(raw))==(p['bytes'],p['sha256']),'BASELINE_FILE_CHANGED: '+name)
    workspace.mkdir(parents=True);env=dict(os.environ);env['SHARED_OFFLINE_TEMP_ROOT']=str(temp_root);env.pop('PYTHONPATH',None);env.pop('PYTHONOPTIMIZE',None)
    code="""import sys,json
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from sources import SourceRegistry
from core import write_rows
b=Path(sys.argv[1]);o=Path(sys.argv[2]);r=SourceRegistry()
r.register('old',b/'input_handoff');r.register('new',b/'input_session25')
a=r.review('old',o/'old_source_review');c=r.review('new',o/'session25_source_review')
write_rows(o/'audited_rows.jsonl',a.records+c.records)
"""
    p=subprocess.run([sys.executable,'-B','-c',code,str(baseline),str(workspace)],env=env,capture_output=True)
    (workspace/'source_review_stdout.log').write_bytes(p.stdout);(workspace/'source_review_stderr.log').write_bytes(p.stderr)
    require(p.returncode==0,'PUBLIC_SOURCE_REVIEW_FAILED; see saved log')
    rows=[json.loads(s) for s in (workspace/'audited_rows.jsonl').read_bytes().splitlines()];require(len(rows)==77,'AUDITED_ROWS')
    records=[]
    for r in rows:
        records.append(dict(uid=r['uid'],kind=r['kind'],origin='AUDITED_MEASUREMENT',status=r['record_status'],
            session=r['key']['session'],identity_hex=r['key']['identity_hex'],condition=r['condition'],labels={
                'B_frame_correct':r['labels']['B_frame_correct'],'STM_payload_correct':r['labels']['STM_payload_correct'],
                'STM_business_success':r['labels']['STM_business_success']},reference=r['raw_result_ref'],
            evidence_references=r['evidence_references'],actual_parameter_basis=r['original']['actual_receiver_B']))
    legacy=[json.loads(s) for s in (baseline/'verification/final_replay/feedback_all.jsonl').read_bytes().splitlines()]
    for r in legacy:
        if r.get('record_status')=='UNKNOWN':
            records.append(dict(uid=r['uid'],kind=r['kind'],origin='AUDITED_MEASUREMENT',status='UNKNOWN',session=r['key']['session'],
                identity_hex=r['key']['identity_hex'],condition=None,labels={t:None for t in ('B_frame_correct','STM_payload_correct','STM_business_success')},
                reference=r.get('raw_result_ref'),evidence_references=r['evidence_references'],unlocated_reason='No approved scan-coordinate binding; known occupied attempt remains UNKNOWN'))
    write(workspace/'real_records.json',records)
    for d in (3,4):write(workspace/('real_heatmap_d%d.json'%d),aggregate(default_plan(d),records))
    image_output=workspace/'image_repair';image_output.mkdir()
    def blob(relative):
        proof=manifest[relative];raw=(baseline/relative).read_bytes()
        require((len(raw),sha(raw))==(proof['bytes'],proof['sha256']),'RAW_EVIDENCE_CHANGED');return raw
    prefix='input_handoff/evidence/sessions/session_00000024/'
    config_raw=blob(prefix+'CH0/epoch_10000024_record_00000001/b_raw.bin');config=config_decode(config_raw)
    (image_output/'received_config.bin').write_bytes(config_raw)
    assemblers={lane:Assembler(config,lane) for lane in ('A','B','STM')};provenance=[]
    # Decode actual saved packet/sample files. No IMAGE_VIEW PNG or source pixels used here.
    for rid in range(2,66):
        suffix='epoch_10000024_record_%08x'%rid;zero=prefix+'CH0/'+suffix;one=prefix+'CH1/main/'+suffix
        metadata=json.loads(blob(zero+'/descriptor.json'));binding=metadata['binding'];identity=hex_identity(binding['identity'])
        result=json.loads(blob(prefix+'EXECUTOR/record_%08x/result/result.json'%rid))
        require(identity==result['identity_hex'] and binding['record_id']==rid and binding['epoch']==config['run_id'],'ARCHIVE_BINDING')
        for lane in ('A','B'):
            name=zero+'/'+lane.lower()+'_raw.bin';raw=blob(name);sample=blob(zero+'/'+lane.lower()+'_samples.bin')
            require(decode_samples(sample,binding['start'],binding['deadline'])==raw,'CH0_RAW_SAMPLE_MISMATCH')
            packet=decode_packet(raw,lane,identity,config,metadata['status']==3 and not metadata['first_fault'] and metadata[lane.lower()+'_errors']==0)
            archive=image_output/'raw_packets'/lane;archive.mkdir(parents=True,exist_ok=True);(archive/('%08x.bin'%rid)).write_bytes(raw)
            assemblers[lane].add(packet,dict(path=name,sha256=sha(raw),bytes=len(raw),record_id=rid,identity_hex=identity))
        descriptor=ch1_descriptor(blob(one+'/descriptor.bin'));raw=blob(one+'/raw_packet.bin')
        require(descriptor['identity']==int(identity,16) and descriptor['epoch']==binding['epoch'] and descriptor['record_id']==rid,'CH1_BINDING')
        require(decode_samples(blob(one+'/samples.bin'),descriptor['start'],descriptor['deadline'])==raw,'CH1_RAW_SAMPLE_MISMATCH')
        packet=decode_packet(raw,'STM',identity,config)
        archive=image_output/'raw_packets'/'STM';archive.mkdir(parents=True,exist_ok=True);(archive/('%08x.bin'%rid)).write_bytes(raw)
        assemblers['STM'].add(packet,dict(path=one+'/raw_packet.bin',sha256=sha(raw),bytes=len(raw),record_id=rid,identity_hex=identity))
        provenance.append(dict(record_id=rid,identity_hex=identity,index=rid-2,quality='VALID_CAPTURE',result_sha256=sha(blob(prefix+'EXECUTOR/record_%08x/result/result.json'%rid))))
    received={};masks={}
    for lane,a in assemblers.items():
        a.stop();raw,mask,trace=a.render();received[lane]=raw;masks[lane]=mask
        (image_output/(lane+'_received.bin')).write_bytes(raw);png(image_output/(lane+'_received.png'),raw,config['width'],config['height'])
        write(image_output/(lane+'_blocks.json'),trace)
    outputs={}
    for method in ('crc_select','crc_burst_B','crc_burst_multi','visual_median_B'):
        start=time.perf_counter();result=repair(config,assemblers,method);elapsed=time.perf_counter()-start
        d=image_output/method;d.mkdir()
        for field in ('data','missing','modified','uncertain','original_B_missing','estimated'):
            (d/(field+'.bin')).write_bytes(result[field]);png(d/(field+'.png'),result[field],config['width'],config['height'])
        result['metadata']['actual_compute_seconds_current_host']=elapsed;write(d/'algorithm.json',result['metadata']);outputs[method]=result
    # Only the independent evaluator below opens the source image.
    source=blob(prefix+'IMAGE_VIEW/source.bin');png(image_output/'evaluation_reference.png',source,config['width'],config['height'])
    metrics=dict(origin='OFFLINE_REAL_EVIDENCE_REPLAY',receiver_config_sha256=sha(config_raw),input_source_pixels_to_repair=False,
        baselines={lane:evaluate(source,received[lane],masks[lane]) for lane in received},methods={},provenance=provenance)
    for method,result in outputs.items():
        m=evaluate(source,result['data'],result['missing']);m['receiver_config_SHA_verified']=result['metadata']['whole_received_config_SHA_verified']
        m['improves_B_error_and_MAE']=m['error_pixels']<metrics['baselines']['B']['error_pixels'] and m['MAE']<metrics['baselines']['B']['MAE']
        m['improves_no_repair_CRC_selection']=m['error_pixels']<evaluate(source,outputs['crc_select']['data'],outputs['crc_select']['missing'])['error_pixels']
        metrics['methods'][method]=m
    write(image_output/'metrics.json',metrics);write(image_output/'config.json',config)
    require([metrics['baselines'][k]['error_pixels'] for k in ('A','B','STM')]==[4402,3174,4296],'RECEIVED_REASSEMBLY_DIFFERS_FROM_AUDITED_METRICS')
    write(workspace/'prepared.json',dict(status='PREPARED_WITH_PUBLIC_SOURCE_REVIEWS',baseline_root=str(baseline),baseline_zip_sha256=BASELINE_SHA,
        audited_rows=77,real_records_sha256=sha((workspace/'real_records.json').read_bytes()),image_packets=192,
        image_metrics_sha256=sha((image_output/'metrics.json').read_bytes()),hardware_access=False,new_physical_starts=0))
    return metrics
