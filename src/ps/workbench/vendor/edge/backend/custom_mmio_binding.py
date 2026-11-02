"""Pure saved-wire READ32 binding. No device imports, writes or hardware grants."""
import json
import struct
from pathlib import Path
from custom_plan import require
from ch1_control_session import decode_frame, event_payload, audit_application_journal
import ch1_evidence_store as store

ADDRESSES = [0xd20, 0xd24, 0xd28] + list(range(0xd30, 0xd50, 4)) + [0xd24, 0xd28]


def journal_entries(root):
    root = Path(root); entries = []
    for path in sorted(root.rglob('application_*.jsonl')):
        audit_application_journal(path)
        for line in path.read_text(encoding='utf-8').splitlines():
            entry = json.loads(line)
            entry['_journal_path'] = path.relative_to(root).as_posix()
            entries.append(entry)
    return entries


def packets(entry):
    if entry['event'] == 'control_rx_stream':
        data = bytes.fromhex(entry['raw_hex'])
    elif entry['event'] == 'uart_byte_exchange_saved':
        require(entry.get('native_error') == 0 and not entry.get('pending_hex') and
                entry.get('bad_rx_word') is None, 'MMIO_BAD_NATIVE_CAPTURE')
        data = bytes.fromhex(entry['rx_hex'])
    else:
        return []
    found = []; pos = 0
    while pos < len(data):
        require(len(data)-pos >= 5, 'MMIO_TRUNCATED_PACKET')
        packet = data[pos:pos+data[pos+4]+7]
        decode_frame(packet)
        found.append((pos, packet)); pos += len(packet)
    return found


def reference(entry, packet, offset=0):
    return dict(path=entry['_journal_path'], journal_index=entry['journal_index'],
                entry_sha256=entry['sha256'], byte_offset=offset,
                raw_hex=packet.hex(), packet_sha256=store.sha(packet))


