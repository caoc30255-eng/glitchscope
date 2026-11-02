"""One HELLO from a fresh UploadLedger; READY is advisory, never completion."""
from h1_protocol import Kind, State, decode_status
from ch1_runtime_driver import unsigned


class HelloSession:
    def __init__(self, transport, upload, journal, *, poll_limit=1000, save_peer=None):
        self.transport, self.upload, self.journal = transport, upload, journal
        self.limit = unsigned(poll_limit, 32, 'HELLO poll limit', 1)
        self.attempted = False
        if save_peer is not None and not callable(save_peer):
            raise ValueError('Peer persistence callback must be callable')
        self.save_peer = save_peer

    def establish(self):
        if self.attempted or self.upload.ready or self.upload.current is not None or self.upload.fault:
            raise RuntimeError('Fresh one-use HELLO required; no automatic retransmission')
        self.attempted = True
        try:
            self.journal.record('HELLO_intent', session=self.upload.session)
            self.upload.prepare(Kind.HELLO)
            self.transport.send_prepared(self.upload)
            # Production 7010 holds even empty HELLO evidence before semantic READY.
            if self.save_peer is not None:
                proof = self.save_peer()
                if not isinstance(proof, dict) or proof.get('peer_store_verified') is not True:
                    raise RuntimeError('HELLO peer persistence not confirmed; no READY consumption')
                self.journal.record('HELLO_peer_store_confirmed',
                    ticket=proof['ticket'], record_id=proof['store_record_id'])
            # Existing transport fsyncs the exact snapshot before interpretation
            # and checks all seven actual read credits before saved queue release.
            hello = self
            class CheckedLedger:
                @property
                def fault(self): return hello.upload.fault
                @fault.setter
                def fault(self, value): hello.upload.fault = value
                def record(self, *args, **kwargs): return hello.upload.record(*args, **kwargs)
                def observe(self, raw):
                    s = decode_status(raw)
                    if (s.state, s.session, s.seq, s.inner_crc, s.code, s.credit) != (
                            State.READY, hello.upload.session, 0, 0, 0, 1):
                        raise ValueError('HELLO requires exact session READY/seq0/CRC0/code0/credit1')
                    return hello.upload.observe(raw)
            for _ in range(self.limit):
                result = self.transport.read_and_preserve(CheckedLedger())
                if result is not None:
                    if self.transport.read(4) & 0x7e:
                        raise RuntimeError('HELLO leaves busy/queued/faulted H1 evidence')
                    self.journal.record('HELLO_saved_READY', session=self.upload.session,
                        physical_completion=False, record_binding=False)
                    return {'session_established': True, 'completion': False}
            raise TimeoutError('No actual HELLO READY; do not resend')
        except Exception:
            self.upload.fault = True
            self.upload.credit = 0
            raise
