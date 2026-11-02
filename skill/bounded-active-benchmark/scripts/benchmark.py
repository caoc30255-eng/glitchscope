"""Offline policy API / same-budget evaluation. Synthetic fixtures are never hardware data."""
import argparse,copy,hashlib,json,math,sys
from pathlib import Path
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def category(outcomes):
    if not outcomes or any(type(v) is not bool for v in outcomes):raise ValueError('OUTCOMES_MUST_BE_KNOWN_BOOLS')
    return 'PASS' if all(outcomes) else 'FAIL' if not any(outcomes) else 'MIXED'
def validate(e):
    if type(e.get('schema')) is not int or e.get('schema')!=1 or e.get('origin')!='SYNTHETIC_ONLY':raise ValueError('DEMO_IS_SYNTHETIC_ONLY')
    domain=e['domain'];ids=[p['id'] for p in domain]
    if not domain or len(ids)!=len(set(ids)) or any(type(i) is not str for i in ids):raise ValueError('DOMAIN_IDS')
    for n in ['budget','setup_records','repeats','max_groups_per_point']:
        if type(e[n]) is not int or e[n]<(0 if n=='setup_records' else 1):raise ValueError('FINITE_BUDGET')
    if e['max_groups_per_point']!=1:raise ValueError('FIXED_TABLE_ONLY_ONE_GROUP_USE_NOISY_CAMPAIGN_FOR_REPEATS')
    if e['budget']<e['setup_records']+e['repeats']:raise ValueError('BUDGET_CANNOT_FUND_ONE_GROUP')
    if set(e['reference'])!=set(ids):raise ValueError('REFERENCE_DOMAIN')
    for values in e['reference'].values():
        if len(values)!=e['repeats']:raise ValueError('REFERENCE_REPEAT_COUNT')
        category(values)
    for a,b in e['adjacency']:
        if a==b or a not in ids or b not in ids:raise ValueError('ADJACENCY')
    # Candidate descriptors may contain input coordinates/context only, never reference labels.
    for p in domain:
        if set(p)!={'id','coordinates'} or not isinstance(p['coordinates'],list) or not p['coordinates'] or any(type(v) is not int for v in p['coordinates']):raise ValueError('DOMAIN_INPUT_FIELDS')
    if len({len(p['coordinates']) for p in domain})!=1:raise ValueError('COORDINATE_DIMENSIONS')
    return e
def snapshot(e,observed,groups,remaining):
    return dict(domain=copy.deepcopy(e['domain']),observed=copy.deepcopy(observed),groups_per_point=dict(groups),remaining_records=remaining,repeats=e['repeats'],max_groups_per_point=e['max_groups_per_point'])
def coverage_policy(s):
    for p in s['domain']:
        if p['id'] not in s['observed']:return p['id']
    return None
def boundary_policy(s):
    # Demonstration rule only, not a learned AI policy. The reference is not passed here.
    known=s['observed'];unseen=[p for p in s['domain'] if p['id'] not in known]
    if not unseen:return None
    mixed=[p for p in s['domain'] if p['id'] in known and category(known[p['id']])=='MIXED']
    if mixed:
        return min(unseen,key=lambda p:(min(sum(abs(x-y) for x,y in zip(p['coordinates'],q['coordinates'])) for q in mixed),p['id']))['id']
    return unseen[-1]['id'] if len(known)%2 else unseen[0]['id']
def simulate(experiment,choose):
    e=validate(copy.deepcopy(experiment));observed={};groups={};events=[];used=e['setup_records'];previous='0'*64;terminal='STOPPED_BUDGET'
    while used+e['repeats']<=e['budget']:
        prefix=snapshot(e,observed,groups,e['budget']-used);prefix_hash=digest(prefix)
        point=choose(copy.deepcopy(prefix))
        if point is None:terminal='STOPPED_POLICY';break
        if point not in e['reference']:raise ValueError('OUT_OF_DOMAIN_SELECTION')
        if groups.get(point,0)>=e['max_groups_per_point']:raise ValueError('PER_POINT_LIMIT')
        # Save decision and its input commitment before revealing this group's outcomes.
        event=dict(index=len(events),previous=previous,input=prefix,input_sha256=prefix_hash,chosen=point)
        event['decision_sha256']=digest(event)
        outcomes=list(e['reference'][point]);event['outcomes']=outcomes
        previous=digest(event);event['event_sha256']=previous;events.append(event)
        observed.setdefault(point,[]).extend(outcomes);groups[point]=groups.get(point,0)+1;used+=e['repeats']
    run=dict(schema=1,origin='SYNTHETIC_ONLY',experiment_sha256=digest(e),used_records=used,setup_records=e['setup_records'],events=events,terminal=terminal,physical_STARTs=0,wall_seconds=None)
    replay(e,run)
    return run
