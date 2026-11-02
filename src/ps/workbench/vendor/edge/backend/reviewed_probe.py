"""Explicit PYNQ read-only probe; never loads Overlay or writes any register."""
from pathlib import Path
import json, hashlib, xml.etree.ElementTree as ET, sys
sys.path.insert(0, str(Path(__file__).resolve().parent/'host'))
from ps_candidate_session import BANKS
from ch1_runtime_driver import unsigned

EXPECTED_HWH_SHA256 = '8d65319fd06ccafb9acdabe1c19868106cd1945f085b2fa03d55b89d238bd2bc'


def probe(mmio_factory, hwh):
    hwh = Path(hwh)
    raw = hwh.read_bytes()
    if hashlib.sha256(raw).hexdigest() != EXPECTED_HWH_SHA256:
        raise ValueError('HWH differs from the reviewed candidate; no MMIO performed')
    xml = ET.fromstring(raw)
    ranges = list(xml.iter('MEMRANGE'))
    for name, (base, size, _) in BANKS.items():
        matches = [r for r in ranges if r.get('INSTANCE') == 'h1_evidence_system_0'
                   and r.get('SLAVEBUSINTERFACE') == 'S_'+name]
        if len(matches) != 1 or (int(matches[0].get('BASEVALUE'), 0),
                int(matches[0].get('HIGHVALUE'), 0)) != (base, base + size - 1):
            raise ValueError('HWH address/range mismatch; no MMIO performed')
    rows = []
    for name, (base, size, identity) in BANKS.items():
        bus = mmio_factory(base, size)
        actual = unsigned(bus.read(0), 32, 'IP ID')
        status = unsigned(bus.read(4), 32, 'IP status')
        rows.append({'bank': name, 'base': hex(base), 'range': size,
                     'ID': hex(actual), 'ID_match': actual == identity,
                     'status': hex(status)})
    sysbus = mmio_factory(BANKS['SYS'][0], BANKS['SYS'][1])
    result = {'read_only': True, 'all_IDs_match': all(r['ID_match'] for r in rows),
        'banks': rows, 'declared_clock_hz': unsigned(sysbus.read(8), 32, 'declared clock'),
        'local_epoch': unsigned(sysbus.read(0x0c), 32, 'epoch'),
        'retire_count': unsigned(sysbus.read(0x18), 32, 'retire count'),
        'grant_count': unsigned(sysbus.read(0x1c), 32, 'grant count'),
        'capacity_permission': unsigned(sysbus.read(0x20), 32, 'permission'),
        'hardware_writes': 0, 'START_sent': False, 'hardware_system_acceptance': False}
    return result


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hwh', required=True)
    parser.add_argument('--out', required=True, help='New report file; never overwrite a prior report')
    args = parser.parse_args()
    # Inspect the output target before reading hardware.
    out = Path(args.out)
    if out.exists(): raise FileExistsError(out)
    from pynq import MMIO
    result = probe(MMIO, args.hwh)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open('x', encoding='utf-8') as f:
        json.dump(result, f, indent=2); f.write('\n'); f.flush()
        import os
        os.fsync(f.fileno())
    print(json.dumps(result, indent=2))
    if not result['all_IDs_match']: raise SystemExit(1)


if __name__ == '__main__': main()
