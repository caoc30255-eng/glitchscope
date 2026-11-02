"""Synthetic two-stump score; not a trained or calibrated GLITCHSCOPE model."""
import math
def predict(q):
    if set(q)!={'width','gap'}:raise ValueError('CONTEXT_KEYS')
    if any(type(q[k]) is not int or not 0<=q[k]<=32 for k in q):
        return dict(action='ABSTAIN',score=None,uncertainty_entropy=None,execution_allowed=False)
    score=(.8 if q['width']<=8 else .2)+(.1 if q['gap']<=16 else -.1)
    entropy=-(score*math.log2(score)+(1-score)*math.log2(1-score))
    return dict(action='PREDICT',score=float(score),uncertainty_entropy=entropy,execution_allowed=False)
