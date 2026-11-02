"""Bounded collector API, fresh noisy observations and campaign-level paired intervals."""
import argparse,copy,hashlib,json,math,random,statistics,time
from pathlib import Path
from benchmark import category,digest
def wilson(successes,total,z=1.959963984540054):
    if total<=0:return None
    p=successes/total;d=1+z*z/total;c=(p+z*z/(2*total))/d
    half=z*math.sqrt(p*(1-p)/total+z*z/(4*total*total))/d
    return [max(0,c-half),min(1,c+half)]
def paired_interval(a,b,resamples=2000,seed=7):
    if len(a)!=len(b) or len(a)<2:raise ValueError('PAIRED_CAMPAIGNS_REQUIRED')
    if type(resamples) is not int or not 200<=resamples<=20000:raise ValueError('BOOTSTRAP_RESAMPLES_RANGE')
    delta=[x-y for x,y in zip(a,b)];rng=random.Random(seed);n=len(delta)
    draws=sorted(statistics.mean(delta[rng.randrange(n)] for _ in range(n)) for _ in range(resamples))
    return dict(mean_difference=statistics.mean(delta),ci95=[draws[int(.025*(resamples-1))],draws[int(.975*(resamples-1))]],method='paired percentile bootstrap across campaigns',campaigns=n)
def public_plan(e):
    keys=['context','domain','budget','setup_records','repeats','max_groups_per_point']
    p={k:copy.deepcopy(e[k]) for k in keys}
    ids=[x['id'] for x in p['domain']]
    if not ids or any(type(i) is not str for i in ids) or len(ids)!=len(set(ids)):raise ValueError('DOMAIN')
    if len({len(x['coordinates']) for x in p['domain']})!=1:raise ValueError('COORDINATE_DIMENSIONS')
    for x in p['domain']:
        if set(x)!={'id','coordinates'} or any(type(v) is not int for v in x['coordinates']):raise ValueError('DOMAIN_INPUT_FIELDS')
    for n in ['budget','setup_records','repeats','max_groups_per_point']:
        if type(p[n]) is not int or p[n]<(0 if n=='setup_records' else 1):raise ValueError('FINITE_PLAN')
    if p['budget']<p['setup_records']+p['repeats']:raise ValueError('BUDGET')
    digest(p);return p
def coverage(s):
    return next((p['id'] for p in s['domain'] if p['id'] not in s['observed']),None)
def confirm_mixed(s):
    for p in s['domain']:
        name=p['id']
        if name in s['observed'] and category(s['observed'][name])=='MIXED' and s['groups_per_point'].get(name,0)<s['max_groups_per_point']:return name
    return coverage(s)
