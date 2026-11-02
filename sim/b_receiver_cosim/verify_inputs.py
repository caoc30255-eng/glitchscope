from pathlib import Path
import json,hashlib
root=Path(__file__).resolve().parent
m=json.loads((root/'SHA256_MANIFEST.json').read_bytes())
for n,p in m.items():
 f=(root/n).resolve()
 if root not in f.parents:raise ValueError('PATH_ESCAPE')
 b=f.read_bytes()
 if len(b)!=p['bytes'] or hashlib.sha256(b).hexdigest()!=p['sha256']:raise ValueError('FILE_CHANGED:'+n)
print('PASS_FIXED_INPUT_FILES',len(m),'simulation_NOT_verified hardware_access=False')
