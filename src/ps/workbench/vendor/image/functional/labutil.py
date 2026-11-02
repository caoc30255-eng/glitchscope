import hashlib,json,os
from pathlib import Path

class Rejected(ValueError):pass
def require(ok,why):
    if not ok:raise Rejected(why)
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')
def sha(raw):return hashlib.sha256(raw).hexdigest()
def digest(value):return sha(canonical(value))
def read(path):return json.loads(Path(path).read_bytes())
def output_path(path):
    path=Path(os.path.abspath(path)).resolve();package=Path(__file__).resolve().parent
    require(path!=package and package not in path.parents,'PACKAGE_SOURCE_IS_READ_ONLY; use separate workspace')
    for ancestor in (path,*path.parents):
        require(not (ancestor/'sha256_manifest.json').is_file() and not (ancestor/'PACKAGE_manifest.json').is_file(),'REGISTERED_OR_DELIVERED_SOURCE_IS_READ_ONLY')
    return path
def write(path,value):
    path=output_path(path);path.parent.mkdir(parents=True,exist_ok=True);temp=path.with_name(path.name+'.tmp')
    temp.write_bytes(canonical(value)+b'\n');os.replace(str(temp),str(path))
def hex_identity(value):
    if isinstance(value,int):value='%064x'%value
    require(isinstance(value,str) and len(value)==64 and all(c in '0123456789abcdef' for c in value),'FULL_IDENTITY_REQUIRED')
    return value
def id_fields(value):
    word=int(hex_identity(value),16);remaining=256;out={}
    for k,w in [('reserved',37),('session',32),('seq',32),('route_epoch',32),('slot',3),('generation',32),('run_id',32),('image_id',8),('trial_id',16),('item_index',16),('attempt_id',8),('route_mode',8)]:
        remaining-=w;out[k]=(word>>remaining)&((1<<w)-1)
    return out
def view(value,key=''):
    """Lossless view conversion, never written back over evidence."""
    if isinstance(value,dict):return {k:view(v,k) for k,v in value.items()}
    if isinstance(value,list):return [view(v,key) for v in value]
    if isinstance(value,int) and not isinstance(value,bool):
        if key in ('identity','identity_hex'):return hex_identity(value)
        if abs(value)>2**53-1 or key in ('start','close','deadline') or any(s in key.lower() for s in ('tick','deadline')):return str(value)
    return value
