"""Provider-neutral data-only checkpoint boundary. No SDK, key, or transport.

Legacy Gemini request fixture is never a permitted adapter. Eligibility is a
separate evidence gate, not inferred from syntactically accepted provider IDs.
"""
import copy
import hashlib
import re
from generation_contract import canonical, parse_script, strict_json
from offline_readiness import FLAGS

REQUIRED = ('ongoing_zero_cost','no_paid_contract','no_payment_method',
            'owner_age_and_contract_eligible','headless_server_inference',
            'at_least_6_generations_per_day','japanese_script_capability','safe_json_validation')
BUDGET = {'distinct_generations_per_day':6,'attempts_per_generation':1,
          'automatic_retry':0,'automatic_regeneration':0,'automatic_render':0,
          'automatic_upload':0,'automatic_fallback':0}

def eligibility(evidence):
    if not isinstance(evidence,dict) or evidence.get('current_official_evidence') is not True:
        return False
    return all(evidence.get(k) is True for k in REQUIRED)

def require_eligible(provider,evidence):
    if provider in ('gemini','github_models') or not eligibility(evidence):
        raise ValueError('provider_not_eligible_no_request')
    return True

def checkpoint_fixture(provider,model,request_sha256,raw,theme,job_id,flags,
                       finish='complete',existing=None):
    """OFFLINE fixtures only; this function never grants inference permission."""
    if existing is not None:raise ValueError('immutable_checkpoint_no_regeneration')
    if flags!=dict.fromkeys(FLAGS,True):raise ValueError('unsafe_flags')
    if not isinstance(provider,str) or not re.fullmatch('[a-z][a-z0-9_-]{1,31}',provider):raise ValueError('provider_id')
    if not isinstance(model,str) or not re.fullmatch('[A-Za-z0-9_./-]{1,96}',model):raise ValueError('model_id')
    if not isinstance(request_sha256,str) or not re.fullmatch('[0-9a-f]{64}',request_sha256):raise ValueError('request_sha')
    if finish!='complete':raise ValueError('partial_or_unknown_stop')
    script=parse_script(raw,theme,job_id,flags)
    encoded=canonical(script)
    return {'provider':provider,'model':model,'request_sha256':request_sha256,
            'script_json':encoded,'script_sha256':hashlib.sha256(encoded.encode()).hexdigest(),
            'job_id':job_id,'theme':theme,'live_permitted':False,'posting_permitted':False}

def render_input_fixture(checkpoint,provider,model,request_sha256):
    if (checkpoint['provider'],checkpoint['model'],checkpoint['request_sha256'])!=(provider,model,request_sha256):raise ValueError('identity_drift')
    text=checkpoint['script_json']
    if hashlib.sha256(text.encode()).hexdigest()!=checkpoint['script_sha256']:raise ValueError('checkpoint_sha_drift')
    script=parse_script(text,checkpoint['theme'],checkpoint['job_id'],dict.fromkeys(FLAGS,True))
    if canonical(script)!=text:raise ValueError('noncanonical_checkpoint')
    return {'script':copy.deepcopy(script),'live_permitted':False,'render_executed':False}

def uncertain_result(kind):
    if kind not in ('timeout','ambiguous','http_error','invalid_json','quota','model_drift'):raise ValueError('unknown_classification')
    return {'decision':'STOP_UNKNOWN_MANUAL_RECONCILIATION','retry':0,'regenerate':0,'render':0,'upload':0,'fallback':0}
