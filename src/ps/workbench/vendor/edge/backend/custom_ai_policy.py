"""Model-assisted finite-domain selection. This module never grants START."""
from pathlib import Path
import math,json
from custom_ai_core import load_model,query,require,digest as model_digest

ROOT=Path(__file__).resolve().parent
VERSION='EDGE_AI_HYBRID_BOUNDARY_V1'

def validate_policy(policy):
    require(type(policy) is dict and set(policy)=={'strategy','model_file_sha256','max_extra_groups','allow_rule_fallback'},'AI_POLICY_FIELDS')
    require(policy['strategy'] in (VERSION,'EDGE_AI_OSS_ENTROPY_COVERAGE_V1'),'AI_STRATEGY_VERSION')
    sha=policy['model_file_sha256'];require(type(sha) is str and len(sha)==64 and all(c in '0123456789abcdef' for c in sha),'AI_MODEL_SHA')
    require(type(policy['max_extra_groups']) is int and 0<=policy['max_extra_groups']<=2 and type(policy['allow_rule_fallback']) is bool,'AI_POLICY_LIMITS')
    return True

def model_for(policy):
    if type(policy) is dict and policy.get('strategy')=='EDGE_AI_OSS_ENTROPY_COVERAGE_V1':
        validate_policy(policy)
        from oss_policy import PortableForest
        return PortableForest(ROOT/'oss_runtime/models'/(policy['model_file_sha256']+'.json'),policy['model_file_sha256'])
    validate_policy(policy);path=ROOT/'models'/(policy['model_file_sha256']+'.json')
    return load_model(path,policy['model_file_sha256'])

def as_query(condition,target):
    f=condition['fault'];b=condition['receiver_B']
    return query(d=b['d'],s=b['s'],phase=f['phase'],width=f['width'],byte=f['byte'],bit=f['bit'],count=condition['count'],
        payload_sha256=condition['payload_sha256'],mode=condition['mode'],route_mode=condition['route_mode'],target=target)

def rank_cells(cells,target,model,need,max_extra_groups):
    measured=[c for c in cells if c['per_target'][target]['valid']]
    candidates=[]
    for cell in cells:
        c=cell['condition'];v=cell['per_target'][target];prediction=model.predict(as_query(c,target))
        n=v['valid'];success=v['success'];prior=prediction['score']
        if n and n>=max(v['required'],need)*(1+max_extra_groups):continue
        disagreement=n>0 and prior is not None and abs(prior-success/n)>.5
        if n and v['state']!='MIXED' and not disagreement:continue
        posterior=None if prior is None else (2*prior+success)/(2+n)
        uncertainty=1.0 if posterior is None else 1-abs(2*posterior-1)
        # Group bootstrap describes model spread, not within-condition noise.
        # Keep known repeat conflict visible instead of treating ensemble
        # agreement as physical stability.
        repeat_noise=prediction.get('training_repeat_disagreement',0.0)*2/(2+n)
        if n:repeat_noise=max(repeat_noise,4*(success/n)*(1-success/n))
        uncertainty=max(uncertainty,repeat_noise)
        spread=0 if prior is None else prediction['ensemble_interval'][1]-prediction['ensemble_interval'][0]
        f=c['fault']
        novelty=min((abs(f['phase']-m['condition']['fault']['phase'])/40+abs(f['width']-m['condition']['fault']['width'])/40 for m in measured),default=1.0)
        novelty=min(1.0,novelty)
        if n:
            score=(.65*uncertainty+.20*spread+.15)/(1+.5*n/need)
            reason='CONFIRM_CURRENT_MIXED' if v['state']=='MIXED' else 'RECHECK_MODEL_OBSERVATION_DISAGREEMENT'
        else:
            score=.50*uncertainty+.20*spread+.20*novelty+.10
            reason='MODEL_BOUNDARY_AND_COVERAGE' if prior is not None else 'RULE_EXPLORATION_OUTSIDE_MODEL_SUPPORT'
        candidates.append(dict(condition=c,condition_id=c['condition_id'],priority=round(score,12),reason=reason,
            model_used=prior is not None,model_prediction=prediction,current_valid=n,current_success=success,
            session_posterior_score=posterior,repeat_disagreement_component=repeat_noise,session_score_is_reliability=False))
    observed_phases={c['condition']['fault']['phase'] for c in measured}
    if len(measured)>=3 and len(observed_phases)==1:
        outside=[r for r in candidates if r['condition']['fault']['phase'] not in observed_phases]
        if outside:
            candidates=outside
            for row in candidates:row['reason']+='__CROSS_PHASE_COVERAGE'
    return sorted(candidates,key=lambda x:(-x['priority'],x['condition_id']))

