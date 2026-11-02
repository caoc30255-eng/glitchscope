"""Shared immutable JSON and path boundaries, Python 3.8+. No device imports."""
import hashlib,json,os,uuid
from contextlib import contextmanager
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def raw(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,allow_nan=False,indent=2).encode('utf-8')
def digest(value):return hashlib.sha256(raw(value)).hexdigest()
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def require(value,message):
    if not value:raise ValueError(message)
def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    pending=path.with_name('.'+path.name+'.'+uuid.uuid4().hex+'.partial')
    try:
        with pending.open('xb') as f:f.write(raw(value));f.flush();os.fsync(f.fileno())
        # Atomic publication without replacing an existing immutable output.
        os.link(pending,path)
    finally:
        if pending.exists():pending.unlink()
def inside(root,path):
    root=Path(root).resolve();path=Path(path).resolve()
    require(root in path.parents,'PATH_OUTSIDE_ALLOWED_ROOT');return path
def notebook_code(data):
    v=json.loads(data)
    return [hashlib.sha256(''.join(c['source']).encode('utf-8')).hexdigest() for c in v['cells'] if c['cell_type']=='code']
def verify():
    manifest=json.loads((ROOT/'manifest.json').read_bytes())
    for name,proof in manifest.items():
        p=inside(ROOT,ROOT/name)
        if p.parent==ROOT and p.name=='workbench.ipynb':
            require(notebook_code(p.read_bytes())==proof.get('code_cells_sha256'),'NOTEBOOK_CODE_CHANGED')
            continue
        require(p.stat().st_size==proof['bytes'] and sha(p)==proof['sha256'],'DELIVERY_CHANGED:'+name)
    return len(manifest)
def verify_execution():
    """Per-record code/model integrity; static samples/fonts are checked at admission."""
    manifest=json.loads((ROOT/'manifest.json').read_bytes());files=set()
    for p in ROOT.iterdir():
        if p.is_file() and p.suffix in ('.py','.json','.ipynb') and p.name!='manifest.json':files.add(p)
    for folder in ('web','vendor'):
        for p in (ROOT/folder).rglob('*'):
            if p.is_file() and '__pycache__' not in p.parts and p.suffix in ('.py','.json','.js','.css','.html'):files.add(p)
    for p in files:
        name=p.relative_to(ROOT).as_posix();require(name in manifest,'UNREVIEWED_EXECUTION_FILE:'+name);proof=manifest[name]
        if p.parent==ROOT and p.name=='workbench.ipynb':require(notebook_code(p.read_bytes())==proof['code_cells_sha256'],'NOTEBOOK_CODE_CHANGED')
        else:require(p.stat().st_size==proof['bytes'] and sha(p)==proof['sha256'],'EXECUTION_FILE_CHANGED:'+name)
    return len(files)
@contextmanager
def read_gate(session):
    """An existing global HIL lock is held shared for the entire source read."""
    f=None
    try:
        if session and os.name=='posix':
            import fcntl
            p=Path(session).resolve().parent/'exclusive.lock'
            if p.is_file():
                f=p.open('rb');fcntl.flock(f,fcntl.LOCK_SH|fcntl.LOCK_NB)
        yield
    finally:
        if f is not None:f.close()
