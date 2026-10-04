"""Manual generation-result/checkpoint/render boundary; strictly offline.

No provider parser, credential, network, render invocation or remote DB.
The manual checkpoint reference is NOT a remote migration or an inference
provider. The pinned v2 candidate requires provider/model + SENT generation;
manual provenance is consequently not fabricated into its provider column.
"""
import copy
import hashlib
import json
import math
import re
import sqlite3
from pathlib import Path
from generation_contract import strict_json,unicode_safe,canonical
from offline_readiness import FLAGS,script_to_render
from parity import normalize_script,render_payload

IDENTITY='manual-japanese-script-fixture-v1'
ROOT=Path(__file__).resolve().parent
SAFE_FLAGS=dict.fromkeys(FLAGS,True)
MAX_BYTES=65536
SCRIPT_FIELDS={'title','hook','narration','scenes','bgm'}
SCENE_FIELDS={'start','end','caption','visual_keyword','motion','sfx','emphasis_words'}
CONTRACT={
 'version':1,'kind':'NORMALIZED_GENERATION_SCRIPT_FOR_EXISTING_RENDER',
 'input_wrapper':['output'],'script_fields':sorted(SCRIPT_FIELDS),
 'scene_fields':sorted(SCENE_FIELDS),'bgm_fields':['mood','volume'],
 'limits':{'script_bytes':65536,'scenes':24,'title':100,'hook':240,'narration':4000,
           'caption':240,'visual_keyword':120,'emphasis_words':10,'emphasis_word':30,'mood':40,'seconds':60},
 'number_normalization':'finite integral numbers -> integer; negative zero -> 0',
 'unicode_normalization':'none: preserve actual text codepoints',
 'hash':'SHA256 of UTF-8 sorted-key compact JSON, no newline, allow_nan=false',
 'provider_fields_allowed':False,
 'output':{'format':'mp4','width':1080,'height':1920,'fps':30},'speaker':1,
 'network_assets_allowed':False,'live_ready':False,'posting_permitted':False}

def digest(value):return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()

def _normal_numbers(value):
    if type(value) is float:
        if not math.isfinite(value):raise ValueError('nonfinite_number')
        return int(value) if value.is_integer() else value
    if isinstance(value,dict):return {k:_normal_numbers(v) for k,v in value.items()}
    if isinstance(value,list):return [_normal_numbers(v) for v in value]
    return value

def _no_references(value):
    if isinstance(value,str):
        unicode_safe(value)
        # Fixture path is content-only. Reject URI/path-like text everywhere.
        if re.search(r'(?i)([a-z][a-z0-9+.-]*:|www\.|(?:^|\s)[a-z]:[\\/]|/|\\|\.\.|\.(?:mp4|wav|mp3|ogg|png|jpg)(?:\s|$))',value):raise ValueError('external_asset_or_path')
    elif isinstance(value,dict):
        for k,v in value.items():_no_references(k);_no_references(v)
    elif isinstance(value,list):
        for v in value:_no_references(v)

def normalize_manual(raw):
    if isinstance(raw,bytes):
        if len(raw)>MAX_BYTES:raise ValueError('oversized_script')
        try:raw=raw.decode('utf-8',errors='strict')
        except UnicodeDecodeError:raise ValueError('invalid_utf8') from None
    response=strict_json(raw)
    if not isinstance(response,dict) or set(response)!={'output'}:raise ValueError('generation_wrapper_fields')
    script=response['output']
    script_to_render('手動オリジナルfixture',script,'youtube_manual_fixture',IDENTITY,SAFE_FLAGS)
    _no_references(script)
    if len(script['scenes'])>24:raise ValueError('scene_limit_matches_renderer')
    for scene in script['scenes']:
        if len(scene['visual_keyword'])>120:raise ValueError('visual_keyword_limit')
        if any(len(w)>30 or w not in scene['caption'] for w in scene['emphasis_words']):raise ValueError('invalid_caption_emphasis_reference')
    script=_normal_numbers(script)
    encoded=canonical(script)
    if len(encoded.encode('utf-8'))>MAX_BYTES:raise ValueError('oversized_script')
    request={'source':'manual_fixture','fixture_identity':IDENTITY,'input_contract_sha256':digest(CONTRACT),'normalized_output_sha256':digest({'output':script})}
    return {'source':'manual_fixture','fixture_identity':IDENTITY,'request_sha256':digest(request),
            'provider_identity':None,'model_identity':None,
            'script':copy.deepcopy(script),'script_json':encoded,'script_sha256':digest(script),
            'input_contract_sha256':digest(CONTRACT),'normalized_output_sha256':digest({'output':script})}

CHECKPOINT_SQL='''
CREATE TABLE offline_manual_checkpoint (
 job_id TEXT PRIMARY KEY,
 source TEXT NOT NULL CHECK(source='manual_fixture'),
 provider_identity TEXT CHECK(provider_identity IS NULL),
 model_identity TEXT CHECK(model_identity IS NULL),
 input_contract_sha256 TEXT NOT NULL CHECK(length(input_contract_sha256)=64),
 request_sha256 TEXT NOT NULL CHECK(length(request_sha256)=64),
 version INTEGER NOT NULL,
 state TEXT NOT NULL,
 script_json TEXT,
 script_sha256 TEXT,
 CHECK((version=1 AND state='STARTED' AND script_json IS NULL AND script_sha256 IS NULL)
 OR(version=2 AND state='COMPLETED' AND json_valid(script_json) AND json_type(script_json)='object' AND length(CAST(script_json AS BLOB))<=65536 AND length(script_sha256)=64))
);
CREATE TRIGGER offline_manual_checkpoint_guard BEFORE UPDATE ON offline_manual_checkpoint
WHEN NEW.job_id IS NOT OLD.job_id OR NEW.source IS NOT OLD.source OR NEW.provider_identity IS NOT OLD.provider_identity
 OR NEW.model_identity IS NOT OLD.model_identity OR NEW.input_contract_sha256 IS NOT OLD.input_contract_sha256
 OR NEW.request_sha256 IS NOT OLD.request_sha256
 OR OLD.state!='STARTED' OR NEW.state!='COMPLETED' OR NEW.version!=OLD.version+1
BEGIN SELECT RAISE(ABORT,'manual_checkpoint_immutable'); END;
'''

