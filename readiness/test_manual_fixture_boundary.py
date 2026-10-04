from oracle_bridge import require_guard
require_guard()
import ast
import copy
import hashlib
import json
import sqlite3
import types
import tempfile
import unittest
from pathlib import Path
from manual_fixture_boundary import (IDENTITY,ROOT,CONTRACT,SAFE_FLAGS,canonical,digest,
 normalize_manual,temporary_reference,start,complete,read_checkpoint,checkpoint_to_render,
 validate_render_payload,workflow_inputs,CHECKPOINT_SQL)
from oracle_bridge import oracle
import test_provider_neutral_audit as neutral

HERE=ROOT/'manual_fixture'
RAW=(HERE/(IDENTITY+'.json')).read_bytes()
SOURCE=json.loads((ROOT/'manual-fixture-production-sources.json').read_text())
FIXED=json.loads((HERE/'fixed-sha256.json').read_text())


def wired(db=None):
    db=temporary_reference() if db is None else db
    start(db)
    cp=complete(db,RAW,FIXED['script_sha256'],FIXED['input_request_contract_sha256'])
    payload=checkpoint_to_render(cp,FIXED['script_sha256'],FIXED['input_request_contract_sha256'])
    return db,cp,payload


def source_functions(path,names,globals_extra=None):
    """Only audited pure function ASTs. Never import renderer, voicevox or ffmpeg.

    No whole-module execution, IO helper, main(), or build_video() permitted.
    """
    allowed={'_json_env','load_payload','_escape_ass','_caption_text',
             '_captions_with_scene_emphasis','_fit_captions_to_audio','_segments','_visual_filters','_ass_time'}
    if set(names)-allowed:raise ValueError('nonpure_production_function')
    tree=ast.parse(SOURCE['sources'][path]);functions=[x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name in names]
    if len(functions)!=len(names):raise ValueError('production_function_drift')
    scope={'json':json,**(globals_extra or {})}
    exec(compile(ast.Module(body=functions,type_ignores=[]),path,'exec'),scope)
    return scope

class ManualFixtureContractTests(unittest.TestCase):
    def test_fixed_identity_original_source_and_no_provider(self):
        r=normalize_manual(RAW)
        self.assertEqual(r['source'],'manual_fixture');self.assertEqual(r['fixture_identity'],IDENTITY)
        self.assertIsNone(r['provider_identity']);self.assertIsNone(r['model_identity'])
        self.assertEqual(set(json.loads(RAW)),{'output'})
    def test_all_fixed_semantic_hashes_and_canonical_bytes(self):
        result=normalize_manual(RAW);db,cp,payload=wired()
        self.assertEqual(result['script_sha256'],FIXED['script_sha256']);self.assertEqual(result['request_sha256'],FIXED['manual_request_sha256'])
        self.assertEqual(digest(CONTRACT),FIXED['input_request_contract_sha256'])
        self.assertEqual(digest(result),FIXED['normalized_contract_sha256'])
        self.assertEqual(digest({'output':result['script']}),FIXED['normalized_output_sha256'])
        self.assertEqual(digest(payload),FIXED['render_payload_sha256'])
        self.assertEqual(digest(cp),FIXED['checkpoint_sha256'])
        pairs=[('script.canonical.json',result['script']),('generation-output.canonical.json',{'output':result['script']}),('normalized-result.canonical.json',result),('render-payload.canonical.json',payload),('checkpoint.canonical.json',cp),('render-workflow-inputs.canonical.json',workflow_inputs(payload)),('input-contract.canonical.json',CONTRACT)]
        for name,value in pairs:
            with self.subTest(file=name):self.assertEqual((HERE/name).read_bytes(),canonical(value).encode('utf-8'))
    def test_repeated_normalization_is_deterministic(self):
        expected=normalize_manual(RAW)
        for _ in range(10):self.assertEqual(normalize_manual(RAW),expected)
    def test_key_order_whitespace_utf8_and_escaped_unicode_have_same_hash(self):
        data=json.loads(RAW)
        def reverse(v):
            if isinstance(v,dict):return {k:reverse(x) for k,x in reversed(list(v.items()))}
            if isinstance(v,list):return [reverse(x) for x in v]
            return v
        for raw in [json.dumps(reverse(data),ensure_ascii=False,indent=4),json.dumps(data,ensure_ascii=True,separators=(',',':')),json.dumps(data,ensure_ascii=False)]:
            self.assertEqual(normalize_manual(raw)['script_sha256'],FIXED['script_sha256'])
    def test_integral_numbers_and_negative_zero_are_normalized(self):
        data=json.loads(RAW)
        for scene in data['output']['scenes']:scene['start']=float(scene['start']);scene['end']=float(scene['end'])
        data['output']['scenes'][0]['start']=-0.0;data['output']['bgm']['volume']=0.0
        self.assertEqual(normalize_manual(json.dumps(data))['script_sha256'],FIXED['script_sha256'])
    def test_textual_semantic_change_changes_script_hash(self):
        data=json.loads(RAW);data['output']['title']+='。'
        self.assertNotEqual(normalize_manual(json.dumps(data))['script_sha256'],FIXED['script_sha256'])
    def test_input_raw_bytes_sha_is_separate_and_fixed(self):
        self.assertEqual(hashlib.sha256(RAW).hexdigest(),FIXED['raw_fixture_sha256'])
        self.assertNotEqual(FIXED['raw_fixture_sha256'],FIXED['script_sha256'])
    def test_existing_parity_code_and_pinned_js_assignments_agree(self):
        _,_,payload=wired();r=normalize_manual(RAW)
        normalized=oracle([{'op':'normalize','input':{'output':r['script']}}])[0]
        self.assertEqual(oracle([{'op':'render','input':normalized}])[0],payload)

