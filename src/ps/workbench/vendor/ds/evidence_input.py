"""Strict, read-only image/session evidence reader. No PYNQ/device imports."""
from pathlib import Path
import json,hashlib,binascii,struct
from b_receiver import PROFILES,require
from window_audit import verify_directory,decode_samples

def sha(data):return hashlib.sha256(data).hexdigest()
def js(path):return json.loads(Path(path).read_bytes())
def checked(root,directory,inventory):
    root=Path(root).resolve();directory=Path(directory).resolve()
    require(root in directory.parents,'EVIDENCE_PATH_ESCAPE')
    verify_directory(directory)
    for p in sorted(directory.iterdir()):
        if p.is_file():
            require(root in p.resolve().parents,'EVIDENCE_SYMLINK_ESCAPE')
            raw=p.read_bytes();inventory[p.relative_to(root).as_posix()]=dict(bytes=len(raw),sha256=sha(raw))

def decode_config(raw,source):
    require(len(raw)>=58 and raw[:2]==b'\x55\xcc','CONFIG_HEADER')
    version,epoch,image,fmt,order,w,h,n,total,chunk,digest=struct.unpack('>BIBBBHHIHH32s',raw[2:54])
    require((version,fmt,order,n,total,chunk)==(2,1,0,16384,64,256) and w*h==n,'CONFIG_IMAGE64_FIELDS')
    require(len(raw)==56+2*total and binascii.crc_hqx(raw[2:-2],0xffff)==int.from_bytes(raw[-2:],'big'),'CONFIG_CRC')
    require(digest.hex()==sha(source),'CONFIG_SOURCE_SHA')
    crcs=[int.from_bytes(raw[54+i*2:56+i*2],'big') for i in range(64)]
    require(crcs==[binascii.crc_hqx(source[i:i+256],0xffff) for i in range(0,16384,256)],'CONFIG_BLOCK_CRCS')
    return dict(epoch=epoch,image_id=image,width=w,height=h,item_total=64,source_sha256=sha(source),block_crcs=crcs)

def check_points(result,count,epoch,rid):
    p=result['MPG1_pre_retirement']
    require(p['configured_points']==p['emitted_points']==count,'ACTUAL_POINT_COUNT_MISMATCH')
    require((p['epoch'],p['record_id'],p['identity_hex'])==(epoch,rid,result['identity_hex']),'POINT_COUNT_IDENTITY_MISMATCH')
    require(p['verified_before_retirement'] is True and p['actual_DONE_fenced'] is True and p['source_fault'] is False,'POINT_COUNT_NOT_VERIFIED')

def open_session(root):
    root=Path(root).resolve();inventory={};checked(root,root/'EXECUTOR/plan',inventory)
    plan=js(root/'EXECUTOR/plan/plan.json');source=(root/'EXECUTOR/plan/source.bin').read_bytes()
    require(len(source)==16384 and sha(source)==plan['source_sha256'],'SOURCE64_HASH_OR_LENGTH')
    require(plan['max_physical_starts_including_CONFIG']==65 and len(plan['requests'])==64,'EXACT65_PLAN_REQUIRED')
    expected=plan['requests'][0]['receiver_B']
    require(type(expected['d']) is int and type(expected['s']) is int and (expected['d'],expected['s']) in PROFILES,'ACTUAL_DS_DOMAIN')
    require(all(r['receiver_B']==expected for r in plan['requests']),'ONE_ACTUAL_DS_REQUIRED')
    require(len({r['client_request_id'] for r in plan['requests']})==64,'UNIQUE_ITEM_REQUESTS_REQUIRED')
    for request in plan['requests']:
        p=request['fault']
        if p is not None:
            first=p.get('first_byte',p.get('byte'));count=p.get('count',1)
            require(all(type(v) is int for v in (first,count,p['bit'],p['phase'],p['width'])),'INTEGER_PROFILE_FIELDS')
            require(20<=first<=275 and 1<=count<=256 and first+count<=276 and 0<=p['bit']<=7 and
                5<=p['phase']<=44 and 1<=p['width']<=40 and p['phase']+p['width']<=45,'PROFILE_OUTSIDE_DECLARED_DOMAIN')
    for p in (root/'EXECUTOR').glob('record_*'):
        require(1<=int(p.name.split('_')[1],16)<=65,'EXTRA_RECORD_OUTSIDE65_PLAN')
    schedule=None
    if 'random_schedule_sha256' in plan:
        directory=root/'EXECUTOR/random_schedule';checked(root,directory,inventory)
        raw=(directory/'schedule.json').read_bytes();require(sha(raw)==plan['random_schedule_sha256'],'RANDOM_SCHEDULE_CHANGED')
        schedule=json.loads(raw);require(len(schedule['items'])==64 and schedule['source_sha256']==sha(source),'RANDOM_SOURCE_CHANGED')
        for i,(entry,request) in enumerate(zip(schedule['items'],plan['requests'])):
            require(entry['item_index']==i and entry['profile']==request['fault'] and entry['receiver_B']==expected,'SCHEDULE_PLAN_MISMATCH')
    config=(root/'EXECUTOR/plan/config.bin').read_bytes();info=decode_config(config,source)
    require(info['epoch']==plan['local_epoch'],'CONFIG_PLAN_EPOCH')
    config_record=read_received(root,1,config,info['epoch'],None,inventory)
    require(config_record['metrics']['B']['frame_correct'],'RECEIVED_CONFIG_B_NOT_CORRECT')
    check_points(config_record['result'],0,info['epoch'],1)
    return dict(root=root,plan=plan,source=source,config=info,actual_profile=expected,inventory=inventory,schedule=schedule)

