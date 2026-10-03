"""Data-only private roundtrip readiness. No clients, credentials or renderer."""
import hashlib
import json
from generation_contract import canonical, checkpoint_inputs, request_fixture
from offline_readiness import FLAGS

MODEL='gemini-3.8-flash'

def request(intent, job_id):
    return request_fixture(intent,job_id,dict.fromkeys(FLAGS,True),model=MODEL)

def ai_preconditions(evidence):
    required=('project_identified','billing_unlinked','free_tier','model_access','quota_remaining',
              'credential_gemini_only','durable_backend_verified','checkpoint_write_verified','owner_ai_approved')
    missing=[k for k in required if evidence.get(k) is not True]
    return {'status':'BLOCKED' if missing else 'PRECONDITIONS_COMPLETE_ONLY',
            'missing':missing,'live_ready':False,'posting_permitted':False,'allow':False,
            'ai_sends_max':1,'retry':0,'resend':0,'fallback':0}

def render_inputs(record, durable_readback):
    # Backend must commit and return immutable script; local journal alone cannot unlock render.
    script=record.script_checkpoint_json
    if not script or durable_readback.get('state')!='COMPLETED' or durable_readback.get('job_id')!=record.job_id:
        raise ValueError('durable_checkpoint_required')
    digest=hashlib.sha256(script.encode()).hexdigest()
    if durable_readback.get('script_json')!=script or durable_readback.get('script_sha256')!=digest:
        raise ValueError('durable_checkpoint_hash_mismatch')
    inputs=checkpoint_inputs(record)['pipeline_inputs']
    inputs.update(privacy_status='private',notify_subscribers=False,scheduled_for='')
    return {'inputs':inputs,'checkpoint_sha256':digest,'allow':False,'live_ready':False,'posting_permitted':False}

def generation_recovery(state, checkpoint_present):
    if checkpoint_present:return 'READ_SAVED_CHECKPOINT_NO_REGENERATION'
    if state in ('SENT','STARTED','UNKNOWN','TIMEOUT','AMBIGUOUS'):return 'STOP_MANUAL_RECONCILIATION_NO_RESEND'
    return 'BLOCKED_PENDING_APPROVAL'