def replay(e,run):
    validate(e)
    if run.get('origin')!='SYNTHETIC_ONLY' or run['experiment_sha256']!=digest(e):raise ValueError('RUN_CONTEXT_BINDING')
    observed={};groups={};used=e['setup_records'];previous='0'*64
    for index,event in enumerate(run['events']):
        prefix=snapshot(e,observed,groups,e['budget']-used)
        if event['index']!=index or event['previous']!=previous or digest(event['input'])!=digest(prefix) or event['input_sha256']!=digest(prefix):raise ValueError('PREFIX_ORDER_OR_LEAK')
        decision={k:v for k,v in event.items() if k not in ('decision_sha256','outcomes','event_sha256')}
        if digest(decision)!=event['decision_sha256']:raise ValueError('DECISION_HASH')
        payload={k:v for k,v in event.items() if k!='event_sha256'}
        if digest(payload)!=event['event_sha256']:raise ValueError('EVENT_HASH')
        point=event['chosen']
        if point not in e['reference'] or groups.get(point,0)>=e['max_groups_per_point']:raise ValueError('DOMAIN_OR_REPEAT_LIMIT')
        if used+e['repeats']>e['budget']:raise ValueError('BUDGET_EXCEEDED')
        if event['outcomes']!=e['reference'][point] or any(type(v) is not bool for v in event['outcomes']):raise ValueError('KNOWN_FEEDBACK_REQUIRED')
        observed.setdefault(point,[]).extend(event['outcomes']);groups[point]=groups.get(point,0)+1;used+=e['repeats'];previous=event['event_sha256']
    if used!=run['used_records']:raise ValueError('COUNTER_MISMATCH')
    if run['setup_records']!=e['setup_records'] or run.get('physical_STARTs')!=0 or run.get('wall_seconds') is not None:raise ValueError('SYNTHETIC_SCOPE')
    if run['terminal'] not in ('STOPPED_POLICY','STOPPED_BUDGET'):raise ValueError('TERMINAL')
    if run['terminal']=='STOPPED_BUDGET' and used+e['repeats']<=e['budget']:raise ValueError('FALSE_BUDGET_STOP')
    return observed
def evaluate(e,run):
    observed=replay(e,run);truth={p:category(v) for p,v in e['reference'].items()};boundary=set()
    for a,b in e['adjacency']:
        if truth[a]!=truth[b]:boundary.update([a,b])
    visited=set(observed)
    return dict(records=run['used_records'],unique_conditions=len(visited),domain_coverage=len(visited)/len(e['domain']),boundary_points_touched=len(visited&boundary),boundary_points_total=len(boundary),
                mixed_points_touched=sum(truth[p]=='MIXED' for p in visited),observed_classes={p:category(v) for p,v in observed.items()},
                full_map_observed=len(visited)==len(e['domain']),hardware_speedup_accepted=False,statistical_superiority_proven=False)
def compare(e,runs):
    if len(runs)<2:raise ValueError('TWO_POLICIES_REQUIRED')
    results={name:evaluate(e,run) for name,run in runs.items()}
    counts={r['records'] for r in results.values()}
    return dict(status='SYNTHETIC_POLICY_CONTRACT_COMPARISON',results=results,equal_actual_records=len(counts)==1,common_declared_budget=e['budget'],
                same_declared_budget_not_same_actual_spend=len(counts)!=1,wall_time_gain_not_evaluated=True,hardware_access=False,
                scope='A small synthetic reference table and API-level information separation; not an OS sandbox, learned-model validation, future-condition generalization or physical experiment')
def main():
    p=argparse.ArgumentParser();p.add_argument('--experiment',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    e=validate(json.loads(Path(a.experiment).read_text(encoding='utf-8')));out=Path(a.output);out.mkdir()
    runs={name:simulate(e,policy) for name,policy in [('coverage',coverage_policy),('boundary_rule',boundary_policy)]}
    for name,run in runs.items():(out/(name+'.json')).write_text(json.dumps(run,indent=2),encoding='utf-8')
    result=compare(e,runs);(out/'report.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
