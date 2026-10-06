from oracle_bridge import require_guard
require_guard()
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch
import youtube_pipeline_offline as y
from youtube_pipeline_production_result_snapshot import build_pipeline_result

ROOT = Path(__file__).resolve().parents[1]

def request():
    return {'job_id': 'yt-900001-1790942400000', 'account_id': 'youtube_game_001',
        'idempotency_key': '2'*64, 'media_sha256': '3'*64, 'video_count': 1,
        'privacy_status': 'private', 'notify_subscribers': False, 'scheduled_for': None,
        'made_for_kids': False, 'contains_synthetic_media': True,
        'oauth_secret_exists': True, 'quota_verified': True, 'zero_cost_verified': True,
        'runtime_verified': True, 'flags': dict.fromkeys(y.FLAGS, True)}

def quality():
    return {'mp4_exists': True, 'bytes': 20000, 'video_stream': True, 'audio_stream': True,
        'width': 1080, 'height': 1920, 'fps': '30/1', 'duration': 18,
        'captions_file_exists': True, 'captions': 'Dialogue: in-memory fixture',
        'max_yavg': 30, 'mean_volume_db': -20, 'media_sha256': '3'*64}

def files():
    return {'short.mp4': 20000, 'payload_snapshot.json': 2000, 'render-result.json': 1000}

def reply():
    return {'post_id': 'offline0001', 'privacy_status': 'private',
            'upload_status': 'processed', 'media_sha256': '3'*64}