# Failure fixtures are rejected unchanged, never corrected or regenerated.
def reject_case(mutator):
    def run(self):
        data=json.loads(RAW);mutator(data)
        raw=json.dumps(data,ensure_ascii=False);before=raw
        with self.assertRaises((ValueError,TypeError,KeyError)):normalize_manual(raw)
        self.assertEqual(raw,before)
    return run
cases={
 'missing_narration':lambda d:d['output'].pop('narration'),
 'empty_narration':lambda d:d['output'].update(narration='  '),
 'wrong_narration_type':lambda d:d['output'].update(narration=42),
 'empty_title':lambda d:d['output'].update(title=''),
 'empty_hook':lambda d:d['output'].update(hook=''),
 'empty_scenes':lambda d:d['output'].update(scenes=[]),
 'scene_limit':lambda d:d['output'].update(scenes=d['output']['scenes']*9),
 'overlap_timing':lambda d:d['output']['scenes'][1].update(start=5),
 'zero_caption_duration':lambda d:d['output']['scenes'][0].update(end=0),
 'negative_start':lambda d:d['output']['scenes'][0].update(start=-1),
 'boolean_time':lambda d:d['output']['scenes'][0].update(start=True),
 'unknown_output_field':lambda d:d['output'].update(extra='bad'),
 'provider_garbage':lambda d:d['output'].update(candidates=[{'finishReason':'STOP'}]),
 'provider_wrapper':lambda d:d.update(usageMetadata={}),
 'unknown_scene_field':lambda d:d['output']['scenes'][0].update(asset='image.png'),
 'external_url_visual':lambda d:d['output']['scenes'][0].update(visual_keyword='https://invalid.example/asset.png'),
 'external_url_narration':lambda d:d['output'].update(narration='https://invalid.example/test'),
 'local_asset_path':lambda d:d['output']['scenes'][0].update(visual_keyword='../media/picture.png'),
 'absolute_path':lambda d:d['output']['scenes'][0].update(visual_keyword='/etc/hosts'),
 'bgm_asset_url':lambda d:d['output']['bgm'].update(asset='https://invalid.example/sound.mp3'),
 'unlicensed_audio_asset':lambda d:d['output']['bgm'].update(asset='unknown.wav'),
 'bgm_wrong_type':lambda d:d['output'].update(bgm=[]),
 'bgm_volume_boolean':lambda d:d['output']['bgm'].update(volume=True),
 'invalid_motion':lambda d:d['output']['scenes'][0].update(motion='execute'),
 'emphasis_not_in_caption':lambda d:d['output']['scenes'][0].update(emphasis_words=['別の文章']),
 'oversized_emphasis_array':lambda d:d['output']['scenes'][0].update(emphasis_words=['一つ']*11),
 'oversized_title':lambda d:d['output'].update(title='あ'*101),
 'oversized_caption':lambda d:d['output']['scenes'][0].update(caption='あ'*241),
 'control_character':lambda d:d['output'].update(narration='abc\x00'),
 'bidi_character':lambda d:d['output'].update(narration='abc\u202e'),
}
for name,mutator in cases.items():setattr(ManualFixtureContractTests,'test_reject_'+name,reject_case(mutator))

