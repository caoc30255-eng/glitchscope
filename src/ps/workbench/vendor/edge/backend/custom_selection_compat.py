"""Verify both native decision hashes, then compare narrowly allowed float drift."""
import math
from learning_domain import digest
def _allowed(path):
    return (len(path)==2 and path[0]=='selected_model_prediction' and path[1] in ('score','uncertainty_entropy')) or (
        len(path)==3 and path[0]=='candidate_ranking' and type(path[1]) is int and path[2]=='priority') or (
        len(path)==4 and path[0]=='candidate_ranking' and type(path[1]) is int and path[2]=='model_prediction' and path[3] in ('score','uncertainty_entropy'))
def compare_selection(expected,saved):
    result=dict(passed=False,numeric_differences=[],reason=None)
    for name,obj in [('expected',expected),('saved',saved)]:
        if type(obj) is not dict or obj.get('action')!='SELECT' or type(obj.get('selection_sha256')) is not str:
            return dict(result,reason='INVALID_'+name.upper()+'_SELECTION')
        try:bound=digest({k:v for k,v in obj.items() if k!='selection_sha256'})
        except (ValueError,TypeError):return dict(result,reason='NONFINITE_OR_INVALID_DECISION')
        if obj['selection_sha256']!=bound:return dict(result,reason=name.upper()+'_DECISION_HASH_CHANGED')
    def same(a,b,path=()):
        if type(a) is not type(b):return False
        if type(a) is dict:
            return set(a)==set(b) and all(same(v,b[k],path+(k,)) for k,v in a.items() if path or k!='selection_sha256')
        if type(a) is list:return len(a)==len(b) and all(same(x,y,path+(i,)) for i,(x,y) in enumerate(zip(a,b)))
        if type(a) is float:
            if not math.isfinite(a) or not math.isfinite(b):return False
            if a==b:return True
            if not _allowed(path) or abs(a-b)>1e-12:return False
            result['numeric_differences'].append(dict(path=list(path),expected=a,saved=b,absolute_difference=abs(a-b)))
            return True
        return a==b
    result['passed']=same(expected,saved)
    result['reason']='SAME_SEMANTIC_DECISION_WITH_VERIFIED_NATIVE_HASHES' if result['passed'] else 'SEMANTIC_DECISION_CHANGED'
    return result
