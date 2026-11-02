"""A real file-loaded synthetic model; not trained/calibrated GLITCHSCOPE weights."""
import hashlib,math
from pathlib import Path
from types import MappingProxyType
class Model:
    def __init__(self,path):
        self.loaded_path=Path(path).resolve();raw=self.loaded_path.read_bytes();lines=raw.decode('ascii').splitlines()
        names=['max_feature','threshold_width','threshold_gap','left_score','right_score','gap_left_delta','gap_right_delta']
        if not lines or lines[0]!='SKILL_STUMPS_V1' or len(lines)!=8:raise ValueError('MODEL_FORMAT')
        d={}
        for n,line in zip(names,lines[1:]):
            k,v=line.split('=')
            if k!=n:raise ValueError('MODEL_KEY_ORDER')
            d[k]=int(v) if k in names[:3] else float(v)
        if any(not math.isfinite(v) for v in d.values()):raise ValueError('MODEL_NONFINITE')
        if not 1<=d['max_feature']<=100000 or not all(0<=d[n]<=d['max_feature'] for n in names[1:3]):raise ValueError('MODEL_RANGE')
        if any(not 0<a+b<1 for a in [d['left_score'],d['right_score']] for b in [d['gap_left_delta'],d['gap_right_delta']]):raise ValueError('MODEL_SCORE_RANGE')
        self.parameters=MappingProxyType(d);self.loaded_sha256=hashlib.sha256(raw).hexdigest()
    def predict(self,q):
        if set(q)!={'width','gap'}:raise ValueError('CONTEXT_KEYS')
        d=self.parameters
        if any(type(q[k]) is not int or not 0<=q[k]<=d['max_feature'] for k in q):return dict(action='ABSTAIN',score=None,uncertainty_entropy=None,execution_allowed=False)
        score=(d['left_score'] if q['width']<=d['threshold_width'] else d['right_score'])+(d['gap_left_delta'] if q['gap']<=d['threshold_gap'] else d['gap_right_delta'])
        entropy=-(score*math.log2(score)+(1-score)*math.log2(1-score))
        return dict(action='PREDICT',score=float(score),uncertainty_entropy=entropy,execution_allowed=False)
def load_model(path):return Model(path)
DEFAULT_MODEL=load_model(Path(__file__).with_name('weights.txt'))
def predict(q):return DEFAULT_MODEL.predict(q)
