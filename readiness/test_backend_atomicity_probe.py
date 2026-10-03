import copy
import hashlib
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3
from backend_atomicity_probe import *

class BackendProbeTests(unittest.TestCase):
    def setUp(self):self.s=SQLiteReference();self.plan=sql_plan()
    def tearDown(self):self.s.close()
    def init(self):self.assertEqual(self.s.mutate(self.plan[0]),1)
    def claimed(self):self.init();self.assertEqual(self.s.mutate(self.plan[2]),1)
    def terminal(self,outcome='succeeded'):
        self.claimed();p=sql_plan(outcome=outcome);self.assertEqual(self.s.mutate(p[7]),1);return p
    def test_migration_only_two_additive_create_statements_and_hash(self):
        c=migration_contract();self.assertEqual(c['destructive_statements'],0);self.assertEqual(c['statements'],2);self.assertFalse(c['execution_permitted'])
    def test_modified_sql_is_rejected(self):
        for extra in [b'\nDROP TABLE test_jobs;',b'\nDELETE FROM backend_probe_v1;',b'\nALTER TABLE test_jobs ADD COLUMN x;']:
            with self.assertRaises(ValueError):migration_contract(SQL_PATH.read_bytes()+extra)
    def test_test_jobs_schema_rows_and_objects_unchanged(self):
        old=Path(__file__).resolve().parents[1]/'serverless/migrations/0001_test_jobs.sql'
        self.s.db.executescript(old.read_text());before=self.s.db.execute("SELECT sql FROM sqlite_master WHERE name='test_jobs'").fetchone()[0]
        self.init();self.assertEqual(self.s.db.execute("SELECT sql FROM sqlite_master WHERE name='test_jobs'").fetchone()[0],before);self.assertEqual(self.s.db.execute('SELECT COUNT(*) FROM test_jobs').fetchone()[0],0)
    def test_unique_identity_replay_mints_once(self):
        self.init();self.assertEqual(self.s.mutate(self.plan[1]),0);self.assertEqual(self.s.read()['job_id'],JOB);self.assertEqual(self.s.db.execute('SELECT COUNT(*) FROM backend_probe_v1').fetchone()[0],1)
    def test_second_identity_is_impossible_not_deleted_to_make_room(self):
        self.init();p=copy.deepcopy(self.plan[0]);p['params'][2]='another_intent'
        with self.assertRaises(sqlite3.IntegrityError):self.s.mutate(p)
        self.assertEqual(self.s.db.execute('SELECT COUNT(*) FROM backend_probe_v1').fetchone()[0],1)
    def test_nine_fixed_requests_only_three_logical_row_changes(self):
        changes=[self.s.mutate(p) for p in self.plan];self.assertEqual(changes,[1,0,1,0,0,0,0,1,0]);self.assertEqual(sum(changes),3);self.assertEqual(self.s.read()['version'],3)
    def test_other_contender_can_win(self):
        p=sql_plan(winner='contender_b');self.s.mutate(p[0]);self.assertEqual(self.s.mutate(p[3]),1);self.assertEqual(self.s.mutate(p[2]),0)
        for i in range(4,9):self.assertEqual(self.s.mutate(p[i]),p[i]['expected_changes'])
        self.assertEqual(self.s.read()['owner'],'contender_b')
    def race(self,count):
        with tempfile.TemporaryDirectory() as temp:
            path=str(Path(temp)/'probe.sqlite');seed=SQLiteReference(path);seed.mutate(self.plan[0]);seed.close();barrier=threading.Barrier(count)
            def contender(i):
                ref=SQLiteReference(path,initialize=False)
                step=sql_plan()[2+i%2];barrier.wait(timeout=5)
                try:return ref.mutate(step)
                finally:ref.close()
            with ThreadPoolExecutor(max_workers=count) as pool:changes=list(pool.map(contender,range(count)))
            ref=SQLiteReference(path,initialize=False)
            try:row=ref.read()
            finally:ref.close()
            self.assertEqual(sum(changes),1);self.assertEqual(row['version'],2);self.assertIn(row['owner'],('contender_a','contender_b'))
    def test_two_contenders_separate_connections_race(self):self.race(2)
    def test_eight_contenders_separate_connections_reference_only(self):self.race(8)
    def test_stale_version_has_zero_changes(self):self.claimed();self.assertEqual(self.s.mutate(self.plan[4]),0);self.assertEqual(self.s.read()['version'],2)
    def test_stale_owner_has_zero_changes(self):self.claimed();self.assertEqual(self.s.mutate(self.plan[5]),0);self.assertEqual(self.s.read()['version'],2)
    def test_wrong_fingerprint_has_zero_changes(self):self.claimed();self.assertEqual(self.s.mutate(self.plan[6]),0);self.assertEqual(self.s.read()['content_fingerprint'],FP)
    def test_immutable_fingerprint_is_database_constraint_not_application_only(self):
        self.init()
        with self.assertRaises(sqlite3.IntegrityError):self.s.db.execute("UPDATE backend_probe_v1 SET content_fingerprint=?",('0'*64,))
        self.assertEqual(self.s.read()['content_fingerprint'],FP)
    def test_database_rejects_version_decrease_and_skip(self):
        self.claimed()
        for version in (1,4):
            with self.assertRaises(sqlite3.IntegrityError):self.s.db.execute('UPDATE backend_probe_v1 SET version=?',(version,))
    def test_database_rejects_owner_or_epoch_takeover(self):
        self.claimed()
        for assignment in ["owner='contender_b'","owner_epoch=2","fencing_token=2"]:
            with self.assertRaises(sqlite3.IntegrityError):self.s.db.execute('UPDATE backend_probe_v1 SET '+assignment)
    def test_created_timestamp_cannot_change_and_updated_cannot_regress(self):
        self.init()
        for assignment in ['created_at=created_at+1','updated_at=created_at-1']:
            with self.assertRaises(sqlite3.IntegrityError):self.s.db.execute('UPDATE backend_probe_v1 SET '+assignment)
    def test_successful_terminal_replay_noop(self):
        self.terminal();before=self.s.read();self.assertEqual(self.s.mutate(self.plan[8]),0);self.assertEqual(self.s.read(),before)
    def test_failed_terminal_replay_noop(self):
        p=self.terminal('failed');before=self.s.read();self.assertEqual(self.s.mutate(p[8]),0);self.assertEqual(self.s.read(),before)
    def test_callback_duplicate_is_terminal_fixture_not_real_auth(self):
        self.terminal();self.assertEqual(self.s.mutate(self.plan[8]),0);self.assertEqual(self.s.read()['delivery_id'],'delivery_001')
    def test_terminal_outcome_and_delivery_identity_cannot_be_replaced(self):
        self.terminal()
        for assignment in ["state='failed'","delivery_id='delivery_other'","result_id='result_other'"]:
            with self.assertRaises(sqlite3.IntegrityError):self.s.db.execute('UPDATE backend_probe_v1 SET '+assignment)
    def test_fixed_payload_refuses_sql_params_and_request_identity_changes(self):
        validate_payload(self.plan[0],1790998200)
        for change in [{'sql':'DELETE FROM backend_probe_v1'},{'id':'arbitrary'},{'params':[True]}]:
            step={**self.plan[0],**change}
            with self.assertRaises(ValueError):validate_payload(step,1790998200)
    def test_duplicate_transport_request_never_sent_twice(self):
        ledger=OnceAttemptLedger();calls=[];transport=lambda p:(calls.append(p) or {'http_status':200,'success':True,'changes':0})
        ledger.send(self.plan[0],transport)
        with self.assertRaises(ValueError):ledger.send(self.plan[0],transport)
        self.assertEqual(len(calls),1)
    def test_ninth_slot_is_last_and_does_not_reset_after_restart(self):
        ledger=OnceAttemptLedger()
        for step in self.plan:ledger.reserve(step);ledger.finish(step['id'],'ACK')
        restored=OnceAttemptLedger(ledger.snapshot())
        with self.assertRaises(ValueError):restored.reserve({'id':'tenth'})
    def test_timeout_before_commit_no_resend_even_read_empty(self):
        ledger=OnceAttemptLedger();calls=[]
        def transport(p):calls.append(p);raise TimeoutError()
        out=ledger.send(self.plan[0],transport);self.assertEqual(out['status'],'UNKNOWN');self.assertEqual(reconcile(self.plan[0],None,primary_confirmed=True)['verdict'],'STILL_UNKNOWN')
        with self.assertRaises(ValueError):ledger.send(self.plan[1],transport)
        self.assertEqual(len(calls),1)
    def test_response_lost_after_commit_primary_read_can_confirm_but_does_not_resume(self):
        ledger=OnceAttemptLedger()
        def transport(p):self.s.mutate(p);raise ConnectionResetError()
        ledger.send(self.plan[0],transport);self.assertEqual(reconcile(self.plan[0],self.s.read(),primary_confirmed=True)['verdict'],'COMMITTED')
        with self.assertRaises(ValueError):OnceAttemptLedger(ledger.snapshot()).reserve(self.plan[1])
    def test_5xx_parse_failure_missing_changes_and_wrong_type_are_unknown(self):
        for reply in [{'http_status':503,'success':False,'changes':0},{'http_status':200,'success':True},{'http_status':200,'success':True,'changes':True},'RAW PRIVATE']:
            ledger=OnceAttemptLedger();r=ledger.send(self.plan[0],lambda p:reply);self.assertEqual(r['status'],'UNKNOWN');self.assertNotIn('PRIVATE',str(r))
    def test_reconciliation_does_not_trust_replica_or_outdated_row(self):
        self.init();self.assertEqual(reconcile(self.plan[0],self.s.read())['verdict'],'STILL_UNKNOWN');self.assertEqual(reconcile(self.plan[2],self.s.read(),primary_confirmed=True)['verdict'],'STILL_UNKNOWN')
    def test_not_committed_requires_authoritative_evidence_not_absence(self):
        r=reconcile(self.plan[0],None,authoritative_not_committed=True);self.assertEqual(r['verdict'],'NOT_COMMITTED');self.assertFalse(r['resend_permitted'])
    def test_sending_intent_survives_restart_as_unknown(self):
        ledger=OnceAttemptLedger();ledger.reserve(self.plan[0]);restored=OnceAttemptLedger(ledger.snapshot());self.assertEqual(restored.events[0]['status'],'UNKNOWN')
        with self.assertRaises(ValueError):restored.reserve(self.plan[1])
    def test_offline_success_does_not_promote_remote_or_permit_execution(self):
        for options in ({},{'schema_added':True,'write_token':True,'execution_approved':True}):
            r=remote_readiness(**options);self.assertEqual(r['remote_atomicity'],'UNVERIFIED');self.assertFalse(r['execution_permitted']);self.assertFalse(r['live_ready']);self.assertFalse(r['posting_permitted'])
    def test_corrupt_journal_duplicate_or_excess_entries_rejected(self):
        for snapshot in [[{'id':'x','status':'ACK'}]*2,[{'id':str(i),'status':'ACK'} for i in range(10)],[{'id':1,'status':'ACK'}]]:
            with self.assertRaises(ValueError):OnceAttemptLedger(snapshot)
    def test_missing_live_preconditions_fail_closed_without_network(self):
        r=validate_remote_preconditions({});self.assertFalse(r['preconditions_pass']);self.assertFalse(r['execution_permitted'])
    def test_exact_future_preconditions_still_cannot_execute(self):
        evidence={'account':CF_ACCOUNT,'database':DB_ID,'database_name':'plm-serverless-sandbox-state','inventory_complete':True,'inventory_count':1,'other_d1_count':0,'probe_table_absent':True,'existing_schema_unchanged':True,'test_jobs_rows':0,'bookmark_fresh':True,'token_kind':'ACCOUNT_TOKEN','token_active':True,'token_unexpired':True,'token_scope_owner_confirmed_d1_write_only':True,'free_owner_confirmed':True,'TEST_ONLY':True,'DRY_RUN':True,'NO_PUBLISH':True,'EMERGENCY_STOP':True,'run_attempt':1,'exact_commit_pinned':True,'migration_history_absent':True,'sql_sha256':SQL_SHA,'destructive_statements':0,'separate_final_migration_approval':True}
        r=validate_remote_preconditions(evidence);self.assertTrue(r['preconditions_pass']);self.assertFalse(r['execution_permitted']);self.assertFalse(r['token_scope_api_verified']);self.assertEqual(r['account_isolation'],'unverified')
        for key in ('account','database','sql_sha256','EMERGENCY_STOP','run_attempt','inventory_count','separate_final_migration_approval'):
            wrong=dict(evidence);wrong[key]='wrong';self.assertFalse(validate_remote_preconditions(wrong)['preconditions_pass'])
    def test_booleans_do_not_pass_numeric_inventory_or_attempt_gates(self):
        r=validate_remote_preconditions({'inventory_count':True,'run_attempt':True,'other_d1_count':False,'test_jobs_rows':False,'destructive_statements':False})
        for key in ('inventory_count','run_attempt','other_d1_count','test_jobs_rows','destructive_statements'):self.assertIn(key,r['failed_gates'])
