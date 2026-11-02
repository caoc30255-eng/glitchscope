"""Proposed mainline integration adapter; default UI has no transport installed.

The transport is owned by the mainline executor and authenticates its own budget
receipt. This client does not create authorizations or touch any device.
"""
import copy
from labutil import *
from scans import validate,propose

class MainlineScanAdapter:
    def __init__(self,transport):self.transport=transport
    def capabilities(self):
        c=self.transport('capabilities',{})
        require(c['contract']=='BOUNDED_SCAN_SERVICE_PROPOSED_V0_1','NEW_SCAN_CONTRACT_REQUIRED')
        require(c['owns_exclusive_hardware_lock'] and c['UNKNOWN_blocks'] and c['strict_retirement_required'],'MAINLINE_SAFETY_CAPABILITIES')
        return c
    def submit(self,plan,approval_receipt,idempotency_key):
        validate(plan);self.capabilities()
        require(approval_receipt['plan_sha256']==plan['plan_sha256'] and approval_receipt['authorized_starts']<=plan['explicit_limit'],'APPROVAL_SCOPE')
        require(approval_receipt['authorized_starts']>=plan['required_starts'],'APPROVAL_BELOW_PLAN')
        require(len(idempotency_key)>=8,'IDEMPOTENCY_KEY')
        # Receipt authenticity and atomic namespace reservation are checked by the server.
        result=self.transport('submit_plan',dict(plan=copy.deepcopy(plan),approval_receipt=copy.deepcopy(approval_receipt),idempotency_key=idempotency_key))
        require(result['plan_sha256']==plan['plan_sha256'] and result['budget_receipt_verified'] and result['namespace_reserved'],'SERVER_ADMISSION_NOT_VERIFIED')
        return result
    def next_proposal(self,plan,run_id):
        status=self.transport('status',dict(run_id=run_id));require(status['plan_sha256']==plan['plan_sha256'],'RUN_PLAN')
        # Reads authoritative executor history; caller cannot inject feedback labels here.
        return propose(plan,status['verified_history'])
    def stop(self,run_id,idempotency_key):
        response=self.transport('stop_unstarted',dict(run_id=run_id,idempotency_key=idempotency_key))
        require(response['refund_or_quota_added'] is False and response['inflight_owner']=='MAINLINE_EXECUTOR','STOP_SEMANTICS')
        return response