def run_policy(plan,choose,collector,run_id,origin='SYNTHETIC_ONLY',on_attempt=None,evidence_verifier=None,on_result=None):
    plan=public_plan(plan)
    if origin not in ('SYNTHETIC_ONLY','ADAPTER_REPORTED'):raise ValueError('ORIGIN')
    if origin=='ADAPTER_REPORTED' and (not callable(on_attempt) or not callable(evidence_verifier) or not callable(on_result)):raise ValueError('DURABLE_ATTEMPT_AND_RAW_VERIFIER_REQUIRED')
    observed={};groups={};records=[];decisions=[];used=0;terminal='STOPPED_BUDGET';started=time.perf_counter();previous='0'*64
    ids={p['id'] for p in plan['domain']}
    def collect(kind,point,index):
        nonlocal used,previous
        request=dict(run_id=run_id,record_id='r%05d'%used,kind=kind,point_id=point,repeat_index=index,context_sha256=digest(plan['context']))
        request_sha=digest(request);used+=1 # Occupied before invoking a potentially non-idempotent collector.
        begin=time.perf_counter()
        try:
            if on_attempt:on_attempt(copy.deepcopy(request))
            reply=collector(copy.deepcopy(request))
            if not isinstance(reply,dict) or reply.get('request_sha256')!=request_sha or reply.get('record_id')!=request['record_id']:raise ValueError('RECEIPT_IDENTITY')
            if reply.get('status')!='VALID':raise ValueError('UNKNOWN_OR_INVALID_RECEIPT')
            value=reply.get('outcome')
            if kind=='ITEM' and type(value) is not bool:raise ValueError('UNKNOWN_IS_NOT_FALSE')
            if kind=='SETUP' and value is not None:raise ValueError('SETUP_OUTCOME')
            if origin=='ADAPTER_REPORTED' and evidence_verifier(request,reply) is not True:raise ValueError('RAW_EVIDENCE_NOT_VERIFIED')
            row=dict(request=request,request_sha256=request_sha,status='VALID',outcome=value,previous=previous,receipt=reply)
        except Exception as e:row=dict(request=request,request_sha256=request_sha,status='UNKNOWN',outcome=None,previous=previous,error=str(e))
        if on_result:
            try:on_result(copy.deepcopy(request),copy.deepcopy(row))
            except Exception as e:row.update(status='UNKNOWN',outcome=None,error='RESULT_JOURNAL_FAILURE:'+str(e))
        row['collector_and_journal_seconds']=time.perf_counter()-begin;row['sha256']=digest(row);previous=row['sha256'];records.append(row)
        return row
    for i in range(plan['setup_records']):
        if collect('SETUP',None,i)['status']!='VALID':terminal='BLOCKED_UNKNOWN';break
    else:
        while used+plan['repeats']<=plan['budget']:
            prefix=dict(context=copy.deepcopy(plan['context']),domain=copy.deepcopy(plan['domain']),observed=copy.deepcopy(observed),groups_per_point=dict(groups),remaining_records=plan['budget']-used,repeats=plan['repeats'],max_groups_per_point=plan['max_groups_per_point'])
            t=time.perf_counter();point=choose(copy.deepcopy(prefix));policy_seconds=time.perf_counter()-t
            if point is None:terminal='STOPPED_POLICY';break
            if point not in ids or groups.get(point,0)>=plan['max_groups_per_point']:terminal='BLOCKED_SELECTION';break
            decision=dict(index=len(decisions),input=prefix,input_sha256=digest(prefix),chosen=point,policy_seconds=policy_seconds,records_before=used)
            decision['sha256']=digest(decision);decisions.append(decision) # Freeze before querying outcomes.
            values=[]
            for _ in range(plan['repeats']):
                row=collect('ITEM',point,len(observed.get(point,[]))+len(values))
                if row['status']!='VALID':terminal='BLOCKED_UNKNOWN';break
                values.append(row['outcome'])
            if terminal=='BLOCKED_UNKNOWN':break
            observed.setdefault(point,[]).extend(values);groups[point]=groups.get(point,0)+1
    report=dict(schema=2,origin=origin,run_id=run_id,plan=plan,plan_sha256=digest(plan),occupied=used,completed_records=sum(r['status']=='VALID' for r in records),unknown_records=sum(r['status']=='UNKNOWN' for r in records),observed=observed,groups_per_point=groups,records=records,decisions=decisions,terminal=terminal,full_run_wall_seconds=time.perf_counter()-started,physical_start_count_verified=False,hardware_speedup_accepted=False)
    audit_run(report);return report
