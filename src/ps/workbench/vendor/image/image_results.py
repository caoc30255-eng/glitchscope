"""Reassemble actual UART originals, repair receiver data, then independently evaluate."""
import copy
import hashlib
import json
from pathlib import Path
import time


def build_results(executor,destination,capture_origin="NEW_LIVE_CAPTURE_PENDING_SOURCE_REVIEW"):
    # Imports resolve to packaged accepted modules; no source image enters repair.
    from images import Assembler,config_decode,decode_packet,decode_samples,ch1_descriptor,repair,png,evaluate
    session=executor.session;root=session.root;dest=Path(destination);dest.mkdir(exist_ok=False)
    sha=lambda raw:hashlib.sha256(raw).hexdigest()
    def checked(directory):
        directory=Path(directory).resolve();commit=json.loads((directory/'committed.json').read_bytes())
        for name,proof in commit['files'].items():
            p=(directory/name).resolve()
            if directory not in p.parents:raise ValueError('RAW_ARCHIVE_PATH')
            data=p.read_bytes();expected=proof if isinstance(proof,str) else proof['sha256']
            if sha(data)!=expected or isinstance(proof,dict) and len(data)!=proof['bytes']:raise ValueError('RAW_ARCHIVE_CHANGED')
        return commit
    epoch=session.local_epoch
    first=root/'CH0'/('epoch_%08x_record_00000001'%epoch)
    checked(first);metadata=json.loads((first/'descriptor.json').read_bytes());binding=metadata['binding']
    config_raw=(first/'b_raw.bin').read_bytes()
    if metadata['status']!=3 or metadata['first_fault'] or metadata['b_errors'] or binding['record_id']!=1 or binding['epoch']!=epoch:
        raise ValueError('RECEIVED_CONFIG_CAPTURE')
    if decode_samples((first/'b_samples.bin').read_bytes(),binding['start'],binding['deadline'])!=config_raw:
        raise ValueError('RECEIVED_CONFIG_SAMPLE_MISMATCH')
    if config_raw!=executor._frozen_config:raise ValueError('RECEIVED_CONFIG_DOES_NOT_MATCH_SENT')
    config=config_decode(config_raw)
    if config['run_id']!=epoch or config['total_bytes']!=16384:raise ValueError('RECEIVED_IMAGE_NAMESPACE')
    (dest/'received_config.bin').write_bytes(config_raw)
    lanes={name:Assembler(config,name) for name in ('A','B','STM')};provenance=[]
    for rid in range(2,executor.index+1):
        folder=executor.root/('record_%08x/result'%rid);checked(folder)
        result=json.loads((folder/'result.json').read_bytes())
        if result!=executor.results[rid-1]:raise ValueError('RESULT_IN_MEMORY_CHANGED')
        if not all(result['retirement'][k] for k in ('CH0_release_verified','CH1_retirement_verified','peer_retirement_verified')):
            raise ValueError('RESULT_NOT_RETIRED')
        suffix='epoch_%08x_record_%08x'%(epoch,rid)
        zero=root/'CH0'/suffix;one=root/'CH1/main'/suffix;checked(zero);checked(one)
        meta=json.loads((zero/'descriptor.json').read_bytes());b=meta['binding'];identity=result['identity_hex']
        if b['identity']!=int(identity,16) or b['record_id']!=rid or b['epoch']!=epoch:raise ValueError('CH0_RESULT_BINDING')
        for lane in ('A','B','STM'):
            try:
                if lane in ('A','B'):
                    letter=lane.lower();path=zero/(letter+'_raw.bin');raw=path.read_bytes()
                    if meta['status']!=3 or meta['first_fault'] or meta[letter+'_errors']:raise ValueError('CH0_CAPTURE_ERROR')
                    if decode_samples((zero/(letter+'_samples.bin')).read_bytes(),b['start'],b['deadline'])!=raw:raise ValueError('CH0_SAMPLE_MISMATCH')
                else:
                    d=ch1_descriptor((one/'descriptor.bin').read_bytes());path=one/'raw_packet.bin';raw=path.read_bytes()
                    if d['identity']!=int(identity,16) or d['record_id']!=rid or d['epoch']!=epoch:raise ValueError('CH1_BINDING')
                    if decode_samples((one/'samples.bin').read_bytes(),d['start'],d['deadline'])!=raw:raise ValueError('CH1_SAMPLE_MISMATCH')
                packet=decode_packet(raw,lane,identity,config)
                if packet['item_index']!=rid-2:raise ValueError('UNEXPECTED_IMAGE_BLOCK_INDEX')
                ref=dict(path=path.relative_to(root).as_posix(),bytes=len(raw),sha256=sha(raw),record_id=rid)
                lanes[lane].add(packet,ref);provenance.append(dict(lane=lane,item_index=rid-2,reference=ref))
            except ValueError as exc:
                lanes[lane].mark_unknown(rid-2,str(exc))
    received={};masks={}
    for lane,assembler in lanes.items():
        assembler.stop();raw,missing,trace=assembler.render();received[lane]=raw;masks[lane]=missing
        (dest/(lane+'_received.bin')).write_bytes(raw);(dest/(lane+'_missing.bin')).write_bytes(missing)
        png(dest/(lane+'_received.png'),raw,128,128);png(dest/(lane+'_missing.png'),missing,128,128)
        (dest/(lane+'_blocks.json')).write_text(json.dumps(trace,ensure_ascii=False,indent=2),encoding='utf-8')
    outputs={}
    for method in ('crc_select','crc_burst_B','crc_burst_multi','visual_median_B'):
        started=time.perf_counter();value=repair(config,lanes,method);elapsed=time.perf_counter()-started
        out=dest/method;out.mkdir()
        for field in ('data','missing','modified','uncertain','original_B_missing','estimated'):
            (out/(field+'.bin')).write_bytes(value[field]);png(out/(field+'.png'),value[field],128,128)
        value['metadata']['capture_origin']=capture_origin
        (out/'algorithm.json').write_text(json.dumps(value['metadata'],indent=2),encoding='utf-8')
        outputs[method]=(value,elapsed)
    # Only after every repair finishes, source bytes enter this independent evaluator.
    source=bytes(executor._frozen_source)
    if sha(source)!=config['image_sha256']:raise ValueError('EVALUATION_REFERENCE_BINDING')
    png(dest/'evaluation_reference.png',source,128,128)
    report=dict(schema='UPLOADED_IMAGE_RX_REPAIR_V0_2',session=root.name,source_sha256=sha(source),
                completed_records=executor.index,total_records=65,all_records_strictly_completed=executor.index==65,
                complete_image_capture=executor.index==65 and not any(any(mask) for mask in masks.values()),
                missing_pixels={lane:sum(bool(v) for v in mask) for lane,mask in masks.items()},
                repair_input_source_pixels=False,repair_input_fault_schedule=False,
                origin=capture_origin,provenance=provenance,
                baselines={lane:evaluate(source,received[lane],masks[lane]) for lane in lanes},methods={})
    for method,(value,elapsed) in outputs.items():
        report['methods'][method]=dict(evaluate(source,value['data'],value['missing']),
            receiver_config_SHA_verified=value['metadata']['whole_received_config_SHA_verified'],
            compute_seconds=elapsed,output_sha256=sha(value['data']))
    (dest/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report
