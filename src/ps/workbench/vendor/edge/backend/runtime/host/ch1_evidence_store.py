"""Durable CH1 archive. Pure filesystem API; no MMIO/Overlay/START/proof sending.

Confirmation means evidence saved, including failures; business success is separate.
The caller must read the complete hardware record and auxiliary journal first.
"""
from pathlib import Path
import binascii,hashlib,json,os,uuid

FIELDS=[('epoch',32),('reserved',1),('identity',256),('record_id',32),('kind',2),
        ('reason',8),('raw_count',16),('start',64),('deadline',64),('close',64),
        ('frame_valid',1),('report_status',8),('report_flags',8),('management_status',16),
        ('uart_errors',32),('observed_flags',4),('first_error_tick',64)]
IDENTITY=[('reserved',37),('session',32),('seq',32),('route_epoch',32),('slot',3),
          ('generation',32),('run_id',32),('image_id',8),('trial_id',16),('item_index',16),
          ('attempt_id',8),('route_mode',8)]

def crc16(raw):return binascii.crc_hqx(raw,0xffff)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def _json(obj):return (json.dumps(obj,ensure_ascii=True,sort_keys=True,indent=2)+'\n').encode('ascii')

def _fields(value,widths):
    remaining=sum(width for _,width in widths);out={}
    for name,width in widths:
        remaining-=width;out[name]=(value>>remaining)&((1<<width)-1)
    return out

def descriptor_decode(raw):
    if len(raw)!=84:raise ValueError('Descriptor requires exactly 84 bytes')
    d=_fields(int.from_bytes(raw,'big'),FIELDS)
    identity=_fields(d['identity'],IDENTITY)
    if d['reserved'] or identity['reserved'] or not d['epoch'] or not d['record_id'] or not identity['session'] or not identity['seq'] or not identity['generation']:
        raise ValueError('Invalid descriptor binding/epoch')
    if d['kind'] not in (1,2,3) or not 1<=d['reason']<=7 or d['raw_count']>544:
        raise ValueError('Invalid kind/reason/count')
    if not d['start']<d['deadline'] or not d['start']<=d['close']<=d['deadline']:
        raise ValueError('Invalid receive window')
    if (d['reason']==5 and d['close']!=d['deadline']) or (d['close']==d['deadline'] and d['reason']<5):
        raise ValueError('Invalid deadline terminal')
    if bool(d['frame_valid'])!=(d['reason']==1):raise ValueError('Terminal validity mismatch')
    if d['frame_valid'] and not ((20<=d['raw_count']<=532) if d['kind']==1 else d['raw_count']==12):
        raise ValueError('Valid terminal length mismatch')
    d['binding']=identity
    return d

