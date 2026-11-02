"""All 64 ITEMs share one receiver profile. Random stimulus never enters repair."""
import copy
from common import require,digest
def profile(p):
    require(type(p) is dict and set(p)=={'d','s'},'B_PROFILE_FIELDS')
    require(type(p['d']) is int and type(p['s']) is int and 1<=p['d']<=4 and -2<=p['s']<=3-p['d'],'ILLEGAL_B_DS')
    return dict(p)
def fault(p):
    require(type(p) is dict and set(p)=={'first_byte','count','bit','phase','width'},'FAULT_FIELDS')
    require(all(type(v) is int for v in p.values()),'INTEGER_FAULT_REQUIRED')
    require(20<=p['first_byte']<=275 and 1<=p['count']<=256 and p['first_byte']+p['count']<=276,'PAYLOAD_POSITION_RANGE')
    require(0<=p['bit']<=7 and p['phase']>=5 and p['width']>=1 and p['phase']+p['width']<=45,'FAULT_TIMING_RANGE')
    return dict(p)
def schedule(request):
    from paired_random_plan import make_schedule
    require(type(request) is dict and set(request)=={'source_sha256','receiver_B','seed','fault_mode','fixed_fault'},'IMAGE_REQUEST_FIELDS')
    b=profile(request['receiver_B']);seed=request['seed']
    require(type(seed) is int and 0<=seed<2**64,'SEED_UINT64')
    require(request['fault_mode'] in ('random','fixed','disabled'),'IMAGE_FAULT_MODE')
    s=make_schedule(seed,source_sha256=request['source_sha256'],receiver_B=b)
    if request['fault_mode']!='random':
        p=fault(request['fixed_fault']) if request['fault_mode']=='fixed' else None
        for item in s['items']:item.update(profile=copy.deepcopy(p),count=0 if p is None else p['count'])
    s.update(schema='UNIFIED_IMAGE64_PLAN_V1',stimulus_mode=request['fault_mode'],request=copy.deepcopy(request),CONFIG_receiver_B={'d':3,'s':-1})
    s['sha256']=digest(s);return s
def validate(s):
    require(s==schedule(s['request']),'IMAGE_SCHEDULE_CHANGED');return True
