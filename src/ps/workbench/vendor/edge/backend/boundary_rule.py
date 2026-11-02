"""Deterministic boundary search. Two declared anchors then current-feedback rules.
No IO, future labels, hardware access, trained weights or measured-map completion.
"""
import math
from learning_domain import CELLS,BY_ID,digest
from conservative_model import hypothesis_catalog
VERSION='BOUNDARY_BRACKET_EXPLORATION_RULE_V0_2'
POLICY=dict(version=VERSION,anchor_phase=15,anchor_widths=[1,30],
    initial_anchors=2,stable_successes=[0,3],mixed_successes=[1,2],
    cross_phase_if_single_phase_after_batches=3,priority='NARROW_OPPOSITE_OBSERVATION_BRACKET_THEN_INFORMATION_AND_COVERAGE',
    success_probability_reward=False,monotonicity_assumed=False,forecast_heatmap_allowed=False)
INDEX={c['point_id']:i for i,c in enumerate(CELLS)}
FULL=(1<<len(CELLS))-1

def tier(width):return 'SHORT' if width==1 else 'MEDIUM' if width in (10,20) else 'LONG'
def entropy(prob):return 0.0 if prob in (0.0,1.0) else -prob*math.log(prob,2)-(1-prob)*math.log(1-prob,2)
def distance(a,b):return ((a['phase']-b['phase'])/30.0)**2+((a['width']-b['width'])/39.0)**2

def decide(batches):
    if not isinstance(batches,(list,tuple)) or len(batches)>len(CELLS):raise ValueError('BOUNDED_CHECKED_HISTORY_REQUIRED')
    history=[];seen=hard_seen=positive=0;observed=[];stable=[]
    for r in batches:
        if type(r) is not dict or r.get('point_id') not in BY_ID or type(r.get('successes')) is not int or not 0<=r['successes']<=3:
            raise ValueError('EXACT_POINT_AND_THREE_REPEAT_COUNT_REQUIRED')
        point=r['point_id'];successes=r['successes'];bit=1<<INDEX[point]
        if seen&bit:raise ValueError('POINT_REPLAY')
        seen|=bit;history.append(dict(point_id=point,successes=successes));observed.append(BY_ID[point])
        # A mixed triplet stays uncertain; do not force majority into a hard hypothesis label.
        if successes in (0,3):
            hard_seen|=bit
            if successes==3:positive|=bit
            stable.append((BY_ID[point],successes==3))
    if [r['point_id'] for r in history[:2]]!=['p15_w1','p15_w30'][:min(len(history),2)]:raise ValueError('DECLARED_ANCHOR_PREFIX_REQUIRED')
    catalog=hypothesis_catalog();support=[m for m in catalog if m&hard_seen==positive]
    stats=dict(version=VERSION,policy_sha256=digest(POLICY),input_sha256=digest(history),
        observed_mask=seen,hard_constraint_mask=hard_seen,observed_stable_pass_mask=positive,
        mixed_points=[r['point_id'] for r in history if r['successes'] in (1,2)],
        observed_B_successes=[r['successes'] for r in history],
        hypothesis_count=len(catalog),consistent_hypotheses=len(support),catalog_sha256=digest(list(catalog)),
        support_scope='AUXILIARY_FINITE_CATALOG_DISAGREEMENT_NOT_CALIBRATED',
        posterior_probability_calibrated=False,monotonicity_assumed=False,unobserved_measurements_created=0)
    remaining=[c for i,c in enumerate(CELLS) if not seen&(1<<i)]
    if not remaining:return dict(action='FREEZE',estimate_ready=False,predictions=None,model_snapshot=stats,reason='DECLARED_DOMAIN_EXHAUSTED_NO_INFERRED_MEASUREMENTS')
    reasons=[];brackets=[]
    for i,(a,ya) in enumerate(stable):
        for b,yb in stable[i+1:]:
            if a['phase']!=b['phase'] or ya==yb:continue
            lo,hi=sorted((a['width'],b['width']))
            interior=[c for c in remaining if c['phase']==a['phase'] and lo<c['width']<hi]
            if interior:brackets.append(dict(phase=a['phase'],lo=lo,hi=hi,span=hi-lo,midpoint=(hi+lo)/2,interior_ids=[c['point_id'] for c in interior]))
    brackets.sort(key=lambda b:(b['span'],b['phase'],b['lo']))
    bracket=brackets[0] if brackets else None
    phases={c['phase'] for c in observed};tiers={tier(c['width']) for c in observed}
    # Initial anchors are deliberately explicit, not disguised as feedback learning.
    if not history:mode='ANCHOR_SHORT';pool=[BY_ID['p15_w1']]
    elif len(history)==1:
        # This plan permits only the declared first anchor before the long anchor.
        if history[0]['point_id']!='p15_w1':raise ValueError('DECLARED_ANCHOR_HISTORY_REQUIRED')
        mode='ANCHOR_LONG';pool=[BY_ID['p15_w30']]
    elif len(history)>=3 and len(phases)==1:
        mode='CROSS_PHASE_CHECK';pool=[c for c in remaining if c['phase'] not in phases]
    elif bracket is not None:
        mode='OBSERVED_OPPOSITE_BRACKET';pool=[BY_ID[k] for k in bracket['interior_ids']]
    else:
        mode='EXPLORE_UNRESOLVED_DOMAIN';pool=remaining
    traces=[]
    for c in remaining:
        bit=1<<INDEX[c['point_id']]
        prob=sum(bool(m&bit) for m in support)/len(support) if support else .5
        info=entropy(prob);novelty=min([distance(c,o) for o in observed] or [1.0])
        new_tier=tier(c['width']) not in tiers;new_phase=c['phase'] not in phases
        midpoint_distance=abs(c['width']-bracket['midpoint']) if bracket else 0.0
        if mode=='OBSERVED_OPPOSITE_BRACKET':key=(-midpoint_distance,info,novelty,-c['phase'],-c['width'])
        elif mode=='CROSS_PHASE_CHECK' and bracket:
            key=(-midpoint_distance,info,novelty,-c['phase'],-c['width'])
        else:key=(int(new_tier),int(new_phase),info,novelty,-c['phase'],-c['width'])
        traces.append(dict(point_id=c['point_id'],eligible=c in pool,
            catalog_disagreement=info,minimum_normalized_distance=novelty,
            width_tier=tier(c['width']),new_width_tier=new_tier,new_phase=new_phase,
            midpoint_distance_if_bracket=midpoint_distance if bracket else None,rank=list(key)))
    eligible=[t for t in traces if t['eligible']];chosen=max(eligible,key=lambda t:tuple(t['rank']))
    return dict(action='SELECT',point_id=chosen['point_id'],estimate_ready=False,
        model_snapshot=stats,reason=mode,policy_sha256=digest(POLICY),
        observed_opposite_bracket=bracket,candidate_ranking=traces,
        selection_is_hardware_measurement=False,first_two_points_are_declared_anchors=True)
