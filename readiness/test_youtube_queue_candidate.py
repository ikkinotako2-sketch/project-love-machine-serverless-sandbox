from oracle_bridge import require_guard
require_guard()
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import unittest
import youtube_queue_candidate as y

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'serverless/migrations/0008_provider_neutral_roundtrip_backend.sql'
EXT=ROOT/'serverless/migrations/0009_youtube_queue_result_proposal.sql'
FLAGS=dict.fromkeys(y.FLAGS,True)
SCRIPT='{"title":"offline fake checkpoint"}'
SCRIPT_SHA=hashlib.sha256(SCRIPT.encode()).hexdigest()
MEDIA='d'*64


def connect(path=':memory:'):
    db=sqlite3.connect(path,isolation_level=None,timeout=5)
    db.row_factory=sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    return db


def schema(db):
    db.executescript(BASE.read_text())
    db.executescript(EXT.read_text())


def checkpoint(db,job='yt-900001-1790942400000',intent=None):
    intent=intent or 'intent-'+job
    db.execute('''INSERT INTO plm_rt_v2_job
      (job_id,platform,account_id,intent_id,owner,owner_epoch,fencing_token,version,state,created_at,updated_at)
      VALUES (?,'youtube','youtube_game_001',?,'offline-worker',1,1,1,'ACTIVE',100,100)''',(job,intent))
    db.execute('''INSERT INTO plm_rt_v2_script
      (checkpoint_id,job_id,owner,owner_epoch,fencing_token,version,state,provider,model,request_sha256,created_at,updated_at)
      VALUES (?,?,'offline-worker',1,1,1,'STARTED','offline_fixture','fixed-script',?,100,100)''',('cp-'+job,job,'a'*64))
    db.execute('''INSERT INTO plm_rt_v2_effect
      (effect_id,job_id,kind,owner,owner_epoch,fencing_token,request_sha256,delivery_id,version,state,created_at,updated_at)
      VALUES (?,?,'GENERATION','offline-worker',1,1,?,?,1,'RESERVED',100,100)''',('gen-'+job,job,'a'*64,'gen-delivery-'+job))
    db.execute("UPDATE plm_rt_v2_effect SET state='SENT',version=2,updated_at=101 WHERE effect_id=?",('gen-'+job,))
    db.execute("UPDATE plm_rt_v2_script SET state='COMPLETED',version=2,updated_at=102,script_json=?,script_sha256=? WHERE job_id=?",(SCRIPT,SCRIPT_SHA,job))
    db.execute("UPDATE plm_rt_v2_effect SET state='CONFIRMED',version=3,updated_at=103,result_id=? WHERE effect_id=?",('gen-result-'+job,'gen-'+job))
    return {'job_id':job,'account_id':'youtube_game_001','intent_id':intent,
      'script_sha256':SCRIPT_SHA,'owner':'offline-worker','owner_epoch':1,
      'fencing_token':1,'not_before':104}


