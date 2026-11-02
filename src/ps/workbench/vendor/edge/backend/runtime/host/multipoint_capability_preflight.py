"""Explicit read-only MPG1 capability probe after fresh session initialization.

No imports touch hardware. No profile command, ARM, START or retirement API.
"""
from ch1_peer_archive_driver import persist_exact
import ch1_evidence_store as store


def inspect_multipoint_capability(session, buses):
    def fresh():
        if (session.fault or session.current is not None or not session.upload.ready or
                session.peer.fault or session.control_transport.fault or
                session.mark_capture is None or session.mark_capture.used):
            raise RuntimeError('Fresh healthy idle session with unused mark preflight required')
        if buses['SYS'].read(0x18) or buses['SYS'].read(0x1c):
            raise RuntimeError('MPG1 first probe requires zero retirement/grant counters')
    fresh()
    peer=session.peer
    capability=peer.read(0xd20)
    if capability!=0x4d504731:
        raise ValueError('MPG1 capability missing; do not use multi-point commands')
    before=(peer.read(0xd24),peer.read(0xd28))
    identity_words=[peer.read(a) for a in range(0xd30,0xd50,4)]
    after=(peer.read(0xd24),peer.read(0xd28))
    if before!=after or before!=(0,0) or any(identity_words):
        raise RuntimeError('MPG1 is not fresh/stable; retain actual evidence, no trial')
    fresh()
    capture=session.mark_capture
    raw={'status':capture.read(8),'sample_count':capture.read(12),
         'trigger_offset':capture.read(16),'live_sample':capture.read(0x20)}
    if raw['status'] or raw['sample_count'] or raw['trigger_offset'] or raw['live_sample']&7!=3:
        raise RuntimeError('Raw capture/pins not fresh; no multi-point trial')
    report={'schema':'MPG1_CAPABILITY_PREFLIGHT_V0_1','session':session.root.name,
        'capability_hex':hex(capability),'MPG1_supported':True,'counts_before':list(before),
        'counts_after':list(after),'native_identity_words':identity_words,
        'configured_points':before[0]&511,'emitted_points':(before[0]>>9)&511,
        'raw_capture':raw,'peer_MMIO_writes_by_this_probe':0,'START_sent_by_this_probe':False,
        'snapshot_ARM_sent_by_this_probe':False,'multi_point_profile_sent':False,
        'exact_loaded_bitstream_hash_read_from_hardware':False,
        'scope':'Fresh MPG1 readback only; initialization precedes this probe; not multi-point execution acceptance'}
    session.journal.verify()
    persist_exact(session.root/'MPG1/preflight',{'preflight.json':store._json(report)})
    session.journal.record('MPG1_capability_preflight_saved',**report)
    return report
