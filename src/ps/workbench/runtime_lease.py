"""One cooperating live worker per OS across installation roots. No FPGA access."""
import os,stat,json
from pathlib import Path
GLOBAL_PATH=Path('/run/lock/glitchscope_pl_runtime.lock')

def _lock(file,unlock=False):
    if os.name=='nt':
        import msvcrt
        file.seek(0);msvcrt.locking(file.fileno(),msvcrt.LK_UNLCK if unlock else msvcrt.LK_NBLCK,1)
    else:
        import fcntl
        fcntl.flock(file.fileno(),fcntl.LOCK_UN if unlock else fcntl.LOCK_EX|fcntl.LOCK_NB)

class RuntimeLock:
    def __init__(self,local,global_file,path):self.local=local;self.global_file=global_file;self.path=Path(path)
    @property
    def name(self):return self.local.name
    @property
    def closed(self):return self.local.closed and self.global_file.closed
    def fileno(self):return self.local.fileno()
    def quarantine(self,reason):
        if self.global_file.closed:raise RuntimeError('GLOBAL_LEASE_REQUIRED')
        marker=Path(str(self.path)+'.quarantine.json')
        if not marker.exists():
            with marker.open('x',encoding='utf-8') as f:json.dump(dict(reason=str(reason),automatic_recovery=False),f);f.flush();os.fsync(f.fileno())
    def close(self):
        try:self.local.close()
        finally:
            if not self.global_file.closed:
                try:_lock(self.global_file,True)
                finally:self.global_file.close()

def acquire_runtime_lock(runs,global_path=GLOBAL_PATH):
    path=Path(global_path);marker=Path(str(path)+'.quarantine.json')
    if marker.exists():raise RuntimeError('GLOBAL_DEVICE_QUARANTINED_REVIEW_REQUIRED')
    fd=os.open(str(path),os.O_RDWR|os.O_CREAT|getattr(os,'O_NOFOLLOW',0),0o600)
    f=os.fdopen(fd,'r+b');local=None
    try:
        if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):raise RuntimeError('GLOBAL_LEASE_NOT_REGULAR_FILE')
        if os.fstat(f.fileno()).st_size==0:f.write(b'0');f.flush()
        _lock(f)
        if marker.exists():raise RuntimeError('GLOBAL_DEVICE_QUARANTINED_REVIEW_REQUIRED')
        local=(Path(runs)/'exclusive.lock').open('a+b')
        if os.name=='nt' and local.seek(0,2)==0:local.write(b'0');local.flush()
        _lock(local)
        return RuntimeLock(local,f,path)
    except BaseException:
        if local:local.close()
        f.close();raise
    # Persistent global lease files are never unlinked by a worker.
