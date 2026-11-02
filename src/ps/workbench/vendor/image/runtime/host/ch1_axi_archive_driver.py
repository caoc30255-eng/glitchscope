"""Explicit MMIO archive driver for H1C1 + H1J1. No Overlay/clock/START/reset.

    Receives caller-owned MMIO objects; this package has no assigned board bases.
    Persistence ACKs follow actual fsync. Hardware retirement is separate.
"""
from pathlib import Path
import json
import ch1_evidence_store as store
import ch1_aux_store as aux_store

class CH1ArchiveDriver:
    def __init__(self,main_mmio,aux_mmio,output_dir,*,poll_limit=1000,event_limit=2048):
        self.main=main_mmio;self.aux=aux_mmio;self.root=Path(output_dir)
        if self._read(self.main,0)!=0x48314331 or self._read(self.aux,0)!=0x48314a31:
            raise RuntimeError('Requires H1C1 and H1J1; no writes performed')
        if not isinstance(poll_limit,int) or poll_limit<1 or not isinstance(event_limit,int) or event_limit<1:
            raise ValueError('Positive polling/event bounds required')
        self.poll_limit=poll_limit;self.event_limit=event_limit

    @staticmethod
    def _read(bus,address):
        value=bus.read(address)
        if isinstance(value,bool) or not isinstance(value,int) or not 0<=value<=0xffffffff:
            raise ValueError('MMIO read must deliver one unsigned DWORD')
        return value

    @staticmethod
    def _write(bus,address,value):bus.write(address,int(value))

    def drain_aux(self):
        """Save old events even under journal fault; does not clear that fault."""
        saved=[]
        for _ in range(self.event_limit):
            status=self._read(self.aux,4)
            if not status&0x21:
                errors=self._read(self.aux,8);orphans=self._read(self.aux,12)
                if not errors and not orphans:return saved
                self._write(self.aux,0x10,1 if errors else 2)
            for _ in range(self.poll_limit):
                status=self._read(self.aux,4)
                if status&1 and not status&0x20:break
            else:raise TimeoutError('Auxiliary snapshot not stable; no ACK')
            packed=b''.join(self._read(self.aux,0x100+i*4).to_bytes(4,'big') for i in range(14))
            if packed[-2:]!=b'\0\0':raise ValueError('Auxiliary DWORD padding changed; no ACK')
            crc=self._read(self.aux,0x18)
            if self._read(self.aux,0x48)!=0x7fff:raise RuntimeError('Incomplete delivered auxiliary reads')
            result=aux_store.persist_event(self.root/'aux',packed[:54],crc)
            for address,key in ((0x20,'epoch'),(0x24,'seq'),(0x28,'kind'),(0x2c,'crc')):
                self._write(self.aux,address,result[key])
            self._write(self.aux,0x14,1)
            if self._read(self.aux,4)&1:raise RuntimeError('Saved auxiliary ACK not consumed; original held')
            saved.append(result)
        if not self._read(self.aux,4)&0x21 and not self._read(self.aux,8) and not self._read(self.aux,12):
            return saved
        raise RuntimeError('Auxiliary drain budget exhausted; remaining evidence held, no main proof')

    def archive_current(self,*,watermark_epoch,watermark_tick,expected_payload=None):
        """Read/archive/assert store, never issue application retirement.

        Watermark must come from the actual epoch's finalized event clock,
        supplied by the future runtime controller, not PC wall time or close+1.
        Replays keep the original main archive watermark/context immutable.
        """
        status=self._read(self.main,4)
        if status&0x10:raise RuntimeError('Main fault: retain cache; use diagnostic readout, no main proof')
        if not status&1:return None
        if not status&2:raise RuntimeError('Main footer not stable; wait before archive')
        descriptor=b''.join(self._read(self.main,0x100+i*4).to_bytes(4,'big') for i in range(21))
        d=store.descriptor_decode(descriptor)
        if watermark_epoch!=d['epoch'] or isinstance(watermark_tick,bool) or not isinstance(watermark_tick,int) or not d['close']<watermark_tick<=0xffffffffffffffff:
            raise ValueError('Actual matching finalized watermark required; no proof')
        samples=bytearray()
        for index in range(d['raw_count']):
            packed=b''.join(self._read(self.main,0x400+index*16+part*4).to_bytes(4,'big') for part in range(3))
            if packed[-2:]!=b'\0\0':raise ValueError('Main sample DWORD padding changed; no proof')
            samples.extend(packed[:10])
        count=self._read(self.main,8);dcrc=self._read(self.main,0x14);scrc=self._read(self.main,0x18)
        if count!=d['raw_count'] or self._read(self.main,0x20)!=24+3*count:
            raise RuntimeError('Incomplete delivered main reads; no proof')
        if store.crc16(descriptor)!=dcrc or store.crc16(samples)!=scrc:
            raise ValueError('Main export fingerprint mismatch; no proof')
        self.drain_aux()
        if self._read(self.aux,4)&2 or self._read(self.main,4)&0x10:
            raise RuntimeError('Archive retained, fault prevents main confirmation')
        streams=aux_store.load_bound_events(self.root/'aux',d['epoch'],d['identity'],d['record_id'],d['start'],d['close'])
        directory=self.root/'main'/f"epoch_{d['epoch']:08x}_record_{d['record_id']:08x}"
        if (directory/'committed.json').is_file():
            frozen=json.loads((directory/'input_context.json').read_text(encoding='utf-8'))
            if watermark_tick<frozen['watermark']:raise ValueError('Actual watermark regressed')
            watermark_tick=frozen['watermark']
        result=store.persist_record(self.root/'main',descriptor,samples,dcrc,scrc,
            errors=streams['errors'],orphans=streams['orphans'],watermark_tick=watermark_tick,expected_payload=expected_payload)
        status=self._read(self.main,4)
        if status&0x10:raise RuntimeError('Fault after persistence: archive kept, main proof withheld')
        phase=(status>>8)&15
        if phase==5:
            for address,value in ((0x30,result['epoch']),(0x34,result['record_id']),(0x38,result['raw_count']),
                                  (0x3c,(result['descriptor_crc']<<16)|result['samples_crc'])):
                self._write(self.main,address,value)
            identity=int(result['identity_hex'],16)
            for index in range(8):self._write(self.main,0x40+index*4,(identity>>(224-index*32))&0xffffffff)
        elif phase not in (6,7):raise RuntimeError('Main phase changed; no confirmation command')
        # PROOF/DONE retry repeats only the cached commit command, not staging writes.
        self._write(self.main,0x60,1)
        if self._read(self.main,4)&0x10:raise RuntimeError('Hardware rejected main persistence proof')
        return {**result,'hardware_proof_command_submitted':True,
                'hardware_retirement_verified':False,'scope':'evidence persistence only'}
