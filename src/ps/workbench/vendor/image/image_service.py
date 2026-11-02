"""Upload/preview and one explicitly sealed 65-record image run; no device imports."""
import base64
import copy
import hashlib
import json
from pathlib import Path
import struct
import threading
import zlib
from pilot_service import PilotService,canonical,digest,save,require

MAX_ORIGINAL=8*1024*1024


def sha(raw):return hashlib.sha256(raw).hexdigest()


def gray_png(raw):
    require(len(raw)==16384,'GRAY8_128_REQUIRED')
    def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    scan=b''.join(b'\0'+raw[i:i+128] for i in range(0,16384,128))
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',128,128,8,0,0,0,0))+chunk(b'IDAT',zlib.compress(scan))+chunk(b'IEND',b'')


class Assets:
    def __init__(self,root):
        self.root=Path(root).resolve();self.root.mkdir(parents=True,exist_ok=True)
        self.lock=threading.RLock()
    def upload(self,body):
        require(set(body)=={'filename','original_base64','raw_base64','transform'},'UPLOAD_FIELDS')
        name=body['filename'];require(type(name) is str and 0<len(name)<=200 and '\0' not in name,'IMAGE_NAME')
        require(type(body['original_base64']) is str and len(body['original_base64'])<=12*1024*1024,'IMAGE_TOO_LARGE')
        require(type(body['raw_base64']) is str and len(body['raw_base64'])<=22000,'PIXEL_ARRAY_SIZE')
        original=base64.b64decode(body['original_base64'],validate=True);raw=base64.b64decode(body['raw_base64'],validate=True)
        require(0<len(original)<=MAX_ORIGINAL and len(raw)==16384,'IMAGE_AND_GRAY128_SIZE')
        require(original.startswith((b'\x89PNG\r\n\x1a\n',b'\xff\xd8\xff',b'BM')) or
                original.startswith(b'RIFF') and original[8:12]==b'WEBP','PNG_JPEG_BMP_WEBP_REQUIRED')
        t=body['transform'];require(type(t) is dict and set(t)=={'width','height','original_width','original_height','fit','conversion'},'TRANSFORM_FIELDS')
        require(t['width']==t['height']==128 and t['fit'] in ('contain','cover') and t['conversion']=='BROWSER_CANVAS_BT601_ROUND','TRANSFORM_POLICY')
        require(all(type(t[k]) is int and 1<=t[k]<=8192 for k in ('original_width','original_height')) and t['original_width']*t['original_height']<=32000000,'ORIGINAL_DIMENSION_BOUND')
        meta=dict(filename=name,width=128,height=128,bytes=16384,source_sha256=sha(raw),original_sha256=sha(original),
                  original_bytes=len(original),transform=t,conversion_location='browser; stored GRAY8 bytes are authoritative for preview/send')
        asset_id=digest(meta);meta['asset_id']=asset_id
        with self.lock:
            folder=self.root/asset_id
            if folder.exists():
                existing=self.read(asset_id);require(existing['metadata']==meta,'ASSET_CONFLICT');return meta
            folder.mkdir()
            files={'original.bin':original,'source.bin':raw,'source.png':gray_png(raw),'metadata.json':canonical(meta)}
            for key,data in files.items():
                with (folder/key).open('xb') as f:
                    f.write(data);f.flush();__import__('os').fsync(f.fileno())
            save(folder/'committed.json',dict(files={k:sha(v) for k,v in files.items()}))
        return copy.deepcopy(meta)
    def read(self,asset_id):
        require(type(asset_id) is str and len(asset_id)==64 and all(c in '0123456789abcdef' for c in asset_id),'ASSET_ID')
        folder=(self.root/asset_id).resolve();require(folder.parent==self.root,'ASSET_PATH')
        commit=json.loads((folder/'committed.json').read_bytes());files={}
        require(set(commit['files'])=={'original.bin','source.bin','source.png','metadata.json'},'ASSET_COMMIT_FIELDS')
        for name,expected in commit['files'].items():
            raw=(folder/name).read_bytes();require(sha(raw)==expected,'UPLOADED_ASSET_CHANGED');files[name]=raw
        meta=json.loads(files['metadata.json']);unsigned={k:v for k,v in meta.items() if k!='asset_id'}
        require(digest(unsigned)==asset_id==meta['asset_id'] and sha(files['source.bin'])==meta['source_sha256'] and len(files['source.bin'])==16384,'ASSET_BINDING')
        return dict(folder=folder,metadata=meta,source=files['source.bin'],files=files)
    def list(self):
        result=[]
        for p in sorted(self.root.glob('*/committed.json')):
            try:
                commit=json.loads(p.read_bytes());raw=(p.parent/'metadata.json').read_bytes()
                require(sha(raw)==commit['files']['metadata.json'],'ASSET_METADATA_CHANGED')
                meta=json.loads(raw);require(meta['asset_id']==p.parent.name,'ASSET_METADATA_ID')
                result.append(meta)
            except (ValueError,OSError,KeyError):continue
        return result


