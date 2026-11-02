"""Separate external approval binding. Templates in this package authorize zero IO."""
import hashlib
import json
from pathlib import Path
from custom_plan import require, validate_plan


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_approval(path, plan, assets, runs, stage):
    validate_plan(plan)
    if plan['request'].get('edge_ai'):
        from custom_ai_policy import model_for
        model_for(plan['request']['edge_ai'])
    path = Path(path).resolve()
    data = path.read_bytes()
    approval = json.loads(data)
    require(type(approval) is dict, 'APPROVAL_OBJECT')
    if approval.get('schema')=='GLITCHSCOPE_DEMO_PERMIT_V1':
        from demo_authority import read_scan_permit
        return read_scan_permit(path,plan,assets,runs,stage)
    require(approval.get('schema') == 'SCAN_EXPLICIT_APPROVAL_V0_2', 'APPROVAL_SCHEMA')
    require(approval.get('approved_by_user') is True and approval.get('reviewed_by_owner') is True,
            'REVIEW_AND_EXPLICIT_USER_APPROVAL_REQUIRED')
    require(type(approval.get('approval_reference')) is str and len(approval['approval_reference']) >= 8,
            'APPROVAL_REFERENCE_REQUIRED')
    require(approval.get('plan_sha256') == plan['sha256'], 'APPROVAL_PLAN_CHANGED')
    require(approval.get('max_records') == plan['max_records'] and type(approval['max_records']) is int,
            'APPROVAL_EXACT_RECORD_LIMIT')
    require(approval.get('runs_directory') == str(Path(runs).resolve()), 'APPROVAL_RUNS_DIRECTORY')
    require(approval.get('asset_sha256') == {n: sha(p) for n,p in assets.items()}, 'APPROVAL_ASSETS_CHANGED')
    from active14_bootstrap import bind
    root = bind()
    inventory = code_inventory(root)
    require(approval.get('code_sha256') == inventory, 'APPROVAL_CODE_CHANGED')
    require(approval.get('stages', {}).get(stage) is True, 'STAGE_NOT_APPROVED')
    require(approval.get('automatic_retry') is False and approval.get('automatic_reset') is False,
            'NO_RETRY_RESET_APPROVAL')
    return approval, data


class ExecutionContext:
    def __init__(self, path, plan, assets, runs, session, board_lock):
        self.path=Path(path).resolve();self.assets=assets;self.runs=Path(runs).resolve()
        self.approval,self.data=read_approval(path,plan,assets,runs,'physical_records')
        self.session=session;self.board_lock=board_lock;self.epoch=session.local_epoch
        self.verify(plan,session,board_lock)

    def verify(self, plan, session, board_lock):
        require(self.path.read_bytes()==self.data, 'APPROVAL_FILE_CHANGED')
        read_approval(self.path,plan,self.assets,self.runs,'physical_records')
        require(session is self.session and board_lock is self.board_lock and not board_lock.closed,
                'APPROVAL_OWNER_CHANGED')
        require(session.local_epoch==self.epoch and session.root.parent.resolve()==self.runs,
                'APPROVAL_SESSION_CHANGED')
        if self.approval.get('schema')=='GLITCHSCOPE_DEMO_PERMIT_V1':
            from demo_authority import scan_record_authority
            t=scan_record_authority(self.approval,self.runs).task(self.approval['job_id'])
            require(t['session_path']==str(session.root.resolve()),'DEMO_PERMIT_SESSION_CHANGED')

    def verify_record(self,plan,session,board_lock,record_id):
        self.verify(plan,session,board_lock)
        if self.approval.get('schema')=='GLITCHSCOPE_DEMO_PERMIT_V1':
            from demo_authority import scan_record_authority
            scan_record_authority(self.approval,self.runs).require_record(self.approval['job_id'],record_id,session.root)


def code_inventory(root):
    root=Path(root)
    files=list(root.glob('*.py'))+list((root/'runtime').rglob('*.py'))+list((root/'models').glob('*.json'))
    files+=list((root/'oss_runtime').rglob('*.py'))+list((root/'oss_runtime/models').glob('*.json'))
    return {p.relative_to(root).as_posix():sha(p) for p in sorted(files) if '__pycache__' not in p.parts}
