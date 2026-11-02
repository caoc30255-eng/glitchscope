"""Offline cycle model of the frozen INPUT_ALREADY_SYNCED=1 B receiver.

One index is one nominal 100MHz clock. The NCO and receiver use old-register
values, including one-clock result_pending latency. No hardware imports/IO.
"""

PROFILES = tuple((d, s) for d in range(1, 5) for s in range(-2, 4-d))


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def replay(levels, d, s, accumulator=0, keep_votes=True):
    require(type(d) is int and type(s) is int and (d, s) in PROFILES, 'ILLEGAL_D_S')
    require(type(accumulator) is int and 0 <= accumulator < 25, 'NCO_ACCUMULATOR_0_TO_24')
    require(all(type(x) is int and x in (0, 1) for x in levels), 'DIGITAL_LEVELS_ONLY')
    acc = accumulator
    # At any non-reset NCO state, old rx_ce is high exactly when old acc<4.
    ce = acc < 4
    state, n, prev, low_count, bit, word, ones = 'IDLE', 0, 1, 0, 0, 0, 0
    start = None
    votes, frames, pending = [], [], None
    for clock, value in enumerate(levels):
        if pending is not None:
            pending['valid_index'] = clock
            frames.append(pending)
            pending = None
        old_ce = ce
        ce = acc + 4 >= 25
        acc = (acc + 4) % 25
        if not old_ce:
            continue
        if state == 'WAIT_HIGH':
            if value:
                state, prev, n = 'IDLE', 1, 0
            continue
        if state == 'IDLE':
            if prev and not value:
                state, n, low_count, bit, word, ones = 'CONFIRM', 0, 1, 0, 0, 0
                start, votes = clock, []
            prev = value
            continue
        n = (n + 1) & 255
        if state == 'CONFIRM':
            if n < 2:
                if not value:
                    low_count += 1
                    if low_count >= 2:
                        state = 'CHECK_START'
                else:
                    state, prev, n = 'IDLE', 1, 0
            else:
                state = 'CHECK_START'
        elif state == 'CHECK_START':
            if n == 8:
                if not value:
                    state, bit, ones = 'DATA', 0, 0
                else:
                    state, prev, n = 'IDLE', value, 0
        else:
            center = (24 + 16*bit if state == 'DATA' else 152) + s
            if n == center-d:
                ones, positions, observed = value, [clock], [value]
            elif n == center:
                ones += value
                positions.append(clock)
                observed.append(value)
            elif n == center+d:
                decision = int(ones + value >= 2)
                positions.append(clock)
                observed.append(value)
                if keep_votes:
                    votes.append(dict(bit=bit if state == 'DATA' else 'STOP',
                                      indices=positions[:], values=observed[:], decision=decision))
                ones = 0
                if state == 'DATA':
                    word = (word & ~(1 << bit)) | (decision << bit)
                    if bit == 7:
                        state = 'STOP'
                    else:
                        bit += 1
                else:
                    pending = dict(start_index=start, stop_index=clock, data=word,
                                   framing_error=not bool(decision), votes=votes[:])
                    state, n = ('IDLE' if decision else 'WAIT_HIGH'), 0
                    if decision:
                        prev = 1
    return frames