def start(db,expected_request_sha256=None):
    if expected_request_sha256 is None:
        expected_request_sha256=json.loads((ROOT/'manual_fixture/fixed-sha256.json').read_text())['manual_request_sha256']
    if not isinstance(expected_request_sha256,str) or not re.fullmatch('[0-9a-f]{64}',expected_request_sha256):raise ValueError('request_sha256')
    db.execute('INSERT INTO offline_manual_checkpoint VALUES (?,?,?,?,?,?,?,?,NULL,NULL)',
      (IDENTITY,'manual_fixture',None,None,digest(CONTRACT),expected_request_sha256,1,'STARTED'))
    db.commit()

def read_checkpoint(db):
    row=db.execute('SELECT * FROM offline_manual_checkpoint WHERE job_id=?',(IDENTITY,)).fetchone()
    if row is None:raise ValueError('checkpoint_absent')
    return dict(row)

def complete(db,raw,expected_script_sha256,expected_contract_sha256):
    # No retry, silent correction or regeneration. Validation precedes write.
    current=read_checkpoint(db)
    if current['state']!='STARTED':raise ValueError('checkpoint_already_complete_no_regeneration')
    result=normalize_manual(raw)
    if (result['script_sha256'],result['input_contract_sha256'])!=(expected_script_sha256,expected_contract_sha256):raise ValueError('fixed_hash_mismatch')
    if current['input_contract_sha256']!=result['input_contract_sha256']:raise ValueError('contract_drift')
    if current['request_sha256']!=result['request_sha256']:raise ValueError('request_identity_drift')
    cursor=db.execute("UPDATE offline_manual_checkpoint SET state='COMPLETED',version=2,script_json=?,script_sha256=? WHERE job_id=? AND state='STARTED' AND version=1 AND input_contract_sha256=?",
                     (result['script_json'],result['script_sha256'],IDENTITY,expected_contract_sha256))
    if cursor.rowcount!=1:raise ValueError('checkpoint_cas_mismatch_stop')
    db.commit()
    after=read_checkpoint(db)
    if after['script_json']!=result['script_json'] or after['script_sha256']!=result['script_sha256']:raise ValueError('checkpoint_readback_mismatch')
    return after

def checkpoint_to_render(checkpoint,expected_script_sha256,expected_contract_sha256):
    required={'job_id','source','provider_identity','model_identity','input_contract_sha256','request_sha256','version','state','script_json','script_sha256'}
    if not isinstance(checkpoint,dict) or set(checkpoint)!=required:raise ValueError('checkpoint_fields')
    if checkpoint['job_id']!=IDENTITY or checkpoint['source']!='manual_fixture' or checkpoint['provider_identity'] is not None or checkpoint['model_identity'] is not None:raise ValueError('checkpoint_provenance_mismatch')
    if checkpoint['state']!='COMPLETED' or type(checkpoint['version'])is not int or checkpoint['version']!=2:raise ValueError('completed_checkpoint_required')
    result=normalize_manual(canonical({'output':strict_json(checkpoint['script_json'])}))
    if checkpoint['script_json']!=result['script_json']:raise ValueError('noncanonical_checkpoint')
    if (result['script_sha256'],checkpoint['script_sha256'])!=(expected_script_sha256,expected_script_sha256):raise ValueError('checkpoint_hash_mismatch')
    if (result['input_contract_sha256'],checkpoint['input_contract_sha256'])!=(expected_contract_sha256,expected_contract_sha256):raise ValueError('checkpoint_contract_mismatch')
    if checkpoint['request_sha256']!=result['request_sha256']:raise ValueError('checkpoint_request_mismatch')
    payload=render_payload(normalize_script({'output':result['script']}))
    validate_render_payload(payload)
    return payload

def validate_render_payload(payload):
    if not isinstance(payload,dict) or set(payload)!=SCRIPT_FIELDS|{'captions','speaker','output'}:raise ValueError('render_payload_fields')
    script={k:payload[k] for k in SCRIPT_FIELDS};checked=normalize_manual(canonical({'output':script}))
    expected=render_payload(normalize_script({'output':checked['script']}))
    # Canonical JSON comparison also distinguishes bool from integer.
    if canonical(payload)!=canonical(expected):raise ValueError('render_payload_timing_reference_or_output_drift')
    return True

def workflow_inputs(payload):
    validate_render_payload(payload)
    return {'render_id':IDENTITY,'title':payload['title'],'hook':payload['hook'],
            'narration':payload['narration'],'speaker':str(payload['speaker']),
            'scenes_json':canonical(payload['scenes']),'captions_json':canonical(payload['captions']),
            'bgm_json':canonical(payload['bgm']),'output_json':canonical(payload['output'])}


def temporary_reference():
    db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row;db.executescript(CHECKPOINT_SQL);return db
