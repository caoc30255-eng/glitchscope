"""Explicit one-baseline/one-marked ITEM pilot. Import performs no device IO."""
from pathlib import Path
import time,json,hashlib
from h1_protocol import Kind
from ch1_completion_ledger import _codec
from ch1_peer_archive_driver import persist_exact
from ps_idle_journal_segments import rotate_idle_journal,verify_sealed_segments
from ch1_runtime_driver import unsigned
from fault_profile import FaultProfile
import ch1_evidence_store as store

PILOT_SOURCE_SHA=hashlib.sha256(bytes(range(256))*2).hexdigest()

def inspect_raw_mark_interface(session,mmio_factory,hwh_path):
    result=session.configure_fault_capture(mmio_factory,hwh_path)
    capture=session.mark_capture
    actual={'config':capture.read(4),'status':capture.read(8),'sample_count':capture.read(12),
            'trigger_offset':capture.read(16),'live_sample':capture.read(0x20)}
    if actual['config']!=0x201 or actual['status'] or actual['sample_count'] or actual['trigger_offset']:
        raise RuntimeError('Raw snapshot is not fresh; retain existing state, no ARM/reset')
    if actual['live_sample']&7!=3:
        raise RuntimeError('CH0/CH1 must idle high and CH2 mark low before any trial')
    report={**result,'actual_raw_registers':actual,'scope':'unarmed CSR readback only; physical pulse not yet verified'}
    persist_exact(session.root/'MARK/preflight',{'preflight.json':store._json(report)})
    session.journal.record('raw_mark_preflight_saved',**report)
    return report

def _one(session,buses,kind,inner,record_id,*,profile,d,s):
    session.prepare_flight(kind,inner,record_id=record_id,d=d,s=s,
        ch1_delay_ticks=100000000,ch1_duration_ticks=4000000000,
        ch0_delay_ticks=10000000,ch0_duration_ticks=1000000000,
        **({'fault_profile':profile} if profile is not None else {}))
    print('PREPARED',Kind(kind).name,record_id,'seconds',session.last_preparation_seconds,flush=True)
    deadline=time.monotonic()+10
    while not session.window_readiness(ch0_margin_ticks=100000000,ch1_margin_ticks=100000000)['windows_open']:
        if time.monotonic()>=deadline:raise TimeoutError('Local windows not open; no START')
        time.sleep(.01)
    started=session.start_current(ch0_margin_ticks=100000000,ch1_margin_ticks=100000000)
    print('START',json.dumps(started),flush=True)
    deadline=time.monotonic()+60
    while True:
        state=session.poll_current()
        if all(state[k] for k in ('physical_start_confirmed','physical_done_confirmed','saved_H1_TX_DONE','CH0_closed','CH1_finalized')) and int(buses['MAIN'].read(4))&2:break
        if time.monotonic()>=deadline:raise TimeoutError('Actual completion not confirmed; no START retry')
        time.sleep(.01)
    owner=session.current
    ch0=session.ch0_archive.archive_current(owner.verified_record['ch0_binding'],expected_request=inner)
    ch0_dir=Path(ch0.evidence_dir);ch0_check=json.loads((ch0_dir/'classification.json').read_text())
    if profile is None and (not ch0_check['a_reception_success'] or not ch0_check['b_reception_success']):
        raise ValueError('Unmarked baseline source mismatch; no release')
    payload=_codec().decode_item(inner)['payload'] if kind==Kind.ITEM else None
    watermark=session.runtime.snapshot()
    saved=session.archive.archive_current(watermark_epoch=watermark['epoch'],watermark_tick=watermark['tick'],expected_payload=payload)
    if saved is None:raise RuntimeError('No actual CH1 archive')
    if profile is None and not saved['business_success']:raise ValueError('Unmarked CONFIG/ITEM did not succeed')
    one=Path(saved['evidence_dir']);raw=(one/'raw_packet.bin').read_bytes()
    decoded=(_codec().decode_config_ack(raw) if kind==Kind.CONFIG else _codec().decode_report(raw))
    if kind==Kind.CONFIG:
        if not decoded.get('valid') or decoded['run_id']!=session.local_epoch or decoded['image_id']!=1 or decoded['ack_status']:
            raise ValueError('Exact actual CONFIG_ACK required')
    mpg1_proof=None
    monitor=getattr(session,'mpg1_monitor',None)
    if monitor is not None:
        points=0 if profile is None else getattr(profile,'count',1)
        mpg1_proof=monitor.verify_completed(owner,points)
    retired=session.retire_current()
    deadline=time.monotonic()+15
    while True:
        credit=session.poll_next_credit()
        if credit['next_item_allowed']:break
        if time.monotonic()>=deadline:raise TimeoutError('No actual READY after retirement')
        time.sleep(.01)
    result={'record_id':record_id,'kind':Kind(kind).name,'business_success':owner.business_success,
            'CH0_classification':ch0_check,'CH1_classification':json.loads((one/'classification.json').read_text()),
            'CH1_evidence_dir':str(one),'CH0_evidence_dir':str(ch0_dir),
            'raw_report_bytes':len(raw),'retirement':retired,'next_credit':credit,
            'decoded_report':{k:v for k,v in decoded.items() if not isinstance(v,(bytes,bytearray))}}
    if profile is not None:
        proof=owner.mark_capture.verify_saved(owner.mark_receipt,owner.binding)
        result['physical_mark']=proof
        result['physical_waveform']=json.loads((Path(proof['evidence_dir'])/'context.json').read_text())['analysis']
        result['profile']=profile.validate(inner)
    if mpg1_proof is not None:result['MPG1_pre_retirement']=mpg1_proof
    print('RECORD_RESULT',json.dumps(result),flush=True)
    return result