def raw_reject(raw):
    def run(self):
        with self.assertRaises((ValueError,UnicodeError)):normalize_manual(raw)
    return run
for name,raw in {'malformed':'{"output":','duplicate_key':'{"output":{},"output":{}}','invalid_utf8':b'\xff',
    'invalid_unicode':'{"output":{"narration":"\\ud800"}}','oversized':' '*65537,
    'nonfinite':'{"output":{"narration":NaN}}','root_array':'[]','deep':'['*26+'0'+']'*26}.items():
    setattr(ManualFixtureContractTests,'test_reject_raw_'+name,raw_reject(raw))

class ManualCheckpointTests(unittest.TestCase):
    def test_started_then_completed_with_exact_readback(self):
        db=temporary_reference();start(db);before=read_checkpoint(db)
        self.assertEqual((before['state'],before['version']),('STARTED',1));self.assertIsNone(before['script_json'])
        cp=complete(db,RAW,FIXED['script_sha256'],FIXED['input_request_contract_sha256'])
        self.assertEqual((cp['state'],cp['version']),('COMPLETED',2));self.assertEqual(cp,read_checkpoint(db))
    def test_no_generation_provider_or_sent_effect_is_fabricated(self):
        db,cp,_=wired();self.assertIsNone(cp['provider_identity']);self.assertIsNone(cp['model_identity'])
        self.assertEqual(cp['source'],'manual_fixture')
        self.assertEqual([r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")],['offline_manual_checkpoint'])
    def test_bad_expected_hash_does_not_complete(self):
        db=temporary_reference();start(db);before=read_checkpoint(db)
        with self.assertRaises(ValueError):complete(db,RAW,'f'*64,FIXED['input_request_contract_sha256'])
        self.assertEqual(read_checkpoint(db),before)
    def test_request_identity_mismatch_prevents_completion(self):
        db=temporary_reference();start(db,'f'*64);before=read_checkpoint(db)
        with self.assertRaises(ValueError):complete(db,RAW,FIXED['script_sha256'],FIXED['input_request_contract_sha256'])
        self.assertEqual(read_checkpoint(db),before)
    def test_request_hash_mismatch_prevents_render(self):
        _,cp,_=wired();cp['request_sha256']='f'*64
        with self.assertRaises(ValueError):checkpoint_to_render(cp,FIXED['script_sha256'],FIXED['input_request_contract_sha256'])
    def test_bad_contract_hash_does_not_complete(self):
        db=temporary_reference();start(db);before=read_checkpoint(db)
        with self.assertRaises(ValueError):complete(db,RAW,FIXED['script_sha256'],'f'*64)
        self.assertEqual(read_checkpoint(db),before)
    def test_invalid_script_does_not_write_then_no_retry(self):
        db=temporary_reference();start(db);before=read_checkpoint(db)
        with self.assertRaises(ValueError):complete(db,'{',FIXED['script_sha256'],FIXED['input_request_contract_sha256'])
        self.assertEqual(read_checkpoint(db),before)
    def test_completed_checkpoint_cannot_be_regenerated_or_overwritten(self):
        db,cp,_=wired()
        with self.assertRaises(ValueError):complete(db,RAW,FIXED['script_sha256'],FIXED['input_request_contract_sha256'])
        with self.assertRaises(sqlite3.IntegrityError):db.execute("UPDATE offline_manual_checkpoint SET script_json='{}'")
        self.assertEqual(read_checkpoint(db),cp)
    def test_sqlite_commit_survives_connection_close_and_reopen(self):
        with tempfile.TemporaryDirectory(prefix='plm-manual-checkpoint-') as directory:
            path=str(Path(directory)/'manual-checkpoint.sqlite')
            db=sqlite3.connect(path);db.row_factory=sqlite3.Row;db.executescript(CHECKPOINT_SQL)
            _,saved,payload=wired(db);db.close()
            reopened=sqlite3.connect(path);reopened.row_factory=sqlite3.Row
            restored=read_checkpoint(reopened);self.assertEqual(restored,saved)
            self.assertEqual(checkpoint_to_render(restored,FIXED['script_sha256'],FIXED['input_request_contract_sha256']),payload)
            with self.assertRaises(ValueError):complete(reopened,RAW,FIXED['script_sha256'],FIXED['input_request_contract_sha256'])
            self.assertEqual(read_checkpoint(reopened),saved);reopened.close()
    def test_checkpoint_reload_is_exact_without_new_generation(self):
        db,cp,payload=wired();saved=json.loads(canonical(cp))
        self.assertEqual(checkpoint_to_render(saved,FIXED['script_sha256'],FIXED['input_request_contract_sha256']),payload)
    def test_checkpoint_hash_mismatch_rejected(self):
        _,cp,_=wired();cp['script_sha256']='f'*64
        with self.assertRaises(ValueError):checkpoint_to_render(cp,FIXED['script_sha256'],FIXED['input_request_contract_sha256'])
    def test_checkpoint_content_mutation_rejected(self):
        _,cp,_=wired();data=json.loads(cp['script_json']);data['title']+='変更';cp['script_json']=canonical(data)
        with self.assertRaises(ValueError):checkpoint_to_render(cp,FIXED['script_sha256'],FIXED['input_request_contract_sha256'])
    def test_started_checkpoint_cannot_render(self):
        db=temporary_reference();start(db)
        with self.assertRaises(ValueError):checkpoint_to_render(read_checkpoint(db),FIXED['script_sha256'],FIXED['input_request_contract_sha256'])
    def test_provenance_as_provider_is_rejected(self):
        _,cp,_=wired();cp['provider_identity']='manual_fixture'
        with self.assertRaises(ValueError):checkpoint_to_render(cp,FIXED['script_sha256'],FIXED['input_request_contract_sha256'])
    def test_noncanonical_persisted_bytes_rejected_even_semantic_hash_matches(self):
        _,cp,_=wired();cp['script_json']=json.dumps(json.loads(cp['script_json']),indent=2)
        with self.assertRaises(ValueError):checkpoint_to_render(cp,FIXED['script_sha256'],FIXED['input_request_contract_sha256'])
    def test_exact_candidate_migration_and_manual_reference_preserve_old_evidence(self):
        db=neutral.fixture();before=neutral.snap(db,neutral.BEFORE['protected_rows'])
        db.executescript(CHECKPOINT_SQL);_,_,payload=wired(db)
        self.assertEqual(neutral.snap(db,neutral.BEFORE['protected_rows']),before)
        self.assertEqual(neutral.snap(db,neutral.TABLES),neutral.AFTER['new']['rows'])
        self.assertNotIn('provider',payload);self.assertNotIn('source',payload)
    def test_candidate_accepts_future_provider_ids_without_schema_change(self):
        # Identifier probes only; these are not selected or eligible providers.
        db=neutral.fixture();before=neutral.snap(db,neutral.BEFORE['protected_rows']);schema=[tuple(r) for r in db.execute('SELECT name,sql FROM sqlite_master')]
        step=next(s for s in neutral.PLAN['steps'] if s['sql'].startswith('INSERT INTO plm_rt_v1_script'))
        for index,provider in enumerate(('future_probe_one','future_probe_two')):
            job_id='offline-provider-identifier-probe-'+str(index)
            db.execute('INSERT INTO plm_rt_v2_job VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',(job_id,'youtube','youtube_offline_probe_'+str(index),'offline-intent-'+str(index),'owner_b',1,1,1,'ACTIVE',None,None,1791077400,1791077400))
            params=neutral.transform(step['params']);params[0]='offline-checkpoint-'+str(index);params[1]=job_id;params[3]=1;params[4]=1;params[7]=provider
            db.execute(neutral.transform(step['sql']),params)
        self.assertEqual([tuple(r) for r in db.execute('SELECT name,sql FROM sqlite_master')],schema)
        self.assertEqual(neutral.snap(db,neutral.BEFORE['protected_rows']),before)
    def test_candidate_not_nullable_manual_checkpoint_is_not_claimed_supported(self):
        # This documents an actual integration limit without inventing a provider.
        schema=neutral.SQL
        self.assertIn('provider TEXT NOT NULL CHECK',schema);self.assertIn("e.kind='GENERATION' AND e.state IN ('SENT','UNKNOWN')",schema)
        self.assertNotIn("provider='gemini'",schema)

class ProductionRenderBoundaryTests(unittest.TestCase):
    def test_actual_production_load_payload_accepts_exact_inputs(self):
        _,_,payload=wired();inputs=workflow_inputs(payload)
        mapping={'title':'INPUT_TITLE','hook':'INPUT_HOOK','narration':'INPUT_NARRATION','speaker':'INPUT_SPEAKER','scenes_json':'INPUT_SCENES_JSON','captions_json':'INPUT_CAPTIONS_JSON','bgm_json':'INPUT_BGM_JSON','output_json':'INPUT_OUTPUT_JSON'}
        env={mapping[k]:v for k,v in inputs.items() if k in mapping}
        scope=source_functions('render-worker/render.py',('_json_env','load_payload'),{'os':types.SimpleNamespace(environ=env)})
        self.assertEqual(scope['load_payload'](),payload)
    def test_narration_title_hook_order_resolution_exact(self):
        _,_,payload=wired();script=json.loads(RAW)['output']
        for key in ('narration','title','hook','scenes'):self.assertEqual(payload[key],script[key])
        self.assertEqual(payload['output'],{'format':'mp4','width':1080,'height':1920,'fps':30})
        self.assertEqual([c['text'] for c in payload['captions']],[s['caption'] for s in script['scenes']])
        self.assertTrue(payload['captions'])
    def test_actual_scene_emphasis_matching_and_ass_escape(self):
        _,_,payload=wired();scope=source_functions('render-worker/ffmpeg_builder.py',('_captions_with_scene_emphasis','_escape_ass','_caption_text'))
        merged=scope['_captions_with_scene_emphasis'](payload['captions'],payload['scenes'])
        for c,s in zip(merged,payload['scenes']):self.assertEqual(c['emphasis_words'],s['emphasis_words'])
        text=scope['_caption_text'](merged[0]);self.assertIn('一つ',text);self.assertIn('\\fs78',text)
        self.assertEqual(scope['_escape_ass']('{test}'),r'\{test\}')
    def test_actual_segments_preserve_all_scene_order(self):
        _,_,payload=wired();scope=source_functions('render-worker/ffmpeg_builder.py',('_segments',))
        result=scope['_segments'](payload['scenes'],18)
        self.assertEqual([r[2] for r in result],payload['scenes']);self.assertEqual([(r[0],r[1])for r in result],[(0,6),(6,12),(12,18)])
    def test_audio_fit_only_adjusts_timing_not_caption_text(self):
        _,_,payload=wired();scope=source_functions('render-worker/ffmpeg_builder.py',('_fit_captions_to_audio',))
        fitted=scope['_fit_captions_to_audio'](payload['captions'],payload['scenes'],24)
        self.assertEqual([c['text']for c in fitted],[c['text']for c in payload['captions']]);self.assertEqual(fitted[-1]['end_seconds'],24)
        self.assertTrue(all(c['start_seconds']<c['end_seconds'] for c in fitted))
    def test_invalid_caption_timing_rejected_in_adapter(self):
        _,_,payload=wired();payload['captions'][1]['start_seconds']=4
        with self.assertRaises(ValueError):validate_render_payload(payload)
    def test_broken_scene_caption_reference_rejected(self):
        _,_,payload=wired();payload['captions'][0]['text']='別の字幕'
        with self.assertRaises(ValueError):validate_render_payload(payload)
    def test_provider_fields_never_enter_render_payload_or_workflow_inputs(self):
        _,_,payload=wired();inputs=workflow_inputs(payload)
        for forbidden in ('provider','model','source','candidates','usageMetadata','oauth_secret_name','privacy_status'):self.assertNotIn(forbidden,payload);self.assertNotIn(forbidden,inputs)
        payload['provider']='garbage'
        with self.assertRaises(ValueError):validate_render_payload(payload)
    def test_invalid_output_and_speaker_boolean_rejected(self):
        _,_,p=wired()
        for patch in ({'speaker':True},{'output':{'format':'mp4','width':720,'height':1920,'fps':30}}):
            q={**p,**patch}
            with self.assertRaises(ValueError):validate_render_payload(q)
    def test_no_assets_in_fixture_or_render_inputs(self):
        _,_,payload=wired();self.assertEqual(payload['bgm'],{'mood':'calm','volume':0})
        self.assertTrue(all(s['sfx']=='none' for s in payload['scenes']));self.assertNotIn('asset',payload['bgm'])
    def test_production_pipeline_passes_only_known_render_fields(self):
        code=SOURCE['sources']['.github/workflows/youtube-pipeline.yml'];render=code.split('\n  render:\n',1)[1].split('\n  youtube:\n',1)[0]
        for k in workflow_inputs(wired()[2]):self.assertIn(k+':',render)
        self.assertNotIn('provider',render);self.assertNotIn('source',render)
    def test_pure_source_oracle_refuses_renderer_execution(self):
        for name in ('main','build_video','generate_voice','_run','_write_ass'):
            with self.assertRaises(ValueError):source_functions('render-worker/ffmpeg_builder.py',(name,))
