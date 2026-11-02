"""VerifiedFeedbackReceipt is not the translated MeasuredRecord schema."""
from common import require
REQUIRED={'record_id','kind','identity_hex','result_sha256','actual_receiver_B','labels','evidence_quality','strict_retirement_verified','actual_READY_saved'}
def validate_feedback(receipt,rid):
    require(type(receipt) is dict,'FEEDBACK_RECEIPT_OBJECT')
    require(REQUIRED<=set(receipt),'FEEDBACK_RECEIPT_SCHEMA_MISMATCH missing='+','.join(sorted(REQUIRED-set(receipt))))
    require(type(receipt['record_id']) is int and receipt['record_id']==rid,'FEEDBACK_RECEIPT_RECORD_ID')
    require(receipt['kind']==('CONFIG' if rid==1 else 'ITEM'),'FEEDBACK_RECEIPT_KIND')
    require(receipt['evidence_quality']=='VALID' and receipt['strict_retirement_verified'] is True and receipt['actual_READY_saved'] is True,'FEEDBACK_RECEIPT_NOT_STRICTLY_COMPLETED')
    require(type(receipt['result_sha256']) is str and len(receipt['result_sha256'])==64 and type(receipt['identity_hex']) is str and receipt['identity_hex'],'FEEDBACK_RECEIPT_ORIGINAL_REFERENCE')
    return receipt
def verify_owner_receipt(owner,rid):
    require(owner.executor.index==rid and len(owner.receipts)==rid,'OWNER_RECEIPT_PREFIX')
    receipt=validate_feedback(owner.receipts[-1],rid)
    # Independently recheck the original CH0/CH1, READY, retirement and MPG1 evidence.
    require(owner.feedback._feedback(rid)==receipt,'OWNER_RECEIPT_DIFFERS_FROM_VERIFIED_ORIGINALS')
    return receipt