def pipeline_callback(db,job):
    # Metadata-only fake stages using the exact, unchanged 0008 guard graph.
    db.execute('''INSERT INTO plm_rt_v2_effect
      (effect_id,job_id,kind,owner,owner_epoch,fencing_token,request_sha256,delivery_id,version,state,created_at,updated_at)
      VALUES (?,?,'RENDER','offline-worker',1,1,?,?,1,'RESERVED',108,108)''',('render-'+job,job,'c'*64,'render-delivery-'+job))
    db.execute("UPDATE plm_rt_v2_effect SET state='SENT',version=2,updated_at=109 WHERE effect_id=?",('render-'+job,))
    db.execute('''INSERT INTO plm_rt_v2_render VALUES (?,?,'offline-worker',1,1,?,?,?,'123','PASS',110)''',
               ('artifact-'+job,job,SCRIPT_SHA,MEDIA,'artifact://'+job))
    db.execute("UPDATE plm_rt_v2_effect SET state='CONFIRMED',version=3,updated_at=111,result_id=? WHERE effect_id=?",('render-result-'+job,'render-'+job))
    db.execute('''INSERT INTO plm_rt_v2_effect
      (effect_id,job_id,kind,owner,owner_epoch,fencing_token,request_sha256,delivery_id,version,state,created_at,updated_at)
      VALUES (?,?,'UPLOAD','offline-worker',1,1,?,?,1,'RESERVED',112,112)''',('upload-'+job,job,MEDIA,'upload-delivery-'+job))
    db.execute("UPDATE plm_rt_v2_effect SET state='SENT',version=2,updated_at=113 WHERE effect_id=?",('upload-'+job,))
    db.execute('''INSERT INTO plm_rt_v2_callback VALUES (?,?,?,'youtube_game_001',1,1,?,?,'CONFIRMED',114)''',
      ('upload-delivery-'+job,'callback-'+job,job,'e'*64,'result-'+job))
    return {'result_id':'result-'+job,'video_id':'offline0001','media_sha256':MEDIA,
            'privacy_status':'private','notify_subscribers':False,'upload_status':'processed'}


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.db=connect();schema(self.db)
        self.entry=checkpoint(self.db)
        self.client=y.SQLiteQueueCandidate(self.db,FLAGS)
        self.job=self.entry['job_id']
    def tearDown(self):self.db.close()
    def reserve(self):
        self.client.enqueue(self.entry,104)
        claimed=self.client.claim(self.job,'offline-worker',1,1,1,105)
        return self.client.reserve_dispatch(self.job,claimed['version'],106)
    def sent(self):
        reserved=self.reserve()
        receipt=self.client.fake_send(reserved['dispatch_id'],lambda:204,107)
        self.assertFalse(receipt['next_job_ready'])
        return reserved

    def test_enqueue_same_identity_replay_no_duplicate(self):
        one=self.client.enqueue(self.entry,104)
        self.assertEqual(one,self.client.enqueue(self.entry,105))
        self.assertEqual(self.db.execute('SELECT count(*) FROM plm_ytq_v1_queue').fetchone()[0],1)

    def test_changed_queue_replay_rejected(self):
        self.client.enqueue(self.entry,104)
        with self.assertRaisesRegex(y.QueueStop,'QUEUE_REPLAY_CHANGED'):
            self.client.enqueue(dict(self.entry,script_sha256='f'*64),105)

    def test_missing_checkpoint_or_wrong_account_rejected(self):
        for field,value in (('script_sha256','f'*64),('account_id','other'),('owner','other'),('owner_epoch',2),('fencing_token',2)):
            with self.subTest(field=field),self.assertRaises(y.QueueStop):
                self.client.enqueue(dict(self.entry,**{field:value}),104)
        self.assertEqual(self.db.execute('SELECT count(*) FROM plm_ytq_v1_queue').fetchone()[0],0)

    def test_no_queue_before_completed_script(self):
        self.db.execute("DELETE FROM plm_rt_v2_effect WHERE kind='GENERATION'")
        with self.assertRaises(y.QueueStop):self.client.enqueue(self.entry,104)

    def test_schedule_not_due_has_no_proposal_or_claim(self):
        self.client.enqueue(dict(self.entry,not_before=200),104)
        self.assertIsNone(self.client.eligible(199))
        self.assertEqual(self.client.eligible(200),self.job)
        with self.assertRaises(y.QueueStop):self.client.claim(self.job,'offline-worker',1,1,1,199)

    def test_stale_owner_epoch_fence_and_version_no_claim(self):
        self.client.enqueue(self.entry,104)
        for owner,epoch,fence,version in (('other',1,1,1),('offline-worker',2,1,1),('offline-worker',1,2,1),('offline-worker',1,1,2)):
            with self.assertRaises(y.QueueStop):self.client.claim(self.job,owner,epoch,fence,version,105)
        self.assertEqual(self.client._row(self.job)['state'],'QUEUED')

    def test_reserve_before_claim_denied(self):
        self.client.enqueue(self.entry,104)
        with self.assertRaises(y.QueueStop):self.client.reserve_dispatch(self.job,1,105)
        self.assertEqual(self.db.execute('SELECT count(*) FROM plm_ytq_v1_outbox').fetchone()[0],0)

    def test_reservation_contains_pinned_private_no_live_proposal(self):
        r=self.reserve();p=r['proposal']
        self.assertEqual(p['ref'],y.PRODUCTION_SHA)
        self.assertEqual(p['privacy_status'],'private');self.assertFalse(p['notify_subscribers'])
        self.assertEqual(p['flags'],FLAGS);self.assertTrue(p['no_retry']);self.assertTrue(p['no_resume'])
        self.assertFalse(p['live_ready']);self.assertEqual(r['actual_operations'],0)

    def test_repeat_reservation_or_fake_send_denied(self):
        r=self.sent()
        with self.assertRaises(y.QueueStop):self.client.reserve_dispatch(self.job,2,108)
        with self.assertRaises(y.QueueStop):self.client.fake_send(r['dispatch_id'],lambda:self.fail('second fake send'),108)
        self.assertEqual(self.client.fake_dispatch_calls,1)

    def test_timeout_permanently_consumes_and_hides_exception(self):
        r=self.reserve()
        def timeout():raise TimeoutError('FAKE_SECRET_PROVIDER_BODY')
        with self.assertRaisesRegex(y.QueueStop,'DISPATCH_UNKNOWN_NO_RETRY_OR_RESUME') as caught:
            self.client.fake_send(r['dispatch_id'],timeout,107)
        self.assertNotIn('FAKE_SECRET',str(caught.exception))
        self.assertEqual(self.client._row(self.job)['state'],'UNKNOWN')
        with self.assertRaises(y.QueueStop):self.client.fake_send(r['dispatch_id'],lambda:204,108)
        self.assertEqual(self.client.fake_dispatch_calls,1)

    def test_non_204_or_boolean_ack_unknown_no_retry(self):
        for status in (200,202,429,500,True,None):
            with self.subTest(status=status):
                db=connect();schema(db);entry=checkpoint(db)
                c=y.SQLiteQueueCandidate(db,FLAGS);c.enqueue(entry,104)
                c.claim(self.job,'offline-worker',1,1,1,105)
                r=c.reserve_dispatch(self.job,2,106)
                with self.assertRaises(y.QueueStop):c.fake_send(r['dispatch_id'],lambda:status,107)
                self.assertEqual(c._row(self.job)['state'],'UNKNOWN');db.close()

    def test_claimed_unknown_dispatched_block_distinct_next_job(self):
        self.client.enqueue(self.entry,104)
        second=checkpoint(self.db,'yt-900002-1790942400001')
        self.client.enqueue(second,104)
        self.client.claim(self.job,'offline-worker',1,1,1,105)
        self.assertIsNone(self.client.eligible(106))
        with self.assertRaises(y.QueueStop):self.client.claim(second['job_id'],'offline-worker',1,1,1,106)
        r=self.client.reserve_dispatch(self.job,2,106)
        with self.assertRaises(y.QueueStop):self.client.fake_send(r['dispatch_id'],lambda:500,107)
        self.assertIsNone(self.client.eligible(108))

    def test_sql_result_cannot_release_queue_without_upstream_callback(self):
        self.sent()
        body={'result_id':'result-'+self.job,'video_id':'offline0001','media_sha256':MEDIA,
          'privacy_status':'private','notify_subscribers':False,'upload_status':'processed'}
        with self.assertRaises(y.QueueStop):self.client.save_result(self.job,body,115)
        self.assertEqual(self.client._row(self.job)['state'],'DISPATCHED')

    def test_success_atomic_result_outbox_queue_and_next_eligible(self):
        self.sent()
        second=checkpoint(self.db,'yt-900002-1790942400001');self.client.enqueue(second,104)
        body=pipeline_callback(self.db,self.job)
        self.assertIsNone(self.client.eligible(114))
        result=self.client.save_result(self.job,body,115)
        self.assertTrue(result['next_job_ready']);self.assertEqual(result['actual_operations'],0)
        self.assertEqual(self.client._row(self.job)['state'],'COMPLETE')
        self.assertEqual(self.db.execute('SELECT state FROM plm_ytq_v1_outbox').fetchone()[0],'CONFIRMED')
        self.assertEqual(self.client.eligible(116),second['job_id'])

    def test_result_replay_identical_noop_changed_rejected(self):
        self.sent();body=pipeline_callback(self.db,self.job)
        self.client.save_result(self.job,body,115)
        self.assertTrue(self.client.save_result(self.job,body,116)['replay'])
        with self.assertRaisesRegex(y.QueueStop,'RESULT_REPLAY_CHANGED'):
            self.client.save_result(self.job,dict(body,video_id='offline0002'),116)

    def test_failed_unknown_queued_public_unlisted_or_extra_body_denied(self):
        self.sent();body=pipeline_callback(self.db,self.job)
        variants=[dict(body,upload_status=s) for s in ('uploaded','queued','failed','unknown')]
        variants += [dict(body,privacy_status=s) for s in ('public','unlisted')]
        variants += [dict(body,notify_subscribers=True),dict(body,raw='FAKE_SECRET_BODY'),dict(body,media_sha256='f'*64)]
        for candidate in variants:
            with self.assertRaises(y.QueueStop):self.client.save_result(self.job,candidate,115)
        self.assertEqual(self.db.execute('SELECT count(*) FROM plm_ytq_v1_result').fetchone()[0],0)

    def test_unknown_dispatch_late_success_requires_reconciliation_never_releases(self):
        r=self.reserve()
        with self.assertRaises(y.QueueStop):self.client.fake_send(r['dispatch_id'],lambda:500,107)
        body=pipeline_callback(self.db,self.job)
        with self.assertRaises(y.QueueStop):self.client.save_result(self.job,body,115)
        self.assertEqual(self.client._row(self.job)['state'],'UNKNOWN')

    def test_result_insert_failure_rolls_back_all_new_queue_changes(self):
        self.sent();body=pipeline_callback(self.db,self.job)
        self.db.execute("CREATE TRIGGER offline_failure AFTER INSERT ON plm_ytq_v1_result BEGIN SELECT RAISE(ABORT,'fixed_test_failure'); END")
        with self.assertRaises(y.QueueStop):self.client.save_result(self.job,body,115)
        self.assertEqual(self.client._row(self.job)['state'],'DISPATCHED')
        self.assertEqual(self.db.execute('SELECT state FROM plm_ytq_v1_outbox').fetchone()[0],'SENT')
        self.assertEqual(self.db.execute('SELECT count(*) FROM plm_ytq_v1_result').fetchone()[0],0)

    def test_delete_identity_change_and_result_update_denied(self):
        self.sent();body=pipeline_callback(self.db,self.job);self.client.save_result(self.job,body,115)
        for sql in ('DELETE FROM plm_ytq_v1_queue','DELETE FROM plm_ytq_v1_outbox',
                    'DELETE FROM plm_ytq_v1_result',"UPDATE plm_ytq_v1_queue SET owner='other',version=version+1",
                    "UPDATE plm_ytq_v1_outbox SET state='RESERVED'",'UPDATE plm_ytq_v1_result SET saved_at=116'):
            with self.assertRaises(sqlite3.IntegrityError):self.db.execute(sql)

    def test_queue_lifetime_cap_32_no_cleanup_or_unbounded_storage(self):
        self.client.enqueue(self.entry,104)
        for n in range(2,33):
            entry=checkpoint(self.db,'yt-'+str(900000+n)+'-1790942400000')
            self.client.enqueue(entry,104)
        extra=checkpoint(self.db,'yt-900033-1790942400000')
        with self.assertRaises(y.QueueStop):self.client.enqueue(extra,104)
        self.assertEqual(self.db.execute('SELECT count(*) FROM plm_ytq_v1_queue').fetchone()[0],32)

    def test_nested_transaction_caller_cannot_suppress_durable_commit(self):
        self.db.execute('BEGIN')
        with self.assertRaisesRegex(y.QueueStop,'TRANSACTION_BOUNDARY_REQUIRED'):
            self.client.enqueue(self.entry,104)
        self.db.rollback()

    def test_flags_foreign_keys_and_live_gate_fail_closed(self):
        for flag in FLAGS:
            with self.assertRaises(y.QueueStop):y.SQLiteQueueCandidate(self.db,dict(FLAGS,**{flag:False}))
        self.db.execute('PRAGMA foreign_keys=OFF')
        with self.assertRaises(y.QueueStop):y.SQLiteQueueCandidate(self.db,FLAGS)
        with self.assertRaises(y.QueueStop):y.live_dispatch_gate()


