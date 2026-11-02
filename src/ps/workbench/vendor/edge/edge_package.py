"""Fixed-file integrity; Notebook outputs are mutable, source cells are bound."""
from pathlib import Path
import json,hashlib
ROOT=Path(__file__).resolve().parent
def verify(notebooks=False):
    manifest=json.loads((ROOT/'sha256_manifest.json').read_bytes())
    for name,proof in manifest.items():
        path=(ROOT/name).resolve()
        if ROOT not in path.parents:raise ValueError('PACKAGE_PATH_ESCAPE')
        raw=path.read_bytes()
        if len(raw)!=proof['bytes'] or hashlib.sha256(raw).hexdigest()!=proof['sha256']:raise ValueError('FIXED_FILE_CHANGED:'+name)
    if notebooks:
        notebook=json.loads((ROOT/'edgeai_baseline.ipynb').read_bytes())
        cells=[''.join(c['source']) for c in notebook['cells'] if c['cell_type']=='code' and ''.join(c['source']).strip()]
        if cells!=json.loads((ROOT/'notebook_cells.json').read_bytes()):raise ValueError('NOTEBOOK_CODE_CHANGED')
        if (ROOT/'oss_notebook_cells.json').exists():
            notebook=json.loads((ROOT/'edgeai_oss.ipynb').read_bytes())
            cells=[''.join(c['source']) for c in notebook['cells'] if c['cell_type']=='code' and ''.join(c['source']).strip()]
            if cells!=json.loads((ROOT/'oss_notebook_cells.json').read_bytes()):raise ValueError('OSS_NOTEBOOK_CODE_CHANGED')
    return len(manifest)
