"""Small kernel posterior estimator, synthetic-fit only; no NumPy dependency."""
import math,time,tracemalloc
from labutil import *

VERSION='RBF_POSTERIOR_ACTIVE_V0_1'
def xy(cell):return (cell['phase']/40.0,cell['width']/40.0)
def kernel(a,b,length):return math.exp(-sum((x-y)**2 for x,y in zip(a,b))/(2*length*length))
def solve_lower(L,b):
    out=[]
    for i in range(len(L)):out.append((b[i]-sum(L[i][j]*out[j] for j in range(i)))/L[i][i])
    return out
def solve_upper(L,b):
    out=[0.0]*len(L)
    for i in range(len(L)-1,-1,-1):out[i]=(b[i]-sum(L[j][i]*out[j] for j in range(i+1,len(L))))/L[i][i]
    return out

class Estimator:
    def __init__(self,target='B_frame_correct',length=0.28,noise=0.04):
        require(target in ('B_frame_correct','STM_business_success'),'TARGET')
        require(0.02<=length<=2 and 0<noise<=1,'HYPERPARAMETERS')
        self.target=target;self.length=length;self.noise=noise;self.samples=[];self.L=[];self.alpha=[]
    def fit(self,samples,origin):
        require(origin=='SIMULATED_DEVELOPMENT','REAL_TRAINING_NOT_AUTHORIZED')
        require(len(samples)<=512,'SMALL_ARM_MODEL_LIMIT')
        clean=[]
        for s in samples:
            require(s['origin']=='SIMULATED_DEVELOPMENT' and 0<=s['y']<=1,'SYNTHETIC_SAMPLES_ONLY')
            clean.append(dict(phase=s['phase'],width=s['width'],y=float(s['y']),origin=origin))
        self.samples=clean;X=[xy(s) for s in clean];n=len(X);L=[[0.0]*n for _ in range(n)]
        for i in range(n):
            for j in range(i+1):
                v=kernel(X[i],X[j],self.length)+(self.noise if i==j else 0)-sum(L[i][k]*L[j][k] for k in range(j))
                L[i][j]=math.sqrt(max(v,1e-12)) if i==j else v/L[j][j]
        self.L=L;self.alpha=solve_upper(L,solve_lower(L,[s['y']-.5 for s in clean])) if n else []
        return self
    def predict(self,cells):
        out=[];X=[xy(s) for s in self.samples]
        for c in cells:
            k=[kernel(xy(c),x,self.length) for x in X];v=solve_lower(self.L,k)
            mean=.5+sum(a*b for a,b in zip(k,self.alpha));variance=max(0.0,1-sum(a*a for a in v))
            out.append(dict(point_id=c['point_id'],phase=c['phase'],width=c['width'],estimate=max(0,min(1,mean)),
                uncertainty=math.sqrt(variance),layer='PREDICTED_NOT_MEASURED',target=self.target,
                calibration='Kernel regression estimate and posterior spread; not calibrated confidence'))
        return out
    def select(self,cells,observed_ids,max_uncertainty=.20):
        predictions=self.predict(cells);remaining=[p for p in predictions if p['point_id'] not in observed_ids]
        if not remaining:return dict(action='STOP',reason='CANDIDATES_EXHAUSTED',predictions=predictions)
        if len(observed_ids)>=8 and max(p['uncertainty'] for p in remaining)<=max_uncertainty:
            return dict(action='STOP',reason='POSTERIOR_SPREAD_BELOW_THRESHOLD',predictions=predictions)
        # Exploration plus preference near the estimated decision boundary, updated after each batch.
        chosen=max(remaining,key=lambda p:(p['uncertainty']*(.6+1-2*abs(p['estimate']-.5)),-p['phase'],-p['width']))
        return dict(action='PROPOSE_OFFLINE_POINT',point_id=chosen['point_id'],reason='UPDATED_UNCERTAINTY_BOUNDARY_SCORE',
            predictions=predictions,hardware_permission=False)
    def save(self,path):
        model=dict(version=VERSION,target=self.target,length=self.length,noise=self.noise,samples=self.samples,L=self.L,alpha=self.alpha,
            training_origin='SIMULATED_DEVELOPMENT',real_training_authorized=False)
        model['sha256']=digest(model);write(path,model)
    @classmethod
    def load(cls,path):
        m=read(path);require(m['sha256']==digest({k:v for k,v in m.items() if k!='sha256'}),'MODEL_DIGEST')
        require(m['version']==VERSION and m['training_origin']=='SIMULATED_DEVELOPMENT' and not m['real_training_authorized'],'MODEL_ORIGIN')
        require(all(s['origin']=='SIMULATED_DEVELOPMENT' for s in m['samples']),'MODEL_SAMPLES_ORIGIN')
        n=len(m['samples']);require(len(m['L'])==len(m['alpha'])==n and all(len(row)==n for row in m['L']),'MODEL_SHAPE')
        model=cls(m['target'],m['length'],m['noise']);model.samples=m['samples'];model.L=m['L'];model.alpha=m['alpha'];return model