def samples_decode(raw,d):
    if len(raw)!=10*d['raw_count']:raise ValueError('Missing/extra sample bytes')
    samples=[];previous=d['start']
    for offset in range(0,len(raw),10):
        word=int.from_bytes(raw[offset:offset+10],'big')
        tick=word&((1<<64)-1);flags=(word>>64)&15;data=(word>>68)&255
        if word>>76 or not d['start']<=tick<d['deadline'] or tick<previous:
            raise ValueError('Invalid sample padding/timestamp/order')
        samples.append({'index':offset//10,'data':data,'flags':flags,'tick':tick});previous=tick
    return samples

def _auxiliary(errors,orphans,d,watermark,samples):
    if not isinstance(watermark,int) or isinstance(watermark,bool) or not d['close']<watermark<=0xffffffffffffffff:
        raise ValueError('Finalized event watermark required')
    streams={}
    for name,events in [('errors',errors),('orphans',orphans)]:
        saved=[];previous=-1
        for entry in events:
            if set(entry)!={'tick','flags','has_byte','data'}:raise ValueError('Incomplete auxiliary event')
            event=dict(entry)
            if not isinstance(event['has_byte'],bool):raise ValueError('Bad has_byte flag')
            for key,limit in [('tick',watermark),('flags',15),('data',255)]:
                if not isinstance(event[key],int) or isinstance(event[key],bool) or not 0<=event[key]<=limit:
                    raise ValueError('Invalid auxiliary event field')
            if event['tick']<previous:raise ValueError('Auxiliary timestamps regress')
            if name=='errors' and not d['start']<=event['tick']<=d['close']:
                raise ValueError('Error event outside bound terminal window')
            previous=event['tick'];saved.append(event)
        streams[name]=saved
    if len(streams['errors'])!=d['uart_errors']:raise ValueError('Missing UART error evidence')
    seen=0
    for event in streams['errors']:seen|=event['flags']
    if seen!=d['observed_flags']:raise ValueError('Error flags summary mismatch')
    if streams['errors'] and streams['errors'][0]['tick']!=d['first_error_tick']:
        raise ValueError('First error timestamp mismatch')
    if not streams['errors'] and d['first_error_tick']!=0:raise ValueError('First error without error evidence')
    # At raw-capacity overflow the same physical byte is logged as an error
    # and an orphan, because it could not enter the full primary sample RAM.
    byte_evidence=list(samples)
    if d['reason']==7:
        byte_evidence.extend(event for event in streams['orphans'] if event['has_byte'])
    for event in streams['errors']:
        if event['has_byte'] and not any((sample['data'],sample['flags'],sample['tick'])==(event['data'],event['flags'],event['tick']) for sample in byte_evidence):
            raise ValueError('Byte error event has no matching actual sample')
    for sample in samples:
        if sample['flags'] and not any(event['has_byte'] and (event['data'],event['flags'],event['tick'])==(sample['data'],sample['flags'],sample['tick']) for event in streams['errors']):
            raise ValueError('Flagged sample lacks matching error event')
    return {'watermark':watermark,**streams}

def classify(raw,d,samples,expected_payload):
    # Import lazily; local frozen reference is part of the source package.
    import sys
    reference=Path(__file__).resolve().parents[1]/'reference'
    if str(reference) not in sys.path:sys.path.insert(0,str(reference))
    from reference_codec import ImagePacketCodec as Codec
    decoded={1:Codec.decode_report,2:Codec.decode_config_ack,3:Codec.decode_cleanup_ack}[d['kind']](raw)
    binding=d['binding'];keys=['run_id','image_id'] if d['kind']!=1 else ['run_id','image_id','trial_id','item_index','attempt_id','route_mode']
    identity_ok=bool(decoded.get('valid')) and all(decoded.get(k)==binding[k] for k in keys)
    if d['frame_valid'] and (not identity_ok or d['uart_errors'] or any(s['flags'] for s in samples)):
        raise ValueError('Hardware valid terminal contradicts actual raw/error evidence')
    success=False;source_match=None
    if d['frame_valid'] and d['kind']==1:
        if (decoded['result_status'],decoded['uart_flags'])!=(d['report_status'],d['report_flags']):
            raise ValueError('Report status summary contradicts raw packet')
        if expected_payload is not None:source_match=decoded['recvd_data']==bytes(expected_payload)
        success=decoded['result_status']==0 and decoded['uart_flags']==0 and source_match is True
    elif d['frame_valid']:
        status=decoded['ack_status'] if d['kind']==2 else decoded['status']
        if status!=d['management_status']:raise ValueError('Management status summary contradicts raw ACK')
        success=status==0
    return {'capture_valid':bool(d['frame_valid']),'raw_frame_crc_and_format_valid':bool(decoded.get('valid')),
            'wire_identity_match':identity_ok,'source_bytes_match':source_match,'business_success':success,
            'reason':d['reason'],'kind':d['kind']}

def _sync_directory(path):
    if os.name=='posix':
        fd=os.open(str(path),os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)

def _write(path,raw):
    with path.open('xb') as handle:handle.write(raw);handle.flush();os.fsync(handle.fileno())

def persist_record(output_dir,descriptor,sample_stream,descriptor_crc,samples_crc,*,
                   errors,orphans,watermark_tick,expected_payload=None):
    """Return confirmation fields only after complete record is committed.

    Caller handles proof sending and actual retirement separately. An evidence
    epoch must come from a persistent unique namespace across resets.
    """
    descriptor=bytes(descriptor);sample_stream=bytes(sample_stream)
    root=Path(output_dir);missing=[];cursor=root
    while not cursor.exists():
        missing.append(cursor)
        if cursor.parent==cursor:break
        cursor=cursor.parent
    root.mkdir(parents=True,exist_ok=True)
    for created in reversed(missing):_sync_directory(created.parent)
    diagnostic={'descriptor.bin':descriptor,'samples.bin':sample_stream}
    try:
        errors=[dict(event) for event in errors];orphans=[dict(event) for event in orphans]
        diagnostic['input_context.json']=_json({'descriptor_crc':descriptor_crc,'samples_crc':samples_crc,
                                               'errors':errors,'orphans':orphans,'watermark':watermark_tick})
        if expected_payload is not None:
            expected_payload=bytes(expected_payload);diagnostic['expected_payload.bin']=expected_payload
        if not isinstance(descriptor_crc,int) or not isinstance(samples_crc,int) or not 0<=descriptor_crc<=65535 or not 0<=samples_crc<=65535:
            raise ValueError('Invalid footer values')
        if crc16(descriptor)!=descriptor_crc or crc16(sample_stream)!=samples_crc:raise ValueError('Export footer fingerprint mismatch')
        d=descriptor_decode(descriptor);samples=samples_decode(sample_stream,d)
        raw=bytes(sample['data'] for sample in samples)
        auxiliary=_auxiliary(errors,orphans,d,watermark_tick,samples)
        result=classify(raw,d,samples,expected_payload)
    except Exception as exc:
        directory=root/('failed_'+uuid.uuid4().hex)
        directory.mkdir()
        for name,data in diagnostic.items():_write(directory/name,data)
        _write(directory/'failure.json',_json({'error':repr(exc),'confirmation_generated':False}))
        _sync_directory(directory);_sync_directory(root)
        raise ValueError(f'Evidence validation failed; no confirmation. Saved {directory}: {exc}') from exc
    payloads={**diagnostic,'raw_packet.bin':raw,'auxiliary.json':_json(auxiliary),'classification.json':_json(result)}
    proof={'epoch':d['epoch'],'identity_hex':f"{d['identity']:064x}",'record_id':d['record_id'],
           'raw_count':d['raw_count'],'descriptor_crc':descriptor_crc,'samples_crc':samples_crc}
    manifest={'format':'CH1_EVIDENCE_V1','confirmation':proof,'classification':result,
              'files':{name:{'sha256':sha(data),'bytes':len(data)} for name,data in payloads.items()}}
    directory=root/f"epoch_{d['epoch']:08x}_record_{d['record_id']:08x}"
    try:directory.mkdir()
    except FileExistsError:
        committed=directory/'committed.json'
        # Verify exact whole record, not only CRC16 or an old completion marker.
        if not committed.is_file() or committed.read_bytes()!=_json(manifest) or any(not (directory/name).is_file() or (directory/name).read_bytes()!=data for name,data in payloads.items()):
            conflict=root/('conflict_'+uuid.uuid4().hex);conflict.mkdir()
            for name,data in payloads.items():_write(conflict/name,data)
            _write(conflict/'failure.json',_json({'reason':'same epoch/record ID differs or prior archive incomplete','confirmation_generated':False}))
            _sync_directory(conflict);_sync_directory(root)
            raise ValueError(f'Archive conflict; original retained. No confirmation. Saved {conflict}')
        # A preceding attempt may have failed while fsyncing the commit marker.
        # Exact files alone are insufficient; re-sync them before cached confirmation.
        for name in [*payloads,'committed.json']:
            with (directory/name).open('r+b') as handle:os.fsync(handle.fileno())
        _sync_directory(directory);_sync_directory(root)
        return {**proof,'evidence_dir':str(directory),'business_success':result['business_success'],'cached':True}
    for name,data in payloads.items():_write(directory/name,data)
    _sync_directory(directory)
    _write(directory/'committed.json',_json(manifest))
    _sync_directory(directory);_sync_directory(root)
    return {**proof,'evidence_dir':str(directory),'business_success':result['business_success'],'cached':False}
