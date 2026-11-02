"""Saved hardware receipt audit only; no device objects, model fixtures or IO writes."""
import json
import struct
from pathlib import Path
from custom_plan import require
from ch1_control_session import decode_frame,decode_event
import ch1_evidence_store as store


def load_trace(root):
    root=Path(root);entries=[];captures=set();journals={}
    for p in root.rglob('application_*.jsonl'):
        from ch1_control_session import audit_application_journal
        audit_application_journal(p)
        lines=[dict(json.loads(line),_journal_path=p.relative_to(root).as_posix()) for line in p.read_text(encoding='utf-8').splitlines()]
        journals[p.relative_to(root).as_posix()]=(p,lines)
        entries.extend(lines)
        for e in lines:
            if e['event']=='control_rx_stream':data=bytes.fromhex(e['raw_hex'])
            elif e['event']=='uart_byte_exchange_saved':
                require(e.get('native_error')==0 and not e.get('pending_hex') and e.get('bad_rx_word') is None,'BAD_NATIVE_CAPTURE')
                data=bytes.fromhex(e['rx_hex'])
            else:continue
            offset=0
            while offset<len(data):
                require(len(data)-offset>=5,'TRUNCATED_CAPTURE')
                size=data[offset+4]+7;packet=data[offset:offset+size];decode_frame(packet);captures.add(packet);offset+=size
            require(offset==len(data),'CAPTURE_BOUNDARY')
    for e in entries:
        if e['event']=='application_segment_link':
            p,lines=journals[e['previous_path']]
            require(store.sha(p.read_bytes())==e['previous_sha256'] and len(lines)==e['previous_records'] and lines[-1]['sha256']==e['previous_chain'],'SEALED_SEGMENT_LINK_CHANGED')
    completion=[]
    for p in (root/'completion').glob('completion_*.jsonl'):
        previous='0'*64
        for index,line in enumerate(p.read_text(encoding='utf-8').splitlines()):
            e=json.loads(line);checksum=e.pop('sha256')
            require(e['index']==index and e['previous_sha256']==previous and store.sha(store._json(e))==checksum,'COMPLETION_CHAIN_CHANGED')
            previous=checksum;completion.append(e)
    require(completion,'SAVED_COMPLETION_LEDGER_REQUIRED')
    return entries,captures,completion


