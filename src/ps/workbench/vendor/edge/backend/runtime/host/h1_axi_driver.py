"""Driver for the NEW H1T1 peripheral, not the old 7020 UARTLite bitstream.

Constructor verifies IP identity before any write. No Overlay/Clocks/START calls.
Actual hardware use awaits AXI RTL validation and a newly built 7020 bit/hwh.
"""
class H1Transport:
    def __init__(self,mmio):
        self.mmio=mmio
        if self.read(0)!=0x48315431:raise RuntimeError('Requires new H1T1 peripheral; old UARTLite is not compatible')
    def read(self,addr):return int(self.mmio.read(addr))
    def write(self,addr,data):self.mmio.write(addr,int(data))
    def send_prepared(self,ledger):
        if ledger.fault or ledger.current is None or ledger.transport_offered:raise RuntimeError('No new durable pending upload; repeat offer forbidden')
        packet=ledger.current[3]
        flags=self.read(4)
        if not flags&1 or flags&0x7e:raise RuntimeError('TX not empty/ready or held RX evidence/fault')
        ledger.transport_offered=True
        ledger.record('transport_offer',raw_hex=packet.hex())
        for i,byte in enumerate(packet):
            if not self.read(4)&1:raise RuntimeError('Unexpected staging backpressure; stop without launch')
            self.write(0x10,byte|(0x100 if i==len(packet)-1 else 0))
        flags=self.read(4)
        if not flags&2 or flags&0x7c or self.read(0x20)!=len(packet):
            raise RuntimeError('Complete immutable packet not sealed; stop without launch')
        self.write(0x18,1)
        ledger.record('transport_launch_command',note='command only; physical completion and peer status separate')

    def read_and_preserve(self,ledger):
        """One held tuple. Write fsynced evidence BEFORE explicit queue release.

        Any malformed/rejected/unexpected status remains held for diagnosis.
        Successful local queue release is not a 7010 store/retirement proof.
        """
        flags=self.read(4)
        if flags&0x60:raise RuntimeError('Transport fault; retain queue and first lost evidence')
        if not flags&8:return None
        if flags&0x10:raise RuntimeError('Old snapshot requires explicit recovery; no automatic release')
        self.write(0x30,1)
        if not self.read(4)&0x10:raise RuntimeError('RX snapshot not accepted')
        ticket=self.read(0x40);meta=self.read(0x44)
        words=[self.read(a) for a in (0x48,0x4c,0x50,0x54,0x58)]
        raw=b''.join(w.to_bytes(4,'big') for w in words)[:18]
        length=meta&31;reason=(meta>>8)&7
        ledger.record('transport_snapshot',ticket=ticket,reason=reason,length=length,raw_hex=raw.hex())
        if length>18 or reason!=1 or length!=18:
            ledger.fault=True
            ledger.record('transport_error_stop',ticket=ticket,reason=reason,length=length)
            raise RuntimeError('Raw UART/CRC/format/partial evidence retained; no queue release')
        status=ledger.observe(raw)
        if ledger.fault:raise RuntimeError('Rejected status retained; no queue release')
        if self.read(0x5c)!=127:raise RuntimeError('Not all snapshot AXI reads delivered')
        # This call asserts actual software persistence, following fsync above.
        self.write(0x34,ticket)
        if self.read(4)&0x10:raise RuntimeError('Evidence release rejected; snapshot retained')
        ledger.record('transport_local_queue_released',ticket=ticket)
        return status
