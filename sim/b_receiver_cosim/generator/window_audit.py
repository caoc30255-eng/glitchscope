"""Hash-checked local waveform analysis. Never starts/changes board state.

Alignment uses lab MARK/target-byte metadata and original UART byte timestamps.
It is explicitly reference-assisted experimental analysis, not blind reception.
"""
from pathlib import Path
import binascii
import hashlib
import json
import statistics
from b_receiver import PROFILES, replay, require


def sha(data):
    return hashlib.sha256(data).hexdigest()


def js(path):
    return json.loads(Path(path).read_bytes())


def verify_directory(path):
    path = Path(path).resolve()
    manifest = js(path/'committed.json')['files']
    for name, proof in manifest.items():
        f = (path/name).resolve()
        require(path in f.parents, 'COMMITMENT_PATH_ESCAPE')
        data = f.read_bytes()
        require(sha(data) == (proof if isinstance(proof, str) else proof['sha256']), 'RAW_SHA_CHANGED:'+name)
        if isinstance(proof, dict):
            require(len(data) == proof['bytes'], 'RAW_LENGTH_CHANGED:'+name)


def decode_samples(data, binding):
    require(len(data) % 10 == 0, 'CH0_SAMPLE_WORD_LENGTH')
    out, last = [], binding['start']
    for i in range(0, len(data), 10):
        v = int.from_bytes(data[i:i+10], 'big')
        tick = v & ((1 << 64)-1)
        require(v >> 76 == 0 and last <= tick < binding['deadline'], 'CH0_SAMPLE_BITS_OR_WINDOW')
        out.append(dict(data=(v >> 68) & 255, flags=(v >> 64) & 15, tick=tick))
        last = tick
    return out


def load_record(session_root, record_id):
    root = Path(session_root).resolve()
    result_dir = root/'EXECUTOR'/('record_%08x'%record_id)/'result'
    verify_directory(result_dir)
    result = js(result_dir/'result.json')
    require(result['record_id'] == record_id and result['evidence_quality'] == 'VALID', 'VALID_RECORD_REQUIRED')
    matches = list((root/'CH0').glob('epoch_*_record_%08x'%record_id))
    require(len(matches) == 1, 'UNIQUE_CH0_RECORD_REQUIRED')
    ch = matches[0]
    desc = js(ch/'descriptor.json')
    epoch = desc['binding']['epoch']
    suffix = 'epoch_%08x_record_%08x'%(epoch, record_id)
    mark = root/'MARK'/suffix/'saved'
    intent = root/'EXECUTOR'/('record_%08x'%record_id)/'intent'
    admission = root/'admission'/suffix
    for p in (ch, mark, intent, admission):
        verify_directory(p)
    request = (ch/'expected_request.bin').read_bytes()
    require(request == (intent/'request.bin').read_bytes(), 'INTENT_SOURCE_MISMATCH')
    require(request[:2] == b'\x55\xaa' and len(request) >= 22 and
            binascii.crc_hqx(request[2:-2], 0xffff) == int.from_bytes(request[-2:], 'big'), 'SOURCE_ITEM_CRC')
    ctx = js(mark/'context.json')
    identity = int(result['identity_hex'], 16)
    require((int.from_bytes(request[3:7], 'big'), request[7], int.from_bytes(request[8:10], 'big'),
             int.from_bytes(request[10:12], 'big'), request[14], request[15]) ==
            ((identity >> 56) & 0xffffffff, (identity >> 48) & 255, (identity >> 32) & 65535,
             (identity >> 16) & 65535, (identity >> 8) & 255, identity & 255), 'SOURCE_WIRE_IDENTITY')
    require(ctx['binding'] == dict(epoch=epoch, record_id=record_id, identity=identity), 'MARK_IDENTITY_MISMATCH')
    require(desc['binding']['identity'] == identity and desc['binding']['record_id'] == record_id and
            desc['status'] == 3 and desc['first_fault'] == 0, 'CH0_BINDING_OR_FAULT')
    require(ctx['arm']['source_sha256'] == sha(request), 'MARK_SOURCE_SHA')
    raw = (mark/'samples.bin').read_bytes()
    require(len(raw) == 4096 and ctx['metadata'][2:4] == [4096, 2048], 'COMPLETE_CAP_WINDOW_REQUIRED')
    mark_levels = [(v >> 2) & 1 for v in raw]
    require([i for i in range(1, 4096) if mark_levels[i] and not mark_levels[i-1]] == [2048], 'MARK_TRIGGER_MISMATCH')
    lanes = {}
    for name in ('a', 'b'):
        lanes[name] = decode_samples((ch/(name+'_samples.bin')).read_bytes(), desc['binding'])
        require(bytes(v['data'] for v in lanes[name]) == (ch/(name+'_raw.bin')).read_bytes(), 'SAMPLES_VS_BYTES')
        require(len(lanes[name]) == desc[name+'_count'], 'ACTUAL_SAMPLE_COUNT')
    profile = result['actual_receiver_B']
    require(profile == js(admission/'admission.json')['profile'] and profile['RX_profile_verified'] is True and
            profile['profile_seq'] == record_id,
            'APPLIED_PROFILE_NOT_SAVED')
    require(result['requested_receiver_B'] == {k: profile[k] for k in ('d', 's')}, 'REQUEST_APPLIED_MISMATCH')
    require(all(result['retirement'][k] is True for k in ('CH0_release_verified', 'CH1_retirement_verified',
                                                       'peer_retirement_verified')) and
            result['next_credit']['next_item_allowed'] is True, 'RETIRED_READY_REQUIRED')
    inputs = {}
    for directory in (result_dir, ch, mark, intent, admission):
        for f in directory.iterdir():
            if f.is_file():
                inputs[f.relative_to(root).as_posix()] = dict(bytes=f.stat().st_size, sha256=sha(f.read_bytes()))
    return dict(session=root.name, record_id=record_id, result=result, source=request, context=ctx,
                levels=[v & 1 for v in raw], lanes=lanes, input_files=inputs)


