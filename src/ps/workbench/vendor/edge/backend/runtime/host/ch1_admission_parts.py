"""Verified partial admission sources. Never invent missing CH0/generation proof.

Registers a software STM expected flight; this is not STM device liveness.
ITEM eligibility also requires the previously retired CONFIG's actual ACK79.
CH0 frame-registration ABI and authoritative pre-START W19 generation remain
unimplemented; returned parts cannot authorize SingleItemOwner.start alone.
"""
from pathlib import Path
import json
import ch1_evidence_store as store
from ch1_completion_ledger import _codec
from ch1_peer_archive_driver import persist_exact
from ch1_control_session import decode_frame,decode_event
from ch1_runtime_driver import unsigned


def _has_exact_rx(journal,packet_hex):
    journal.verify()
    for line in journal.path.read_text().splitlines():
        item=json.loads(line)
        if item['event']=='control_rx_stream':
            capture=item['raw_hex']
        elif item['event']=='uart_byte_exchange_saved':
            # Native transports already fsync this exact RX stream; the peer
            # session deliberately avoids writing a duplicate control_rx_stream.
            if (item.get('collector') not in ('native_C','native_C_background') or
                    item.get('native_error') != 0 or item.get('bad_rx_word') is not None or
                    item.get('pending_hex') != ''):
                continue
            capture=item.get('rx_hex','')
        else:continue
        data=bytes.fromhex(capture);pos=0;found=False
        while pos<len(data):
            if len(data)-pos<5:break
            n=data[pos+4]+7;raw=data[pos:pos+n]
            if len(raw)!=n:break
            decode_frame(raw)
            if raw.hex()==packet_hex:found=True
            pos+=n
        if pos==len(data) and found:return True
    return False


class AdmissionParts:
    def __init__(self,root,journal):
        self.root=Path(root);self.journal=journal
    def register(self,binding,upload,peer,*,config_owner=None,fault_profile=None):
        if upload.fault or upload.current is None:raise RuntimeError('No immutable prepared upload')
        kind,seq,inner,packet=upload.current
        unsigned(binding.epoch,32,'flight local epoch',1);unsigned(binding.record_id,32,'flight record ID',1)
        unsigned(binding.identity,256,'flight identity')
        f=store._fields(binding.identity,store.IDENTITY)
        if f['reserved'] or f['slot']!=0 or not f['generation'] or not f['session'] or not f['seq'] or f['route_mode']!=0 or (upload.session,seq,int(kind))!=(f['session'],f['seq'],{1:3,2:2,3:4}.get(binding.kind)):
            raise ValueError('Direct prepared upload and binding differ')
        codec=_codec();decoder={1:codec.decode_item,2:codec.decode_config,3:codec.decode_cleanup}[binding.kind]
        decoded=decoder(inner)
        keys=('run_id','image_id','trial_id','item_index','attempt_id','route_mode') if binding.kind==1 else ('run_id','image_id')
        if not decoded['valid'] or any(decoded[k]!=f[k] for k in keys):raise ValueError('Flight identity does not match actual prepared bytes')
        status=peer.read(4)
        if peer.read(0)!=0x48354531 or status&0x50 or not status&1:
            raise RuntimeError('Peer backend fault/unauthorized/wrong identity')
        namespace=(peer.read(0x24),peer.read(0x28),peer.read(0x2c))
        if namespace!=(f['route_epoch'],f['session'],0):raise RuntimeError('Actual peer namespace differs from flight')
        cfg_ack=None
        if binding.kind==1:
            if config_owner is None or config_owner.fault or config_owner.phase!='RETIRED' or config_owner.business_success is not True or config_owner.config_success_ack is None:
                raise RuntimeError('ITEM requires prior CONFIG business success and exact peer CONFIG_SUCCESS ACK')
            cfg=codec.decode_config(config_owner.prepared_inner);ack=config_owner.config_success_ack
            old=store._fields(config_owner.binding.identity,store.IDENTITY)
            if config_owner.binding.epoch!=binding.epoch or (old['session'],old['route_epoch'])!=(f['session'],f['route_epoch']) or old['seq']>=f['seq']:
                raise ValueError('CONFIG approval belongs to another namespace or sequence')
            if not cfg['valid'] or (cfg['run_id'],cfg['image_id'])!=(f['run_id'],f['image_id']):raise ValueError('Wrong CONFIG flight context')
            if decoded['item_total']!=cfg['item_total'] or decoded['src_crc']!=cfg['item_crc_list'][decoded['item_index']]:raise ValueError('ITEM source CRC/table does not match frozen CONFIG')
            expected_len=min(cfg['chunk_size'],cfg['total_bytes']-decoded['item_index']*cfg['chunk_size'])
            if decoded['payload_len']!=expected_len:raise ValueError('ITEM length differs from configured source item')
            if decode_event(bytes.fromhex(ack['raw_hex']))!=ack or ack['type']!=0x79 or ack['identity']!=config_owner.binding.identity or ack['record_id']!=config_owner.binding.record_id or not _has_exact_rx(config_owner.journal,ack['raw_hex']):
                raise ValueError('CONFIG_SUCCESS ACK not present as exact captured control evidence')
            cfg_ack=ack['raw_hex']
        context={'identity':binding.identity,'local_epoch':binding.epoch,'peer_epoch':f['route_epoch'],
                 'record_id':binding.record_id,'kind':binding.kind,'inner_sha256':store.sha(inner),
                 'outer_sha256':store.sha(packet),'config_success_ack_hex':cfg_ack}
        directory=self.root/f'epoch_{binding.epoch:08x}_record_{binding.record_id:08x}'
        persist_exact(directory,{'flight.json':store._json(context),'inner.bin':bytes(inner),'outer.bin':bytes(packet)})
        self.journal.record('STM_expected_flight_registered',**context,directory=str(directory))
        if fault_profile is not None:
            if binding.kind!=1:raise ValueError('Only ITEM permits a fault profile')
            policy=peer.request_profile_fault(binding.identity,fault_profile,bytes(inner))
        else:
            policy=peer.request_profile_none(binding.identity) if binding.kind==1 else {'not_required_for_management':True,'mark_required':False}
        if (peer.read(0x24),peer.read(0x28),peer.read(0x2c))!=namespace or peer.read(4)&0x50:
            raise RuntimeError('Peer namespace/fault changed during admission capture')
        self.journal.record('verified_admission_parts',identity=binding.identity,namespace=list(namespace),policy=policy)
        return {**context,'STM_expected_flight_registered':True,'policy_ready':True,'mark_required':bool(policy.get('mark_required')),
                'CH0_registered':False,'generation_continuity_verified':False,'admission_complete':False,
                'missing_sources':['CH0 complete-frame registration','authoritative next W19 generation'],
                'policy_receipt':policy,'flight_dir':str(directory)}
    @staticmethod
    def require_complete(parts):
        if not parts.get('admission_complete') or not parts.get('CH0_registered') or not parts.get('generation_continuity_verified'):
            raise RuntimeError('Incomplete admission sources; no START authorization')
        return parts
