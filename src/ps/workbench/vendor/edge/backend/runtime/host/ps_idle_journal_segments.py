"""Explicit application-log segmentation at a fully retired idle boundary.

Every ApplicationJournal still verifies ALL bytes of its own file. Sealed files
remain retained and are rehashed at each segment boundary; CONFIG owners retain
and verify their original journal when their evidence is used. This changes the
verification scope: ordinary exchanges verify the ACTIVE segment, not the entire
historical session. No resets, retries, identity rewrites or hardware writes.
"""
from pathlib import Path
import uuid
from ch1_control_session import ApplicationJournal
from ch1_runtime_driver import unsigned


def _idle(session,buses):
    session._available()
    if (session.current is not None or session.ticket is not None or
            session.upload.current is not None or session.completion.current is not None or
            not session.upload.ready or session.upload.credit!=1 or
            session.peer.fault or session.peer.events or session.coordinator.fault or
            session.control_transport.fault or session.control_transport.busy or
            session.gate.grant is not None):
        raise RuntimeError('Journal boundary requires retired flight and consumed actual READY')
    status={name:int(bus.read(4)) for name,bus in buses.items()}
    if (not status['CTRL']&1 or status['CTRL']&(2|4|8|32|64|256) or
            status['H1']&0x7e or status['MAIN']&0x11 or status['MAP']&7 or
            status['CH0']&7 or status['SYS']&0xf7 or status['AUX']&0x3f or
            buses['AUX'].read(8) or buses['AUX'].read(12) or
            buses['CTRL'].read(8)!=session.local_epoch):
        raise RuntimeError('Actual hardware is not idle and empty; no journal switch')
    return status


def _consumers(session):
    return [session,session.peer,session.control_transport,session.gate,
            session.coordinator,session.coordinator.parts]


def verify_sealed_segments(session):
    try:
        for journal,proof in getattr(session,'_sealed_application_segments',[]):
            journal.verify()
            if (journal.index!=proof['previous_records'] or journal.digest!=proof['previous_chain'] or
                    journal._content_hash.hexdigest()!=proof['previous_sha256']):
                raise ValueError('Sealed application segment state differs from linked proof')
        session.journal.verify()
        return len(getattr(session,'_sealed_application_segments',[]))
    except Exception as exc:
        session._stop(exc)
        raise


def rotate_idle_journal(session,*,buses,next_record_id):
    unsigned(next_record_id,32,'next record ID',1)
    if getattr(session,'_journal_rotation_active',False):
        raise RuntimeError('Concurrent journal rotation denied')
    expected={'H1':session.transport.mmio,'CTRL':session.runtime.bus,
              'MAIN':session.archive.main,'AUX':session.archive.aux,
              'MAP':session.mapping.bus,'CH0':session.ch0.bus,'SYS':session.gate.bus}
    if any(buses.get(name) is not bus for name,bus in expected.items()):
        raise ValueError('MMIO buses differ from the existing session drivers')
    before=_idle(session,buses)
    stamp=(session.upload.seq,next_record_id)
    if getattr(session,'_last_journal_rotation',None)==stamp:
        raise RuntimeError('This idle boundary was already segmented')
    old=session.journal;consumers=_consumers(session)
    if not isinstance(old,ApplicationJournal) or any(obj.journal is not old for obj in consumers):
        raise ValueError('Live application journal consumers differ')
    root=Path(session.root).resolve()
    for journal in [old,*[j for j,p in getattr(session,'_sealed_application_segments',[])]]:
        resolved=journal.path.resolve()
        if root not in resolved.parents:raise ValueError('Journal outside this session')
    verify_sealed_segments(session)
    session._journal_rotation_active=True
    new=None
    try:
        directory=root/'application_segments'/('before_record_%08x_%s'%(next_record_id,uuid.uuid4().hex))
        new=ApplicationJournal(directory,session.local_epoch)
        from ch1_evidence_store import _sync_directory
        _sync_directory(directory.parent);_sync_directory(root)
        old.record('application_segment_sealed',next_path=str(new.path.relative_to(root)),
                   next_record_id=next_record_id,h1_seq=session.upload.seq,
                   next_control_txn=session.peer.txn)
        old.verify()
        proof={'previous_path':str(old.path.relative_to(root)),
               'previous_sha256':old._content_hash.hexdigest(),
               'previous_records':old.index,'previous_chain':old.digest,
               'next_record_id':next_record_id,'h1_seq':session.upload.seq,
               'next_control_txn':session.peer.txn}
        new.record('application_segment_link',**proof)
        new.verify();verify_sealed_segments(session)
        if _idle(session,buses)!=before:raise RuntimeError('Idle hardware changed while sealing journals')
        # No exchange is active. The C worker buffers RX but never writes journals.
        for obj in consumers:obj.journal=new
        session.control_transport._saved_capture=None
        session.handles.append(new)
        sealed=list(getattr(session,'_sealed_application_segments',[]))
        sealed.append((old,proof));session._sealed_application_segments=sealed
        old.close() # old owner.verify still works; further appends fail closed.
        session._last_journal_rotation=stamp
        new.record('application_segment_activated',next_record_id=next_record_id,
                   sealed_segments=len(sealed))
        new.verify()
        return {'next_record_id':next_record_id,'sealed_segments':len(sealed),
                'sealed_path':str(old.path),'active_path':str(new.path),
                'sealed_bytes':old.path.stat().st_size,'active_bytes':new.path.stat().st_size,
                'hardware_writes':0,'START_sent':False}
    except Exception as exc:
        if new is not None and session.journal is not new:new.close()
        session._stop(exc)
        raise
    finally:session._journal_rotation_active=False