def synthetic_truth(cell,seed,target):
    # Development oracle. Only evaluator/simulator can call it, never the selector.
    p=cell['phase'];threshold=(8 if target=='B_frame_correct' else 5)+(.018 if target=='B_frame_correct' else .012)*(p-22-(seed%5))**2+(seed%3-1)
    return cell['width']<=threshold

def boundary_error(cells,truth,predicted):
    errors=[];misclassified=0
    for phase in sorted({c['phase'] for c in cells}):
        group=[c for c in cells if c['phase']==phase]
        actual=max([c['width'] for c in group if truth[c['point_id']]] or [0])
        estimate=max([c['width'] for c in group if predicted[c['point_id']]] or [0])
        errors.append(abs(actual-estimate))
    for c in cells:misclassified+=truth[c['point_id']]!=predicted[c['point_id']]
    return dict(max_discrete_boundary_tick_error=max(errors),classification_error=misclassified/len(cells),misclassified=misclassified)

def evaluate(plan,seeds=(11,22,33,44,55),target='B_frame_correct',tolerance_ticks=0):
    from scans import validate
    validate(plan);cells=[c for c in plan['cells'] if c['legal']];runs=[]
    for seed in seeds:
        truth={c['point_id']:synthetic_truth(c,seed,target) for c in cells};model=Estimator(target);samples=[];seen=set();computation=0
        while len(seen)<len(cells):
            started=time.perf_counter();proposal=model.select(cells,seen);computation+=time.perf_counter()-started
            if proposal['action']=='STOP':break
            c=next(c for c in cells if c['point_id']==proposal['point_id']);seen.add(c['point_id'])
            samples.append(dict(phase=c['phase'],width=c['width'],y=float(truth[c['point_id']]),origin='SIMULATED_DEVELOPMENT'))
            started=time.perf_counter();model.fit(samples,'SIMULATED_DEVELOPMENT');computation+=time.perf_counter()-started
        prediction={p['point_id']:p['estimate']>=.5 for p in model.predict(cells)}
        error=boundary_error(cells,truth,prediction);count=2+len(seen)*plan['repeats'];baseline=2+len(cells)*plan['repeats']
        comparable=error['max_discrete_boundary_tick_error']<=tolerance_ticks
        runs.append(dict(seed=seed,group='synthetic-session-%d'%seed,baseline_ITEMs=len(cells)*plan['repeats'],
            selected_ITEMs=len(seen)*plan['repeats'],baseline_total_starts=baseline,selected_total_starts=count,
            CONFIG_and_control=2,unknown=0,invalid=0,boundary_error=error,precision_comparable=comparable,
            synthetic_measurement_reduction=1-count/baseline if comparable else None,
            acceleration_goal_met_in_simulation=comparable and count<baseline,
            algorithm_compute_seconds=computation,hardware_end_to_end_seconds=None,
            stop_reason=proposal.get('reason','CANDIDATES_EXHAUSTED'),sampled_points=sorted(seen)))
    return dict(version=VERSION,origin='SIMULATED_DEVELOPMENT_ONLY',target=target,tolerance_ticks=tolerance_ticks,runs=runs,
        real_trial_reduction_proven=False,real_AI_acceleration_accepted=False,
        evaluation_rule='Selector stops by its uncertainty rule, not by oracle error. Failed precision comparisons earn no reduction.',
        grouping='Independent latent synthetic sessions; no real image/trial used for fitting')

def benchmark(model,cells,repeats=50):
    tracemalloc.start();started=time.perf_counter()
    for _ in range(repeats):model.predict(cells)
    elapsed=time.perf_counter()-started;current,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
    return dict(predict_calls=repeats,cells_per_call=len(cells),mean_seconds=elapsed/repeats,python_traced_peak_bytes=peak,
        model_version=VERSION,scope='Actual current interpreter timing; not automatically an ARM result or hardware speedup')
