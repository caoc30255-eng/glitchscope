"""Custom fixed-profile TYPE3A plan compiler; no device IO, Python 3.8+."""
import copy,hashlib,itertools,json,math
from active14_bootstrap import bind
ROOT=bind()
from ch1_completion_ledger import _codec
from fault_profile import FaultProfile
from multi_point_profile import MultiPointProfile
from learning_domain import digest

TARGETS=('B_frame_correct','STM_payload_correct','STM_business_success')
CONFIRMATION='OFFLINE_CUSTOM_PLAN_ONLY'
def raw(v):return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')
def diagnostic(value):
    # Invalid Python/JSON-extension input is represented only in rejection diagnostics.
    # Never rewrite a value in an accepted physical plan.
    if type(value) is float and not math.isfinite(value):return dict(rejected_nonfinite_float=repr(value))
    if type(value) is dict:return {str(k):diagnostic(v) for k,v in value.items()}
    if type(value) in (list,tuple):return [diagnostic(v) for v in value]
    if value is None or type(value) in (str,int,float,bool):return value
    return dict(rejected_python_type=type(value).__name__)


def require(ok,reason):
    if not ok:raise ValueError(reason)
def integer(v,name,lo,hi):require(type(v) is int and lo<=v<=hi,'INVALID_'+name);return v

def capabilities():
    return dict(schema='CUSTOM_SCAN_CAPABILITIES_V0_1',implemented='FIXED_B_TYPE3A_TYPE3C_DISABLED_ADAPTER_CANDIDATE',
        receiver_B=dict(d=[1,2,3,4],s='integer -2 <= s <= 3-d'),payload_bytes=256,route_modes=[0],
        TYPE3A_SINGLE=dict(byte=[20,275],bit=[0,7],phase=[5,44],width=[1,40],constraint='phase+width<=45',count=1,implemented=True),
        TYPE3C_CONTIGUOUS=dict(first_byte_min=20,count=[1,256],constraint='first_byte+count<=276; shared bit/phase/width; phase+width<=45',driver_codec_available=True,execution_implemented=True,real_hardware_verified=False),
        independent_per_point_multipoint=False,multiple_B_profiles_in_one_session=False,
        candidate_record_capacity=44,candidate_capacity_is_not_a_universal_RTL_limit=True,new_physical_STARTs_authorized=0,real_hardware_verified=False,DISABLED=dict(count=0,encoded_as='disabled TYPE3A policy',implemented=True),
        CONFIG_receiver_B=dict(d=3,s=-1),CONFIG_profile_is_inherited_and_explicit=True,
        source_drivers={n:hashlib.sha256((ROOT/'runtime/host'/n).read_bytes()).hexdigest() for n in ('fault_profile.py','multi_point_profile.py','ch0_rx_profile_driver.py','controlled_trial_executor.py')})

def condition(profile,payload,route,fault,mode="TYPE3A_SINGLE",count=1):
    full=dict(receiver_B=copy.deepcopy(profile),payload_sha256=hashlib.sha256(payload).hexdigest(),route_mode=route,
        mode=mode,protocol={'TYPE3A_SINGLE':'TYPE3A','TYPE3C_CONTIGUOUS':'TYPE3C','DISABLED':'TYPE3A_DISABLED'}[mode],fault=dict(fault),count=count)
    sha=digest(full);return dict(full,condition_sha256=sha,condition_id='c_'+sha[:16])

def values(v,name):
    if type(v) is list:
        require(0<len(v)<=256 and all(type(n) is int for n in v),name+'_INTEGER_LIST')
        require(len(set(v))==len(v),name+'_DUPLICATE_VALUES');return v
    require(type(v) is dict and set(v)=={'start','stop','step'},name+'_RANGE_FIELDS')
    require(all(type(v[k]) is int for k in v) and v['step']>0 and v['stop']>=v['start'],name+'_RANGE_ORDER_STEP')
    count=(v['stop']-v['start'])//v['step']+1;require(count<=256,name+'_RANGE_TOO_LARGE')
    return list(range(v['start'],v['stop']+1,v['step']))

