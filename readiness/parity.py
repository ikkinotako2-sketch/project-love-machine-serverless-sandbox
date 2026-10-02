"""Pinned one-account offline parity. No IO clients or execution permission.

The producer and consumer intentionally have different validation semantics.
Pipeline input dictionaries are comparison data only, never sent anywhere.
"""
import copy
import json
import re
from pathlib import Path
from offline_readiness import FLAGS, _identifier, script_to_render

CATEGORIES = ('hook', 'duration', 'caption_density', 'scene_changes', 'narration', 'cta', 'topic_selection')
_JS_WHITESPACE = '\u0009\u000a\u000b\u000c\u000d\u0020\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000\ufeff'


def validate_improvement(output):
    """Exact production validate_ai port (Python code-point lengths)."""
    if not isinstance(output, dict) or not isinstance(output.get('analysis'), str):
        return None
    actions = output.get('improvement_actions')
    if not isinstance(actions, dict) or set(actions) != set(CATEGORIES):
        return None
    if any(not isinstance(actions[k], str) or not 1 <= len(actions[k]) <= 180 for k in CATEGORIES):
        return None
    if len(output['analysis']) > 250:
        return None
    return {'method': 'gemini', 'analysis': output['analysis'], 'improvement_actions': copy.deepcopy(actions)}


def improvement_guidance(response):
    """V2 JSON response consumer, including JS UTF-16 length and trim rules.

    Invalid/unavailable feedback is empty guidance, not a script failure.
    Non-JSON values and the live HTTP node's coercions remain out of scope.
    """
    try:
        if not isinstance(response, dict):
            return ''
        code = response.get('statusCode')
        if code and (type(code) not in (int, float) or code != 200):
            return ''
        body = response.get('body')
        payload = body.get('data') if isinstance(body, dict) else None
        if payload is None:
            payload = body if body is not None else response.get('data')
        feedback = json.loads(payload) if isinstance(payload, str) else payload
        if not isinstance(feedback, dict) or feedback.get('status') != 'ready':
            return ''
        actions = feedback.get('improvement_actions')
        if not isinstance(actions, dict):
            return ''
        if any(not isinstance(actions.get(k), str) or not actions[k].strip(_JS_WHITESPACE)
               or len(actions[k].encode('utf-16-le', errors='surrogatepass')) // 2 > 240
               or re.search(r'[\r\n\x00-\x1f]', actions[k]) for k in CATEGORIES):
            return ''
        return '\n'.join(k + ': ' + actions[k].strip(_JS_WHITESPACE) for k in CATEGORIES)
    except (ValueError, TypeError):
        return ''


def normalize_script(response):
    """V2 post-parser Set node for valid schema-shaped JSON fixtures."""
    script = response['output']
    out = {k: copy.deepcopy(script[k]) for k in ('title', 'hook', 'narration', 'scenes', 'bgm')}
    out['captions'] = [{'index': i + 1, 'start_seconds': s['start'],
                        'end_seconds': s['end'], 'text': s['caption']}
                       for i, s in enumerate(script['scenes'])]
    return out


def render_payload(normalized):
    return {**copy.deepcopy(normalized), 'speaker': 1,
            'output': {'format': 'mp4', 'width': 1080, 'height': 1920, 'fps': 30}}


def _json(value):
    # These fixture numbers are integers. Arbitrary floating-point JS stringify
    # byte equivalence is not claimed. No NaN/Infinity accepted.
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def pipeline_inputs(payload, job_id):
    """Exact V2 dispatch input fields/defaults, as offline comparison data.

    Legacy false audience/AI declarations are NOT a factual determination.
    OAuth secret NAME is an identifier; no secret is read or registered.
    """
    _identifier(job_id)
    out = {'job_id': job_id, 'account_id': 'youtube_game_001',
           'oauth_secret_name': 'PLM_YOUTUBE_GAME_001',
           'title': payload.get('title') or '', 'hook': payload.get('hook') or '',
           'narration': payload.get('narration') or '', 'speaker': str(payload.get('speaker', 1)),
           'scenes_json': _json(payload.get('scenes', [])),
           'captions_json': _json(payload.get('captions', [])),
           'bgm_json': _json(payload.get('bgm', {})),
           'output_json': _json(payload.get('output', {'format': 'mp4', 'width': 1080, 'height': 1920, 'fps': 30})),
           'description': payload.get('description') or '', 'tags': 'game,shorts',
           'privacy_status': 'private', 'scheduled_for': '',
           'made_for_kids': False, 'contains_synthetic_media': False, 'notify_subscribers': False}
    validate_pipeline_inputs(out)
    return out


def validate_pipeline_inputs(inputs):
    schema = json.loads(Path(__file__).with_name('parity_sources.json').read_text())['pipeline_inputs']
    if not isinstance(inputs, dict) or set(inputs) != set(schema):
        raise ValueError('pipeline_fields')
    for key, rule in schema.items():
        value = inputs[key]
        expected = rule['type']
        if expected == 'boolean':
            if type(value) is not bool:
                raise ValueError('pipeline_boolean')
        elif not isinstance(value, str):
            raise ValueError('pipeline_string')
        if expected == 'choice' and value not in rule['options']:
            raise ValueError('pipeline_choice')
    if len(_json(inputs).encode('utf-16-le')) // 2 > 65535:
        raise ValueError('pipeline_payload_size')
    return True


def offline_e2e(theme, response, job_id, flags, entry_kind='manual', feedback=None):
    if entry_kind not in ('manual', 'schedule'):
        raise ValueError('invalid_entry')
    # Validate flags and conservative project bounds before parity transforms.
    checked = script_to_render(theme, response['output'], 'youtube_game_001', job_id, flags)
    payload = render_payload(normalize_script(response))
    assert payload == checked['render_payload']
    return {'mode': 'offline_fixture', 'entry_kind': entry_kind,
            'safety': {k: flags[k] for k in FLAGS}, 'posting_permitted': False,
            'job_id': job_id, 'content_fingerprint': checked['content_fingerprint'],
            'improvement_guidance': improvement_guidance(feedback),
            'render_payload': payload, 'pipeline_inputs': pipeline_inputs(payload, job_id)}