def read_received(root,rid,expected,epoch,profile,inventory):
    root=Path(root).resolve();rd=root/'EXECUTOR'/('record_%08x'%rid)/'result'
    checked(root,rd,inventory);result=js(rd/'result.json')
    require(result['record_id']==rid and result['evidence_quality']=='VALID','RECORD_NOT_VALID')
    require(all(result['retirement'][k] is True for k in ('CH0_release_verified','CH1_retirement_verified','peer_retirement_verified')) and result['next_credit']['next_item_allowed'] is True,'RECORD_NOT_RETIRED_READY')
    matches=list((root/'CH0').glob('epoch_*_record_%08x'%rid));require(len(matches)==1,'UNIQUE_CH0_REQUIRED')
    ch=matches[0];checked(root,ch,inventory);desc=js(ch/'descriptor.json')
    identity=int(result['identity_hex'],16);binding=desc['binding']
    require(0<=identity<2**256 and len(result['identity_hex'])==64,'IDENTITY_WIDTH')
    require((binding['epoch'],binding['record_id'],binding['identity'])==(epoch,rid,identity),'CH0_RECORD_IDENTITY')
    require(desc['status']==3 and desc['first_fault']==0,'CH0_CAPTURE_FAULT')
    intent=root/'EXECUTOR'/('record_%08x'%rid)/'intent';checked(root,intent,inventory)
    request=(intent/'request.bin').read_bytes()
    require(request==expected and (ch/'expected_request.bin').read_bytes()==expected,'REQUEST_SOURCE_CHANGED')
    if rid>1:
        require((int.from_bytes(request[3:7],'big'),request[7],int.from_bytes(request[8:10],'big'),int.from_bytes(request[10:12],'big'),request[14],request[15])==
            ((identity>>56)&0xffffffff,(identity>>48)&255,(identity>>32)&65535,(identity>>16)&65535,(identity>>8)&255,identity&255),'REQUEST_WIRE_IDENTITY')
    suffix='epoch_%08x_record_%08x'%(epoch,rid);admission=root/'admission'/suffix;checked(root,admission,inventory)
    actual=result['actual_receiver_B']
    require(actual==js(admission/'admission.json')['profile'] and actual['RX_profile_verified'] is True and actual['profile_seq']==rid,'ACTUAL_B_PROFILE_CHANGED')
    require(result['requested_receiver_B']=={k:actual[k] for k in ('d','s')},'REQUESTED_ACTUAL_DS_MISMATCH')
    if profile is not None:require({k:actual[k] for k in ('d','s')}==profile,'GLOBAL_ACTUAL_DS_MISMATCH')
    lanes={};metrics={}
    for name in ('a','b'):
        raw=(ch/(name+'_raw.bin')).read_bytes();samples=decode_samples((ch/(name+'_samples.bin')).read_bytes(),binding)
        require(bytes(s['data'] for s in samples)==raw and len(samples)==desc[name+'_count'],'SAMPLES_BYTES_COUNT_MISMATCH')
        equal_length=len(raw)==len(expected);flags=sum(s['flags']!=0 for s in samples)
        payload_aligned=rid>1 and equal_length and raw[:20]==expected[:20]
        metrics[name.upper()]=dict(expected_bytes=len(expected),received_bytes=len(raw),flagged_bytes=flags,
            frame_correct=raw==expected and flags==0,
            positional_frame_bit_errors=sum(bin(a^b).count('1') for a,b in zip(raw,expected)) if equal_length else None,
            payload_bit_errors=sum(bin(a^b).count('1') for a,b in zip(raw[20:-2],expected[20:-2])) if payload_aligned else None,
            payload_comparison_valid=payload_aligned,
            positional_comparison_scope='Equal-length ordered byte comparison; not a candidate full-frame prediction')
        lanes[name]=samples
    return dict(result=result,lanes=lanes,metrics=metrics,source=request,actual_profile={k:actual[k] for k in ('d','s')})

