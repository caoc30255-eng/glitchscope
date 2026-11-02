"""Explicit Linux/PYNQ assembly. Import does not import PYNQ or native services.

No Overlay loading, clock setting, reset, resume or retry operations exist here.
Caller must arrange a reviewed fresh image in a separately approved stage.
"""
import json
import os
import platform
import struct
import sys
from pathlib import Path
from custom_authorization import sha, read_approval, ExecutionContext, code_inventory
from custom_plan import require, validate_plan

BIT_SHA='0c0b686e80e37e49e64ab07b719a0c1ea3387451f3ceebdba5dcf38b8c68b61c'
HWH_SHA='8d65319fd06ccafb9acdabe1c19868106cd1945f085b2fa03d55b89d238bd2bc'


def environment():
    return dict(os=platform.platform(),machine=platform.machine(),bits=struct.calcsize('P')*8,
                python=sys.version,executable=sys.executable,prefix=sys.prefix,
                uid=os.getuid() if hasattr(os,'getuid') else None,
                affinity=sorted(os.sched_getaffinity(0)) if hasattr(os,'sched_getaffinity') else None,
                hardware_access=False,STARTs=0)


def check_assets(assets):
    require(set(assets)=={'bit','hwh','native'},'EXACT_BIT_HWH_NATIVE_ASSETS')
    require(sha(assets['bit'])==BIT_SHA and sha(assets['hwh'])==HWH_SHA,'REVIEWED_IMAGE_HASH_REQUIRED')
    native=Path(assets['native']).read_bytes()
    require(native[:5]==b'\x7fELF\x01' and int.from_bytes(native[18:20],'little')==40,
            'ARM32_ELF_NATIVE_REQUIRED')
    return {k:dict(path=str(Path(v).resolve()),bytes=Path(v).stat().st_size,sha256=sha(v)) for k,v in assets.items()}


def approval_template(plan,assets,runs):
    validate_plan(plan)
    from active14_bootstrap import bind
    root=bind()
    return dict(schema='SCAN_EXPLICIT_APPROVAL_V0_2',approved_by_user=False,reviewed_by_owner=False,
                approval_reference='',plan_sha256=plan['sha256'],max_records=plan['max_records'],
                runs_directory=str(Path(runs).resolve()),asset_sha256={k:sha(v) for k,v in assets.items()},
                code_sha256=code_inventory(root),
                stages=dict(local_read_preflight=False,initialize_namespace_and_receiver=False,physical_records=False),
                automatic_retry=False,automatic_reset=False,
                note='Template only. Human review and explicit user approval must precede changing fields. No authorization in this delivery.')


def local_preflight(plan,assets,runs,approval):
    """Approved local CSR reads only; no remote UART, reset, Overlay, trial or worker."""
    check_assets(assets);read_approval(approval,plan,assets,runs,'local_read_preflight')
    require(platform.system()=='Linux' and platform.machine()=='armv7l' and struct.calcsize('P')==4,
            'PYNQ_ARMV7L_32_REQUIRED')
    import fcntl
    runs=Path(runs).resolve();require(runs.is_dir(),'EXISTING_RUNS_REQUIRED')
    lock=(runs/'exclusive.lock').open('a+')
    try:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        from pynq import MMIO
        from reviewed_probe import probe
        result=probe(MMIO,assets['hwh'])
        expected=dict(H1=1,CTRL=0,MAIN=0,AUX=0,MAP=0,CH0=8,PROFILE=4,SYS=0)
        require(result['all_IDs_match'] and all(int(b['status'],16)==expected[b['bank']] for b in result['banks']),
                'FRESH_BANK_STATUS_REQUIRED_NO_RESET')
        require(all(result[k]==0 for k in ('local_epoch','retire_count','grant_count','capacity_permission')),
                'USED_EPOCH_NO_RESET')
        result.update(environment=environment(),assets=check_assets(assets),
                      board_identity_verified=False,process_inventory=process_inventory(),
                      note='CSR identities and image files do not attest physical board identity. No peer probe before initialization.')
        return result
    finally:lock.close()


def process_inventory():
    rows=[]
    for p in Path('/proc').glob('[0-9]*/comm'):
        try:rows.append(dict(pid=int(p.parent.name),name=p.read_text().strip()))
        except (OSError,ValueError):pass
    return rows