class ImageService:
    def __init__(self,workspace,*,owner_factory=None,session_root=None,assets_root=None):
        self.workspace=Path(workspace).resolve();self.assets=Assets(assets_root or self.workspace/'uploads')
        self.factory=owner_factory;self.pilot=None;self.lock=threading.RLock();self.prepared=None;self.prepare_error=None
        if session_root is None:
            self.root=self.workspace/'image_web_runs'/__import__('uuid').uuid4().hex
        else:self.root=Path(session_root)/'WEB_IMAGE_SERVICE'
        self.root.mkdir(parents=True,exist_ok=False)
    def status(self):
        with self.lock:
            out=dict(linked=self.factory is not None,assets=self.assets.list(),prepared=self.prepared,
                     limit=65,stage='UPLOAD_READY',hardware_access_by_upload=False)
            if self.prepare_error:out.update(stage='BLOCKED_SETUP',error=self.prepare_error)
            if self.pilot:
                out['pilot']=self.pilot.status();out['stage']=out['pilot']['state']
                out['artifacts']=copy.deepcopy(self.pilot.owner.artifacts)
                out['worker_finished']=self.pilot.join(0)
            return out
    def upload(self,body):
        with self.lock:
            require(self.pilot is None,'PLAN_SEALED_UPLOAD_DISABLED_FOR_THIS_SESSION')
            return self.assets.upload(body)
    def prepare(self,body):
        require(set(body)=={'asset_id','seed'},'FIXED_IMAGE_PLAN_FIELDS')
        require(type(body['seed']) is int and 0<=body['seed']<2**32,'SEED_UINT32')
        with self.lock:
            require(self.factory is not None,'IMAGE_HARDWARE_NOT_LINKED')
            require(self.prepare_error is None,'PREPARE_FAILED_NO_RETRY_IN_THIS_SESSION')
            if self.pilot:
                require(self.prepared['asset_id']==body['asset_id'] and self.prepared['seed']==body['seed'],'ONE_SEALED_IMAGE_PLAN_ONLY')
                return self.status()
            asset=self.assets.read(body['asset_id'])
            # No CONFIG/ITEM or physical START is sent by owner construction.
            try:
                save(self.root/'prepare_intent.json',dict(asset_id=body['asset_id'],seed=body['seed'],limit=65))
                owner=self.factory(asset,body['seed'])
                self.pilot=PilotService(owner,self.root/'pilot',limit=65)
            except BaseException as exc:
                self.prepare_error=repr(exc)
                raise
            self.prepared=dict(asset_id=body['asset_id'],seed=body['seed'],metadata=asset['metadata'],
                               plan_sha256=self.pilot.status()['plan_sha256'],max_records=65)
            save(self.root/'prepared.json',self.prepared)
            return self.status()
    def command(self,action,body):
        require(set(body)=={'idempotency_key','plan_sha256'},'IMAGE_START_STOP_FIELDS')
        with self.lock:
            require(self.pilot is not None,'PREPARE_UPLOADED_IMAGE_FIRST')
            return self.pilot.command(action,body['idempotency_key'],body['plan_sha256'])
    def artifact_path(self,name):
        require(self.pilot is not None and self.pilot.owner.artifacts.get('status')=='READY','RECEIVED_IMAGES_NOT_READY')
        root=Path(self.pilot.owner.artifact_root).resolve();path=(root/name).resolve()
        require(root in path.parents and path.is_file() and path.suffix in ('.png','.json','.bin'),'IMAGE_ARTIFACT_PATH')
        return path
