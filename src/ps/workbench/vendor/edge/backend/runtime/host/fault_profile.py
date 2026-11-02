"""Frozen Direct ITEM payload-only fault coordinates for the existing 7010 ABI."""
from dataclasses import dataclass,asdict
from ch1_runtime_driver import unsigned

@dataclass(frozen=True)
class FaultProfile:
    byte: int
    bit: int
    phase: int
    width: int
    def validate(self,inner):
        from ch1_completion_ledger import _codec
        decoded=_codec().decode_item(bytes(inner))
        if not decoded['valid'] or decoded['route_mode']!=0:raise ValueError('Direct ITEM required')
        unsigned(self.byte,16,'fault byte',20);unsigned(self.bit,3,'fault bit')
        unsigned(self.phase,16,'fault phase');unsigned(self.width,16,'fault width',1)
        if self.byte>=len(inner)-2:raise ValueError('Fault must target ITEM payload only')
        # Interior windows make pin-level restoration observable unambiguously.
        if self.phase<5 or self.phase+self.width>45:
            raise ValueError('First marked stage requires interior bit window [5,45] of50 LIFE clocks')
        return asdict(self)
    def wire_suffix(self):
        import struct
        return bytes([1])+struct.pack('>HBHHB',self.byte,self.bit,self.phase,self.width,0)