def audit_run(run):
    plan=public_plan(run['plan'])
    if run.get('origin') not in ('SYNTHETIC_ONLY','ADAPTER_REPORTED') or any(type(run.get(k)) is not int for k in ['occupied','completed_records','unknown_records']):raise ValueError('RUN_ORIGIN_OR_COUNTER_TYPE')
    if run['plan_sha256']!=digest(plan) or run['occupied']!=len(run['records']) or run['occupied']>plan['budget']:raise ValueError('RUN_PLAN_OR_COUNT')
    observed={};groups={};cursor=0;head='0'*64;unknown=False;seen_decisions=0
    def consume(kind,point,index):
        nonlocal cursor,head,unknown
        if cursor>=len(run['records']):raise ValueError('MISSING_RECORD')
        row=run['records'][cursor];req=row['request']
        expected=dict(run_id=run['run_id'],record_id='r%05d'%cursor,kind=kind,point_id=point,repeat_index=index,context_sha256=digest(plan['context']))
        if digest(req)!=digest(expected) or row['request_sha256']!=digest(req) or row['previous']!=head:raise ValueError('RECORD_ORDER')
        if digest({k:v for k,v in row.items() if k!='sha256'})!=row['sha256']:raise ValueError('RECORD_HASH')
        head=row['sha256'];cursor+=1
        if row['status']=='UNKNOWN':
            if row['outcome'] is not None:raise ValueError('UNKNOWN_OUTCOME')
            unknown=True;return None
        if row['status']!='VALID' or row['receipt'].get('request_sha256')!=digest(req) or row['receipt'].get('record_id')!=req['record_id'] or row['receipt'].get('status')!='VALID':raise ValueError('RECEIPT_BINDING')
        if kind=='ITEM' and type(row['outcome']) is not bool:raise ValueError('OUTCOME_TYPE')
        if kind=='SETUP' and row['outcome'] is not None:raise ValueError('SETUP_OUTCOME')
        if digest(row['outcome'])!=digest(row['receipt'].get('outcome')):raise ValueError('RECEIPT_OUTCOME')
        return row['outcome']
    for i in range(plan['setup_records']):
        consume('SETUP',None,i)
        if unknown:break
    if not unknown:
        for n,d in enumerate(run['decisions']):
            seen_decisions+=1
            prefix=dict(context=copy.deepcopy(plan['context']),domain=copy.deepcopy(plan['domain']),observed=copy.deepcopy(observed),groups_per_point=dict(groups),remaining_records=plan['budget']-cursor,repeats=plan['repeats'],max_groups_per_point=plan['max_groups_per_point'])
            if d['index']!=n or d['records_before']!=cursor or d['input_sha256']!=digest(prefix) or digest(d['input'])!=digest(prefix) or digest({k:v for k,v in d.items() if k!='sha256'})!=d['sha256']:raise ValueError('DECISION_PREFIX')
            point=d['chosen']
            if point not in {p['id'] for p in plan['domain']} or groups.get(point,0)>=plan['max_groups_per_point'] or cursor+plan['repeats']>plan['budget']:raise ValueError('SELECTION_BUDGET')
            values=[]
            for _ in range(plan['repeats']):
                value=consume('ITEM',point,len(observed.get(point,[]))+len(values))
                if unknown:break
                values.append(value)
            if unknown:break
            observed.setdefault(point,[]).extend(values);groups[point]=groups.get(point,0)+1
    if cursor!=len(run['records']) or digest(observed)!=digest(run['observed']) or digest(groups)!=digest(run['groups_per_point']):raise ValueError('UNREPLAYED_OR_FALSE_OBSERVATIONS')
    if len(run['decisions'])!=seen_decisions:raise ValueError('EXTRA_DECISIONS_AFTER_UNKNOWN')
    if run['completed_records']!=sum(r['status']=='VALID' for r in run['records']) or run['unknown_records']!=sum(r['status']=='UNKNOWN' for r in run['records']):raise ValueError('FALSE_COMPLETION_COUNTER')
    if unknown and run['terminal']!='BLOCKED_UNKNOWN':raise ValueError('UNKNOWN_MUST_STOP')
    if not unknown and run['terminal'] not in ('STOPPED_BUDGET','STOPPED_POLICY','BLOCKED_SELECTION'):raise ValueError('TERMINAL')
    if run['terminal']=='STOPPED_BUDGET' and cursor+plan['repeats']<=plan['budget']:raise ValueError('FALSE_BUDGET_STOP')
    return dict(passed=True,scope='Local trace replay; external raw verification and hardware identity remain adapter responsibilities')
class NoisyOracle:
    def __init__(self,truth,seed,unknown_probability=0):self.truth=truth;self.seed=seed;self.unknown=unknown_probability
    def __call__(self,request):
        key=[self.seed,request['kind'],request['point_id'],request['repeat_index']]
        rng=random.Random(int(digest(key),16));u=rng.random();status='UNKNOWN' if u<self.unknown else 'VALID'
        value=rng.random()<self.truth[request['point_id']] if request['kind']=='ITEM' and status=='VALID' else None
        return dict(record_id=request['record_id'],request_sha256=digest(request),status=status,outcome=value,source='FRESH_SYNTHETIC_DRAW')
