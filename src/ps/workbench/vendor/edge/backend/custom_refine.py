"""Deterministic finite-domain refinement; no interpolation, monotonicity or model."""
from custom_plan import require,validate_plan,TARGETS
from custom_stats import aggregate
from learning_domain import digest
from boundary_rule import decide as legacy_decide,VERSION as LEGACY_VERSION
from learning_domain import CELLS

def legacy_choice(plan,cells,target):
    """Reuse exact v0.2 when its grid/triplets/anchor-prefix contract applies."""
    if plan['mode']!='TYPE3A_SINGLE':return None
    if plan['repeats']!=3 or plan['refinement']['confirmation_repeats']!=3:return None
    lookup={(c['condition']['fault']['phase'],c['condition']['fault']['width']):c for c in cells}
    if len(lookup)!=len(cells) or set(lookup)!={(c['phase'],c['width']) for c in CELLS}:return None
    if len({(c['condition']['fault']['byte'],c['condition']['fault']['bit']) for c in cells})!=1:return None
    observed=sorted((c for c in cells if c['per_target'][target]['valid']),key=lambda c:min(r['record_id'] for r in c['record_refs']))
    if any(c['per_target'][target]['valid']!=3 for c in observed):return None
    batches=[dict(point_id='p%d_w%d'%(c['condition']['fault']['phase'],c['condition']['fault']['width']),successes=c['per_target'][target]['success']) for c in observed]
    if [b['point_id'] for b in batches[:2]]!=['p15_w1','p15_w30'][:min(len(batches),2)]:return None
    choice=legacy_decide(batches)
    if choice['action']!='SELECT':return None
    return next((c['condition'] for c in cells if 'p%d_w%d'%(c['condition']['fault']['phase'],c['condition']['fault']['width'])==choice['point_id']),None)

def rule_suggest(plan,records,session,remaining_records,target=None,confirmed_domain_sha256=None):
    out=dict(action='ABSTAIN',hardware_permission=False,training_model_used=False)
    try:
        validate_plan(plan);target=plan['target'] if target is None else target;require(target in TARGETS,'TARGET')
        require(type(remaining_records) is int and remaining_records==plan['max_records']-len(records),'EXACT_REMAINING_BUDGET')
        require(confirmed_domain_sha256==digest(plan['conditions']),'CONFIRMED_DOMAIN_SHA')
        state=aggregate(plan,records,session);out.update(plan_sha256=plan['sha256'],domain_sha256=confirmed_domain_sha256,input_sha256=state['input_sha256'],target=target)
        if state['state']=='BLOCKED_UNKNOWN':return dict(out,reason='UNKNOWN_BLOCKS_SELECTION')
        need=plan['refinement']['confirmation_repeats']
        if remaining_records<need:return dict(out,action='STOP_BUDGET',reason='INSUFFICIENT_BUDGET_FOR_CONFIRMED_REPEAT_GROUP',required_records=need)
        if not plan['refinement']['enabled']:return dict(out,action='STOP',reason='REFINEMENT_NOT_ENABLED')
        scored=[];cells=state['conditions']
        stable=[c for c in cells if c['per_target'][target]['state'] in ('OBSERVED_ALL_PASS','OBSERVED_ALL_FAIL')]
        for cell in cells:
            v=cell['per_target'][target];c=cell['condition'];reason=None;rank=None
            if v['state']=='PARTIAL':return dict(out,reason='PARTIAL_GROUP_MUST_FINISH_OR_STOP')
            if v['state']=='MIXED':rank=(0,v['valid'],c['condition_id']);reason='CONFIRM_OBSERVED_MIXED_REGION'
            elif v['state']=='UNMEASURED':
                bracket=False
                for a in stable:
                    for b in stable:
                        av=a['per_target'][target];bv=b['per_target'][target];af=a['condition']['fault'];bf=b['condition']['fault'];cf=c['fault']
                        same_context=all(a['condition'][k]==c[k] and b['condition'][k]==c[k] for k in ('receiver_B','payload_sha256','route_mode','mode','count')) and all(af[k]==cf[k] and bf[k]==cf[k] for k in ('byte','bit'))
                        opposite={av['state'],bv['state']}=={'OBSERVED_ALL_PASS','OBSERVED_ALL_FAIL'}
                        if same_context and opposite and af['phase']==bf['phase']==cf['phase'] and min(af['width'],bf['width'])<cf['width']<max(af['width'],bf['width']):bracket=True
                rank=(1 if bracket else 2,0,c['condition_id']);reason='OBSERVED_OPPOSITE_BRACKET_NO_MONOTONIC_CLAIM' if bracket else 'UNMEASURED_CONFIRMED_CONDITION'
            if rank is not None:scored.append((rank,c,reason))
        if not scored:return dict(out,action='STOP',reason='NO_MIXED_OR_UNMEASURED_CONFIRMED_CONDITION')
        _,c,reason=min(scored,key=lambda row:row[0])
        rule='CUSTOM_FINITE_CONFIRMED_DOMAIN_RULE_V0_1'
        if not any(x['per_target'][target]['state']=='MIXED' for x in cells):
            legacy=legacy_choice(plan,cells,target)
            if legacy is not None:c=legacy;reason='UNCHANGED_V0_2_GRID_TRIPLET_RULE';rule=LEGACY_VERSION
        result=dict(out,action='SELECT',condition=c,condition_id=c['condition_id'],reason=reason,rule_version=rule,required_records=need,budget_after=remaining_records-need)
        result['selection_sha256']=digest(result);return result
    except (ValueError,TypeError,KeyError) as error:return dict(out,reason=str(error))


def suggest(plan,records,session,remaining_records,target=None,confirmed_domain_sha256=None):
    if type(plan) is dict and plan.get('request',{}).get('edge_ai') is not None:
        from custom_ai_policy import suggest as ai_suggest
        return ai_suggest(plan,records,session,remaining_records,target,confirmed_domain_sha256)
    return rule_suggest(plan,records,session,remaining_records,target,confirmed_domain_sha256)
