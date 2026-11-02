"""Wire codec matching the frozen AX7010 PL design. No device access."""
from dataclasses import dataclass
import struct
from enum import IntEnum

class Kind(IntEnum):
    HELLO=1; CONFIG=2; ITEM=3; CLEANUP=4

class State(IntEnum):
    READY=0x80; ACCEPTED=0x81; REJECTED=0x82; TX_DONE=0x83

def crc16(data):
    value=0xffff
    for byte in data:
        value ^= byte << 8
        for _ in range(8):
            value=((value<<1)^0x1021)&0xffff if value&0x8000 else (value<<1)&0xffff
    return value

def encode_data(kind, session, seq, inner=b''):
    kind=Kind(kind); inner=bytes(inner)
    if not 0<session<=0xffffffff or not 0<=seq<0xffffffff:
        raise ValueError('Nonzero session and non-wrapping sequence required')
    if kind==Kind.HELLO:
        if seq or inner: raise ValueError('HELLO requires empty seq0')
    else:
        sof={Kind.CONFIG:b'\x55\xcc',Kind.ITEM:b'\x55\xaa',Kind.CLEANUP:b'\x55\xee'}[kind]
        if not seq or not 4<=len(inner)<=534 or not inner.startswith(sof):
            raise ValueError('Wrong inner kind/length/sequence')
        if crc16(inner[2:-2])!=int.from_bytes(inner[-2:],'big'):
            raise ValueError('Invalid inner CRC')
    body=struct.pack('>BBIIH',1,kind,session,seq,len(inner))+inner
    return b'\xa6\x69'+body+crc16(body).to_bytes(2,'big')

@dataclass(frozen=True)
class Status:
    state: State
    session: int
    seq: int
    inner_crc: int
    code: int
    credit: int

def decode_status(raw):
    raw=bytes(raw)
    if len(raw)!=18 or raw[:2]!=b'\xa6\x6a': raise ValueError('Status length/SOF')
    if crc16(raw[2:16])!=int.from_bytes(raw[16:],'big'): raise ValueError('Status CRC')
    version,state,session,seq,inner_crc,code,credit=struct.unpack('>BBIIHBB',raw[2:16])
    if version!=1 or code>8 or credit>1: raise ValueError('Status fields')
    state=State(state)
    if state!=State.REJECTED and code: raise ValueError('Non-rejection error code')
    return Status(state,session,seq,inner_crc,code,credit)

class StatusStream:
    """Byte-at-a-time bounded framing. Corruption is surfaced to the caller.

    No automatic retransmission: the AX raw-evidence slot may still be held.
    At most 18 bytes are retained regardless of input chunk size.
    """
    def __init__(self): self.pending=bytearray(); self.bad_frames=0; self.discarded=0
    def feed(self,data):
        frames=[]; errors=[]
        for byte in data:
            if not self.pending:
                if byte==0xa6:self.pending.append(byte)
                else:self.discarded+=1
            elif len(self.pending)==1:
                if byte==0x6a:self.pending.append(byte)
                elif byte!=0xa6:self.pending.clear();self.discarded+=2
                else:self.discarded+=1
            else:
                self.pending.append(byte)
                if len(self.pending)==18:
                    raw=bytes(self.pending)
                    try: frames.append((decode_status(raw),raw));self.pending.clear()
                    except ValueError as exc:
                        self.bad_frames+=1;errors.append((raw,str(exc)))
                        # Search only after rejecting the entire 18-byte candidate.
                        pos=raw.find(b'\xa6\x6a',1)
                        self.pending=bytearray(raw[pos:] if pos>=0 else (b'\xa6' if raw[-1]==0xa6 else b''))
        return frames,errors

    def end_partial(self):
        raw=bytes(self.pending);self.pending.clear()
        return raw
