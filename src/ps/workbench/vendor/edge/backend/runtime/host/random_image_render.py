"""Render only bytes from saved receiver originals; no simulated corruption."""
from pathlib import Path
import json,struct,zlib
from ch1_completion_ledger import _codec
from ch1_peer_archive_driver import persist_exact
from ch0_archive_driver import CH0ArchiveDriver
import ch1_evidence_store as store

def png_gray(raw,width=128,height=128):
    raw=bytes(raw)
    if len(raw)!=width*height:raise ValueError('Complete grayscale pixel array required')
    def chunk(kind,payload):
        return struct.pack('>I',len(payload))+kind+payload+struct.pack('>I',zlib.crc32(kind+payload)&0xffffffff)
    scan=b''.join(b'\0'+raw[i:i+width] for i in range(0,len(raw),width))
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,0,0,0,0))+chunk(b'IDAT',zlib.compress(scan))+chunk(b'IEND',b'')

def metrics(source,received,planned_mask=None):
    source=bytes(source);received=bytes(received)
    if len(source)!=16384 or len(received)!=len(source):raise ValueError('Complete128x128 image required')
    changed=[i for i,(a,b) in enumerate(zip(source,received)) if a!=b]
    absolute=[abs(a-b) for a,b in zip(source,received)]
    return {'pixels':len(source),'changed_pixels':len(changed),'pixel_error_rate':len(changed)/len(source),
        'bit_errors':sum(bin(a^b).count('1') for a,b in zip(source,received)),
        'mean_absolute_gray_error':sum(absolute)/len(source),'maximum_absolute_gray_error':max(absolute),
        'received_sha256':store.sha(received),'source_sha256':store.sha(source),
        'changed_outside_planned_target_pixels':None if planned_mask is None else sum(not planned_mask[i] for i in changed)}

def _check(directory):
    directory=Path(directory)
    m=json.loads((directory/'committed.json').read_bytes())
    for name,proof in m['files'].items():
        p=(directory/name).resolve()
        if directory.resolve() not in p.parents:raise ValueError('Archive path escape')
        raw=p.read_bytes();digest=proof if isinstance(proof,str) else proof['sha256']
        if store.sha(raw)!=digest or (isinstance(proof,dict) and len(raw)!=proof['bytes']):
            raise ValueError('Saved receiver original changed')
    return m

