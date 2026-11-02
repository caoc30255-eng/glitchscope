"""Read-only checksum, path and requested empty-directory verification."""
import hashlib,json,re
from pathlib import Path
root=Path(__file__).resolve().parents[1]
manifest=json.loads((root/'release_manifest.json').read_bytes())
for n,v in manifest['files'].items():
    p=root/n
    if not p.is_file() or p.stat().st_size!=v['bytes'] or hashlib.sha256(p.read_bytes()).hexdigest()!=v['sha256']:raise ValueError('File changed: '+n)
actual={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() and '__pycache__' not in p.parts and '.git' not in p.relative_to(root).parts}
if actual!=set(manifest['files'])|{'release_manifest.json'}:raise ValueError('Unexpected or missing release files')
for p in root.rglob('*'):
    if '__pycache__' in p.parts or '.git' in p.relative_to(root).parts:continue
    if p.is_file() and p.name not in ('README.md','SKILL.md','LICENSE') and not re.fullmatch('[a-z0-9_.-]+',p.name):raise ValueError('Invalid name: '+str(p.relative_to(root)))
for n in json.loads((root/'required_empty_directories.json').read_bytes()):
    p=root/n
    if not p.is_dir() or any(p.iterdir()):raise ValueError('Expected empty directory: '+n)
print('PASS_RELEASE_CONTENTS',len(manifest['files']),'files; required empty directories preserved; no hardware accessed')