class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.ledger = y.ReferenceLedger(self.db)
        self.calls = []
    def tearDown(self):
        self.db.close()
    def run_fake(self, req=None, q=None, inventory=None, response=None):
        def upload():
            self.calls.append('fake_upload')
            return copy.deepcopy(reply() if response is None else response)
        return y.OfflinePrivatePipeline(self.ledger).execute(
            req if req is not None else request(), q if q is not None else quality(),
            inventory if inventory is not None else files(), upload)
    def reject(self, req=None, q=None, inventory=None):
        with self.assertRaises(y.Stop):
            self.run_fake(req, q, inventory)
        self.assertEqual(self.calls, [])
        self.assertIsNone(self.ledger.state(request()['idempotency_key']))

    def test_private_success_saved_before_next_job(self):
        r = self.run_fake()
        self.assertEqual(self.calls, ['fake_upload'])
        self.assertEqual(self.ledger.state(request()['idempotency_key']), 'RESULT_SAVED')
        self.assertEqual(self.ledger.result(request()['idempotency_key']), r)
        self.assertTrue(r['next_job_ready'])
        self.assertEqual(r['privacy_status'], 'private')
        self.assertFalse(r['notify_subscribers'])
        self.assertFalse(r['live_ready'])
        self.assertEqual(r['actual_operations'], 0)

    def test_second_object_same_database_never_reuploads(self):
        self.run_fake()
        other = y.ReferenceLedger(self.db)
        with self.assertRaisesRegex(y.Stop, 'DUPLICATE_OR_CONSUMED'):
            y.OfflinePrivatePipeline(other).execute(request(),quality(),files(),
                                                    lambda:self.calls.append('second'))
        self.assertEqual(self.calls, ['fake_upload'])

    def test_new_key_cannot_resend_same_job_or_bytes(self):
        self.run_fake()
        for same_job in (True, False):
            req=request();req['idempotency_key']='4'*64
            if same_job: req['media_sha256']='5'*64
            else: req['job_id']='yt-900002-1790942400001'
            q=quality();q['media_sha256']=req['media_sha256']
            with self.assertRaisesRegex(y.Stop,'DUPLICATE_OR_CONSUMED'):
                self.run_fake(req,q)
        self.assertEqual(self.calls,['fake_upload'])

    def test_claim_without_upload_consumes_after_crash(self):
        self.ledger.claim(request(),quality(),files())
        with self.assertRaisesRegex(y.Stop,'DUPLICATE_OR_CONSUMED'):
            self.run_fake()
        self.assertEqual(self.calls,[])

    def test_timeout_consumes_and_does_not_retain_error(self):
        def timeout():
            self.calls.append('fake_upload')
            raise TimeoutError('FAKE_SECRET_BODY_TOKEN_NEVER_RETAIN')
        runner=y.OfflinePrivatePipeline(self.ledger)
        with self.assertRaises(y.Stop) as caught:
            runner.execute(request(),quality(),files(),timeout)
        self.assertEqual(str(caught.exception),'UPLOAD_UNKNOWN_PERMANENTLY_CONSUMED')
        self.assertEqual(self.ledger.state(request()['idempotency_key']),'UNKNOWN')
        self.assertIsNone(self.ledger.result(request()['idempotency_key']))
        with self.assertRaises(y.Stop): self.run_fake()
        self.assertEqual(self.calls,['fake_upload'])
        self.assertEqual(runner.fake_upload_attempts,1)

    def test_result_save_timeout_consumes_without_resend(self):
        with patch.object(self.ledger,'save',side_effect=TimeoutError('FAKE_SECRET')):
            with self.assertRaisesRegex(y.Stop,'RESULT_PERSISTENCE_UNKNOWN_NO_RESEND'):
                self.run_fake()
        self.assertEqual(self.ledger.state(request()['idempotency_key']),'UNKNOWN')
        with self.assertRaises(y.Stop):self.run_fake()
        self.assertEqual(self.calls,['fake_upload'])

    def test_readback_timeout_does_not_erase_committed_result(self):
        with patch.object(self.ledger,'result',side_effect=TimeoutError('FAKE_SECRET')):
            with self.assertRaisesRegex(y.Stop,'RESULT_PERSISTENCE_UNKNOWN_NO_RESEND'):
                self.run_fake()
        self.assertEqual(self.ledger.state(request()['idempotency_key']),'RESULT_SAVED')
        with self.assertRaises(y.Stop):self.run_fake()
        self.assertEqual(self.calls,['fake_upload'])

    def test_raw_body_and_exception_fields_rejected_without_storage(self):
        r=reply();r['raw']='FAKE_SECRET_BODY'
        with self.assertRaisesRegex(y.Stop,'UPLOAD_UNKNOWN_PERMANENTLY_CONSUMED'):
            self.run_fake(response=r)
        self.assertIsNone(self.ledger.result(request()['idempotency_key']))

    def test_failed_unknown_queued_are_not_success_even_with_ok_true(self):
        # Existing builder marks these envelopes succeeded; guarded boundary must not.
        for state in ('failed','unknown','queued'):
            with self.subTest(state=state):
                old=build_pipeline_result(job_id='old',render_job_status='success',
                    youtube_job_status='success',render_result={'ok':True},
                    youtube_result={'ok':True,'result':{'state':state}})
                self.assertEqual(old['status'],'succeeded')
                with self.assertRaises(y.Stop):
                    y.confirmed_result(dict(reply(),upload_status=state),request())

    def test_returned_public_or_unlisted_is_unknown(self):
        for privacy in ('public','unlisted'):
            with self.assertRaises(y.Stop):
                y.confirmed_result(dict(reply(),privacy_status=privacy),request())

    def test_returned_media_mismatch_stops(self):
        with self.assertRaises(y.Stop):
            y.confirmed_result(dict(reply(),media_sha256='4'*64),request())

    def test_missing_video_id_stops(self):
        for value in (None,'','FAKE_SECRET_LONG_BODY',False):
            with self.assertRaises(y.Stop):
                y.confirmed_result(dict(reply(),post_id=value),request())

    def test_quality_media_mismatch_before_claim(self):
        q=quality();q['media_sha256']='4'*64;self.reject(q=q)

    def test_quality_size_mismatch_before_claim(self):
        q=quality();q['bytes']=20001;self.reject(q=q)

    def test_quality_signal_failure_before_claim(self):
        for field,value in (('max_yavg',0),('mean_volume_db',-80),
                            ('audio_stream',False),('width',1920),('duration',float('nan'))):
            q=quality();q[field]=value;self.reject(q=q)

    def test_size_cap_before_claim(self):
        f=files();f['payload_snapshot.json']=12*1024*1024;self.reject(inventory=f)

    def test_extra_artifact_before_claim(self):
        f=files();f['oauth.json']=1;self.reject(inventory=f)

    def test_quality_extra_raw_body_rejected_before_claim(self):
        q=quality();q['raw_stdout']='FAKE_SECRET_BODY';self.reject(q=q)

    def test_quality_secret_like_captions_rejected_before_claim(self):
        q=quality();q['captions']='Dialogue: refresh_token=FAKE_SECRET';self.reject(q=q)

    def test_extra_request_secrets_before_claim(self):
        req=request();req['oauth_token']='FAKE_SECRET';self.reject(req=req)

    def test_claim_and_result_cannot_be_deleted_or_identity_changed(self):
        self.run_fake()
        for sql in ('DELETE FROM youtube_claim','UPDATE youtube_claim SET key="changed"',
                    'UPDATE youtube_claim SET state="CLAIMED"',
                    'UPDATE youtube_claim SET result="raw"'):
            with self.assertRaises(sqlite3.IntegrityError):
                self.db.execute(sql)
        self.assertEqual(self.ledger.state(request()['idempotency_key']),'RESULT_SAVED')

    def test_second_job_only_after_result_and_distinct_claim(self):
        self.run_fake()
        req=request();req.update(job_id='yt-900002-1790942400001',idempotency_key='5'*64,media_sha256='6'*64)
        q=quality();q['media_sha256']=req['media_sha256']
        r=reply();r['media_sha256']=req['media_sha256'];r['post_id']='offline0002'
        self.run_fake(req,q,response=r)
        self.assertEqual(len(self.calls),2)

    def test_unknown_prior_job_blocks_distinct_next_job(self):
        self.ledger.claim(request(),quality(),files())
        self.ledger.transition(request()['idempotency_key'],'CLAIMED','ATTEMPTED')
        self.ledger.transition(request()['idempotency_key'],'ATTEMPTED','UNKNOWN')
        req=request();req.update(job_id='yt-900002-1790942400001',idempotency_key='5'*64,media_sha256='6'*64)
        q=quality();q['media_sha256']=req['media_sha256']
        with self.assertRaisesRegex(y.Stop,'PRIOR_JOB_UNRESOLVED'):
            self.run_fake(req,q)
        self.assertEqual(self.calls,[])
        self.assertIsNone(self.ledger.state(req['idempotency_key']))

    def test_live_gate_cannot_be_unlocked_by_flags(self):
        with self.assertRaisesRegex(y.Stop,'BLOCKED_RUNTIME_DURABLE_LEDGER_AND_UPLOAD_APPROVAL_REQUIRED'):
            y.live_upload_gate()