def read_item(session,rid):
    root=session['root'];inventory=session['inventory'];epoch=session['config']['epoch']
    result=root/'EXECUTOR'/('record_%08x'%rid)/'result/result.json'
    if not result.exists():
        intent=(result.parent.parent/'intent/intent.json').exists()
        return dict(state='UNKNOWN_OR_UNRETIRED' if intent else 'NOT_CAPTURED',reason='No valid retired result',metrics=None)
    intent_dir=result.parent.parent/'intent';checked(root,intent_dir,inventory)
    raw=(intent_dir/'request.bin').read_bytes();require(len(raw)==278 and raw[:2]==b'\x55\xaa','ITEM_FRAME_SIZE')
    version,run,image,trial,index,total,attempt,route,src_crc,size=struct.unpack('>BIBHHHBBHH',raw[2:20])
    require((version,run,image,index,total,attempt,route,size)==(2,epoch,session['config']['image_id'],rid-2,64,0,0,256),'ITEM_WIRE_NAMESPACE')
    require(raw[20:-2]==session['source'][(rid-2)*256:(rid-1)*256] and src_crc==session['config']['block_crcs'][rid-2],'ITEM_SOURCE_ORDER_OR_CRC')
    require(binascii.crc_hqx(raw[2:-2],0xffff)==int.from_bytes(raw[-2:],'big'),'ITEM_FRAME_CRC')
    received=read_received(root,rid,raw,epoch,session['actual_profile'],inventory)
    intent=js(intent_dir/'intent.json');expected=session['plan']['requests'][rid-2]['fault']
    require(intent['fault']==expected and intent['trial_id']==trial,'ITEM_PROFILE_OR_TRIAL_CHANGED')
    profile=expected;received['stimulus']=profile
    require(received['result'].get('profile')==profile,'RESULT_STIMULUS_CHANGED')
    mark=root/'MARK'/('epoch_%08x_record_%08x'%(epoch,rid))/'saved'
    check_points(received['result'],0 if profile is None else profile.get('count',1),epoch,rid)
    if profile is None:
        require(not mark.exists() and not (mark.parent/'arm').exists(),'DISABLED_ITEM_HAS_ARMED_MARK_EVIDENCE')
        return dict(received,state='NO_MARK_WINDOW',reason='Zero/disabled fault has no triggered CAP; no candidate waveform is invented')
    if not (mark/'committed.json').exists():return dict(received,state='MISSING_WINDOW',reason='Retired ITEM has no saved triggered CAP')
    checked(root,mark,inventory);context=js(mark/'context.json')
    require(context['arm']['profile']==profile,'CAP_STIMULUS_CHANGED')
    return dict(received,state='HAS_WINDOW',reason=None)

def verify_stable(session):
    for name,proof in session['inventory'].items():
        p=(session['root']/name).resolve();require(session['root'] in p.parents,'INPUT_PATH_ESCAPE')
        raw=p.read_bytes();require(len(raw)==proof['bytes'] and sha(raw)==proof['sha256'],'INPUT_CHANGED_DURING_ANALYSIS:'+name)
