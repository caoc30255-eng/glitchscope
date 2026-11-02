"""H7S1 production retirement capacity gate. No reset, START or blind retries."""
from pathlib import Path
import json
import ch1_evidence_store as store
from ch1_runtime_driver import unsigned
from ch0_archive_driver import CH0ArchiveDriver
from ps_path_compat import path_within


class SystemGate:
    def __init__(self, bus, journal):
        self.bus, self.journal = bus, journal
        self.ch0 = None
        self.grant = None
        self.fault = False
        if self.read(0) != 0x48375331 or self.read(8) != 100000000:
            raise RuntimeError('Requires production H7S1 at declared 100MHz; no writes')

    def read(self, offset):
        return unsigned(self.bus.read(offset), 32, 'SYS DWORD')

    def status(self):
        status = self.read(4)
        if status & 0x82 or self.fault:
            raise RuntimeError('SYS stopped/faulted; retain evidence')
        return status

    def bind_ch0_release(self, driver, proof, binding):
        if not isinstance(driver, CH0ArchiveDriver):
            raise TypeError('Actual CH0 archive driver required')
        driver.verify_release(proof)
        actual = proof['binding']
        if any(actual[k] != getattr(binding, k) for k in ('epoch', 'record_id', 'kind', 'identity')):
            raise ValueError('CH0 release belongs to another CH1 flight')
        if self.grant is not None:
            raise RuntimeError('Previous SYS grant has not been verified retired')
        self.ch0 = (driver, proof, binding)

    def _saved(self, saved, binding):
        if saved.get('hardware_proof_command_submitted') is not True:
            raise RuntimeError('Actual main persistence proof has not been submitted')
        if (saved['epoch'], saved['record_id'], int(saved['identity_hex'], 16)) != (
                binding.epoch, binding.record_id, binding.identity):
            raise ValueError('CH1 saved archive differs from flight')
        directory = Path(saved['evidence_dir']).resolve()
        marker = json.loads((directory / 'committed.json').read_bytes())
        proof = marker['confirmation']
        if any(saved.get(k) != v for k, v in proof.items()):
            raise ValueError('Archive confirmation changed from observed saved receipt')
        if not {'descriptor.bin', 'samples.bin'} <= marker['files'].keys():
            raise ValueError('Incomplete CH1 archive')
        for name, info in marker['files'].items():
            path = (directory / name).resolve()
            if not path_within(path, directory):
                raise ValueError('Archive file escapes evidence directory')
            data = path.read_bytes()
            if len(data) != info['bytes'] or store.sha(data) != info['sha256']:
                raise ValueError('CH1 saved data altered')
        descriptor_raw = (directory / 'descriptor.bin').read_bytes()
        samples = (directory / 'samples.bin').read_bytes()
        descriptor = store.descriptor_decode(descriptor_raw)
        if (store.crc16(descriptor_raw) != saved['descriptor_crc']
                or store.crc16(samples) != saved['samples_crc']
                or len(samples) != descriptor['raw_count'] * 10
                or descriptor['raw_count'] != saved['raw_count']):
            raise ValueError('Saved data differs from hardware export fingerprints/count')
        if any(descriptor[k] != getattr(binding, k) for k in (
                'epoch', 'record_id', 'kind', 'identity', 'start', 'deadline')):
            raise ValueError('Saved actual descriptor differs from runtime binding')
        return store.sha((directory / 'committed.json').read_bytes())

    def _live(self, runtime, binding):
        if self.ch0 is None or self.ch0[2] != binding:
            raise RuntimeError('Missing matching observed CH0 release')
        self.ch0[0].verify_release(self.ch0[1])
        if runtime.binding() != binding or runtime.status() & (4 | 32 | 256):
            raise RuntimeError('Runtime is not ready for a new saved release')
        if runtime.status() & (64 | 128) != (64 | 128):
            raise RuntimeError('Actual guard has not qualified saved evidence and physical done')
        status = self.status()
        if status & 0x75 != 0x70 or self.read(0x20) != 0:
            raise RuntimeError('SYS requires released CH0, active valid CH1, matching DONE and no old grant')
        if (self.read(0x0c), self.read(0x10), self.read(0x18)) != (
                binding.epoch, binding.record_id, runtime._read(0x24)):
            raise RuntimeError('SYS actual epoch/id/count differs from flight')

    def grant_saved_release(self, runtime, binding, saved):
        if self.fault or self.grant is not None:
            raise RuntimeError('No second/uncertain SYS grant attempt')
        try:
            self._live(runtime, binding)
            digest = self._saved(saved, binding)
            count = self.read(0x1c)
            if count == 0xffffffff:
                raise RuntimeError('SYS grant counter exhausted')
            self.journal.record('SYS_grant_intent', epoch=binding.epoch,
                record_id=binding.record_id, identity=binding.identity,
                committed_sha256=digest, grant_count_before=count)
            self.journal.verify()
            self._live(runtime, binding)
            if self._saved(saved, binding) != digest or self.read(0x1c) != count:
                raise RuntimeError('Sources changed during grant-intent persistence')
            # Burn before the MMIO command. A lost response cannot authorize replay.
            self.grant = (binding, count + 1)
            self.bus.write(0x20, 1)
            if self.status() & 0x75 != 0x71 or self.read(0x20) != 1 or self.read(0x1c) != count + 1:
                raise RuntimeError('Actual SYS grant unconfirmed; no release retry')
            self.journal.record('SYS_grant_verified', epoch=binding.epoch,
                record_id=binding.record_id, grant_count=count + 1)
        except Exception:
            self.fault = True
            raise

    def verify_retired(self, binding, retire_count):
        if self.grant is None or self.grant[0] != binding:
            raise RuntimeError('No matching SYS grant')
        if (self.status() & 0x75 or self.read(0x20) or self.read(0x0c) != binding.epoch
                or self.read(0x18) != retire_count or self.read(0x1c) != self.grant[1]):
            self.fault = True
            raise RuntimeError('SYS retirement/count/capacity-clear not confirmed')
        self.journal.record('SYS_retirement_verified', epoch=binding.epoch,
            record_id=binding.record_id, retire_count=retire_count, capacity=0)
        self.grant = self.ch0 = None
