"""Reviewed finite-domain adapter to OSS model + entropy acquisition."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent/'oss_runtime'))
from oss_portable import STRATEGY,PortableForest,rank,require

def suggest(plan,records,session,remaining_records,target=None,confirmed_domain_sha256=None):
    from custom_plan import validate_plan,TARGETS
    from custom_stats import aggregate
    from learning_domain import digest
    out=dict(action='ABSTAIN',hardware_permission=False,training_model_used=False,rule_version=STRATEGY)
    try:
        validate_plan(plan);policy=plan['request']['edge_ai'];require(policy['strategy']==STRATEGY,'OSS_POLICY_VERSION')
        target=plan['target'] if target is None else target;require(target in TARGETS,'TARGET')
        require(type(remaining_records) is int and remaining_records==plan['max_records']-len(records),'EXACT_REMAINING_BUDGET')
        require(confirmed_domain_sha256==digest(plan['conditions']),'CONFIRMED_DOMAIN_SHA')
        state=aggregate(plan,records,session);out.update(plan_sha256=plan['sha256'],domain_sha256=confirmed_domain_sha256,input_sha256=state['input_sha256'],target=target)
        if state['state']=='BLOCKED_UNKNOWN':return dict(out,reason='UNKNOWN_BLOCKS_SELECTION')
        if any(c['per_target'][target]['state']=='PARTIAL' for c in state['conditions']):return dict(out,reason='PARTIAL_REPEAT_GROUP_BLOCKS_SELECTION')
        need=plan['refinement']['confirmation_repeats']
        if remaining_records<need:return dict(out,action='STOP_BUDGET',reason='INSUFFICIENT_BUDGET_FOR_FULL_REPEAT_GROUP')
        if not plan['refinement']['enabled']:return dict(out,action='STOP',reason='REFINEMENT_NOT_ENABLED')
        if not state['coarse_domain_complete']:return dict(out,action='WAIT',reason='COMPLETE_DECLARED_COARSE_QUEUE_FIRST')
        sha=policy['model_file_sha256'];model=PortableForest(Path(__file__).resolve().parent/'oss_runtime/models'/(sha+'.json'),sha)
        candidates=rank(state['conditions'],target,model,need,policy['max_extra_groups'])
        if not policy['allow_rule_fallback']:candidates=[r for r in candidates if r['model_used']]
        if not candidates:return dict(out,action='STOP',reason='NO_ELIGIBLE_MEASUREMENTS_OR_MODEL_SUPPORT')
        chosen=candidates[0]
        result=dict(out,action='SELECT',condition=chosen['condition'],condition_id=chosen['condition_id'],
            reason=chosen['reason'],required_records=need,budget_after=remaining_records-need,
            training_model_used=chosen['model_used'],model_sha256=model.model_sha256,model_file_sha256=sha,
            policy_sha256=digest(policy),selected_model_prediction=chosen['model_prediction'],
            candidate_ranking=[{k:v for k,v in r.items() if k!='condition'} for r in candidates],
            prediction_is_measurement=False,feedback_retrains_global_model=False,
            acquisition_reference='scikit-activeml 1.0.1 entropy normalized from nats to bits + declared coverage/repeat guards')
        result['selection_sha256']=digest(result);return result
    except (OSError,KeyError,TypeError,ValueError) as error:return dict(out,reason=str(error),blocked_input=True)