def analyze(record):
    source, levels, ctx = record['source'], record['levels'], record['context']
    d, s = (record['result']['actual_receiver_B'][k] for k in ('d', 's'))
    require((d, s) in PROFILES, 'SUPPORTED_ACTUAL_PROFILE')
    profile = ctx['arm']['profile']
    target, bit = profile['byte'], profile['bit']
    require(0 <= target < len(source) and 0 <= bit < 8, 'TARGET_BYTE_BIT')
    # MARK and target bit give a one-bit-wide possible start interval. Phase/
    # width are NOT used to select a clock phase or force a successful decode.
    lower, upper = 2048-(bit+2)*100-2, 2048-(bit+1)*100+2
    anchors = [i for i in range(max(1, lower), min(len(levels), upper+1)) if levels[i-1] and not levels[i]]
    base = dict(schema='B_LOCAL_PARAMETER_REPLAY_V0_1', session=record['session'], record_id=record['record_id'],
                actual_profile=dict(d=d, s=s), input_files=record['input_files'],
                scope='LOCAL_REFERENCE_ASSISTED_SOFTWARE_REPLAY_NOT_FULL_FRAME_OR_HARDWARE_RECOMMENDATION',
                model_validation='SEMANTIC_TESTS_ONLY_RTL_COSIM_NOT_YET_RUN',
                nominal_sample_ns=10, samples=4096, full_ITEM_CRC_evaluated=False,
                hardware_verified_recommendation=False, AI_used=False, new_STARTs=0,
                alignment_uses=['MARK_WINDOW', 'SAVED_TARGET_BYTE_AND_BIT', 'NON_TARGET_B_BYTES_FLAGS',
                                'ACTUAL_B_RELATIVE_TIMESTAMPS'],
                target_byte_value_held_out_of_phase_fit=True,
                assumed_byte_clock_count=100, capture_input_path_phase_measured=False)
    if len(anchors) != 1:
        return dict(base, state='UNALIGNED', reason='TARGET_START_EDGE_NOT_UNIQUE', start_candidates=anchors, profiles=[])
    anchor = anchors[0]
    a, b = record['lanes']['a'], record['lanes']['b']
    if len(a) != len(source) or len(b) != len(source):
        return dict(base, state='UNALIGNED', reason='BYTE_LOSS_OR_EXTRA_REQUIRES_SEPARATE_ALIGNMENT', profiles=[])
    spacings = [a[i+1]['tick']-a[i]['tick'] for i in range(len(a)-1)]
    period = int(statistics.median(spacings))
    if not 1000 <= period <= 1100:
        return dict(base, state='UNALIGNED', reason='UNSUPPORTED_CHARACTER_PERIOD', profiles=[])
    # Cold-start edge artifacts are excluded until >=1 full character of warmup.
    slots = [(j, anchor+(j-target)*period) for j in range(len(source))
             if 1000 <= anchor+(j-target)*period and anchor+(j-target)*period+1000 < len(levels)]
    if len(slots) < 2 or target not in [j for j, _ in slots]:
        return dict(base, state='UNALIGNED', reason='TWO_COMPLETE_REFERENCE_SLOTS_REQUIRED', profiles=[])

    def match(frames):
        pairs = []
        for index, at in slots:
            found = [f for f in frames if at <= f['start_index'] <= at+8]
            if len(found) != 1:
                return None
            pairs.append((index, found[0]))
        return pairs

    fits = []
    for phase in range(25):
        matched = match(replay(levels, d, s, phase, False))
        if matched is None:
            continue
        if any(f['data'] != b[j]['data'] or b[j]['flags'] not in (0, 2) or
               f['framing_error'] != bool(b[j]['flags'] & 2) for j, f in matched if j != target):
            continue
        offsets = [b[j]['tick']-f['valid_index'] for j, f in matched]
        if len(set(offsets)) == 1:
            fits.append(phase)
    base.update(target_byte=target, target_bit=bit, target_start_index=anchor,
                byte_period_clocks=period, compared_byte_indices=[j for j, _ in slots],
                matching_NCO_accumulators=fits,
                inference_limit='UNKNOWN_RELATIVE_CE_PHASE_ENUMERATED; MODEL_INITIAL_IDLE_WITH_WARMUP; '
                                'ALIGNMENT_CONDITIONAL_ON_LAB_METADATA_AND_ACTUAL_B_MATCH')
    if not fits:
        return dict(base, state='UNALIGNED', reason='NO_PHASE_REPRODUCES_ACTUAL_B_BYTES_FLAGS_AND_TIME_DIFFERENCES', profiles=[])
    rows = []
    for dd, ss in PROFILES:
        observations = []
        for phase in fits:
            matched = match(replay(levels, dd, ss, phase))
            if matched is None:
                observations.append(dict(phase=phase, aligned=False))
                continue
            errors = sum(bin(f['data'] ^ source[j]).count('1') for j, f in matched)
            observations.append(dict(phase=phase, aligned=True, bit_errors=errors,
                                     byte_errors=sum(f['data'] != source[j] for j, f in matched),
                                     framing_errors=sum(f['framing_error'] for _, f in matched),
                                     frames=[dict(byte_index=j, **f) for j, f in matched]))
        aligned = [o for o in observations if o['aligned']]
        state = ('UNRESOLVED' if len(aligned) != len(observations) else
                 'SOFTWARE_ZERO_ERROR_ALL_RETAINED_PHASES' if all(o['bit_errors'] == o['framing_errors'] == 0 for o in aligned) else
                 'SOFTWARE_PHASE_DEPENDENT' if len({(o['bit_errors'], o['framing_errors']) for o in aligned}) > 1 else
                 'SOFTWARE_ERRORS')
        rows.append(dict(d=dd, s=ss, state=state, compared_bits=8*len(slots),
                         bit_errors_min=min((o['bit_errors'] for o in aligned), default=None),
                         bit_errors_max=max((o['bit_errors'] for o in aligned), default=None),
                         scenarios=observations))
    actual_errors = sum(bin(b[j]['data'] ^ source[j]).count('1') for j, _ in slots)
    actual_row = next(r for r in rows if (r['d'], r['s']) == (d, s))
    predictions = [f for o in actual_row['scenarios'] if o['aligned'] for f in o['frames']
                   if f['byte_index'] == target]
    target_matches = sum(f['data'] == b[target]['data'] and
                         f['framing_error'] == bool(b[target]['flags'] & 2) for f in predictions)
    target_validation = ('ALL_RETAINED_PHASES_MATCH_HELD_OUT_TARGET' if target_matches == len(fits) else
                         'PHASE_AMBIGUOUS_HELD_OUT_TARGET' if target_matches else 'HELD_OUT_TARGET_MISMATCH')
    if target_matches != len(fits):
        for row in rows:
            row['state_before_alignment_check'] = row['state']
            row['state'] = 'MODEL_ALIGNMENT_UNCERTAIN'
    candidates = [dict(d=r['d'], s=r['s']) for r in rows if r['state'] == 'SOFTWARE_ZERO_ERROR_ALL_RETAINED_PHASES']
    return dict(base, state='LOCAL_CURRENT_B_MATCHED' if target_matches == len(fits) else 'LOCAL_PHASE_UNCERTAIN',
                held_out_target_validation=target_validation, held_out_target_matched_phases=target_matches,
                actual_target_byte=b[target]['data'], actual_compared_bit_errors=actual_errors,
                software_candidate_region=candidates, profiles=rows)
