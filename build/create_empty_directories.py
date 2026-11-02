import json
from pathlib import Path
root=Path(__file__).resolve().parents[1]
for n in json.loads((root/'required_empty_directories.json').read_bytes()):
    p=(root/n).resolve()
    if root not in p.parents:raise ValueError('Directory outside repository')
    p.mkdir(parents=True,exist_ok=True)
print('Required empty directories created; no files written inside.')