def run_single_item_pair(session,buses,source,*,profile,d=3,s=-1):
    if type(profile) is not FaultProfile:raise TypeError('Explicit reviewed FaultProfile required')
    source=bytes(source)
    if len(source)!=512 or store.sha(source)!=PILOT_SOURCE_SHA:raise ValueError('Pilot requires frozen two identical256B chunks')
    if session.current is not None or session.config_owner is not None or session.mark_capture is None or session.mark_capture.used:
        raise RuntimeError('Fresh initialized pilot session and unarmed physical snapshot required')
    if getattr(session,'_fault_pilot_started',False):raise RuntimeError('Pilot cannot be repeated/resumed')
    preflight=session.root/'MARK/preflight'
    marker=preflight/'committed.json'
    if not marker.is_file():raise RuntimeError('Reviewed unarmed raw-mark preflight required first')
    for name,digest in json.loads(marker.read_bytes())['files'].items():
        if store.sha((preflight/name).read_bytes())!=digest:raise ValueError('Mark preflight archive changed')
    session._fault_pilot_started=True
    try:
        codec=_codec();chunks=[source[:256],source[256:]]
        config=codec.encode_config(session.local_epoch,1,32,16,512,2,256,hashlib.sha256(source).digest(),[store.crc16(x) for x in chunks])
        persist_exact(session.root/'pilot_input',{'source.bin':source,'config.bin':config,'policy.json':store._json({'profile':profile.validate(codec.encode_item(session.local_epoch,1,1,1,2,0,0,chunks[1])),'d':d,'s':s})})
        before=int(buses['SYS'].read(0x18));grants=int(buses['SYS'].read(0x1c))
        records=[_one(session,buses,Kind.CONFIG,config,1,profile=None,d=d,s=s)]
        registry=Path(session.root).parent/'trial_registry';registry.mkdir(exist_ok=True)
        for index in range(2):
            rotate_idle_journal(session,buses=buses,next_record_id=index+2)
            trial=max((int(p.stem.split('_')[1],16) for p in registry.glob('trial_*.json')),default=0)+1
            unsigned(trial,16,'trial ID',1)
            store._write(registry/('trial_%04x.json'%trial),store._json({'epoch':session.local_epoch,'index':index,'attempt':0,'trial_id':trial,'scope':'direct_single_mark_pair'}))
            store._sync_directory(registry)
            inner=codec.encode_item(session.local_epoch,1,trial,index,2,0,0,chunks[index])
            records.append(_one(session,buses,Kind.ITEM,inner,index+2,profile=None if index==0 else profile,d=d,s=s))
        verify_sealed_segments(session)
        if int(buses['SYS'].read(0x18))!=before+3 or int(buses['SYS'].read(0x1c))!=grants+3:
            raise RuntimeError('Actual three-record retirement/grant totals differ')
        summary={'scope':'One unmarked/one physically marked Direct ITEM pair; not tuning statistics or image recovery',
                 'source_sha256':store.sha(source),'records':records,'all_three_records_retired':True,
                 'physical_injection_verified':True,'marked_business_success':records[-1]['business_success']}
        persist_exact(session.root/'fault_pilot_acceptance',{'summary.json':store._json(summary)})
        print('DIRECT_MARK_PAIR_COMPLETE',json.dumps(summary),flush=True)
        return summary
    except Exception as exc:
        session._stop(exc)
        transport=session.control_transport
        diagnostic={'error':repr(exc),'trace':transport.last_trace,'RX':transport.pending_snapshot(limit=65536)}
        directory=session.root/('fault_pilot_failure_'+__import__('uuid').uuid4().hex)
        persist_exact(directory,{'diagnostic.json':store._json(diagnostic)})
        print('STOP_RETAIN_NO_RETRY',str(directory),repr(exc),flush=True)
        raise