def suggest(plan,records,session,remaining_records,target=None,confirmed_domain_sha256=None):
    if type(plan) is dict and type(plan.get('request',{}).get('edge_ai')) is dict and plan['request']['edge_ai'].get('strategy')=='EDGE_AI_OSS_ENTROPY_COVERAGE_V1':
        from oss_policy import suggest as oss_suggest
        return oss_suggest(plan,records,session,remaining_records,target,confirmed_domain_sha256)
    from custom_plan import validate_plan,TARGETS
    from custom_stats import aggregate
    from learning_domain import digest
    from custom_refine import rule_suggest
    out=dict(action='ABSTAIN',hardware_permission=False,training_model_used=False,rule_version=VERSION)
    try:
        validate_plan(plan);policy=plan['request']['edge_ai'];validate_policy(policy)
        target=plan['target'] if target is None else target;require(target in TARGETS,'TARGET')
        require(type(remaining_records) is int and remaining_records==plan['max_records']-len(records),'EXACT_REMAINING_BUDGET')
        require(confirmed_domain_sha256==digest(plan['conditions']),'CONFIRMED_DOMAIN_SHA')
        state=aggregate(plan,records,session);out.update(plan_sha256=plan['sha256'],domain_sha256=confirmed_domain_sha256,input_sha256=state['input_sha256'],target=target)
        if state['state']=='BLOCKED_UNKNOWN':return dict(out,reason='UNKNOWN_BLOCKS_SELECTION')
        if any(c['per_target'][target]['state']=='PARTIAL' for c in state['conditions']):return dict(out,reason='PARTIAL_REPEAT_GROUP_BLOCKS_SELECTION')
        need=plan['refinement']['confirmation_repeats']
        if remaining_records<need:return dict(out,action='STOP_BUDGET',reason='INSUFFICIENT_BUDGET_FOR_FULL_REPEAT_GROUP',required_records=need)
        if not plan['refinement']['enabled']:return dict(out,action='STOP',reason='REFINEMENT_NOT_ENABLED')
        if not state['coarse_domain_complete']:return dict(out,action='WAIT',reason='COMPLETE_DECLARED_COARSE_QUEUE_FIRST')
        model=model_for(policy);ranked=rank_cells(state['conditions'],target,model,need,policy['max_extra_groups'])
        out.update(model_sha256=model.model_sha256,model_file_sha256=policy['model_file_sha256'],policy_sha256=digest(policy))
        if not ranked:return dict(out,action='STOP',reason='ALL_FINITE_CONDITIONS_MEASURED_OR_REPEAT_CAP_REACHED')
        if not any(r['model_used'] for r in ranked):
            if not policy['allow_rule_fallback']:return dict(out,reason='MODEL_SUPPORT_ABSENT_FALLBACK_DISABLED')
            legacy=rule_suggest(plan,records,session,remaining_records,target=target,confirmed_domain_sha256=confirmed_domain_sha256)
            allowed={r['condition_id'] for r in ranked}
            chosen=next((r for r in ranked if r['condition_id']==legacy.get('condition_id')),ranked[0])
            reason='RULE_FALLBACK_UNSUPPORTED_CONTEXT'
        else:chosen=ranked[0];reason=chosen['reason']
        result=dict(out,action='SELECT',condition=chosen['condition'],condition_id=chosen['condition_id'],reason=reason,
            required_records=need,budget_after=remaining_records-need,training_model_used=chosen['model_used'],
            selected_model_prediction=chosen['model_prediction'],session_posterior_score=chosen['session_posterior_score'],
            candidate_ranking=[{k:v for k,v in r.items() if k!='condition'} for r in ranked],
            prediction_is_measurement=False,feedback_retrains_global_model=False)
        result['selection_sha256']=digest(result);return result
    except (ValueError,KeyError,TypeError,OSError) as error:return dict(out,reason=str(error),blocked_input=True)