def contract_rejection(field,value):
    def test(self):
        req=request();req[field]=value;self.reject(req=req)
    return test

for name,field,value in (
    ('public','privacy_status','public'),('unlisted','privacy_status','unlisted'),
    ('notify','notify_subscribers',True),('schedule','scheduled_for','2026-10-07T00:00:00Z'),
    ('multi_video','video_count',2),('bool_video','video_count',True),
    ('oauth','oauth_secret_exists',False),('quota','quota_verified',False),
    ('billing','zero_cost_verified',False),('runtime','runtime_verified',False),
    ('account','account_id','other'),('job','job_id','FAKE_SECRET_BODY'),
    ('key','idempotency_key','FAKE_SECRET_BODY'),
    ('audience','made_for_kids',None),('synthetic','contains_synthetic_media',None),
    ('unsafe_flags','flags',dict.fromkeys(y.FLAGS,False))):
    setattr(PipelineTests,'test_reject_'+name,contract_rejection(field,value))

class AuditTests(unittest.TestCase):
    def test_production_snapshot_byte_hash(self):
        data=(ROOT/'readiness/youtube_pipeline_production_result_snapshot.py').read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(),'b76138393519d0da46943d6675930c39df03aa6f1efea21da420bf38594ed257')

    def test_consumed_004h_unchanged_and_unlaunched_markers_absent(self):
        manifest=json.loads((ROOT/'readiness/youtube-automation-offline-plan.json').read_text())
        for path,expected in manifest['frozen_sandbox_sha256'].items():
            self.assertEqual(hashlib.sha256((ROOT/path).read_bytes()).hexdigest(),expected)
        for path in manifest['absent_markers']:
            self.assertFalse((ROOT/path).exists())

    def test_no_new_executable_workflow_or_installer(self):
        self.assertFalse(list((ROOT/'.github/workflows').glob('*v4j*')))
        self.assertFalse(list((ROOT/'.github/workflows').glob('*youtube*upload*')))
        self.assertFalse(list((ROOT/'readiness').glob('*005*')))

    def test_source_manifest_and_all_gates_present(self):
        plan=json.loads((ROOT/'readiness/youtube-automation-offline-plan.json').read_text())
        self.assertEqual(len(plan['gates']),14)
        self.assertFalse(plan['live_ready'])
        self.assertEqual(plan['runtime_operations'],0)
        self.assertTrue(plan['no_retry']);self.assertTrue(plan['no_resume'])
        self.assertEqual(plan['apt_conclusion'],'NO_EXACT_MATCH_IN_FROZEN_SOURCE_CONFIRMED_GLOBALERROR_E_TEMPLATES')
        self.assertEqual(plan['production_sha'],'b0c7f429a1f58726c4a75f4fb090928cf567b585')

    def test_no_raw_capture_or_credentials_in_success_projection(self):
        payload=y.confirmed_result(reply(),request())
        raw=json.dumps(payload)
        for key in ('raw_stdout','raw_stderr','raw_line','oauth_token','exception','message'):
            self.assertNotIn(key,raw)
        self.assertFalse(payload['live_ready'])

