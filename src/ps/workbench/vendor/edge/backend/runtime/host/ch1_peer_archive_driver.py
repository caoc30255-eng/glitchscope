"""H5E1 peer raw-cache archive via caller-owned READ32/WRITE32 control adapter.

Peer cache generation is not W19 START generation. Never use one for the other.
No START, Overlay, UART FIFO clearing, or blind confirmation retries.
"""
from pathlib import Path
import json,os
import ch1_evidence_store as store
from ch1_runtime_driver import unsigned


def persist_exact(directory,files):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    for name,raw in files.items():
        path=directory/name
        if path.exists():
            if path.read_bytes()!=raw:raise ValueError('Existing peer archive differs; original retained')
            with path.open('r+b') as handle:os.fsync(handle.fileno())
        else:store._write(path,raw)
    store._sync_directory(directory)
    marker=store._json({'files':{name:store.sha(raw) for name,raw in files.items()}})
    path=directory/'committed.json'
    if path.exists():
        if path.read_bytes()!=marker:raise ValueError('Peer archive manifest changed')
        with path.open('r+b') as handle:os.fsync(handle.fileno())
    else:store._write(path,marker)
    store._sync_directory(directory)


class AXPeerArchiveDriver:
    def __init__(self,peer,root,*,poll_limit=1000):
        self.peer=peer;self.root=Path(root);self.limit=unsigned(poll_limit,32,'poll_limit',1)
        if self.read(0)!=0x48354531:raise RuntimeError('Requires frozen H5E1 peer; no writes performed')
    def read(self,a):return unsigned(self.peer.read(a),32,'peer DWORD')
    def _namespace(self,epoch,session,route):
        if (self.read(0x24),self.read(0x28),self.read(0x2c))!=(epoch,session,route):
            raise RuntimeError('Peer runtime namespace changed; no proof')
    def archive_prepared(self,upload,*,peer_epoch,record_id,route):
        unsigned(peer_epoch,32,'peer epoch',1);unsigned(record_id,32,'store record ID',1)
        unsigned(route,1,'route')
        if upload.fault or upload.current is None:raise RuntimeError('No retained prepared upload')
        kind,seq,inner,packet=upload.current
        directory=self.root/f'epoch_{peer_epoch:08x}_session_{upload.session:08x}_seq_{seq:08x}'
        status=self.read(4)
        if status&0x50 or not status&1:raise RuntimeError('Peer fault/unauthorized; retain evidence')
        self._namespace(peer_epoch,upload.session,route)
        if not status&2:
            # Only a matching durable archive + exact actual last-take registers
            # can recover a previously executed store with a lost reply.
            context_path=directory/'context.json'
            if not context_path.is_file():return None
            context=json.loads(context_path.read_text())
            expected={'kind':int(kind),'epoch':peer_epoch,'session':upload.session,'seq':seq,
                      'len':len(inner),'crc':store.crc16(inner),'store_record_id':record_id,'route':route}
            if any(context.get(k)!=v for k,v in expected.items()):raise ValueError('Cached peer archive context conflict')
            files={'context.json':store._json(context),'inner.bin':bytes(inner),'outer.bin':bytes(packet)}
            persist_exact(directory,files)
            if status&8:raise RuntimeError('Peer confirmation pending; no blind retry')
            if (self.read(0x68),self.read(0x6c))!=(record_id,context['ticket']):
                raise RuntimeError('Peer actual saved-take not observed')
            return {**context,'peer_store_verified':True,'directory':str(directory),'cached':True}
        if not status&4:return None  # Acquisition is still in progress; no proof or writes.
        values=[self.read(0x100+4*i) for i in range(8)]
        keys=('kind','epoch','session','seq','ticket','len','crc','capture_generation')
        meta=dict(zip(keys,values))
        raw=bytearray()
        if not meta['ticket'] or not meta['capture_generation'] or meta['len']>534:
            raise ValueError('Invalid peer raw descriptor')
        burst=getattr(self.peer,'read_bytes',None)
        if callable(burst):
            for i in range(0,meta['len'],16):
                count=min(16,meta['len']-i)
                data=burst(0x400+4*i,count)
                if not isinstance(data,bytes) or len(data)!=count:
                    raise ValueError('Peer OP2 returned incomplete actual bytes')
                raw.extend(data)
        else:
            for i in range(meta['len']):
                value=self.read(0x400+4*i)
                if value>255:raise ValueError('Peer raw DWORD padding changed')
                raw.append(value)
        expected=(int(kind),peer_epoch,upload.session,seq,len(inner),store.crc16(inner))
        if tuple(meta[k] for k in ('kind','epoch','session','seq','len','crc'))!=expected or bytes(raw)!=bytes(inner) or store.crc16(raw)!=meta['crc']:
            # Keep actual bytes for diagnosis, but never return a persistence proof.
            diag=self.root/f'failed_{peer_epoch:08x}_{meta["ticket"]:08x}'
            persist_exact(diag,{'actual.bin':bytes(raw),'descriptor.json':store._json(meta)})
            raise ValueError('Peer raw frame differs from immutable prepared bytes')
        if self.read(0x30)!=meta['len'] or self.read(0x34)!=255:
            raise RuntimeError('Missing actual delivered peer byte/descriptor coverage')
        context={**meta,'store_record_id':record_id,'route':route}
        persist_exact(directory,{'context.json':store._json(context),'inner.bin':bytes(raw),'outer.bin':bytes(packet)})
        upload.record('peer_raw_saved',**context,directory=str(directory))
        self._namespace(peer_epoch,upload.session,route)
        if self.read(4)&0x50:raise RuntimeError('Peer fault after persistence; proof withheld')
        for a,k in ((0x40,'epoch'),(0x44,'kind'),(0x48,'session'),(0x4c,'seq'),(0x50,'ticket'),
                    (0x54,'len'),(0x58,'crc'),(0x5c,'store_record_id'),(0x60,'capture_generation')):
            self.peer.write(a,context[k])
        self.peer.write(0x64,1)
        for _ in range(self.limit):
            status=self.read(4)
            if status&0x50:raise RuntimeError('Peer proof rejected; archive retained')
            if not status&0x0e:
                if (self.read(0x68),self.read(0x6c))!=(record_id,meta['ticket']):
                    raise RuntimeError('Peer saved-take identity mismatch')
                return {**context,'peer_store_verified':True,'directory':str(directory),'cached':False}
        raise TimeoutError('Peer actual store-take unconfirmed; no START or new upload')
