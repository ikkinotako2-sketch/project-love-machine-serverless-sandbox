"""Versioned canonical HMAC boundary using ONLY PUBLIC fixture keys.

NOT real authentication. No real key injection, env lookup, secret or transport.
"""
import hashlib
import hmac
import re
from generation_contract import canonical, strict_json
from offline_readiness import _identifier

PUBLIC_KEYS={'fixture-current':b'PUBLIC-PLM-CALLBACK-CURRENT-NOT-A-SECRET','fixture-previous':b'PUBLIC-PLM-CALLBACK-PREVIOUS-NOT-A-SECRET'}
FIELDS={'protocol','key_id','platform','account_id','intent_id','job_id','owner','owner_epoch','version','issued_at','delivery_id','result_id','outcome'}


def validate_body(body):
    if not isinstance(body,dict) or set(body)!=FIELDS or body['protocol']!='plm-callback-v1' or not isinstance(body['key_id'],str) or body['key_id'] not in PUBLIC_KEYS:raise ValueError('invalid_callback_contract')
    if body['platform']!='youtube' or body['account_id']!='youtube_game_001' or body['outcome'] not in ('succeeded','failed'):raise ValueError('invalid_callback_scope')
    for k in ('account_id','intent_id','job_id','owner','delivery_id','result_id'):_identifier(body[k])
    for k in ('owner_epoch','version'):
        if type(body[k]) is not int or body[k]<1:raise ValueError('invalid_callback_fence')
    if type(body['issued_at']) is not int or not 0<=body['issued_at']<=4102444800:raise ValueError('invalid_issued_at')
    return body


def sign_fixture(body):
    validate_body(body);text=canonical(body)
    return {'mode':'PUBLIC_FIXTURE_NOT_AUTH','body':text,'signature':hmac.new(PUBLIC_KEYS[body['key_id']],('plm-callback-v1\n'+text).encode(),hashlib.sha256).hexdigest()}


def verify_fixture(envelope,now,previous_valid_until=None):
    if not isinstance(envelope,dict) or set(envelope)!={'mode','body','signature'} or envelope['mode']!='PUBLIC_FIXTURE_NOT_AUTH':raise ValueError('public_mock_only')
    if type(now) is not int or not 0<=now<=4102444800:raise ValueError('invalid_virtual_time')
    if previous_valid_until is not None and (type(previous_valid_until) is not int or previous_valid_until<0):raise ValueError('invalid_overlap')
    text=envelope['body'];body=validate_body(strict_json(text,8192))
    if canonical(body)!=text:raise ValueError('noncanonical_body')
    signature=envelope['signature']
    if not isinstance(signature,str) or not re.fullmatch(r'[a-f0-9]{64}',signature):raise ValueError('invalid_signature_format')
    expected=hmac.new(PUBLIC_KEYS[body['key_id']],('plm-callback-v1\n'+text).encode(),hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected,signature):raise ValueError('invalid_fixture_signature')
    if now-body['issued_at']>300 or body['issued_at']-now>30:raise ValueError('stale_or_future_signature')
    if body['key_id']=='fixture-previous' and (previous_valid_until is None or now>previous_valid_until):raise ValueError('previous_key_expired')
    return body


def accept_fixture(client,envelope,now,completed_at,previous_valid_until=None):
    # Signature verification BEFORE any ledger mutation; duplicate result
    # transaction belongs to the store, not a separate nonce pre-write.
    body=verify_fixture(envelope,now,previous_valid_until)
    return client.complete_delivery(body,completed_at)