def archive_images(executor):
    if executor.index!=65 or executor.attempts!=65 or len(executor.results)!=65 or executor.stopped:
        raise RuntimeError('All65 exact records required; incomplete images cannot be fabricated')
    executor._verify_plan();session=executor.session;source=executor._frozen_source
    schedule=json.loads(executor._schedule);received={name:bytearray() for name in ('A','B','STM')}
    references=[];mask=bytearray(16384)
    for index,entry in enumerate(schedule['items']):
        rid=index+2;suffix='epoch_%08x_record_%08x'%(session.local_epoch,rid)
        result_dir=executor.root/('record_%08x'%rid)/'result';_check(result_dir)
        result=json.loads((result_dir/'result.json').read_bytes())
        if result!=executor.results[rid-1]:raise ValueError('In-memory result differs from exact saved result')
        zero=session.root/'CH0'/suffix;one=session.root/'CH1/main'/suffix
        _check(zero);_check(one)
        request=(zero/'expected_request.bin').read_bytes();item=_codec().decode_item(request)
        if (not item['valid'] or item['item_index']!=index or item['item_total']!=64 or
                item['payload']!=executor.parts[index]):raise ValueError('CH0 original request differs from image plan')
        metadata=json.loads((zero/'descriptor.json').read_bytes());binding=metadata['binding']
        identity=int(result['identity_hex'],16)
        if (binding['identity']!=identity or binding['record_id']!=rid or binding['epoch']!=session.local_epoch or
                metadata['status']!=3 or metadata['first_fault']):raise ValueError('CH0 metadata not exact complete capture')
        for name,lane in (('A','a'),('B','b')):
            samples=CH0ArchiveDriver._decode((zero/(lane+'_samples.bin')).read_bytes(),binding)
            raw=bytes(s['data'] for s in samples)
            if (raw!=(zero/(lane+'_raw.bin')).read_bytes() or len(raw)!=278 or
                    raw[:20]!=request[:20] or raw[-2:]!=request[-2:] or
                    metadata[lane+'_errors'] or any(s['flags'] for s in samples)):
                raise ValueError('Incomplete UART capture/header/CRC-region disturbance; retain originals')
            correct=raw==request
            if result['receiver_'+name+'_frame_correct']!=correct:raise ValueError('A/B result classification changed')
            received[name].extend(raw[20:-2])
        descriptor=store.descriptor_decode((one/'descriptor.bin').read_bytes())
        samples=store.samples_decode((one/'samples.bin').read_bytes(),descriptor)
        raw=bytes(s['data'] for s in samples)
        if (raw!=(one/'raw_packet.bin').read_bytes() or descriptor['identity']!=identity or
                descriptor['record_id']!=rid or descriptor['epoch']!=session.local_epoch):
            raise ValueError('STM report original identity differs')
        classification=store.classify(raw,descriptor,samples,item['payload'])
        if classification!=json.loads((one/'classification.json').read_bytes()):raise ValueError('CH1 classification changed')
        if not all(classification[k] for k in ('capture_valid','wire_identity_match','raw_frame_crc_and_format_valid')):
            raise ValueError('Invalid report cannot become image bytes')
        report=_codec().decode_report(raw)
        if (not report['valid'] or report['recvd_len']!=256 or len(report['recvd_data'])!=256 or
                any(report[k]!=item[k] for k in ('run_id','image_id','trial_id','item_index','attempt_id','route_mode'))):
            raise ValueError('Missing/truncated/misbound STM report payload')
        if classification['business_success']!=result['STM_business_success']:raise ValueError('STM result label changed')
        received['STM'].extend(report['recvd_data'])
        refs=[]
        for p in (zero/'a_raw.bin',zero/'b_raw.bin',one/'raw_packet.bin',result_dir/'result.json'):
            refs.append({'path':p.relative_to(session.root).as_posix(),'bytes':p.stat().st_size,'sha256':store.sha(p.read_bytes())})
        references.append({'item_index':index,'record_id':rid,'identity_hex':result['identity_hex'],'files':refs})
        if entry['profile']:
            start=index*256+entry['profile']['first_byte']-20
            mask[start:start+entry['count']]=bytes([255])*entry['count']
    payloads={'source.bin':source,'source.png':png_gray(source),'planned_targets.png':png_gray(mask)}
    info={'schema':'RANDOM_IMAGE_ACTUAL_RX_VIEW_V0_1','session':session.root.name,'seed':schedule['seed'],
        'source_is_reference_not_new_unmarked_control_run':True,'image_acceptance_claimed':False,
        'scope':'Diagnostic rendering of actual saved bytes, including business-failed reports; not image repair',
        'planned_target_pixels':sum(bool(v) for v in mask),'planned_points':sum(e['count'] for e in schedule['items']),
        'actual_changed_pixels_are_not_assumed_equal_to_planned_points':True,
        'all_points_waveform_verified':False,'receivers':{},'references':references}
    for name,data in received.items():
        data=bytes(data);info['receivers'][name]=metrics(source,data,mask)
        payloads[name+'_received.bin']=data;payloads[name+'_received.png']=png_gray(data)
        payloads[name+'_error_mask.png']=png_gray(bytes(255 if a!=b else 0 for a,b in zip(source,data)))
        payloads[name+'_absolute_difference.png']=png_gray(bytes(abs(a-b) for a,b in zip(source,data)))
    payloads['metrics.json']=store._json(info)
    html='<!doctype html><meta charset="utf-8"><title>实际图片接收对照</title><style>body{font-family:sans-serif}figure{display:inline-block}img{width:256px;image-rendering:pixelated}</style><h1>随机毛刺实际接收结果</h1><p>受损图来自实际保存数据；不是修复结果，也不表示业务接收成功。白色差分点表示实际像素变化。</p>'
    for title,file in [('源图','source.png'),('A路接收','A_received.png'),('B路接收','B_received.png'),('STM32回报载荷','STM_received.png'),('B路实际变化位置','B_error_mask.png'),('STM32实际变化位置','STM_error_mask.png'),('计划注入位置（不等于误码）','planned_targets.png')]:
        html+='<figure><figcaption>'+title+'</figcaption><img src="'+file+'"></figure>'
    payloads['图片对照.html']=html.encode('utf-8')
    destination=session.root/'IMAGE_VIEW';persist_exact(destination,payloads)
    session.journal.record('random_image_actual_view_saved',metrics_sha256=store.sha(payloads['metrics.json']),
        source_sha256=store.sha(source),images_from_actual_received_bytes=True)
    return info
