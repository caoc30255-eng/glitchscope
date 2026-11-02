"""Conservative, local, reference-assisted phase envelopes; no device access.

Never select phase using the held-out target answer. Absolute timestamps are
reported as a conditional diagnostic, not an attested capture-clock origin.
"""
import copy
import hashlib
from window_audit import analyze


def classify(scenarios):
    if not scenarios or not all(s.get('aligned') for s in scenarios):
        return 'UNRESOLVED'
    good = sum(s['bit_errors'] == 0 and s['framing_errors'] == 0 for s in scenarios)
    if good == len(scenarios):
        return 'ROBUST_LOCAL_SOFTWARE_ZERO'
    if good == 0:
        return 'ERROR_IN_EVERY_RETAINED_PHASE'
    return 'PHASE_SENSITIVE'


def evaluate(record, analyzer=None):
    # This frozen baseline fits only non-target bytes, flags and relative times.
    baseline = (analyzer or analyze)(record)
    out = dict(schema='B_LOCAL_PHASE_ENVELOPE_V0_1', session=record['session'],
               record_id=record['record_id'], baseline_alignment_state=baseline['state'],
               hardware_access=False, new_STARTs=0, AI_used=False,
               full_ITEM_CRC_evaluated=False, hardware_verified_region=False,
               scope='MODEL_CONDITIONAL_LOCAL_ENVELOPE_NOT_HARDWARE_RECOMMENDATION',
               phase_selection_uses_target_value=False, input_files=record['input_files'])
    phases = baseline.get('matching_NCO_accumulators', [])
    out['retained_phases'] = phases
    # An entirely contradicted model cannot create green recommendations.
    usable = bool(phases) and baseline.get('held_out_target_matched_phases', 0) > 0
    out['model_has_at_least_one_actual_target_match'] = usable
    out['current_target_matches_all_retained_phases'] = (
        usable and baseline['held_out_target_matched_phases'] == len(phases))
    out['target_matches_are_validation_only_not_phase_filter'] = True
    if not phases:
        out.update(state='UNALIGNED', profiles=[], robust_candidate_region=[],
                   timestamp_diagnostic=dict(status='NO_ALIGNMENT', adopted=False))
        return out, baseline
    rows = []
    for original in baseline['profiles']:
        row = copy.deepcopy(original)
        row['baseline_display_state'] = row.pop('state')
        row['state'] = classify(row['scenarios']) if usable else 'MODEL_CONTRADICTED'
        row['zero_error_phases'] = [s['phase'] for s in row['scenarios']
                                   if s.get('aligned') and s['bit_errors'] == s['framing_errors'] == 0]
        row['total_retained_phases'] = len(phases)
        rows.append(row)
    # The CH0 event tick and NCO share reset/clock in the reference source.
    # This does not supply CAP sample-zero's tick. Enumerate an offset for each
    # hypothesis, and show the extra, UNATTESTED pipeline/reset assumption.
    timestamp_rows = []
    actual = next(r for r in rows if (r['d'], r['s']) ==
                  (baseline['actual_profile']['d'], baseline['actual_profile']['s']))
    for scenario in actual['scenarios']:
        if not scenario['aligned']:
            continue
        offsets = [record['lanes']['b'][f['byte_index']]['tick'] - f['valid_index']
                   for f in scenario['frames']]
        origin = offsets[0] - 1
        timestamp_rows.append(dict(
            phase=scenario['phase'], event_tick_minus_model_valid_index=offsets[0],
            all_relative_event_offsets_equal=len(set(offsets)) == 1,
            hypothetical_capture_sample_zero_tick=origin,
            shared_reset_pipeline_1_congruence=(scenario['phase'] == (4 * origin) % 25)))
    out.update(state='LOCAL_ENVELOPE_AVAILABLE' if usable else 'MODEL_CONTRADICTED',
               profiles=rows,
               robust_candidate_region=[dict(d=r['d'], s=r['s']) for r in rows
                                        if r['state'] == 'ROBUST_LOCAL_SOFTWARE_ZERO'],
               timestamp_diagnostic=dict(
                   status='ABSOLUTE_ORIGIN_NOT_INDEPENDENTLY_ATTESTED', adopted=False,
                   hypotheses=timestamp_rows,
                   missing='Independent mapping of CAP sample zero to CH0 event tick',
                   metadata_0x28_meaning='Circular buffer base/trigger addresses, not a timestamp',
                   assumption='Shared reset plus exact one-clock event-register latency; diagnostic only'),
               retained_phase_count_after_timestamp_review=len(phases),
               raw_CH0_sha256=hashlib.sha256(bytes(record['levels'])).hexdigest())
    return out, baseline
