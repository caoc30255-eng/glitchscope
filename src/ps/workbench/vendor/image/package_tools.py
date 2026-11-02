"""Read-only fixed-file verification; runtime outputs live outside the kit."""
import ast
import hashlib
import json
from pathlib import Path
import platform
import sys

ROOT = Path(__file__).resolve().parent


def verify():
    manifest = json.loads((ROOT/'sha256.json').read_bytes())
    for name, proof in manifest.items():
        path = (ROOT/name).resolve()
        if ROOT not in path.parents:
            raise ValueError('MANIFEST_PATH')
        raw = path.read_bytes()
        if len(raw) != proof['bytes'] or hashlib.sha256(raw).hexdigest() != proof['sha256']:
            raise ValueError('FIXED_FILE_CHANGED: ' + name)
    from notebook_code_compat import verify_notebook
    result=verify_notebook(ROOT/'image_upload.ipynb',
        [ROOT/('step%d_complete_cell.py'%i) for i in range(1,4)])
    return dict(status='PASS_FIXED_FILES', files=len(manifest), hardware_access=False,notebook=result)


def preflight(output):
    """Does not import pynq, inspect MMIO or start a receiver."""
    result = verify()
    for p in list(ROOT.glob('*.py'))+list((ROOT/'tests').glob('*.py')):
        ast.parse(p.read_text(encoding='utf-8'), feature_version=(3, 8))
    result.update(python=sys.version, machine=platform.machine(),
                  Python38_syntax=True, target_identity_verified=False,
                  FPGA_access=False, physical_STARTs=0)
    path = Path(output).resolve()
    if path == ROOT or ROOT in path.parents:
        raise ValueError('OUTPUT_MUST_BE_OUTSIDE_KIT')
    with path.open('x', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return result


if __name__ == '__main__':
    print(json.dumps(preflight(sys.argv[1]), ensure_ascii=False, indent=2))