class DurableReopenTests(unittest.TestCase):
    def test_reopen_after_claim_and_reservation_has_no_resume_or_second_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=str(Path(tmp)/'queue.sqlite');db=connect(path);schema(db)
            entry=checkpoint(db);c=y.SQLiteQueueCandidate(db,FLAGS);c.enqueue(entry,104)
            c.claim(entry['job_id'],'offline-worker',1,1,1,105)
            r=c.reserve_dispatch(entry['job_id'],2,106);db.close()
            db=connect(path);c=y.SQLiteQueueCandidate(db,FLAGS)
            try:
                with self.assertRaises(y.QueueStop):c.claim(entry['job_id'],'offline-worker',1,1,1,107)
                with self.assertRaises(y.QueueStop):c.reserve_dispatch(entry['job_id'],2,107)
                self.assertEqual(c._row(entry['job_id'])['state'],'DISPATCHED')
                self.assertEqual(db.execute('SELECT state FROM plm_ytq_v1_outbox').fetchone()[0],'RESERVED')
                with self.assertRaisesRegex(y.QueueStop,'NO_RESUME'):
                    c.fake_send(r['dispatch_id'],lambda:self.fail('resume'),107)
            finally:db.close()

    def test_reopen_after_timeout_never_fake_sends_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=str(Path(tmp)/'queue.sqlite');db=connect(path);schema(db);entry=checkpoint(db)
            c=y.SQLiteQueueCandidate(db,FLAGS);c.enqueue(entry,104);c.claim(entry['job_id'],'offline-worker',1,1,1,105)
            r=c.reserve_dispatch(entry['job_id'],2,106)
            with self.assertRaises(y.QueueStop):c.fake_send(r['dispatch_id'],lambda:500,107)
            db.close();db=connect(path);c=y.SQLiteQueueCandidate(db,FLAGS)
            try:
                with self.assertRaises(y.QueueStop):c.fake_send(r['dispatch_id'],lambda:self.fail('retry'),108)
                self.assertEqual(c.fake_dispatch_calls,0)
                self.assertIsNone(c.eligible(109))
            finally:db.close()

    def test_committed_success_survives_reopen(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=str(Path(tmp)/'queue.sqlite');db=connect(path);schema(db);entry=checkpoint(db)
            c=y.SQLiteQueueCandidate(db,FLAGS);c.enqueue(entry,104);c.claim(entry['job_id'],'offline-worker',1,1,1,105)
            r=c.reserve_dispatch(entry['job_id'],2,106);c.fake_send(r['dispatch_id'],lambda:204,107)
            body=pipeline_callback(db,entry['job_id']);c.save_result(entry['job_id'],body,115);db.close()
            db=connect(path);c=y.SQLiteQueueCandidate(db,FLAGS)
            try:
                self.assertEqual(c._row(entry['job_id'])['state'],'COMPLETE')
                self.assertTrue(c.save_result(entry['job_id'],body,116)['replay'])
                with self.assertRaises(y.QueueStop):c.fake_send(r['dispatch_id'],lambda:self.fail('retry'),117)
            finally:db.close()

    def test_two_independent_connections_concurrently_one_claim_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=str(Path(tmp)/'queue.sqlite');db=connect(path);schema(db);entry=checkpoint(db)
            y.SQLiteQueueCandidate(db,FLAGS).enqueue(entry,104);db.close();barrier=Barrier(2)
            def contender():
                db=connect(path);c=y.SQLiteQueueCandidate(db,FLAGS);barrier.wait(timeout=5)
                try:c.claim(entry['job_id'],'offline-worker',1,1,1,105);return 'CLAIMED'
                except y.QueueStop:return 'REJECTED'
                finally:db.close()
            with ThreadPoolExecutor(max_workers=2) as pool:
                result=list(pool.map(lambda _:contender(),range(2)))
            self.assertEqual(sorted(result),['CLAIMED','REJECTED'])


class PreparationEvidenceTests(unittest.TestCase):
    def test_candidate_hashes_disabled_gates_and_no_new_launch_markers(self):
        plan=json.loads((ROOT/'readiness/youtube-queue-result-offline-plan.json').read_text())
        for path,expected in plan['candidate_sha256'].items():
            self.assertEqual(hashlib.sha256((ROOT/path).read_bytes()).hexdigest(),expected)
        for flag in ('allow','execution_approved','live_ready','workflow_created',
                     'runtime_marker_created','automatic_trigger_enabled'):
            self.assertFalse(plan[flag])
        self.assertEqual(plan['progress_axes']['A']['percent'],98)
        self.assertEqual(plan['progress_axes']['B']['new_live_E2E'],'0/1')
        self.assertEqual(plan['current_oauth_classification'],'HISTORICALLY_CONFIRMED / CURRENTLY_UNVERIFIED')
        self.assertTrue(plan['no_retry']);self.assertTrue(plan['no_resume'])
        self.assertEqual(plan['budgets']['real_dispatch'],0);self.assertEqual(plan['budgets']['real_upload'],0)
        for identity in ('manual-fixture-runtime-preflight-20261006-004j','manual-fixture-render-20261004-001'):
            self.assertFalse((ROOT/'audit-evidence/consumed'/f'{identity}.json').exists())

    def test_historical_success_and_progress_axes_are_separate(self):
        evidence=json.loads((ROOT/'readiness/youtube-production-history-20261006.json').read_text())
        self.assertEqual(evidence['run_id'],36153932146)
        self.assertEqual(evidence['conclusion'],'success')
        self.assertTrue(all(j['conclusion']=='success' for j in evidence['jobs']))
        self.assertFalse(evidence['code_changed'])
        self.assertEqual(evidence['repository_diff_paths'],['docs/COMMAND_CENTER.md'])
        self.assertTrue(all(x['same'] and x['success_blob_sha']==x['current_blob_sha'] for x in evidence['major_file_comparison']))
        self.assertEqual(evidence['artifact']['status'],'succeeded')
        self.assertTrue(evidence['artifact']['video_id_present'])
        for stage in ('voice','render','quality_gate'):
            self.assertEqual(evidence['artifact'][stage],'succeeded')
        self.assertEqual(evidence['interpretation']['existing_youtube_automation_percent'],98)
        self.assertEqual(evidence['interpretation']['new_hardened_live_e2e_completed'],0)
        self.assertFalse(evidence['interpretation']['existing_production_unfinished_from_004h'])

    def test_oauth_historical_confirmed_current_unknown_not_absent(self):
        evidence=json.loads((ROOT/'readiness/youtube-production-history-20261006.json').read_text())
        self.assertEqual(evidence['oauth']['classification'],'HISTORICALLY_CONFIRMED / CURRENTLY_UNVERIFIED')
        self.assertIsNone(evidence['oauth']['current_exists'])
        self.assertFalse(evidence['oauth']['values_read'])
        self.assertTrue(evidence['historical_cross_run_claim']['present'])
        self.assertFalse(evidence['historical_cross_run_claim']['permanent_durability_proven'])

    def test_corrected_previous_plan_preserves_apt_scope_and_all_four_axes(self):
        plan=json.loads((ROOT/'readiness/youtube-automation-offline-plan.json').read_text())
        self.assertEqual(set(plan['axes']),{'A','B','C','D'})
        self.assertEqual(plan['axes']['A']['progress_percent'],98)
        self.assertEqual(plan['progress_baseline']['new_hardened_live_e2e'],'0/1')
        self.assertFalse(plan['progress_baseline']['apt_004h_is_existing_production_completion_blocker'])
        self.assertTrue(all(x['applies_to']=='NEW_HARDENED_SERVERLESS_ROUTE' for x in plan['gates']))
        self.assertFalse(plan['live_ready']);self.assertEqual(plan['runtime_operations'],0)

    def test_extension_preserves_preexisting_schema_and_sentinel_rows(self):
        db=connect()
        try:
            db.execute('CREATE TABLE offline_legacy_sentinel (identity TEXT PRIMARY KEY, value TEXT)')
            db.execute("INSERT INTO offline_legacy_sentinel VALUES ('protected','fixed')")
            db.executescript(BASE.read_text())
            before=[tuple(r) for r in db.execute('SELECT name,sql FROM sqlite_master ORDER BY name')]
            db.executescript(EXT.read_text())
            after={r['name']:r['sql'] for r in db.execute('SELECT name,sql FROM sqlite_master')}
            self.assertTrue(all(after[name]==sql for name,sql in before))
            self.assertEqual(tuple(db.execute('SELECT * FROM offline_legacy_sentinel').fetchone()),('protected','fixed'))
        finally:db.close()

    def test_base_schema_pin_preserved_and_no_existing_object_modification(self):
        self.assertEqual(hashlib.sha256(BASE.read_bytes()).hexdigest(),
                         '7734fe9ae6d950b5af444cc9a3f917b3da8d050c5e63083f51a79ea42d620bfe')
        text=EXT.read_text()
        self.assertNotIn('ALTER TABLE',text);self.assertNotIn('DROP TABLE',text)
        self.assertEqual(text.count('CREATE TABLE '),3)
        self.assertNotIn('CREATE TABLE IF NOT EXISTS',text)

    def test_second_schema_application_denied_without_resume(self):
        db=connect();schema(db)
        try:
            before=list(db.execute('SELECT name,sql FROM sqlite_master'))
            with self.assertRaises(sqlite3.OperationalError):db.executescript(EXT.read_text())
            self.assertEqual(before,list(db.execute('SELECT name,sql FROM sqlite_master')))
        finally:db.close()
