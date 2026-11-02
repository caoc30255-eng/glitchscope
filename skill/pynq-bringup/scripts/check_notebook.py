"""Compare code cells by AST; never execute a notebook."""
import argparse, ast, json, sys
from pathlib import Path
def fingerprints(notebook):
    result = []
    for cell in notebook['cells']:
        if cell['cell_type'] == 'code':
            source = cell.get('source', '')
            if isinstance(source, list): source = ''.join(source)
            result.append(ast.dump(ast.parse(source), include_attributes=False))
    return result
def compare(reference, candidate):
    a, b = fingerprints(reference), fingerprints(candidate)
    changed = [i+1 for i in range(max(len(a),len(b))) if i>=len(a) or i>=len(b) or a[i]!=b[i]]
    return dict(passed=not changed, code_cells_reference=len(a), code_cells_candidate=len(b), changed_cells=changed,
                scope='AST equality only; not a safety proof or file authenticity check')
def main():
    p=argparse.ArgumentParser();p.add_argument('--reference',required=True);p.add_argument('--candidate',required=True)
    a=p.parse_args()
    try: r=compare(json.loads(Path(a.reference).read_text(encoding='utf-8')),json.loads(Path(a.candidate).read_text(encoding='utf-8')))
    except Exception as e:r=dict(passed=False,error=type(e).__name__,message=str(e))
    print(json.dumps(r));return 0 if r['passed'] else 2
if __name__=='__main__':sys.exit(main())
