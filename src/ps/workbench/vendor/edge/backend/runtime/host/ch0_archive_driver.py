"""H0R2 complete evidence readout and one-use durable release.

Caller owns an exclusive, synchronous AXI bus which raises on non-OK responses.
No physical addresses, resets, START, peer retirement or next-item credit.
SHA256 protects the saved files; H0R2 does not provide an export CRC footer.
"""
from dataclasses import dataclass
from pathlib import Path
import hashlib
import json
import os
import uuid

from ch0_registration_driver_v0_2 import CH0RegistrationDriverV2, unsigned


def encode(value):
    return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode('ascii')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def sync_dir(path):
    if os.name == 'posix':
        fd = os.open(str(path), os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def write_new(path, raw):
    with path.open('xb') as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())


@dataclass(frozen=True)
class CH0ArchiveReceipt:
    token: str
    evidence_dir: str
    manifest_sha256: str
    release_eligible: bool


class CH0ArchiveDriver:
    def __init__(self, registration, output_dir):
        if not isinstance(registration, CH0RegistrationDriverV2):
            raise TypeError('Actual H0R2 driver required')
        self.registration = registration
        self.root = Path(output_dir)
        self.receipts = {}
        self.releases = {}

    def _read(self, address):
        return self.registration.read(address)

    def _metadata(self):
        status = self._read(4)
        if not status & 1 or not (status & 2 or status & 4):
            raise RuntimeError('Capture still open or resource absent; no archive/release')
        binding = self.registration._binding()
        return {'binding': binding, 'status': status, 'first_fault': self._read(0x1c),
                'release_count': self._read(0x14),
                'a_count': self._read(8), 'b_count': self._read(12),
                'a_errors': self._read(0x140), 'b_errors': self._read(0x144),
                'a_first_error': self._read(0x148) << 32 | self._read(0x14c),
                'b_first_error': self._read(0x150) << 32 | self._read(0x154),
                'rejected_word': self._read(0x158),
                'rejected_tick': self._read(0x15c) << 32 | self._read(0x160)}

    def _samples(self, base, count):
        unsigned(count, 16)
        if count > 544:
            raise ValueError('Sample count exceeds physical capacity')
        raw = bytearray()
        for index in range(count):
            packed = b''.join(self._read(base + index * 16 + part * 4).to_bytes(4, 'big')
                              for part in range(3))
            if packed[-2:] != b'\0\0':
                raise ValueError('Sample DWORD padding invalid; no release')
            raw.extend(packed[:10])
        return bytes(raw)

    @staticmethod
    def _decode(raw, binding):
        decoded = []
        previous = binding['start']
        for offset in range(0, len(raw), 10):
            value = int.from_bytes(raw[offset:offset + 10], 'big')
            tick = value & ((1 << 64) - 1)
            if value >> 76 or not binding['start'] <= tick < binding['deadline'] or tick < previous:
                raise ValueError('Sample reserved bits/window/order invalid; no release')
            decoded.append({'data': value >> 68 & 255, 'flags': value >> 64 & 15, 'tick': tick})
            previous = tick
        return decoded

    def _persist(self, metadata, payloads):
        missing = []
        cursor = self.root
        while not cursor.exists():
            missing.append(cursor)
            cursor = cursor.parent
        self.root.mkdir(parents=True, exist_ok=True)
        for path in reversed(missing):
            sync_dir(path.parent)
        b = metadata['binding']
        directory = self.root / f"epoch_{b['epoch']:08x}_record_{b['record_id']:08x}"
        if directory.exists() and any(directory.glob('release_intent_*.json')):
            raise RuntimeError('Existing release intent: inspect uncertain state; no automatic restart/retry')
        manifest = encode({'format': 'H0R2_EVIDENCE_V1', 'metadata': metadata,
                           'files': {name: {'sha256': sha(raw), 'bytes': len(raw)}
                                     for name, raw in payloads.items()},
                           'hardware_export_crc': 'NOT_PROVIDED',
                           'complete_orphan_journal': False})
        if directory.exists():
            if not (directory / 'committed.json').is_file() or (directory / 'committed.json').read_bytes() != manifest or any(
                    not (directory / name).is_file() or (directory / name).read_bytes() != raw
                    for name, raw in payloads.items()):
                raise RuntimeError('Archive identity conflict/incomplete commit; original retained')
            for name in [*payloads, 'committed.json']:
                with (directory / name).open('r+b') as handle:
                    os.fsync(handle.fileno())
        else:
            directory.mkdir()
            sync_dir(self.root)
            for name, raw in payloads.items():
                write_new(directory / name, raw)
            sync_dir(directory)
            write_new(directory / 'committed.json', manifest)
        sync_dir(directory)
        sync_dir(self.root)
        return directory, sha(manifest)

    def archive_current(self, expected_binding, *, expected_request=None):
        """Faulted evidence may be saved diagnostically, never released.

        expected_request is the complete on-wire request, not image payload only.
        Classification is per-lane reception, never STM32/image business success.
        """
        before = self._metadata()
        if before['binding'] != expected_binding:
            raise RuntimeError('Actual immutable binding differs from caller flight')
        a = self._samples(0x400, before['a_count'])
        b = self._samples(0x2800, before['b_count'])
        if self._metadata() != before:
            raise RuntimeError('Evidence changed during readout; original held')
        eligible = before['status'] == 3 and not before['first_fault']
        if eligible and (self._read(0x20) != 0x1ffffff or self._read(0x24) !=
                         before['a_count'] << 16 | before['b_count']):
            raise RuntimeError('Incomplete actual metadata/sample R delivery')
        payloads = {'descriptor.json': encode(before), 'a_samples.bin': a, 'b_samples.bin': b}
        lanes = [self._decode(raw, expected_binding) for raw in (a, b)]
        if expected_request is not None:
            expected_request = bytes(expected_request)
            if len(expected_request) != expected_binding['request_length']:
                raise ValueError('Expected complete request length differs from registration')
            payloads['expected_request.bin'] = expected_request
        classification = {'faulted': bool(before['status'] & 4), 'source_provided': expected_request is not None}
        for name, samples in zip(('a', 'b'), lanes):
            actual = bytes(sample['data'] for sample in samples)
            payloads[name + '_raw.bin'] = actual
            classification[name + '_source_match'] = None if expected_request is None else actual == expected_request
            classification[name + '_reception_success'] = (not bool(before['status'] & 4) and
                expected_request is not None and actual == expected_request and not before[name + '_errors'] and
                not any(sample['flags'] for sample in samples))
        payloads['classification.json'] = encode(classification)
        directory, manifest_sha = self._persist(before, payloads)
        # Recheck after filesystem latency, even for an exact cached archive.
        if self._metadata() != before:
            raise RuntimeError('Evidence changed while saving; archive retained, no release receipt')
        receipt = CH0ArchiveReceipt(uuid.uuid4().hex, str(directory), manifest_sha, eligible)
        self.receipts[receipt.token] = {'object': receipt, 'metadata': before, 'used': False}
        return receipt

    def release_saved(self, receipt):
        """One attempt only. Lost replies need inspection, never automatic retry."""
        if type(receipt) is not CH0ArchiveReceipt:
            raise TypeError('Driver-issued saved receipt required')
        record = self.receipts.get(receipt.token)
        if record is None or record['object'] is not receipt or record['used'] or not receipt.release_eligible:
            raise RuntimeError('Unknown/used/diagnostic receipt; no release')
        record['used'] = True
        metadata = record['metadata']
        directory = Path(receipt.evidence_dir)
        if any(directory.glob('release_intent_*.json')):
            raise RuntimeError('Prior release intent exists; no second attempt')
        manifest_raw = (directory / 'committed.json').read_bytes()
        if sha(manifest_raw) != receipt.manifest_sha256:
            raise ValueError('Saved manifest changed; no release')
        manifest = json.loads(manifest_raw)
        for name, fingerprint in manifest['files'].items():
            raw = (directory / name).read_bytes()
            if len(raw) != fingerprint['bytes'] or sha(raw) != fingerprint['sha256']:
                raise ValueError('Saved evidence changed; no release')
        if self._metadata() != metadata or self._read(0x20) != 0x1ffffff or self._read(0x24) != metadata['a_count'] << 16 | metadata['b_count']:
            raise RuntimeError('Live evidence/coverage changed; no release')
        unsigned(metadata['release_count'], minimum=0)
        if metadata['release_count'] == 0xffffffff:
            raise RuntimeError('Release counter would wrap; no release')
        # Persist intent before any proof write. A crash never creates permission
        # to resume this in-memory receipt or to blindly reissue the command.
        write_new(directory / ('release_intent_' + receipt.token + '.json'), encode(metadata))
        sync_dir(directory)
        if self._metadata() != metadata:
            raise RuntimeError('Late fault during intent fsync; no proof writes')
        binding = metadata['binding']
        writes = [(0x80, binding['epoch']), (0x84, binding['record_id']),
                  (0x88, metadata['a_count'] << 16 | metadata['b_count'])]
        writes += [(0x90 + i * 4, binding['identity'] >> (224 - i * 32) & 0xffffffff) for i in range(8)]
        for address, value in writes:
            self.registration.bus.write(address, value)
        if self._metadata() != metadata:
            raise RuntimeError('Evidence changed during proof staging; no release command')
        self.registration.bus.write(0x74, 1)
        status = self._read(4)
        if status != 8 or self._read(0x14) != metadata['release_count'] + 1:
            raise RuntimeError('Actual CH0 release not confirmed; inspect retained state')
        result = {'binding': binding, 'release_count': metadata['release_count'] + 1,
                  'CH0_hardware_release_verified': True, 'evidence_dir': receipt.evidence_dir,
                  'next_item_allowed': False, 'peer_retirement_verified': False}
        observed = directory / ('release_observed_' + receipt.token + '.json')
        frozen = encode(result)
        write_new(observed, frozen)
        sync_dir(directory)
        self.releases[receipt.token] = {'object': result, 'frozen': frozen,
                                        'observed': observed, 'receipt': receipt}
        return result

    def verify_release(self, result):
        """Recheck this driver's exact observed release; dictionaries cannot mint proof."""
        records = [record for record in self.releases.values() if record['object'] is result]
        if len(records) != 1:
            raise RuntimeError('No driver-issued observed CH0 release')
        record = records[0]
        if encode(result) != record['frozen'] or record['observed'].read_bytes() != record['frozen']:
            raise ValueError('CH0 observed release altered')
        receipt = record['receipt']
        directory = Path(receipt.evidence_dir)
        raw = (directory / 'committed.json').read_bytes()
        if sha(raw) != receipt.manifest_sha256:
            raise ValueError('CH0 saved manifest altered')
        for name, info in json.loads(raw)['files'].items():
            data = (directory / name).read_bytes()
            if sha(data) != info['sha256'] or len(data) != info['bytes']:
                raise ValueError('CH0 saved original altered')
        if self._read(4) != 8 or self._read(0x14) != result['release_count']:
            raise RuntimeError('CH0 release no longer matches actual idle/count')
        return result
