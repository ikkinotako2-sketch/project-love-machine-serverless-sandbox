"""SQLite behavioral verification only. No D1, provider, render or upload calls."""
import hashlib
import json
import sqlite3
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]/'serverless'
SHA='a'*64

class GeneralizedBackendTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:');self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript((ROOT/'migrations/0007_generalized_roundtrip_backend.sql').read_text())
        self.job()

    def job(self,job='job-one',account='youtube_account_a',intent='intent-one'):
        self.db.execute('INSERT INTO plm_rt_v1_job VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',(job,'youtube',account,intent,'owner-a',1,1,1,'ACTIVE',None,None,1,1))

    def script(self):
        self.db.execute('INSERT INTO plm_rt_v1_script VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',('cp-one','job-one','owner-a',1,1,1,'STARTED','gemini','gemini-3.8-flash',SHA,None,None,2,2))

    def reserve(self,kind):
        self.db.execute('INSERT INTO plm_rt_v1_effect VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',('effect-'+kind,'job-one',kind,'owner-a',1,1,SHA,'delivery-'+kind,None,1,'RESERVED',3,3))

    def transition(self,kind,state,result=None):
        return self.db.execute('UPDATE plm_rt_v1_effect SET state=?,result_id=?,version=version+1,updated_at=updated_at+1 WHERE job_id=? AND kind=? AND owner=? AND owner_epoch=? AND fencing_token=?',(state,result,'job-one',kind,'owner-a',1,1)).rowcount

    def generated(self):
        self.script();self.reserve('GENERATION');self.transition('GENERATION','SENT')
        script='{"title":"offline verified fixture"}';digest=hashlib.sha256(script.encode()).hexdigest()
        self.db.execute("UPDATE plm_rt_v1_script SET state='COMPLETED',script_json=?,script_sha256=?,version=2,updated_at=5 WHERE job_id='job-one'",(script,digest))
        self.transition('GENERATION','CONFIRMED','cp-one');return digest

    def rendered(self):
        digest=self.generated();self.reserve('RENDER');self.transition('RENDER','SENT')
        self.db.execute('INSERT INTO plm_rt_v1_render VALUES (?,?,?,?,?,?,?,?,?,?,?)',('artifact-one','job-one','owner-a',1,1,digest,SHA,'artifact://repository/run/name','12345','PASS',10))
        self.transition('RENDER','CONFIRMED','artifact-one')

    def uploaded(self,unknown=False):
        self.rendered();self.reserve('UPLOAD');self.transition('UPLOAD','SENT')
        if unknown:
            self.transition('UPLOAD','UNKNOWN')
            self.db.execute("UPDATE plm_rt_v1_job SET state='UNKNOWN',version=version+1,updated_at=12 WHERE job_id='job-one'")

    def callback(self,sql='INSERT INTO',payload=SHA,epoch=1,result='video-one'):
        return self.db.execute(sql+' plm_rt_v1_callback VALUES (?,?,?,?,?,?,?,?,?,?)',('delivery-UPLOAD','callback-one','job-one','youtube_account_a',epoch,1,payload,result,'CONFIRMED',20)).rowcount

    def test_exact_schema_after_raw_sql(self):
        self.db.row_factory=sqlite3.Row
        actual=[dict(x) for x in self.db.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name")]
        after=json.loads((ROOT/'generalized-backend-after.json').read_text())['new']
        self.assertEqual(actual,after['schema'])
        for t in after['columns']:
            self.assertEqual([dict(x) for x in self.db.execute('PRAGMA table_info('+t+')')],after['columns'][t])
            self.assertEqual([dict(x) for x in self.db.execute('PRAGMA index_list('+t+')')],after['indexes'][t])

    def test_identities_are_generalized_and_intent_unique(self):
        self.job('different-job','different-account','different-intent')
        self.assertEqual(self.db.execute('SELECT count(*) FROM plm_rt_v1_job').fetchone()[0],2)
        with self.assertRaises(sqlite3.IntegrityError):self.job('another-job')

    def test_handoff_before_generation_increases_epoch_and_fence(self):
        self.db.execute("UPDATE plm_rt_v1_job SET owner='owner-b',owner_epoch=2,fencing_token=2,version=2,old_owner_stop_proof=?,updated_at=2 WHERE job_id='job-one'",(SHA,))
        with self.assertRaises(sqlite3.IntegrityError):self.script()
        self.assertEqual(self.db.execute("UPDATE plm_rt_v1_job SET version=version+1 WHERE owner='owner-a' AND fencing_token=1").rowcount,0)

    def test_handoff_without_stop_proof_rejected(self):
        with self.assertRaises(sqlite3.IntegrityError):self.db.execute("UPDATE plm_rt_v1_job SET owner='owner-b',owner_epoch=2,fencing_token=2,version=2,updated_at=2")

    def test_handoff_after_generation_started_rejected(self):
        self.script()
        with self.assertRaises(sqlite3.IntegrityError):self.db.execute("UPDATE plm_rt_v1_job SET owner='owner-b',owner_epoch=2,fencing_token=2,version=2,old_owner_stop_proof=?,updated_at=2",(SHA,))

    def test_render_and_upload_require_saved_predecessor(self):
        for kind in ('GENERATION','RENDER','UPLOAD'):
            with self.assertRaises(sqlite3.IntegrityError):self.reserve(kind)
        self.script();self.reserve('GENERATION')
        with self.assertRaises(sqlite3.IntegrityError):self.reserve('RENDER')

    def test_response_before_sent_is_rejected(self):
        self.script();self.reserve('GENERATION')
        with self.assertRaises(sqlite3.IntegrityError):self.db.execute("UPDATE plm_rt_v1_script SET state='COMPLETED',version=2,script_json='{}',script_sha256=?",(SHA,))

    def test_checkpoint_immutable_and_hash_persisted(self):
        self.generated();raw,digest=self.db.execute('SELECT script_json,script_sha256 FROM plm_rt_v1_script').fetchone()
        self.assertEqual(hashlib.sha256(raw.encode()).hexdigest(),digest)
        with self.assertRaises(sqlite3.IntegrityError):self.db.execute("UPDATE plm_rt_v1_script SET script_json='{}',version=version+1")

    def test_unknown_generation_never_resets(self):
        self.script();self.reserve('GENERATION');self.transition('GENERATION','SENT');self.transition('GENERATION','UNKNOWN')
        self.db.execute("UPDATE plm_rt_v1_script SET state='UNKNOWN',version=2,updated_at=6")
        with self.assertRaises(sqlite3.IntegrityError):self.db.execute("UPDATE plm_rt_v1_script SET state='STARTED',version=1")
        with self.assertRaises(sqlite3.IntegrityError):self.transition('GENERATION','RESERVED')
        with self.assertRaises(sqlite3.IntegrityError):self.reserve('GENERATION')
        with self.assertRaises(sqlite3.IntegrityError):self.reserve('RENDER')

    def test_stale_owner_or_fence_zero_change(self):
        self.script();self.reserve('GENERATION')
        for owner,fence in [('stale-owner',1),('owner-a',99)]:
            self.assertEqual(self.db.execute("UPDATE plm_rt_v1_effect SET state='SENT',version=version+1 WHERE owner=? AND fencing_token=?",(owner,fence)).rowcount,0)

    def test_invalid_json_hash_and_oversized_checkpoint_rejected(self):
        self.script();self.reserve('GENERATION');self.transition('GENERATION','SENT')
        for raw,digest in [('invalid',SHA),('[]',SHA),('{}','g'*64),(json.dumps({'x':'a'*65536}),SHA)]:
            with self.assertRaises(sqlite3.IntegrityError):self.db.execute("UPDATE plm_rt_v1_script SET state='COMPLETED',version=2,script_json=?,script_sha256=?",(raw,digest))

    def test_render_ref_no_signed_query_and_immutable(self):
        self.rendered()
        with self.assertRaises(sqlite3.IntegrityError):self.db.execute("UPDATE plm_rt_v1_render SET artifact_ref='artifact://x?secret=y'")

    def test_unknown_upload_stops_reservation_and_send(self):
        self.uploaded(True)
        with self.assertRaises(sqlite3.IntegrityError):self.transition('UPLOAD','SENT')
        with self.assertRaises(sqlite3.IntegrityError):self.reserve('UPLOAD')

    def test_callback_applies_atomically_to_effect_and_job(self):
        self.uploaded(True);self.assertEqual(self.callback(),1)
        self.assertEqual(self.db.execute('SELECT state,result_id FROM plm_rt_v1_job').fetchone(),('SUCCEEDED','video-one'))
        self.assertEqual(self.db.execute("SELECT state,result_id FROM plm_rt_v1_effect WHERE kind='UPLOAD'").fetchone(),('CONFIRMED','video-one'))

    def test_exact_duplicate_callback_zero_changes(self):
        self.uploaded();self.callback()
        self.assertEqual(self.callback('INSERT OR IGNORE INTO'),0)
        with self.assertRaises(sqlite3.IntegrityError):self.callback('INSERT OR IGNORE INTO',payload='b'*64)
        with self.assertRaises(sqlite3.IntegrityError):self.db.execute("UPDATE plm_rt_v1_callback SET result_id='other-result'")

    def test_stale_callback_no_rows_or_terminal_change(self):
        self.uploaded()
        with self.assertRaises(sqlite3.IntegrityError):self.callback(epoch=99)
        self.assertEqual(self.db.execute('SELECT count(*) FROM plm_rt_v1_callback').fetchone()[0],0)
        self.assertEqual(self.db.execute('SELECT state FROM plm_rt_v1_job').fetchone()[0],'ACTIVE')

    def test_callback_failure_rolls_back_all_three_rows(self):
        self.uploaded();self.db.execute("CREATE TRIGGER fixture_fail BEFORE UPDATE ON plm_rt_v1_job BEGIN SELECT RAISE(ABORT,'fixture'); END")
        with self.assertRaises(sqlite3.IntegrityError):self.callback()
        self.assertEqual(self.db.execute('SELECT count(*) FROM plm_rt_v1_callback').fetchone()[0],0)
        self.assertEqual(self.db.execute("SELECT state FROM plm_rt_v1_effect WHERE kind='UPLOAD'").fetchone()[0],'SENT')

    def test_existing_stage2_snapshot_not_modified_by_candidate(self):
        before=json.loads((ROOT/'generalized-backend-before.json').read_text())
        db=sqlite3.connect(':memory:');db.execute('PRAGMA foreign_keys=ON')
        # Build the saved preflight schema and its rows locally. This is not a remote replay.
        for obj in before['schema']:
            if obj['type']=='table':db.execute(obj['sql'])
        for t,rows in before['stage2_rows'].items():
            for row in rows:db.execute('INSERT INTO '+t+' ('+','.join(row)+') VALUES ('+','.join('?' for _ in row)+')',tuple(row.values()))
        row=before['atomicity_row'];db.execute('INSERT INTO backend_probe_v1 ('+','.join(row)+') VALUES ('+','.join('?' for _ in row)+')',tuple(row.values()))
        for obj in before['schema']:
            if obj['type']=='trigger':db.execute(obj['sql'])
        snapshot={t:db.execute('SELECT * FROM '+t).fetchall() for t in (*before['stage2_rows'],'backend_probe_v1','test_jobs')}
        db.executescript((ROOT/'migrations/0007_generalized_roundtrip_backend.sql').read_text())
        self.assertEqual(snapshot,{t:db.execute('SELECT * FROM '+t).fetchall() for t in snapshot})
        for obj in before['schema']:self.assertEqual(db.execute('SELECT sql FROM sqlite_master WHERE name=?',(obj['name'],)).fetchone()[0].strip().rstrip(';'),obj['sql'].strip().rstrip(';'))