def compile_plan(request):
    """Returns an accepted immutable plan or all-or-nothing rejection diagnostics."""
    result=dict(status='REJECTED',legal_conditions=[],rejected_conditions=[],errors=[],plan=None)
    try:
        require(type(request) is dict,'REQUEST_OBJECT')
        allowed={'receiver_B','mode','fault','scan','repeats','max_records','payload_hex','route_mode','target','refinement','edge_ai'}
        require(set(request)<=allowed and {'receiver_B','mode','fault','scan','repeats','max_records'}<=set(request),'REQUEST_FIELDS')
        r=copy.deepcopy(request);profile=r['receiver_B']
        if 'edge_ai' in r:
            from custom_ai_policy import validate_policy
            validate_policy(r['edge_ai'])
        require(type(profile) is dict and set(profile)=={'d','s'},'ONE_FIXED_PROFILE_REQUIRED')
        integer(profile['d'],'D',1,4);integer(profile['s'],'S',-2,3-profile['d'])
        route=r.get('route_mode',0);require(type(route) is int and route==0,'DIRECT_ROUTE_ZERO_ONLY')
        payload_hex=r.get('payload_hex',bytes(range(256)).hex());require(type(payload_hex) is str and len(payload_hex)==512,'PAYLOAD_HEX_STRING_512_CHARACTERS')
        payload=bytes.fromhex(payload_hex);require(len(payload)==256 and payload_hex==payload.hex(),'EXACT_LOWERCASE_256_BYTE_PAYLOAD_HEX')
        repeats=integer(r['repeats'],'REPEATS',1,32);limit=integer(r['max_records'],'MAX_RECORDS',2,44)
        target=r.get('target','B_frame_correct');require(target in TARGETS,'INDEPENDENT_TARGET_REQUIRED')
        refine=r.get('refinement',dict(enabled=False,confirmation_repeats=1,candidates=[]))
        require(type(refine) is dict and set(refine)=={'enabled','confirmation_repeats','candidates'} and type(refine['enabled']) is bool,'REFINEMENT_FIELDS')
        integer(refine['confirmation_repeats'],'CONFIRM_REPEATS',1,32)
        require(type(refine['candidates']) is list and len(refine['candidates'])<=256,'CONFIRMED_REFINEMENT_CANDIDATES_LIST_MAX_256')
        base=r['fault'];require(type(base) is dict,'FAULT_FIELDS')
        if r['mode']=='TYPE3C_CONTIGUOUS' and set(base)=={'first_byte','bit','count'}:base=dict(byte=base['first_byte'],bit=base['bit'],count=base['count'])
        require(set(base)=={'byte','bit','count'},'FAULT_FIELDS')
        require(r['mode'] in ('TYPE3A_SINGLE','TYPE3C_CONTIGUOUS','DISABLED'),'MODE_UNSUPPORTED')
        scan=r['scan'];require(type(scan) is dict,'SCAN_OBJECT')
        if set(scan)=={'points'}:
            require(type(scan['points']) is list and 0<len(scan['points'])<=256,'POINT_LIST_REQUIRED');points=scan['points']
        else:
            require(set(scan)=={'phase','width'},'SCAN_LIST_OR_TWO_RANGES')
            pp=values(scan['phase'],'PHASE');ww=values(scan['width'],'WIDTH');require(len(pp)*len(ww)<=256,'GRID_TOO_LARGE')
            points=[dict(phase=p,width=w) for p,w in itertools.product(pp,ww)]
        inner=_codec().encode_item(1,1,1,0,1,0,0,payload)
        coarse=[];confirmed=[];seen=set()
        for source,entries in [('scan',points),('refinement',refine['candidates'])]:
            for index,point in enumerate(entries):
                try:
                    require(type(point) is dict and {'phase','width'}<=set(point)<= {'byte','bit','count','phase','width'},'POINT_FIELDS')
                    coords=dict(base,**point)
                    if r['mode']=='TYPE3C_CONTIGUOUS':
                        MultiPointProfile(coords['byte'],coords['count'],coords['bit'],coords['phase'],coords['width']).validate(inner)
                    else:
                        require(type(coords['count']) is int and coords['count']==(0 if r['mode']=='DISABLED' else 1),'EXPLICIT_DISABLED_ZERO_OR_SINGLE_ONE_REQUIRED')
                        FaultProfile(**{k:coords[k] for k in ('byte','bit','phase','width')}).validate(inner)
                    fault={k:coords[k] for k in ('byte','bit','phase','width')}
                    c=condition(profile,payload,route,fault,r['mode'],coords['count'])
                    if source=='scan':require(c['condition_sha256'] not in seen,'DUPLICATE_FULL_SCAN_CONDITION');coarse.append(c);seen.add(c['condition_sha256'])
                    if all(x['condition_sha256']!=c['condition_sha256'] for x in confirmed):confirmed.append(c)
                    result['legal_conditions'].append(dict(source=source,index=index,condition=c))
                except (ValueError,TypeError,KeyError) as error:result['rejected_conditions'].append(dict(source=source,index=index,requested=diagnostic(point),reason=str(error)))
        required=2+len(points)*repeats;result.update(preparation_records=2,required_records=required,legal_only_diagnostic_records=2+len(coarse)*repeats,
            required_item_total=required-1,required_source_bytes=(required-1)*256,requested_record_cap=limit,source_capacity_bytes=(limit-1)*256,
            source_bytes=(limit-1)*256,item_total=limit-1,CONFIG_width=32,CONFIG_height=(limit-1)*8,
            source_sha256=hashlib.sha256(payload*(limit-1)).hexdigest())
        require(not result['rejected_conditions'],'ILLEGAL_OR_UNIMPLEMENTED_CONDITIONS_REJECT_WHOLE_PLAN')
        require(required<=limit,'INSUFFICIENT_TOTAL_BUDGET_INCLUDING_PREPARATION')
        require(len({c['condition_id'] for c in confirmed})==len(confirmed),'CONDITION_ID_PREFIX_COLLISION')
        require(len(confirmed)<=256,'CONFIRMED_DOMAIN_TOO_LARGE')
        plan=dict(schema='CUSTOM_FIXED_PROFILE_SCAN_PLAN_V0_1',request=r,receiver_B=profile,payload_hex=payload.hex(),payload_sha256=hashlib.sha256(payload).hexdigest(),route_mode=route,
            mode=r['mode'],conditions=confirmed,coarse_condition_ids=[c['condition_id'] for c in coarse],repeats=repeats,target=target,
            initial_queue=[dict(condition_id=c['condition_id'],repeat=i+1) for c in coarse for i in range(repeats)],
            required_records=required,max_records=limit,preparation_records=2,reserved_refinement_records=limit-required,
            refinement=refine,item_total=limit-1,source_bytes=(limit-1)*256,source_sha256=result['source_sha256'],CONFIG_width=32,CONFIG_height=(limit-1)*8,
            items=[dict(receiver_B=profile,profile=None if i==0 else dict(dynamic_committed_profile=True)) for i in range(limit-1)],
            preparation=[dict(kind='CONFIG',receiver_B=dict(d=3,s=-1)),dict(kind='CONTROL',receiver_B=profile)],
            automatic_retry=False,resume_allowed=False,live_execution_authorized=False,new_physical_STARTs_authorized=0)
        plan['sha256']=digest(plan);result.update(status='ACCEPTED',plan=plan)
        return result
    except (ValueError,TypeError,KeyError) as error:result['errors'].append(str(error));return result

def validate_plan(plan):
    require(type(plan) is dict and type(plan.get('request')) is dict,'PLAN_OBJECT')
    rebuilt=compile_plan(plan['request']);require(rebuilt['status']=='ACCEPTED' and plan==rebuilt['plan'],'FROZEN_COMPILED_PLAN_CHANGED')
    return True


def typed_profile(c):
    if c['mode']=='DISABLED':return None
    if c['mode']=='TYPE3A_SINGLE':return FaultProfile(**c['fault'])
    f=c['fault'];return MultiPointProfile(f['byte'],c['count'],f['bit'],f['phase'],f['width'])