def bind_reads(entries, captures, proof, observed, window=None):
    """Validate raw transactions independently of outer file inventories.

    New evidence supplies an exact committed window. Historical evidence uses
    its original DONE/completion events, without rewriting or inventing refs.
    """
    identity = int(proof['identity_hex'], 16); rid = proof['record_id']
    if window is None:
        end = [e for e in entries if e['event'] == 'MPG1_completed_count_before_retirement'
               and e['identity_hex'] == proof['identity_hex'] and e['record_id'] == rid
               and e['epoch'] == proof['epoch']]
        require(len(end) == 1, 'MMIO_UNIQUE_COMPLETION_WINDOW_REQUIRED')
        end = end[0]; path = end['_journal_path']; stop = end['journal_index']
        start = -1; control_epoch = None
    else:
        path = window['path']; start = window['start_index']; stop = window['stop_index']
        control_epoch = window['control_epoch']
        require(type(start) is int and type(stop) is int and 0 <= start < stop,
                'MMIO_INVALID_WINDOW')
    rows = sorted([e for e in entries if e['_journal_path'] == path], key=lambda e:e['journal_index'])
    done = [e for e in rows if e['event'] == 'peer_event_effect' and e.get('effect') == 'W19_DONE'
            and e['event_receipt']['identity'] == identity and e['journal_index'] < stop]
    require(len(done) == 1, 'MMIO_CURRENT_RECORD_DONE_REQUIRED')
    if window is None:
        start = done[0]['journal_index']+1
    require(done[0]['journal_index'] < start, 'MMIO_READS_MUST_FOLLOW_CURRENT_DONE')
    require(not any(e['event'] == 'strict_three_party_retire_intent' and e.get('identity') == identity
                    and e['journal_index'] < stop for e in rows), 'MMIO_READS_AFTER_RETIREMENT')
    selected = [e for e in rows if start <= e['journal_index'] < stop]
    intents = []
    for e in selected:
        if e['event'] != 'control_tx_intent': continue
        packet = bytes.fromhex(e['raw_hex']); kind, payload = decode_frame(packet)
        if kind == 0x3b and len(payload) == 32 and payload[8] == 0:
            intents.append(e)
    # Historical window may contain other completed-record diagnostics, but
    # its final thirteen requests must be the complete point-proof sequence.
    if window is None: intents = intents[-13:]
    require(len(intents) == 13, 'MMIO_EXACT_THIRTEEN_READS_REQUIRED')
    values = []; transactions = []; previous_txn = None
    for e, address in zip(intents, ADDRESSES):
        request = bytes.fromhex(e['raw_hex']); kind, payload = decode_frame(request)
        require(len(request) == 39 and kind == 0x3b, 'MMIO_READ32_REQUEST_TYPE_LENGTH')
        epoch, txn, op, count, actual_address, value = struct.unpack('>IIBBHI', payload[:16])
        if control_epoch is None: control_epoch = epoch
        require(epoch == control_epoch and epoch > 0 and txn > 0 and
                (previous_txn is None or txn == previous_txn+1), 'MMIO_EPOCH_OR_TXN_CHANGED')
        previous_txn = txn
        require(op == 0 and count == 1 and actual_address == address and value == 0 and
                payload[16:] == bytes(16), 'MMIO_READ32_ADDRESS_OR_OPERATION_CHANGED')
        following = [r for r in selected if r['journal_index'] > e['journal_index']]
        capture = []
        for r in following:
            if r['event'] in ('control_tx_intent', 'control_poll_intent'): break
            for offset, packet in packets(r):
                if decode_frame(packet)[0] == 0x7b: capture.append((r, offset, packet))
        require(len(capture) == 1, 'MMIO_EXACT_RAW_REPLY_REQUIRED')
        r, offset, reply = capture[0]
        require(reply in captures, 'MMIO_REPLY_MISSING_FROM_CAPTURE')
        if r['event'] == 'uart_byte_exchange_saved':
            require(r['request_hex'] == request.hex() and r['tx_bytes_confirmed'] == 39,
                    'MMIO_NATIVE_REQUEST_NOT_TRANSMITTED')
        typ, body = decode_frame(reply)
        require(len(reply) == 39 and typ == 0x7b and body[:12] == payload[:12] and
                body[12:16] == bytes((0,0,1,0)) and body[20:] == bytes(12),
                'MMIO_REPLY_TXN_ADDRESS_STATUS_OR_COUNT_CHANGED')
        value = int.from_bytes(body[16:20], 'big'); values.append(value)
        transactions.append(dict(control_epoch=epoch, txn=txn, op=op, address=address, value=value,
                                 request=reference(e, request), reply=reference(r, reply, offset)))
    expected = [0x4d504731] + observed['count_status_before'] + observed['native_identity_words'] + observed['count_status_after']
    require(values == expected, 'MMIO_RAW_VALUES_DIFFER_FROM_READBACK')
    points = observed['expected_points']
    require(type(points) is int and 0 <= points <= 256 and values[1:3] == values[-2:] == [points|(points<<9),1],
            'MMIO_RAW_COUNTS_DONE_OR_STABILITY_CHANGED')
    native = 0
    for word in values[3:11]: native = (native<<32)|word
    require(native == int.from_bytes(event_payload(identity,0),'little'), 'MMIO_RAW_IDENTITY_CHANGED')
    require(all(observed[k] == proof[k] for k in ('epoch','record_id','identity_hex','count_status_before',
                'count_status_after','native_identity_words')) and proof['configured_points'] == proof['emitted_points'] == points
            and proof['actual_DONE_fenced'] is True and proof['source_fault'] is False,
            'MMIO_PROOF_DIFFERS_FROM_RAW')
    return dict(raw_MMIO_transaction_binding_verified=True, record_id=rid, identity_hex=proof['identity_hex'],
                epoch=proof['epoch'], control_epoch=control_epoch, transactions=transactions,
                window=dict(path=path,start_index=start,stop_index=stop,control_epoch=control_epoch))


def saved_record_binding(root, rid, result, trace, expected_points=None):
    root = Path(root); directory = root/'MPG1_SCAN'/('record_%08x'%rid)
    proof = json.loads((directory/'completed/counts.json').read_bytes())
    require(result['MPG1_pre_retirement'] == proof, 'MMIO_RESULT_PROOF_CHANGED')
    require(proof['record_id'] == rid and proof['identity_hex'] == result['identity_hex'],
            'MMIO_CURRENT_RESULT_IDENTITY_REQUIRED')
    if expected_points is not None:
        require(proof['configured_points'] == proof['emitted_points'] == expected_points,
                'MMIO_COUNT_DIFFERS_FROM_CURRENT_PROFILE')
    if not (root/'CUSTOM_SCAN/scope/scope.json').exists():
        # Legacy public originals have no custom readback sidecar. Reconstruct
        # their values and transaction refs in memory; never rewrite originals.
        observed=dict(proof, expected_points=proof['configured_points'])
        return bind_reads(trace[0], trace[1], proof, observed)
    observed = json.loads((directory/'completion_readback/readback.json').read_bytes())
    bound = bind_reads(trace[0], trace[1], proof, observed, observed.get('raw_MMIO_window'))
    saved=json.loads((directory/'raw_MMIO_binding/binding.json').read_bytes())
    require(observed.get('raw_MMIO_window') is not None and saved == proof.get('raw_MMIO_binding') == bound,
            'MMIO_COMMITTED_TRANSACTION_REFERENCES_REQUIRED')
    return bound
