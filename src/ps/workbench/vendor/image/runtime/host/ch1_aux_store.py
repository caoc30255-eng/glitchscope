"""Durable independent CH1 event journal; no MMIO operations."""
from pathlib import Path
import json,os,uuid
import ch1_evidence_store as store

FIELDS=[('reserved',1),('epoch',32),('seq',32),('bound',1),('kind',1),
        ('identity',256),('record_id',32),('flags',4),('has_byte',1),('data',8),('tick',64)]

def decode(raw):
    raw=bytes(raw)
    if len(raw)!=54:raise ValueError('Auxiliary event requires exactly 54 bytes')
    event=store._fields(int.from_bytes(raw,'big'),FIELDS)
    identity=store._fields(event['identity'],store.IDENTITY)
    if event['reserved'] or not event['epoch'] or not event['seq']:
        raise ValueError('Invalid auxiliary epoch/sequence/padding')
    if event['bound']:
        if identity['reserved'] or not identity['seq'] or not identity['generation'] or not event['record_id']:
            raise ValueError('Invalid bound auxiliary identity')
    elif event['identity'] or event['record_id']:
        raise ValueError('Unbound event cannot fabricate a binding')
    event['has_byte']=bool(event['has_byte'])
    return event

def _root(path):
    root=Path(path);missing=[];cursor=root
    while not cursor.exists():
        missing.append(cursor);cursor=cursor.parent
    root.mkdir(parents=True,exist_ok=True)
    for created in reversed(missing):store._sync_directory(created.parent)
    return root

def persist_event(output_dir,raw,crc):
    """Return exact queue ACK fields only after all event files are fsynced."""
    raw=bytes(raw);root=_root(output_dir)
    try:
        event=decode(raw)
        if not isinstance(crc,int) or isinstance(crc,bool) or not 0<=crc<=65535 or store.crc16(raw)!=crc:
            raise ValueError('Auxiliary fingerprint mismatch')
    except ValueError as exc:
        failed=root/('failed_'+uuid.uuid4().hex);failed.mkdir()
        store._write(failed/'event.bin',raw)
        store._write(failed/'failure.json',store._json({'error':str(exc),'confirmation_generated':False}))
        store._sync_directory(failed);store._sync_directory(root)
        raise
    proof={key:event[key] for key in ('epoch','seq','kind')};proof['crc']=crc
    payloads={'event.bin':raw,'event.json':store._json(event)}
    manifest={'format':'CH1_AUX_V1','confirmation':proof,
              'files':{name:{'bytes':len(data),'sha256':store.sha(data)} for name,data in payloads.items()}}
    directory=root/f"event_{event['epoch']:08x}_{event['kind']}_{event['seq']:08x}"
    try:directory.mkdir();cached=False
    except FileExistsError:
        cached=True
        if not (directory/'committed.json').is_file() or (directory/'committed.json').read_bytes()!=store._json(manifest) or any(not (directory/name).is_file() or (directory/name).read_bytes()!=data for name,data in payloads.items()):
            conflict=root/('conflict_'+uuid.uuid4().hex);conflict.mkdir()
            store._write(conflict/'event.bin',raw)
            store._write(conflict/'failure.json',store._json({'reason':'event identity reused or archive incomplete','confirmation_generated':False}))
            store._sync_directory(conflict);store._sync_directory(root)
            raise ValueError('Auxiliary archive conflict; original retained, no ACK')
    if cached:
        for name in [*payloads,'committed.json']:
            with (directory/name).open('r+b') as handle:os.fsync(handle.fileno())
    else:
        for name,data in payloads.items():store._write(directory/name,data)
        store._sync_directory(directory)
        store._write(directory/'committed.json',store._json(manifest))
    store._sync_directory(directory);store._sync_directory(root)
    return {**proof,'event':event,'evidence_dir':str(directory),'cached':cached}

def load_bound_events(output_dir,epoch,identity,record_id,start,close):
    """Verify/resync already popped events before rejoining the primary record.

    Late events remain in their independent archive; they do not mutate a
    previously committed main record. Overflow byte evidence at close joins it.
    """
    streams={'errors':[],'orphans':[]}
    for directory in sorted(Path(output_dir).glob(f'event_{epoch:08x}_*_*')):
        manifest=json.loads((directory/'committed.json').read_text(encoding='utf-8'))
        raw=(directory/'event.bin').read_bytes()
        event=decode(raw)
        proof={key:event[key] for key in ('epoch','seq','kind')};proof['crc']=store.crc16(raw)
        expected_name=f"event_{event['epoch']:08x}_{event['kind']}_{event['seq']:08x}"
        if manifest.get('format')!='CH1_AUX_V1' or manifest.get('confirmation')!=proof or directory.name!=expected_name:
            raise ValueError('Saved auxiliary manifest identity changed; no main proof')
        for name in ('event.bin','event.json'):
            data=(directory/name).read_bytes()
            if manifest['files'].get(name)!={'bytes':len(data),'sha256':store.sha(data)}:
                raise ValueError('Saved auxiliary file changed; no main proof')
        if (directory/'event.json').read_bytes()!=store._json(event):
            raise ValueError('Saved auxiliary decoded fields changed; no main proof')
        result=persist_event(output_dir,raw,manifest['confirmation']['crc'])
        event=result['event']
        if event['epoch']==epoch and event['bound'] and event['identity']==identity and event['record_id']==record_id and start<=event['tick']<=close:
            name='errors' if event['kind']==0 else 'orphans'
            streams[name].append({key:event[key] for key in ('tick','flags','has_byte','data')})
    for events in streams.values():events.sort(key=lambda event:event['tick'])
    return streams