class ExistingRouteBridgeTests(unittest.TestCase):
    def script(self):
        payload=json.loads((ROOT/'readiness/manual_fixture/render-payload.canonical.json').read_text())
        return {k:payload[k] for k in ('title','hook','narration','scenes','bgm')}

    def prepare(self, runtime=True):
        from youtube_preparation_bridge import prepare_fixture
        return prepare_fixture('机の上に余白を作る',self.script(),request()['job_id'],
            dict.fromkeys(y.FLAGS,True),quality(),files(),
            {'oauth_secret_exists':True,'quota_verified':True,
             'zero_cost_verified':True,'runtime_verified':runtime})

    def test_theme_to_existing_inputs_quality_private_result_next_data_only(self):
        prepared=self.prepare()
        req=prepared['request']
        self.assertEqual(prepared['pipeline_inputs']['job_id'],req['job_id'])
        self.assertEqual(prepared['render_payload']['speaker'],1)
        for field in ('privacy_status','notify_subscribers','made_for_kids','contains_synthetic_media'):
            self.assertEqual(prepared['pipeline_inputs'][field],req[field])
        self.assertFalse(prepared['render_executed'])
        self.assertFalse(prepared['upload_executed'])
        db=sqlite3.connect(':memory:')
        try:
            ledger=y.ReferenceLedger(db)
            result=y.OfflinePrivatePipeline(ledger).execute(req,quality(),files(),reply)
            self.assertEqual(result['job_id'],req['job_id'])
            self.assertTrue(result['next_job_ready'])
            self.assertEqual(ledger.result(req['idempotency_key']),result)
            self.assertEqual(result['actual_operations'],0)
        finally:db.close()

    def test_existing_id_and_immutable_checkpoint_reuse_no_provider_call(self):
        from provider_neutral_generation import checkpoint_fixture, render_input_fixture
        raw=json.dumps(self.script(),ensure_ascii=False)
        checkpoint=checkpoint_fixture('manual_fixture','fixed-script-v1','a'*64,raw,
            '机の上に余白を作る',request()['job_id'],dict.fromkeys(y.FLAGS,True))
        restored=render_input_fixture(checkpoint,'manual_fixture','fixed-script-v1','a'*64)
        self.assertEqual(restored['script'],self.script())
        self.assertFalse(restored['live_permitted'])
        with self.assertRaisesRegex(ValueError,'immutable_checkpoint'):
            checkpoint_fixture('manual_fixture','fixed-script-v1','a'*64,raw,
                '机の上に余白を作る',request()['job_id'],dict.fromkeys(y.FLAGS,True),
                existing=checkpoint)

    def test_runtime_blocker_reaches_bridge_before_any_effect(self):
        with self.assertRaisesRegex(y.Stop,'RUNTIME_NOT_VERIFIED'):
            self.prepare(runtime=False)

    def test_replay_stable_idempotency_and_content_change_binding(self):
        self.assertEqual(self.prepare()['request']['idempotency_key'],
                         self.prepare()['request']['idempotency_key'])
