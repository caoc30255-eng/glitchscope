"""HPQ1 observation driver. Bus routing must be explicitly integrated first.

No base-address default, guessed W19 generation, START or device reset.
The supplied bus propagates non-OK AXI responses and delivers unsigned DWORDs.
"""
def word(value):
    if type(value) is not int or not 0<=value<=0xffffffff:raise ValueError('Unsigned DWORD required')
    return value

class PeerPrestartDriver:
    def __init__(self,bus):
        self.bus=bus;self.last_seq=0
        if self.read(0)!=0x48505131:raise RuntimeError('HPQ1 observer required; no writes')
    def read(self,a):return word(self.bus.read(a))
    def snapshot(self,*,current,epoch,session):
        word(epoch);word(session)
        if not epoch or not session:raise ValueError('Nonzero expected peer namespace required')
        status=self.read(4)
        if not status&1 or status&16:raise RuntimeError('Observer unauthorized/source fault')
        # Finish a prior held snapshot before requesting replacement.
        if status&2:
            for a in [0x100,0x104,0x108,0x10c,*range(0x110,0x130,4)]:self.read(a)
            if self.read(0x00c)!=4095:raise RuntimeError('Prior snapshot not delivered')
        self.bus.write(0x010 if current else 0x014,1)
        seq=self.read(8)
        values=[self.read(a) for a in [0x100,0x104,0x108,0x10c,*range(0x110,0x130,4)]]
        identity=0
        for value in values[4:]:identity=(identity<<32)|value
        status=self.read(4)
        if self.read(0x00c)!=4095 or seq<=self.last_seq or not status&32 or bool(status&64)!=current or bool(status&128)!=current:
            raise RuntimeError('Snapshot stale/wrong mode/unconsumed or sequence regressed')
        if (values[0],values[3])!=(epoch,session) or not values[1] or values[2]>>24:
            raise ValueError('Actual observer namespace/generation/format mismatch')
        if current:
            if values[2]&255 not in (2,3,4) or not 12<=(values[2]>>8)&65535<=534 or (identity>>120)&7 or identity>>219 or (identity>>187)&0xffffffff!=session or (identity>>123)&0xffffffff!=epoch or (identity>>88)&0xffffffff!=values[1]:
                raise ValueError('Current identity not bound to actual W19 generation')
        elif identity or values[2]:raise ValueError('Basis must not fabricate a current identity')
        self.last_seq=seq
        return {'peer_epoch':epoch,'session':session,'next_generation':values[1],
                'identity':identity,'kind':values[2]&255,'length':(values[2]>>8)&65535,
                'snapshot_seq':seq,'current':current,'source':'HPQ1 actual W19 core snapshot'}