class RealHarness:
    """Explicit initialization (writes/HELLO) followed by individually requested steps."""
    def __init__(self,plan,assets,runs,approval):
        validate_plan(plan);self.owner=None;self.session=None;self.control=None;self.lock=None
        self.assets=assets;self.runs=Path(runs).resolve();self.approval=Path(approval).resolve()
        # All three stages must be approved before namespace allocation or native loading.
        for stage in ('local_read_preflight','initialize_namespace_and_receiver','physical_records'):
            read_approval(approval,plan,assets,runs,stage)
        preflight=local_preflight(plan,assets,runs,approval)
        import fcntl
        self.lock=(self.runs/'exclusive.lock').open('a+')
        try:
            fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            # Recheck CSR state while holding the lifetime lock (no unlocked stale preflight).
            from pynq import MMIO, Clocks
            from reviewed_probe import probe
            require(abs(float(Clocks.fclk0_mhz)-150)<0.1,'FCLK_CONFIGURATION_REQUIRES_SEPARATE_APPROVED_SETUP')
            current=probe(MMIO,assets['hwh'])
            require(current=={k:v for k,v in preflight.items() if k not in ('environment','assets','board_identity_verified','process_inventory','note')},'LOCAL_STATE_CHANGED')
            registry=self.runs/'namespace_allocations.jsonl'
            require(registry.is_file(),'EXISTING_NAMESPACE_REGISTRY_REQUIRED_DO_NOT_CREATE')
            records=[json.loads(line) for line in registry.read_text(encoding='utf-8').splitlines() if line.strip()]
            require(all(type(r.get('number')) is int for r in records) and [r['number'] for r in records]==list(range(1,len(records)+1)),'NAMESPACE_HISTORY_INVALID')
            trials=self.runs/'trial_registry'
            require(trials.is_dir(),'EXISTING_TRIAL_REGISTRY_REQUIRED_DO_NOT_RECREATE')
            trial_files=sorted(trials.glob('trial_*.json'))
            numbers=[]
            for f in trial_files:
                number=int(f.stem.split('_')[1],16)
                trial=json.loads(f.read_bytes()).get('trial_id')
                require(type(trial) is int and trial==number,'TRIAL_REGISTRY_IDENTITY_CHANGED')
                numbers.append(number)
            require(numbers==list(range(1,len(numbers)+1)) and len(numbers)<65535,'TRIAL_HISTORY_MISSING_OR_EXHAUSTED')
            number=len(records)+1;require(number<0x10000000,'EPOCH_EXHAUSTED')
            root=self.runs/('session_%08x'%number);require(not root.exists(),'NEVER_RESUME_EXISTING_SESSION')
            with registry.open('a',encoding='utf-8') as f:
                f.write(json.dumps(dict(number=number))+'\n');f.flush();os.fsync(f.fileno())
            fd=os.open(str(self.runs),os.O_RDONLY)
            try:os.fsync(fd)
            finally:os.close(fd)
            from ps_candidate_session import CandidateSession,BANKS
            buses={k:MMIO(base,size) for k,(base,size,_) in BANKS.items()}
            self.session=CandidateSession(buses,root,local_epoch=0x10000000+number,peer_epoch=0x20000000+number,
                session=0x30000000+number,control_epoch=0x40000000+number,exclusive_owner=True,poll_limit=10000)
            from ch1_peer_archive_driver import persist_exact
            from custom_plan import raw
            persist_exact(root/'REAL_ASSEMBLY',{'preflight.json':raw(preflight),
                'approval.json':self.approval.read_bytes(),
                'initialization.json':raw(dict(writes=True,namespace_allocated=number,Overlay_loaded_by_this_code=False,
                FCLK_set_by_this_code=False,FCLK_readback_mhz=Clocks.fclk0_mhz,logic_declared_hz=100000000,
                generator_nominal_ns=20,CAP_nominal_ns=10,physical_clocks_measured=False))})
            from ch1_uartlite_realtime_transport import RealtimeUARTLiteControlTransport
            self.control=RealtimeUARTLiteControlTransport(MMIO(0x42c00000,0x10000),self.session.journal,
                library=assets['native'],exclusive_owner=True,timeout=2.0,receiver_cpu=1,receiver_priority=10,receiver_idle_ns=50000)
            self.control.start_receiver()
            self.session.initialize(self.control)
            self.session.journal.record('real_RX_setup',scheduling=self.control.scheduling_snapshot(),
                                        pending=self.control.pending_snapshot())
            from fault_pilot_workflow import inspect_raw_mark_interface
            from multipoint_capability_preflight import inspect_multipoint_capability
            inspect_raw_mark_interface(self.session,MMIO,assets['hwh'])
            inspect_multipoint_capability(self.session,buses)
            context=ExecutionContext(approval,plan,assets,runs,self.session,self.lock)
            from custom_owner import CustomOwner
            self.owner=CustomOwner(self.session,buses,self.lock,plan,execution_context=context)
        except BaseException as error:
            if self.session:self.session._stop(error)
            self.close();raise

    def backend(self):
        from custom_backend import Backend
        return Backend(self.owner)

    def close(self):
        errors=[]
        if self.owner and self.owner.state in ('READY','RUNNING','AWAITING_SELECTION'):
            try:self.owner.request_stop()
            except BaseException as error:
                errors.append(repr(error));self.session._stop(error)
                try:self.owner._close()
                except BaseException as close_error:errors.append(repr(close_error))
        if self.session:
            if self.control and self.control.context:
                try:self.session.journal.record('real_RX_before_close',pending=self.control.pending_snapshot())
                except Exception as error:errors.append(repr(error))
            for handle in reversed(self.session.handles):
                try:handle.close()
                except Exception as error:errors.append(repr(error))
            self.session.handles.clear()
        if self.control:
            try:self.control.close()
            except Exception as error:errors.append(repr(error))
        if self.lock and not self.lock.closed:
            try:self.lock.close()
            except Exception as error:errors.append(repr(error))
        if errors and self.session:
            import uuid
            failure=self.session.root/('close_errors_'+uuid.uuid4().hex+'.json')
            with failure.open('x',encoding='utf-8') as f:json.dump(errors,f)
