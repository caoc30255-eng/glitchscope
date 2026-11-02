"""Bounded polling UARTLite byte adapter for the frozen shared control UART.

Caller supplies the existing UARTLite object and exclusive ownership. Reads
STATUS/RX, writes TX_FIFO only; never resets FIFOs, enables IRQs, changes clock
or loads Overlay. Host timing bounds are transport limits, not hardware ticks.
"""
import math,time
from ch1_control_session import decode_frame
from ch1_runtime_driver import unsigned

RX_FIFO,TX_FIFO,STATUS=0,4,8
RX_VALID,TX_EMPTY,TX_FULL,UART_ERRORS=1,4,8,0xe0
NOTIFICATIONS=(0x31,0x32,0x33,0x38)


class UARTLiteControlTransport:
    def __init__(self,uart,journal,*,exclusive_owner=False,timeout=1.0,
                 quiet_time=0.002,interbyte_timeout=0.01,max_frames=64,
                 poll_limit=1000000,clock=time.monotonic,fast_mmio=True):
        if exclusive_owner is not True:raise ValueError('Caller must own the shared UART exclusively')
        for name,value in [('timeout',timeout),('quiet_time',quiet_time),('interbyte_timeout',interbyte_timeout)]:
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<=0:
                raise ValueError(f'Positive finite {name} required')
        if timeout<=max(quiet_time,interbyte_timeout):raise ValueError('Overall timeout must exceed receive timing bounds')
        self.uart=uart;self.journal=journal;self.timeout=timeout;self.quiet=quiet_time
        self.gap=interbyte_timeout;self.frame_limit=unsigned(max_frames,32,'max_frames',1)
        self.poll_limit=unsigned(poll_limit,32,'poll_limit',1);self.clock=clock
        self.fault=False;self.busy=False;self.last_trace=None
        # PYNQ's public array is the same live DWORD mapping used by MMIO.read.
        # Cache it once; never copy/slice the register map or touch extra offsets.
        array=getattr(uart,'array',None) if fast_mmio else None
        if array is not None:
            if (getattr(array,'ndim',None)!=1 or getattr(array,'size',0)<4 or
                    getattr(array.dtype,'kind',None)!='u' or array.dtype.itemsize!=4):
                raise ValueError('UARTLite fast MMIO requires a live uint32 mapping')
        self.array=array
        # No constructor I/O: mere creation does not consume unknown RX data.

    def exchange(self,request,expected_type):
        return self._exchange(request,expected_type)

    def exchange_checked(self,request,expected_type,before_first_tx):
        if not request or not callable(before_first_tx):raise ValueError('Nonempty request and local first-TX guard required')
        return self._exchange(request,expected_type,before_first_tx=before_first_tx)

    def _exchange(self,request,expected_type,*,before_first_tx=None):
        if self.fault or self.busy:raise RuntimeError('UART transport fault/concurrent exchange; no further I/O')
        request=bytes(request)
        if request:decode_frame(request)
        elif expected_type is not None:raise ValueError('Receive-only poll cannot expect a command response')
        if expected_type is not None:unsigned(expected_type,8,'expected control type')
        self.busy=True
        raw=bytearray();pending=bytearray();frames=[];statuses=[];tx_count=0;tx_attempts=0;reply_count=0;bad_rx_word=None
        started=self.clock();last_activity=started;last_rx=started;polls=0

        def status():
            nonlocal polls
            polls+=1
            if polls>self.poll_limit:raise TimeoutError('UART polling operation budget exhausted')
            value=(int(self.array[STATUS//4]) if self.array is not None else
                   unsigned(self.uart.read(STATUS),32,'UARTLite STATUS DWORD'))
            if not statuses or value!=statuses[-1]:
                if len(statuses)>=4096:raise RuntimeError('Status-transition capture bound exceeded')
                statuses.append(value)
            if value&~0xff:raise ValueError('UARTLite STATUS reserved bits changed')
            if value&UART_ERRORS:raise RuntimeError(f'UARTLite error flags 0x{value:02x}; preserve unread FIFO')
            if value&(TX_EMPTY|TX_FULL)==(TX_EMPTY|TX_FULL):raise ValueError('Impossible UARTLite TX empty/full flags')
            return value

        def check_time():
            now=self.clock()
            if now-started>=self.timeout:raise TimeoutError('UART exchange deadline; request effect may be uncertain')
            if pending and now-last_rx>=self.gap:raise TimeoutError('Partial control frame interbyte deadline')
            return now

        def parse_pending(before_tx):
            nonlocal reply_count
            # Parse only after the currently available RX bytes have been drained.
            while pending:
                if pending[0]!=0xa5 or (len(pending)>=2 and pending[1]!=0x5a) or (len(pending)>=3 and pending[2]!=1):
                    raise ValueError('Control stream prefix/version mismatch')
                if len(pending)>=5:
                    if pending[4]>32:raise ValueError('Control payload exceeds frozen bound')
                    size=pending[4]+7
                    if len(pending)>=size:
                        packet=bytes(pending[:size]);kind,payload=decode_frame(packet)
                        if before_tx and kind not in NOTIFICATIONS:
                            raise RuntimeError('Stale command reply before TX; no new request sent')
                        if kind not in NOTIFICATIONS and kind!=expected_type:
                            raise RuntimeError('Unexpected control reply; stop without retry')
                        if kind==expected_type:
                            if tx_count<len(request):raise RuntimeError('Reply arrived before request fully handed to TX FIFO')
                            reply_count+=1
                            if reply_count>1:raise RuntimeError('Duplicate command replies in one exchange')
                        frames.append(packet);del pending[:size]
                        if len(frames)>self.frame_limit:raise RuntimeError('Control frame-count bound exceeded')
                        continue
                break

        def receive(*,before_tx=False):
            nonlocal last_activity,last_rx,bad_rx_word
            while True:
                flags=status();check_time()
                if not flags&RX_VALID:
                    parse_pending(before_tx)
                    return flags
                # Exclusive owner: RX_FULL proves 16 bytes are available. Drain
                # that known count without expensive per-byte status/time/parser calls.
                count=16 if flags&2 else 1
                for _ in range(count):
                    word=(int(self.array[RX_FIFO//4]) if self.array is not None else
                          unsigned(self.uart.read(RX_FIFO),32,'UARTLite RX DWORD'))
                    if word>255:
                        bad_rx_word=word
                        raise ValueError('UARTLite RX DWORD padding changed; no byte invented')
                    raw.append(word);pending.append(word)
                last_rx=self.clock();last_activity=last_rx
                if len(raw)>39*(self.frame_limit+1):raise RuntimeError('Raw control capture bound exceeded')

        try:
            self.journal.verify()
            self.journal.record('uart_byte_exchange_intent',request_hex=request.hex(),expected_type=expected_type)
            # Finish and preserve queued notifications/partial header before a new TX.
            while True:
                flags=receive(before_tx=True)
                if not pending and flags&TX_EMPTY:break
                check_time()
            for byte in request:
                while True:
                    flags=receive();check_time()
                    if not flags&TX_FULL:break
                if tx_count==0 and before_first_tx is not None:
                    before_first_tx() # after adapter intent fsync/RX drain/TX wait
                    check_time()
                tx_attempts+=1
                if self.array is not None:self.array[TX_FIFO//4]=byte
                else:self.uart.write(TX_FIFO,byte) # May execute and then throw; never replay.
                tx_count+=1;last_activity=self.clock()
            while True:
                flags=receive();now=check_time()
                complete=(reply_count==1) if expected_type is not None else True
                if complete and not pending and flags&TX_EMPTY and now-last_activity>=self.quiet:
                    break
            trace={'request_hex':request.hex(),'rx_hex':raw.hex(),'tx_bytes_confirmed':tx_count,
                   'receive_mode':'fifo_first','direct_mmio':self.array is not None,
                   'tx_write_attempts':tx_attempts,'status_transitions':statuses,'frames':len(frames),
                   'pending_hex':pending.hex(),'polls':polls,'elapsed_seconds':self.clock()-started}
            self.last_trace=trace
            # No file writes in the byte-drain loop. Save before caller sees any frame.
            self.journal.record('uart_byte_exchange_saved',**trace)
            return b''.join(frames)
        except Exception as exc:
            self.fault=True
            trace={'request_hex':request.hex(),'rx_hex':raw.hex(),'tx_bytes_confirmed':tx_count,
                   'receive_mode':'fifo_first','direct_mmio':self.array is not None,
                   'tx_write_attempts':tx_attempts,'status_transitions':statuses,'pending_hex':pending.hex(),
                   'frames':len(frames),'polls':polls,'reason':str(exc),'bad_rx_word':bad_rx_word,
                   'request_effect_uncertain':bool(tx_attempts)}
            self.last_trace=trace
            if not self.journal.fault:
                try:self.journal.record('uart_byte_exchange_stopped',**trace)
                except Exception:pass
            raise
        finally:self.busy=False
