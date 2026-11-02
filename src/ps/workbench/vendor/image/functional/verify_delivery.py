"""Read-only integrity verification of this delivery. Standard library only."""
import hashlib,json,sys
from pathlib import Path

def verify(root):
    root=Path(root).resolve();manifest=json.loads((root/'sha256_manifest.json').read_text(encoding='utf-8'))
    for name,p in manifest['files'].items():
        target=(root/name).resolve()
        if root not in target.parents:raise ValueError('Unsafe manifest path')
        raw=target.read_bytes()
        if len(raw)!=p['bytes'] or hashlib.sha256(raw).hexdigest()!=p['sha256']:raise ValueError('Changed: '+name)
    return len(manifest['files'])

if __name__=='__main__':print('Verified delivery files:',verify(Path(__file__).resolve().parent))
