"""Durable single-upload admission ledger; transport/retirement integration pending.

Import never touches devices. Open creates a NEW ledger only; existing sessions
cannot silently resume after process/board reset. No START or blind retry API.
"""
from pathlib import Path
import os, json, hashlib
from h1_protocol import Kind, State, encode_data, crc16, decode_status

class UploadLedger:
    def __init__(self,directory,session):
        if not 0<session<=0xffffffff:raise ValueError('Invalid session')
        directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
        self.path=directory/f'session_{session:08x}.jsonl'
        self.file=self.path.open('x',encoding='utf-8')
        self.session=session;self.ready=False;self.credit=0;self.seq=0
        self.current=None;self.accepted=False;self.done=False;self.fault=False;self.transport_offered=False
        self.record('begin',session=session,scope='offline admission ledger; hardware transport pending')

    def record(self,event,**fields):
        self.file.write(json.dumps({'event':event,**fields},sort_keys=True)+'\n')
        self.file.flush();os.fsync(self.file.fileno())

    def prepare(self,kind,inner=b''):
        if self.fault or self.current is not None:raise RuntimeError('Pending upload/fault; no new frame')
        kind=Kind(kind)
        if kind==Kind.HELLO:
            if self.ready:raise RuntimeError('Session already established')
            seq=0
        else:
            if not self.ready or self.credit!=1:raise RuntimeError('No trusted READY credit')
            seq=self.seq+1
        raw=encode_data(kind,self.session,seq,inner)
        # Durability before bytes can be handed to a future PL driver.
        self.record('prepared',kind=int(kind),session=self.session,seq=seq,
                    inner_crc=crc16(inner) if inner else 0,raw_hex=raw.hex(),sha256=hashlib.sha256(raw).hexdigest())
        self.current=(kind,seq,bytes(inner),raw);self.accepted=False;self.done=False;self.transport_offered=False
        self.credit=0
        return raw

    def observe(self,raw):
        raw=bytes(raw)
        # Preserve even malformed or unsolicited evidence before interpreting it.
        self.record('status_raw',raw_hex=raw.hex())
        try:
            status=decode_status(raw)
            if self.fault or self.current is None:raise ValueError('Unsolicited status or locked ledger')
            kind,seq,inner,packet=self.current
            if (status.session,status.seq)!=(self.session,seq):raise ValueError('Status identity mismatch')
            if status.state==State.REJECTED:
                self.fault=True;self.record('rejected',code=status.code,credit=status.credit)
                return status
            expected=crc16(inner) if inner else 0
            if status.inner_crc!=expected:raise ValueError('Full-inner fingerprint mismatch')
            if kind==Kind.HELLO:
                if status.state!=State.READY or status.credit!=1:raise ValueError('HELLO requires READY credit1')
                self.record('hello_ready');self.ready=True;self.credit=1;self.current=None
            elif status.state==State.ACCEPTED:
                if self.done:raise ValueError('Status regressed after TX_DONE')
                self.record('accepted',seq=seq,credit=status.credit);self.accepted=True
            elif status.state==State.TX_DONE:
                if not self.accepted:raise ValueError('TX_DONE before saved ACCEPTED')
                self.record('physical_done_report',seq=seq,credit=status.credit);self.done=True
            elif status.state==State.READY:
                # READY alone is not a persisted CH1/core-retirement identity proof.
                self.record('ready_advisory',seq=seq,credit=status.credit)
            return status
        except ValueError as exc:
            self.fault=True;self.record('fault',reason=str(exc));raise

    def stop_timeout(self):
        self.record('timeout_stop',pending_hex=self.current[3].hex() if self.current else '')
        self.fault=True

    def close(self): self.file.close()