def run_campaign(config,output):
    if config.get('origin')!='SYNTHETIC_ONLY':raise ValueError('CLI_SYNTHETIC_ONLY_USE_CALLBACK_API_FOR_REAL_ADAPTER')
    plan=public_plan(config);seeds=config['seeds'];truth=config['truth_probabilities'];rate=config.get('unknown_probability',0)
    if not isinstance(seeds,list) or not 2<=len(seeds)<=500 or any(type(v) is not int for v in seeds) or len(seeds)!=len(set(seeds)):raise ValueError('INDEPENDENT_CAMPAIGN_SEEDS')
    if set(truth)!={p['id'] for p in plan['domain']} or any(type(p) not in (int,float) or not math.isfinite(p) or not 0<=p<=1 for p in truth.values()):raise ValueError('TRUTH_PROBABILITIES')
    if type(rate) not in (int,float) or not 0<=rate<=1:raise ValueError('UNKNOWN_RATE')
    level=config.get('confidence_level',.95)
    if level!=.95:raise ValueError('THIS_VERSION_REQUIRES_PREDECLARED_95_PERCENT_INTERVALS')
    low,high=config.get('fail_probability_le',.1),config.get('pass_probability_ge',.9)
    if type(low) not in (int,float) or type(high) not in (int,float) or not 0<=low<high<=1:raise ValueError('PROBABILITY_THRESHOLDS')
    kinds={p:('PASS' if v>=high else 'FAIL' if v<=low else 'MIXED') for p,v in truth.items()}
    boundary=set()
    for a,b in config['adjacency']:
        if a not in truth or b not in truth or a==b:raise ValueError('ADJACENCY')
        if kinds[a]!=kinds[b]:boundary.update([a,b])
    out=Path(output);out.mkdir();summaries={};policies={'coverage':coverage,'confirm_mixed':confirm_mixed};traces=out/'traces';traces.mkdir()
    for name,policy in policies.items():
        rows=[]
        for seed in seeds:
            run=run_policy(plan,policy,NoisyOracle(truth,seed,rate),name+'_'+str(seed));(traces/(name+'_'+str(seed)+'.json')).write_text(json.dumps(run,indent=2),encoding='utf-8')
            hit=any(kinds[p]=='MIXED' for p in run['observed']);rows.append(dict(seed=seed,unique_conditions=len(run['observed']),boundary_points_touched=len(set(run['observed'])&boundary),mixed_touched=int(hit),occupied=run['occupied'],unknown=run['unknown_records']))
        summaries[name]=dict(campaigns=rows,mixed_touch_rate=sum(r['mixed_touched'] for r in rows)/len(rows),mixed_touch_wilson95=wilson(sum(r['mixed_touched'] for r in rows),len(rows)),unknown_campaigns=sum(r['unknown']>0 for r in rows))
    paired={metric:paired_interval([r[metric] for r in summaries['confirm_mixed']['campaigns']],[r[metric] for r in summaries['coverage']['campaigns']],config.get('bootstrap_resamples',2000),seed=123) for metric in ['unique_conditions','boundary_points_touched','mixed_touched','occupied']}
    report=dict(status='PASS_NOISY_CAMPAIGN_FRAMEWORK',config_sha256=digest(config),code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),confidence_level=level,probability_classification=dict(fail_le=low,pass_ge=high),boundary_points_total=len(boundary),equal_actual_spend_all_pairs=all(a['occupied']==b['occupied'] for a,b in zip(summaries['coverage']['campaigns'],summaries['confirm_mixed']['campaigns'])),campaign_count_per_policy=len(seeds),results=summaries,paired_confirm_minus_coverage=paired,hardware_access=False,statistical_hardware_superiority_proven=False,wall_gain_not_evaluated=True,scope='Fresh independent synthetic draws per campaign/point/index; paired bootstrap across campaigns, not individual UART items')
    (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(report['status'],len(seeds),'campaigns per policy');return report
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--output',required=True);a=p.parse_args();run_campaign(json.loads(Path(a.config).read_text(encoding='utf-8')),a.output)
