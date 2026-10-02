"""Offline migration reference. No clients, credentials, dispatch, render or posting.

Fixture script input is NOT AI generation. Readiness never grants permission to
publish. ClaimStore remains in PR15; this module never mutates or transfers it.
"""
import hashlib
import json
import math
import re

FLAGS = ('TEST_ONLY', 'DRY_RUN', 'NO_PUBLISH', 'EMERGENCY_STOP')
IDENTIFIER = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z')
SENSITIVE = re.compile(r'(?i)(bearer\s|access[_ -]?token|refresh[_ -]?token|client[_ -]?secret|authorization|api[_ -]?key|password|upload[_ -]?url)')


def _text(value, limit):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError('invalid_text')
    if SENSITIVE.search(value) or any(ord(c) < 32 and c not in '\n\t' for c in value):
        raise ValueError('unsafe_text')
    return value


def _identifier(value):
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value) or '..' in value or SENSITIVE.search(value):
        raise ValueError('invalid_identifier')
    return value


def _number(value, minimum, maximum):
    if type(value) not in (int, float) or not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError('invalid_number')
    return value


def _keys(value, required):
    if not isinstance(value, dict) or set(value) != set(required):
        raise ValueError('unexpected_fields')


def script_to_render(theme, script, account_id, job_id, flags):
    """Validate a dummy V2 script and map to audited renderer input fields.

    Length/duration bounds here are conservative offline project bounds, not
    SNS API policy limits. Real narration/audio timing remains unverified.
    """
    _keys(flags, FLAGS)
    if any(flags[k] is not True for k in FLAGS):
        raise ValueError('unsafe_flags')
    _identifier(account_id)
    _identifier(job_id)
    if not account_id.startswith('youtube-'):
        raise ValueError('platform_mismatch')
    _text(theme, 240)
    _keys(script, ('title', 'hook', 'narration', 'scenes', 'bgm'))
    for k, limit in (('title', 100), ('hook', 240), ('narration', 4000)):
        _text(script[k], limit)
    scenes = script['scenes']
    if not isinstance(scenes, list) or not 1 <= len(scenes) <= 60:
        raise ValueError('invalid_scenes')
    previous = 0
    captions = []
    for scene in scenes:
        _keys(scene, ('start', 'end', 'caption', 'visual_keyword', 'motion', 'sfx', 'emphasis_words'))
        start, end = _number(scene['start'], 0, 60), _number(scene['end'], 0, 60)
        if start < previous or end <= start:
            raise ValueError('invalid_timeline')
        previous = end
        _text(scene['caption'], 240)
        _text(scene['visual_keyword'], 240)
        if scene['motion'] not in ('zoom_in', 'zoom_out', 'pan_left', 'pan_right', 'none'):
            raise ValueError('invalid_motion')
        if scene['sfx'] not in ('pop', 'none'):
            raise ValueError('invalid_sfx')
        if not isinstance(scene['emphasis_words'], list) or len(scene['emphasis_words']) > 10:
            raise ValueError('invalid_emphasis')
        for word in scene['emphasis_words']:
            _text(word, 40)
        captions.append({'start': start, 'end': end, 'text': scene['caption']})
    _keys(script['bgm'], ('mood', 'volume'))
    _text(script['bgm']['mood'], 40)
    _number(script['bgm']['volume'], 0, 1)
    payload = {**script, 'captions': captions, 'speaker': 1,
               'output': {'format': 'mp4', 'width': 1080, 'height': 1920, 'fps': 30}}
    # Copy defensively so mutation by a future caller cannot change this record.
    payload = json.loads(json.dumps(payload, ensure_ascii=False, allow_nan=False))
    content = {'platform': 'youtube', 'account_id': account_id, 'theme': theme, 'payload': payload}
    fingerprint = hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False,
                                            separators=(',', ':')).encode()).hexdigest()
    return {'job_id': job_id, 'account_id': account_id, 'platform': 'youtube',
            'content_fingerprint': fingerprint, 'render_payload': payload,
            'posting_permitted': False, 'mode': 'offline_fixture'}


def storage_envelope(accounts, posts_per_day, video_bytes, retention_days,
                     existing_bytes=0, verified_allowance_bytes=None):
    """Steady-state estimate; not a billing prediction or deletion procedure.

    Allowance must be verified for the owner's plan/shared pool. Free runner
    time is never interpreted as unlimited free artifact storage.
    """
    for value in (accounts, posts_per_day, video_bytes, retention_days):
        if type(value) is not int or value < 1:
            raise ValueError('invalid_budget')
    if type(existing_bytes) is not int or existing_bytes < 0:
        raise ValueError('invalid_budget')
    if verified_allowance_bytes is not None and (type(verified_allowance_bytes) is not int or verified_allowance_bytes < 1):
        raise ValueError('invalid_allowance')
    required = existing_bytes + accounts * posts_per_day * video_bytes * retention_days
    status = 'UNVERIFIED' if verified_allowance_bytes is None else (
        'WITHIN_ASSUMPTIONS' if required <= verified_allowance_bytes else 'BLOCKED')
    return {'required_bytes': required, 'status': status, 'posting_permitted': False}


def recovery_hint(state, publish_id_present, owner_verified):
    """Offline review hint only. No takeover and no initialize authorization.

    owner_verified is a fixture input, not proof/fencing implementation. A real
    store must verify owner/version atomically. Time elapsed is not accepted.
    """
    states = {'unclaimed', 'claimed', 'initializing', 'initialized', 'transferring',
              'processing', 'succeeded', 'failed', 'unknown', 'reconciliation_required'}
    if not isinstance(state, str) or state not in states or type(publish_id_present) is not bool or type(owner_verified) is not bool:
        raise ValueError('invalid_state')
    if not owner_verified:
        action = 'blocked_owner'
    elif state in ('unknown', 'reconciliation_required', 'initializing'):
        action = 'manual_reconciliation'
    elif state in ('succeeded', 'failed'):
        action = 'terminal_noop'
    elif publish_id_present:
        action = 'status_reconciliation_only'
    elif state in ('initialized', 'transferring', 'processing'):
        action = 'manual_reconciliation'
    else:
        action = 'offline_preflight_only'
    return {'action': action, 'initialize_permitted': False, 'takeover_permitted': False,
            'posting_permitted': False}
