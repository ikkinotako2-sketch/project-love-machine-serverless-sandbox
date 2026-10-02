"""Offline fixture flow only: checkpoint -> input mapping -> reservation.

No AI/render/API/dispatch clients. Mock HMAC uses a PUBLIC fixture key and is
NOT authentication. Real credentials are neither accepted nor read.
"""
import hashlib
import hmac
import json
import re
from intent_ledger import Ledger, Conflict, normalize_intent, recovery
from offline_readiness import FLAGS, _identifier, script_to_render
from parity import normalize_script, render_payload, pipeline_inputs

PUBLIC_FIXTURE_KEY = b'PLM-OFFLINE-PUBLIC-FIXTURE-KEY-NOT-A-CREDENTIAL'
CALLBACK_FIELDS = {'platform','account_id','intent_id','job_id','owner','version',
                   'callback_id','result_id','outcome','issued_at'}


def _canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',', ':'),allow_nan=False)


def _no_duplicates(pairs):
    value = {}
    for key,item in pairs:
        if key in value:
            raise ValueError('duplicate_json_field')
        value[key] = item
    return value


def _strict_json(text, limit=65535):
    if not isinstance(text,str) or len(text) > limit:
        raise ValueError('invalid_json')
    def invalid(_):
        raise ValueError('nonfinite_json')
    try:
        return json.loads(text,object_pairs_hook=_no_duplicates,parse_constant=invalid)
    except (TypeError, ValueError):
        raise ValueError('invalid_json') from None


def parse_generation_fixture(response):
    """Accept parser-shaped output ONLY, never a raw AI HTTP response."""
    if isinstance(response,str):
        response = _strict_json(response)
    if not isinstance(response,dict) or set(response) != {'output'} or not isinstance(response['output'],dict):
        raise ValueError('invalid_generation_response')
    return response['output']


def _callback_body(body):
    if not isinstance(body,dict) or set(body) != CALLBACK_FIELDS:
        raise ValueError('invalid_mock_callback_fields')
    if body['platform'] != 'youtube' or body['account_id'] != 'youtube_game_001' or body['outcome'] not in ('succeeded','failed'):
        raise ValueError('invalid_mock_callback')
    for key in ('account_id','intent_id','job_id','owner','callback_id','result_id'):
        _identifier(body[key])
    if type(body['version']) is not int or body['version'] < 1 or type(body['issued_at']) is not int or body['issued_at'] < 0:
        raise ValueError('invalid_mock_callback_numbers')
    return _canonical(body)


def mock_signed_callback(body):
    """Public deterministic fixture signature; no real key argument allowed."""
    canonical = _callback_body(body)
    return {'mode':'OFFLINE_MOCK_ONLY','body':canonical,
            'signature':hmac.new(PUBLIC_FIXTURE_KEY,canonical.encode(),hashlib.sha256).hexdigest()}


def verify_mock_callback(envelope, now):
    if not isinstance(envelope,dict) or set(envelope) != {'mode','body','signature'} or envelope['mode'] != 'OFFLINE_MOCK_ONLY':
        raise ValueError('mock_only_required')
    if type(now) is not int or now < 0:
        raise ValueError('invalid_mock_clock')
    if not isinstance(envelope['signature'],str) or not re.fullmatch(r'[a-f0-9]{64}',envelope['signature']):
        raise ValueError('invalid_mock_signature')
    body = _strict_json(envelope['body'])
    canonical = _callback_body(body)
    if canonical != envelope['body']:
        raise ValueError('noncanonical_mock_callback')
    expected = hmac.new(PUBLIC_FIXTURE_KEY,canonical.encode(),hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected,envelope['signature']):
        raise ValueError('invalid_mock_signature')
    if now - body['issued_at'] > 300 or body['issued_at'] - now > 30:
        raise ValueError('expired_mock_callback')
    return body


class OfflineCheckpointE2E:
    def __init__(self, flags, ledger=None):
        # Validate each wrapper construction even with an existing ledger.
        verified = Ledger(flags)
        self.flags = {k:flags[k] for k in FLAGS}
        self.ledger = ledger if ledger is not None else verified
        if not isinstance(self.ledger,Ledger):
            raise ValueError('reference_ledger_required')

    def begin(self, entry, owner, mint_job_id):
        intent = normalize_intent(entry)
        if intent.account_id != 'youtube_game_001':
            raise ValueError('one_account_contract_required')
        _identifier(owner)
        record = self.ledger.register(intent,mint_job_id)
        record = self.ledger.claim(intent.key,owner)
        if record.state == 'claimed':
            record = self.ledger.advance(intent.key,owner,record.version,'generating')
        return record # ready/unknown/initializing/terminal replay never auto sends

    def checkpoint(self, key, owner, version, response):
        script = parse_generation_fixture(response)
        record = self.ledger.read(key)
        # Validation-only mapping; no audio/video created.
        script_to_render(record.intent.theme,script,record.intent.account_id,record.job_id,self.flags)
        return self.ledger.save_script_checkpoint(key,owner,version,script)

    def make_ready(self, key, owner, version):
        record = self.ledger.read(key)
        if record.state not in ('generating','ready'):
            raise Conflict('conversion_forbidden')
        if record.script_checkpoint_json is None:
            raise Conflict('checkpoint_required')
        script = _strict_json(record.script_checkpoint_json)
        payload = render_payload(normalize_script({'output':script}))
        inputs = pipeline_inputs(payload,record.job_id)
        if inputs['account_id'] != record.intent.account_id:
            raise Conflict('account_contract_mismatch')
        # CAS saves payload/hash + ready together, AFTER complete input validation.
        record = self.ledger.bind_content(key,owner,version,payload)
        return {'record':record,'render_payload':payload,'pipeline_inputs':inputs,
                'safety':dict(self.flags),'posting_permitted':False}

    def reserve(self, key, owner, version):
        record = self.ledger.read(key)
        if not record.script_checkpoint_json:
            raise Conflict('checkpoint_required')
        return self.ledger.reserve_mock_dispatch(key,owner,version)

    def accept_callback(self, envelope, now):
        body = verify_mock_callback(envelope,now) # verify BEFORE ledger mutation
        key = (body['platform'],body['account_id'],body['intent_id'])
        try:
            record = self.ledger.read(key)
        except KeyError:
            raise ValueError('unknown_callback_intent') from None
        if record.job_id != body['job_id']:
            raise Conflict('callback_job_mismatch')
        return self.ledger.callback(key,body['owner'],body['version'],body['callback_id'],
                                    body['result_id'],body['outcome'])

    def recovery(self, key, owner):
        record = self.ledger.read(key)
        hint = recovery(record,owner)
        if record.state == 'generating' and record.owner == owner:
            hint['action'] = 'convert_saved_checkpoint' if record.script_checkpoint_json else 'reconcile_generation_only'
        return hint

    def snapshot(self):
        # No raw generation response, callback envelope or signature/key persisted.
        return _canonical({'format':'offline_checkpoint_e2e_v1','ledger':json.loads(self.ledger.snapshot())})

    @classmethod
    def restore(cls, snapshot, flags):
        value = _strict_json(snapshot, limit=1048576)
        if not isinstance(value,dict) or set(value) != {'format','ledger'} or value['format'] != 'offline_checkpoint_e2e_v1':
            raise ValueError('invalid_e2e_snapshot')
        ledger = Ledger.restore(_canonical(value['ledger']),flags)
        return cls(flags,ledger)
