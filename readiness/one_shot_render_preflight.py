"""Candidate-only preflight. Never imports renderer or starts any subprocess.

Unresolved runtime digest is a mandatory STOP, even if flags are accidentally
changed. No inference or render executor is present in this preparation.
"""
import ast
import hashlib
import json
from pathlib import Path
from manual_fixture_boundary import normalize_manual,canonical,digest,validate_render_payload

ROOT=Path(__file__).resolve().parents[1]
SCRIPT_SHA='9077ccd4b61ff3bcdadcccaaea90219377acfd4abf19ebd414af36f7eb7c0b8b'
NORMALIZED_SHA='dbcc62dfe12ef550bb37987839c6cd3e30743ca9bc307d6f8131d42e7e0f555e'
PAYLOAD_SHA='2b92b1b2266da9be38e0cebdd061add724734049f08afc0bbffbe06b7aa53c40'
RENDER_ID='manual-fixture-render-20261004-001'


def load(path):return json.loads((ROOT/path).read_text())

def validate_offline():
    for path,sha in load('readiness/one-shot-render-sha256.json').items():
        if hashlib.sha256((ROOT/path).read_bytes()).hexdigest()!=sha:raise ValueError('preparation_raw_sha_drift')
    p=load('readiness/one-shot-render-plan.json');source=load('readiness/one-shot-render-sources.json')
    if p['render_identity']!=RENDER_ID or p['production_sha']!=source['production_sha']:raise ValueError('identity_or_source_drift')
    result=normalize_manual((ROOT/'readiness/manual_fixture/manual-japanese-script-fixture-v1.json').read_bytes())
    if result['script_sha256']!=SCRIPT_SHA or digest(result)!=NORMALIZED_SHA:raise ValueError('fixture_sha_drift')
    payload=load('readiness/manual_fixture/render-payload.canonical.json');validate_render_payload(payload)
    if digest(payload)!=PAYLOAD_SHA:raise ValueError('payload_sha_drift')
    for path,sha in p['renderer_files'].items():
        text=source['sources'][path]
        if hashlib.sha256(text.encode()).hexdigest()!=sha:raise ValueError('production_file_sha_drift')
        if path.endswith('.py'):compile(text,path,'exec') # compile only, never execute/import
    if p['checkout_destination']!='.preparation/production-render':raise ValueError('checkout_path_drift')
    env=load('readiness/one-shot-render-env.json')
    if env['RENDER_ID']!=RENDER_ID or env['INPUT_NARRATION']!=payload['narration'] or env['INPUT_SPEAKER']!='1':raise ValueError('env_drift')
    for key,field in [('SCENES_JSON','scenes'),('CAPTIONS_JSON','captions'),('BGM_JSON','bgm'),('OUTPUT_JSON','output')]:
        if json.loads(env['INPUT_'+key])!=payload[field]:raise ValueError('env_json_drift')
    if set(env)!={'RENDER_ID','INPUT_TITLE','INPUT_HOOK','INPUT_NARRATION','INPUT_SPEAKER','INPUT_SCENES_JSON','INPUT_CAPTIONS_JSON','INPUT_BGM_JSON','INPUT_OUTPUT_JSON'}:raise ValueError('env_unknown_or_secret')
    return {'offline_validation':'PASS','render_execution':0,'blockers':p['blockers']}

def require_runtime_ready(plan):
    runtime=plan['runtime']
    import re
    if runtime['voicevox_image_digest_verified'] is not True or not isinstance(runtime['voicevox_image_digest'],str) or not re.fullmatch('sha256:[0-9a-f]{64}',runtime['voicevox_image_digest']):
        raise ValueError('BLOCKED_RENDER_RUNTIME_UNPINNED')
    if plan['blockers']:raise ValueError('BLOCKED_RENDER_PREPARATION')
    # Candidate is not an execution entry point, even with spoofed plan fields.
    raise ValueError('EXECUTOR_ABSENT_AND_NOT_APPROVED')

if __name__=='__main__':
    validate_offline()
    try:require_runtime_ready(load('readiness/one-shot-render-plan.json'))
    except ValueError as error:
        print(str(error));raise SystemExit(1)
