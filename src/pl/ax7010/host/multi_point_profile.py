"""Offline TYPE3C codec only; no transport, MMIO, START, retry or billing API.

The old FaultProfile and old live executor intentionally do not accept this type.
"""
from dataclasses import dataclass,asdict
import struct


@dataclass(frozen=True)
class MultiPointProfile:
    first_byte: int
    count: int
    bit: int
    phase: int
    width: int

    def validate(self, inner):
        from ch1_completion_ledger import _codec
        fields=_codec().decode_item(bytes(inner))
        if not fields['valid'] or fields['route_mode']!=0:
            raise ValueError('CRC-valid original Direct ITEM required')
        for name in ('first_byte','count','bit','phase','width'):
            if type(getattr(self,name)) is not int:
                raise TypeError('Integer coordinates only: '+name)
        if not (20<=self.first_byte and 1<=self.count<=256 and
                self.first_byte+self.count<=len(inner)-2 and 0<=self.bit<8 and
                5<=self.phase and 1<=self.width and self.phase+self.width<=45):
            raise ValueError('Payload-only contiguous range, interior bit window [5,45] required')
        return asdict(self)

    def build_request(self, identity, inner):
        import ch1_evidence_store as store
        from ch1_control_session import event_payload,frame
        from ch1_completion_ledger import _codec
        self.validate(inner)
        if type(identity) is not int or not 0<=identity<1<<256:
            raise ValueError('Canonical full identity required')
        f=store._fields(identity,store.IDENTITY)
        decoded=_codec().decode_item(bytes(inner))
        if (f['reserved'] or f['slot']!=0 or not f['session'] or not f['seq'] or
                not f['route_epoch'] or not f['generation'] or f['attempt_id']>3 or f['route_mode']!=0):
            raise ValueError('Canonical Direct one-slot identity required')
        if any(f[k]!=decoded[k] for k in ('run_id','image_id','trial_id','item_index','attempt_id','route_mode')):
            raise ValueError('Profile identity differs from immutable ITEM')
        context=event_payload(identity & ~(0xffffffff<<88),0)
        suffix=b'\x01'+struct.pack('>HBHHB',self.first_byte,self.bit,self.phase,self.width,self.count-1)
        payload=context[:12]+context[17:28]+suffix
        assert len(payload)==32
        return frame(0x3c,payload)

    @staticmethod
    def verify_ack(request, reply):
        from ch1_control_session import decode_frame
        kind,payload=decode_frame(bytes(request))
        ack_kind,ack_payload=decode_frame(bytes(reply))
        if kind!=0x3c or ack_kind!=0x7c or payload!=ack_payload:
            raise ValueError('Exact TYPE7C context and range ACK required')
        return True


def decode_stats(capability,packed_counts,status,identity_words):
    """Decode stable post-DONE MMIO readbacks; caller must fence reads by identity.

    Returned identity bits are native RTL P1 payload storage, not store.IDENTITY.
    This is not an independent physical waveform proof of every glitch.
    """
    if capability!=0x4d504731 or packed_counts>>18 or status>>2:
        raise ValueError('MPG1 readback required, reserved bits zero')
    words=tuple(identity_words)
    if len(words)!=8 or any(type(w) is not int or not 0<=w<=0xffffffff for w in words):
        raise ValueError('Eight actual identity words required')
    native=0
    for w in words:native=(native<<32)|w
    return {'expected_points':packed_counts&511,'emitted_points':(packed_counts>>9)&511,
            'tx_done_fenced':bool(status&1),'source_fault':bool(status&2),
            'native_P1_identity_hex':'%064x'%native}
