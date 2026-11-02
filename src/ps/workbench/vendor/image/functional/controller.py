import copy,hashlib,json,sqlite3,threading,time,uuid
from contextlib import closing
from pathlib import Path
from labutil import *
from scans import validate,TARGETS,aggregate
from learner import Estimator,synthetic_truth

class Store:
    def __init__(self,workspace):
        self.workspace=output_path(workspace);self.path=self.workspace/'lab_state.sqlite';self.lock=threading.RLock()
        with closing(self.connect()) as c:
            c.executescript('CREATE TABLE IF NOT EXISTS plans (id TEXT PRIMARY KEY,body TEXT NOT NULL); CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY,body TEXT NOT NULL); CREATE TABLE IF NOT EXISTS commands(id TEXT PRIMARY KEY,sha TEXT NOT NULL,response TEXT NOT NULL);')
            for rid,body in c.execute('SELECT id,body FROM runs').fetchall():
                r=json.loads(body)
                if r['state']=='RUNNING':r.update(state='BLOCKED_RESTART',reason='Process restart; explicit new simulation only, no automatic resume');c.execute('UPDATE runs SET body=? WHERE id=?',(canonical(r).decode(),rid))
            c.commit()
    def connect(self):
        c=sqlite3.connect(str(self.path),timeout=15);c.execute('PRAGMA synchronous=FULL');return c
    def plan(self,plan):
        validate(plan)
        with self.lock,closing(self.connect()) as c:
            saved=c.execute('SELECT body FROM plans WHERE id=?',(plan['plan_sha256'],)).fetchone()
            require(not saved or saved[0].encode()==canonical(plan),'PLAN_CONFLICT')
            c.execute('INSERT OR IGNORE INTO plans VALUES (?,?)',(plan['plan_sha256'],canonical(plan).decode()));c.commit()
        return plan
    def get_plan(self,key):
        with closing(self.connect()) as c:row=c.execute('SELECT body FROM plans WHERE id=?',(key,)).fetchone()
        require(row is not None,'PLAN_NOT_FOUND');p=json.loads(row[0]);validate(p);return p
    def command(self,key,body,operation):
        require(type(key) is str and 8<=len(key)<=128,'IDEMPOTENCY_KEY_REQUIRED')
        with self.lock,closing(self.connect()) as c:
            c.execute('BEGIN IMMEDIATE');prior=c.execute('SELECT sha,response FROM commands WHERE id=?',(key,)).fetchone()
            if prior:require(prior[0]==digest(body),'IDEMPOTENCY_CONFLICT');return json.loads(prior[1])
            result=operation(c);c.execute('INSERT INTO commands VALUES (?,?,?)',(key,digest(body),canonical(result).decode()));c.commit();return result
    def start(self,plan_id,seed,strategy,key,unknown_rate=0):
        require(strategy in ('grid','active'),'STRATEGY');require(type(seed) is int and 0<=unknown_rate<=.5,'SIMULATION_CONFIG')
        plan=self.get_plan(plan_id)
        def operation(c):
            require(not any(json.loads(row[0])['state']=='RUNNING' for row in c.execute('SELECT body FROM runs')),'EXCLUSIVE_RUN_ALREADY_ACTIVE')
            r=dict(run_id=uuid.uuid4().hex,plan_sha256=plan_id,origin='SIMULATED_DEVELOPMENT',state='RUNNING',seed=seed,strategy=strategy,
                unknown_rate=unknown_rate,records=[],history=[],seen=[],selected_point=None,used_starts=0,
                cancelled_unstarted=0,predictions=[],target=plan['targets'][0],hardware_permission=False,real_training_performed=False)
            c.execute('INSERT INTO runs VALUES (?,?)',(r['run_id'],canonical(r).decode()));return r
        return self.command(key,dict(action='START_SIMULATION',plan=plan_id,seed=seed,strategy=strategy,unknown_rate=unknown_rate),operation)
    def stop(self,rid,key):
        def operation(c):
            row=c.execute('SELECT body FROM runs WHERE id=?',(rid,)).fetchone();require(row,'RUN_NOT_FOUND');r=json.loads(row[0])
            if r['state']=='RUNNING':
                plan=self.get_plan(r['plan_sha256']);r.update(state='STOPPED',reason='EXPLICIT_STOP_CANCEL_UNSTARTED',cancelled_unstarted=plan['required_starts']-r['used_starts'])
                c.execute('UPDATE runs SET body=? WHERE id=?',(canonical(r).decode(),rid))
            return r
        return self.command(key,dict(action='STOP_SIMULATION',run=rid),operation)
    def runs(self):
        with closing(self.connect()) as c:return [json.loads(row[0]) for row in c.execute('SELECT body FROM runs ORDER BY rowid DESC')]
    def step(self,rid):
        with self.lock,closing(self.connect()) as c:
            c.execute('BEGIN IMMEDIATE');row=c.execute('SELECT body FROM runs WHERE id=?',(rid,)).fetchone();require(row,'RUN_NOT_FOUND');r=json.loads(row[0])
            if r['state']!='RUNNING':return r
            plan=self.get_plan(r['plan_sha256']);n=r['used_starts'];request=None
            if n>=plan['explicit_limit']:r.update(state='STOPPED',reason='BUDGET_EXHAUSTED')
            elif n<2:request=dict(kind='CONFIG' if n==0 else 'CONTROL',request_index=n)
            else:
                if r['strategy']=='grid':
                    if n>=plan['required_starts']:r.update(state='COMPLETE',reason='GRID_COMPLETE')
                    else:request=dict(kind='ITEM',**plan['requests'][n-2])
                else:
                    point_records=[x for x in r['records'] if x['kind']=='ITEM']
                    samples=[]
                    for pid in r['seen']:
                        rr=[x for x in point_records if x['point_id']==pid];cell=next(x for x in plan['cells'] if x['point_id']==pid)
                        samples.append(dict(phase=cell['phase'],width=cell['width'],y=sum(x['labels'][r['target']] for x in rr)/len(rr),origin='SIMULATED_DEVELOPMENT'))
                    model=Estimator(r['target']).fit(samples,'SIMULATED_DEVELOPMENT')
                    if r['selected_point'] is None:
                        proposal=model.select([x for x in plan['cells'] if x['legal']],set(r['seen']));r['predictions']=proposal['predictions']
                        if proposal['action']=='STOP':r.update(state='COMPLETE',reason=proposal['reason'],cancelled_unstarted=plan['required_starts']-n)
                        else:r['selected_point']=proposal['point_id']
                    if r['state']=='RUNNING':
                        already=sum(x['point_id']==r['selected_point'] for x in point_records)
                        request=dict(kind='ITEM',**next(x for x in plan['requests'] if x['point_id']==r['selected_point'] and x['repeat']==already))
            if request is not None:
                before=r['history'][-1] if r['history'] else None;ordinal=len(r['history'])
                proof=dict(schema='SIMULATION_SCAN_RECEIPT_V0_1',plan_sha256=plan['plan_sha256'],request_index=ordinal,
                    identity_hex=digest(dict(simulation_run=rid,ordinal=ordinal)),origin='SIMULATED_DEVELOPMENT',request=request,
                    after_identity_hex=before['identity_hex'] if before else None,after_receipt_sha256=before['receipt_sha256'] if before else None)
                unknown=request['kind']=='ITEM' and int(hashlib.sha256(('%d:%d'%(r['seed'],ordinal)).encode()).hexdigest()[:8],16)/2**32<r['unknown_rate']
                proof.update(status='UNKNOWN' if unknown else 'VALID',simulated_START=True,simulated_DONE=not unknown,
                    labels={t:None if unknown else synthetic_truth(request,r['seed'],'B_frame_correct' if t=='B_frame_correct' else 'STM_business_success') if request['kind']=='ITEM' else True for t in TARGETS})
                proof['receipt_sha256']=digest(proof);r['history'].append(proof);r['used_starts']+=1
                if request['kind']=='ITEM':
                    cond=dict(block_sha256=plan['payload_sha256'],d=plan['fixed']['d'],s=plan['fixed']['s'],first_byte=plan['fixed']['byte'],
                        bit=plan['fixed']['bit'],count=1,protocol='TYPE3A',phase=request['phase'],width=request['width'])
                    r['records'].append(dict(uid=proof['receipt_sha256'],kind='ITEM',point_id=request['point_id'],condition=cond,
                        origin='SIMULATED_DEVELOPMENT',status=proof['status'],labels=proof['labels'],identity_hex=proof['identity_hex'],
                        reference=dict(simulation_receipt=proof['receipt_sha256'],not_real_evidence=True)))
                    if unknown:r.update(state='BLOCKED_UNKNOWN',reason='UNKNOWN_OCCUPIES_BUDGET_NO_RETRY')
                    elif r['strategy']=='active' and sum(x['point_id']==r['selected_point'] for x in r['records'])==plan['repeats']:
                        r['seen'].append(r['selected_point']);r['selected_point']=None
            c.execute('UPDATE runs SET body=? WHERE id=?',(canonical(r).decode(),rid));c.commit();return r

def live_submit(*args,**kwargs):
    raise Rejected('MAINLINE_SCAN_EXECUTOR_NOT_PROVIDED; no live adapter enabled, legacy four-record executor is incompatible')
