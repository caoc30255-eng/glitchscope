"""Finite-hypothesis active learner. No IO, real-data reader or hardware import.

This is a structured-model estimate, never a guarantee for arbitrary bitmaps.
Unqueried cells are always forecast FAIL; no unobserved PASS is manufactured.
"""
import math
from functools import lru_cache
from learning_domain import CELLS,BY_ID,digest

VERSION='CONSERVATIVE_VERSION_SPACE_V0_3_1'
INDEX={c['point_id']:i for i,c in enumerate(CELLS)}
FULL=(1<<len(CELLS))-1

def popcount(value):return bin(value).count('1')

@lru_cache(maxsize=1)
def hypothesis_catalog():
    """Generic grid structures, chosen before new holdout evaluation, no oracle labels."""
    phases=sorted({c['phase'] for c in CELLS});widths=sorted({c['width'] for c in CELLS})
    def mask(fn):return sum(1<<i for i,c in enumerate(CELLS) if fn(c))
    maps={0,FULL}
    # All row-wise width thresholds: arbitrary phase dependence, monotone per row.
    import itertools
    limits=[[-1]+[c['width'] for c in CELLS if c['phase']==p] for p in phases]
    for row_limits in itertools.product(*limits):
        bound=dict(zip(phases,row_limits))
        maps.add(mask(lambda c:c['width']<=bound[c['phase']]))
    # Axis-aligned patches and complements; single-cell islands/holes included.
    for p0 in phases:
        for p1 in phases:
            if p1<p0:continue
            for w0 in widths:
                for w1 in widths:
                    if w1<w0:continue
                    m=mask(lambda c:p0<=c['phase']<=p1 and w0<=c['width']<=w1)
                    maps.update((m,FULL^m))
    # General two alternating-row groups, each with its own arbitrary width pattern.
    # This adds periodic/nonmonotone alternatives, not an oracle's boundary formula.
    for a in range(1<<len(widths)):
        for b in range(1<<len(widths)):
            maps.add(mask(lambda c:bool(((a if phases.index(c['phase'])%2==0 else b)
                >> widths.index(c['width']))&1)))
    # Stronger sparse adversaries: all patterns with up to4 PASS cells and complements.
    # A negative observed region no longer eliminates multiple hidden success islands.
    for size in range(5):
        for positions in itertools.combinations(range(len(CELLS)),size):
            m=sum(1<<i for i in positions)
            maps.update((m,FULL^m))
    return tuple(sorted(maps))

def decide(batches):
    """batches: checked point/success-count pairs; origin checked by caller's reader."""
    seen=positives=0;mixed=False;history=[]
    for batch in batches:
        point=batch['point_id'];successes=batch['successes']
        if point not in INDEX or type(successes) is not int or not 0<=successes<=3:
            raise ValueError('EXACT_POINT_AND_THREE_REPEAT_COUNT_REQUIRED')
        bit=1<<INDEX[point]
        if seen&bit:raise ValueError('POINT_REPLAY')
        seen|=bit
        if successes>=2:positives|=bit
        mixed|=successes not in (0,3)
        history.append(dict(point_id=point,successes=successes))
    n=len(history)
    if n>10:raise ValueError('ACTIVE_TEN_POINT_LIMIT')
    candidates=[m for m in hypothesis_catalog() if m&seen==positives]
    unmeasured=FULL^seen
    max_unseen_successes=max([popcount(m&unmeasured) for m in candidates] or [14])
    # Unmeasured values remain conservative estimates of failure, not observations.
    predicted={c['point_id']:bool(positives&(1<<i)) for i,c in enumerate(CELLS)}
    eligible=(n>=8 and not mixed and bool(candidates) and max_unseen_successes<=1)
    snapshot=dict(version=VERSION,catalog_sha256=digest(list(hypothesis_catalog())),
        hypothesis_count=len(hypothesis_catalog()),consistent_hypotheses=len(candidates),
        seen_mask=seen,observed_pass_mask=positives,mixed_repeats=mixed,
        max_unseen_successes_under_catalog=max_unseen_successes,
        input_sha256=digest(history),scope='STRUCTURED_FINITE_CATALOG_ONLY_NOT_CALIBRATED',
        arbitrary_hidden_islands_guaranteed=False,unobserved_pass_predictions=0,
        posterior_probability_calibrated=False)
    if n==10 or (n>=8 and (eligible or mixed or not candidates)):
        return dict(action='FREEZE',estimate_ready=eligible,
            predictions=predicted if eligible else None,model_snapshot=snapshot,
            reason='CONSERVATIVE_CATALOG_ESTIMATE_REQUIRES_BLIND_REVIEW' if eligible else
                'MIXED_REPEATS_NO_RAPID_ESTIMATE' if mixed else
                'CATALOG_INCONSISTENT_NO_RAPID_ESTIMATE' if not candidates else 'TEN_POINT_LIMIT_NO_ESTIMATE')
    choices=[]
    for i,c in enumerate(CELLS):
        if seen&(1<<i):continue
        p=sum(bool(m&(1<<i)) for m in candidates)/len(candidates) if candidates else .5
        entropy=0 if p in (0,1) else -p*math.log(p,2)-(1-p)*math.log(1-p,2)
        # Cover probable PASS cells (never predict them unseen), with information gain.
        score=p+.5*entropy
        choices.append((score,-c['phase'],-c['width'],c['point_id']))
    chosen=max(choices)[3]
    return dict(action='SELECT',point_id=chosen,estimate_ready=False,
        model_snapshot=snapshot,reason='PASS_COVERAGE_AND_VERSION_DISAGREEMENT')
