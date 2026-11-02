"""Compare saved Python code structure, ignoring notebook outputs and formatting.

Fixed .py sources still require exact SHA256. This is not a bypass for code
changes: names, calls, ordering, literals and number of code cells must match.
"""
import ast
import hashlib
import json
from pathlib import Path


def fingerprint(source):
    tree=ast.parse(source,mode='exec',feature_version=(3,8))
    return hashlib.sha256(ast.dump(tree,include_attributes=False).encode('utf-8')).hexdigest()


def verify_notebook(notebook,expected_files):
    notebook=Path(notebook)
    value=json.loads(notebook.read_bytes())
    cells=[''.join(c['source']) for c in value['cells'] if c['cell_type']=='code']
    expected=[Path(p).read_text(encoding='utf-8') for p in expected_files]
    if len(cells)!=len(expected):raise ValueError('NOTEBOOK_CODE_CELL_COUNT_CHANGED')
    actual=[];wanted=[]
    for index,(cell,source) in enumerate(zip(cells,expected),1):
        try:a=fingerprint(cell);b=fingerprint(source)
        except (SyntaxError,TypeError,ValueError) as exc:
            raise ValueError('NOTEBOOK_INVALID_PYTHON_CELL_%d'%index) from exc
        if a!=b:raise ValueError('NOTEBOOK_EXECUTABLE_CODE_CHANGED_CELL_%d'%index)
        actual.append(a);wanted.append(b)
    return dict(notebook_code_ast_match=True,code_cells=len(cells),
                exact_text_match=cells==expected,code_fingerprints=actual,
                ignored='Outputs, execution counts, metadata, comments and formatting only')