def record_audit(root,rid,result,profile,trace):
    root=Path(root);entries,captures,completion=trace;identity=int(result['identity_hex'],16)
    from custom_mmio_binding import saved_record_binding
    mmio_binding=saved_record_binding(root,rid,result,trace,0 if profile is None else getattr(profile,'count',1))
    # START ACK is not physical completion; both independently captured lifecycle effects are required.
    start_ack_payload=b'\x11'+(result['trial_id'] or 0).to_bytes(2,'little')+b'\x01'
    require(any(decode_frame(p)==(0x80,start_ack_payload) for p in captures),'EXACT_START_COMMAND_ACK_MISSING')
    for typ,effect in ((0x31,'START_ACCEPT'),(0x32,'W19_DONE'),(0x38,'RETIRED'))+(((0x33,'FAULT_MARK'),) if profile else ()):
        found=[]
        for e in entries:
            if e['event']!='peer_event_effect' or e['effect']!=effect:continue
            event=e['event_receipt'];packet=bytes.fromhex(event['raw_hex'])
            if event['identity']==identity:
                require(packet in captures and decode_event(packet)==event and event['type']==typ and event['record_id']==(rid if typ==0x38 else 0),'PHYSICAL_EVENT_RAW_OR_IDENTITY_CHANGED')
                found.append(event)
        require(len(found)==1,'EXACT_PHYSICAL_EVENT_MISSING_OR_DUPLICATED:'+effect)
    strict=[e for e in entries if e['event']=='strict_three_party_retire_intent' and e['identity']==identity and e['record_id']==rid]
    require(len(strict)==1,'STRICT_RETIREMENT_INTENT_MISSING')
    # The original intent does not store epoch; find by verified record suffix instead.
    observed=list((root/'CH0').glob('epoch_*_record_%08x/release_observed_*.json'%rid))
    require(len(observed)==1,'CH0_RELEASE_OBSERVATION_MISSING')
    release=json.loads(observed[0].read_bytes());require(release['binding']['identity']==identity and release['binding']['record_id']==rid and release['CH0_hardware_release_verified'] is True,'CH0_RELEASE_CHANGED')
    require(any(e['event']=='strict_CH0_released' and e['proof']==release for e in entries),'CH0_RELEASE_JOURNAL_MISSING')
    local=[e['proof'] for e in entries if e['event']=='local_record_retired' and int(e['proof']['identity_hex'],16)==identity and e['proof']['record_id']==rid]
    require(len(local)==1 and local[0]['hardware_retirement_verified'] is True and local[0]['mapping_retirement_verified'] is True,'CH1_MAPPING_RETIREMENT_MISSING')
    matched=[e for e in completion if e['event']=='status_matched' and e['binding']['identity']==identity]
    for state in (0x81,0x83,0x80):
        values=[e for e in matched if e['state']==state];require(values,'ACCEPTED_TX_DONE_READY_REQUIRED')
        for e in values:
            packet=bytes.fromhex(e['raw_hex']);require(len(packet)==18 and packet[:2]==b'\xa6\x6a' and store.crc16(packet[2:16])==int.from_bytes(packet[16:],'big'),'RAW_H1_STATUS_CRC')
            version,actual,session,seq,crc,code,credit=struct.unpack('>BBIIHBB',packet[2:16])
            require(version==1 and actual==state and code==0 and credit==e['credit'],'RAW_H1_STATUS_FIELDS')
            fields=store._fields(identity,store.IDENTITY)
            require(session==fields['session'] and ((seq==fields['seq'] and crc==e['inner_crc']) or (state==0x80 and seq==crc==0)),'H1_WIRE_IDENTITY_CHANGED')
    credit=[e for e in entries if e['event']=='next_item_credit_committed' and e['identity']==identity]
    require(len(credit)==1 and any(e['state']==0x80 and e['ticket']==credit[0]['ticket'] and e['credit']==1 for e in matched),'RETURNED_READY_NOT_IN_LEDGER')
    require(any(e['event']=='retired_and_ready' and e['record_id']==rid and e['ready_ticket']==credit[0]['ticket'] for e in completion),'READY_RETIREMENT_COMMITMENT_MISSING')
    require(result['next_credit']==dict(next_item_allowed=True,last_seq=store._fields(identity,store.IDENTITY)['seq']),'RETURNED_READY_SEQUENCE_CHANGED')
    if rid>=2:
        policies=[e['policy'] for e in entries if e['event']=='verified_admission_parts' and e['identity']==identity]
        require(len(policies)==1,'EXACT_ADMISSION_POLICY_REQUIRED')
        policy=policies[0];request=bytes.fromhex(policy['request_hex']);ack=bytes.fromhex(policy['ack_hex'])
        require(ack in captures and decode_frame(ack)==(decode_frame(request)[0]+0x40,decode_frame(request)[1]),'EXACT_CAPTURED_POLICY_ACK_REQUIRED')
        if profile and hasattr(profile,'count'):
            inner=(root/'EXECUTOR'/('record_%08x/intent/request.bin'%rid)).read_bytes()
            require(request==profile.build_request(identity,inner),'TYPE3C_REQUEST_CHANGED');profile.verify_ack(request,ack)
        else:
            from ch1_control_session import event_payload,frame
            context=event_payload(identity & ~(0xffffffff<<88),0)
            suffix=profile.wire_suffix() if profile else bytes(9)
            require(request==frame(0x3a,context[:12]+context[17:28]+suffix),'TYPE3A_OR_DISABLED_REQUEST_CHANGED')
        require(policy['injection_enable']==(profile is not None),'DISABLED_POLICY_CHANGED')
    return dict(record_id=rid,physical_START=True,physical_DONE=True,H1_TX_DONE=True,strict_retirement=True,actual_READY=True,
                waveform_scope='FIRST_POINT_ONLY' if profile else 'UNARMED',all_points_waveform_verified=False,
                raw_MMIO_transaction_binding_verified=True,raw_MMIO_binding=mmio_binding)
