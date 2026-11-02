"""Cooperating processes share one persistent lock file per physical device."""
import os,json
from pathlib import Path
class DeviceLease:
    def __init__(self,path):self.path=Path(path);self.released=False;self.held=False;self.quarantine_path=Path(str(self.path)+'.quarantine.json')
    def __enter__(self):
        if self.quarantine_path.exists():raise RuntimeError('DEVICE_QUARANTINED_RELEASE_NOT_CONFIRMED')
        self.f=self.path.open('a+b')
        self.f.seek(0,2)
        if self.f.tell()==0:self.f.write(b'0');self.f.flush()
        self.f.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(self.f.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.f.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:self.f.close();raise RuntimeError('DEVICE_LEASE_BUSY')
        self.held=True
        if self.quarantine_path.exists():self.__exit__();raise RuntimeError('DEVICE_QUARANTINED_RELEASE_NOT_CONFIRMED')
        return self
    def quarantine(self,reason):
        if not self.held:raise RuntimeError('LEASE_REQUIRED_FOR_QUARANTINE')
        if not self.quarantine_path.exists():
            with self.quarantine_path.open('x',encoding='utf-8') as f:json.dump(dict(reason=str(reason),pid=os.getpid(),automatic_recovery=False),f);f.flush();os.fsync(f.fileno())
    def __exit__(self,*args):
        try:
            self.f.seek(0)
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(self.f.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl
                fcntl.flock(self.f.fileno(),fcntl.LOCK_UN)
        finally:self.f.close();self.held=False;self.released=True
        # Never unlink a global lease file; deleting it could create two lock domains.
