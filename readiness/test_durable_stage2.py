import unittest,sqlite3,tempfile,threading
from pathlib import Path
import durable_stage2 as m
class Stage2(unittest.TestCase):
 def setUp(self):self.c=m.db()
 def tearDown(self):self.c.close()
 def run_to(self,n):
  for s in m.steps()[:n]:self.assertEqual(m.execute(self.c,s),s[3])
 def test_fixed_14_operations_and_nine_logical_changes(self):
  self.run_to(14);r=m.rows(self.c);self.assertEqual(self.c.total_changes,9);self.assertEqual(r['durable_stage2_job'][0]['version'],6);self.assertEqual(r['durable_stage2_checkpoint'][0]['state'],'COMPLETED');self.assertEqual(len(r['durable_stage2_callback']),1)
 def test_fencing_handoff_increments_epoch_token(self):
  self.run_to(2);r=m.rows(self.c)['durable_stage2_job'][0];self.assertEqual((r['owner'],r['owner_epoch'],r['fencing_token']),('owner_b',2,2))
 def test_stale_owner_zero(self):self.run_to(2);self.assertEqual(m.execute(self.c,m.steps()[2]),0)
 def test_stale_fence_zero(self):self.run_to(3);self.assertEqual(m.execute(self.c,m.steps()[3]),0)
 def test_duplicate_handoff_zero(self):self.run_to(4);self.assertEqual(m.execute(self.c,m.steps()[4]),0)
 def test_timeout_alone_not_handoff_evidence(self):self.assertFalse(m.handoff_authorized(timeout=True))
 def test_old_owner_stop_and_no_inflight_required(self):
  self.assertFalse(m.handoff_authorized(old_owner_stopped=True,inflight='UNKNOWN',proof=m.PROOF));self.assertTrue(m.handoff_authorized(old_owner_stopped=True,inflight='NONE',proof=m.PROOF))
 def test_handoff_blocked_when_generation_started(self):
  self.run_to(6)
  with self.assertRaises(sqlite3.IntegrityError):self.c.execute("UPDATE durable_stage2_job SET owner='owner_a',owner_epoch=3,fencing_token=3,version=3 WHERE job_id=?",[m.JOB])
 def test_arbitrary_fingerprint_overwrite_guard(self):
  self.run_to(1)
  with self.assertRaises(sqlite3.IntegrityError):self.c.execute("UPDATE durable_stage2_job SET content_fingerprint=?,version=2",['0'*64])
  self.assertEqual(m.rows(self.c)['durable_stage2_job'][0]['content_fingerprint'],m.FP)
 def test_checkpoint_create_and_duplicate(self):self.run_to(6);self.assertEqual(m.execute(self.c,m.steps()[5]),0)
 def test_checkpoint_input_fingerprint_mismatch(self):
  self.run_to(6);p=m.steps()[5][2].copy();p[2]='0'*64
  with self.assertRaises(sqlite3.IntegrityError):self.c.execute(m.CK_CREATE,p)
 def test_checkpoint_request_contract_mismatch(self):
  self.run_to(6);p=m.steps()[5][2].copy();p[3]='0'*64
  with self.assertRaises(sqlite3.IntegrityError):self.c.execute(m.CK_CREATE,p)
 def test_checkpoint_stale_owner_cannot_complete(self):
  self.run_to(6);p=m.steps()[6][2].copy();p[-3]='owner_a';p[-2]=1;p[-1]=1;self.assertEqual(self.c.execute(m.CK_COMPLETE,p).rowcount,0)
 def test_completed_checkpoint_resume_never_regenerates(self):self.run_to(7);self.assertEqual(m.checkpoint_resume(self.c),'RESUME_FROM_COMPLETED_NO_GENERATION')
 def test_completed_checkpoint_missing_output_stops(self):self.run_to(7);self.assertIn('NO_REGENERATION',m.checkpoint_resume(self.c,output_available=False))
 def test_completed_checkpoint_corrupt_output_stops(self):self.run_to(7);self.assertIn('NO_REGENERATION',m.checkpoint_resume(self.c,output_hash='0'*64))
 def test_resume_fingerprint_mismatch(self):self.run_to(7);self.assertEqual(m.checkpoint_resume(self.c,request_fp='0'*64),'REJECT_FINGERPRINT')
 def test_started_checkpoint_unknown_response_no_regeneration(self):self.run_to(6);self.assertEqual(m.checkpoint_resume(self.c),'STOP_NO_AUTOMATIC_GENERATION')
 def test_unknown_checkpoint_no_regeneration(self):
  self.run_to(6);self.c.execute("UPDATE durable_stage2_checkpoint SET state='UNKNOWN',version=2,updated_at=103");self.assertEqual(m.checkpoint_resume(self.c),'STOP_NO_AUTOMATIC_GENERATION')
 def test_checkpoint_crash_before_commit(self):
  self.run_to(5);self.c.execute('BEGIN');m.execute(self.c,m.steps()[5]);self.c.execute('ROLLBACK');self.assertEqual(m.checkpoint_resume(self.c),'CREATE_RESERVATION_ONLY')
 def test_checkpoint_response_lost_after_commit_and_restart(self):
  self.run_to(7);self.assertEqual(m.checkpoint_resume(self.c),'RESUME_FROM_COMPLETED_NO_GENERATION');self.assertEqual(m.execute(self.c,m.steps()[6]),0)
 def test_callback_first_delivery_applies_terminal_atomically(self):
  self.run_to(12);self.assertEqual(m.execute(self.c,m.steps()[12]),2);self.assertEqual(m.rows(self.c)['durable_stage2_job'][0]['state'],'SUCCEEDED')
 def test_callback_duplicate_noop(self):self.run_to(13);self.assertEqual(m.execute(self.c,m.steps()[13]),0)
 def test_callback_wrong_job_zero(self):
  self.run_to(11);p=m.steps()[12][2].copy();p[2]='wrong_job';self.assertEqual(self.c.execute(m.CALLBACK,p).rowcount,0)
 def test_callback_wrong_account_zero(self):
  self.run_to(11);p=m.steps()[12][2].copy();p[3]='wrong_account';self.assertEqual(self.c.execute(m.CALLBACK,p).rowcount,0)
 def test_callback_stale_epoch_zero(self):self.run_to(11);self.assertEqual(m.execute(self.c,m.steps()[11]),0)
 def test_callback_tampered_duplicate_rejected(self):
  self.run_to(13);p=m.steps()[13][2].copy();p[0]='0'*64
  with self.assertRaises(sqlite3.IntegrityError):self.c.execute(m.CALLBACK,p)
 def test_callback_after_terminal_first_identity_only_replay(self):self.run_to(13);self.assertEqual(m.execute(self.c,m.steps()[13]),0);self.assertEqual(len(m.rows(self.c)['durable_stage2_callback']),1)
 def test_callback_crash_before_commit_no_partial_terminal(self):
  self.run_to(12);self.c.execute('BEGIN');m.execute(self.c,m.steps()[12]);self.c.execute('ROLLBACK');r=m.rows(self.c);self.assertEqual(r['durable_stage2_callback'],[]);self.assertEqual(r['durable_stage2_job'][0]['state'],'UNKNOWN')
 def test_terminal_callback_response_lost_restart_no_second_consume(self):self.run_to(13);self.assertEqual(m.execute(self.c,m.steps()[13]),0);self.assertEqual(m.rows(self.c)['durable_stage2_job'][0]['version'],6)
 def test_unknown_external_side_effect_no_resend(self):
  x=m.SideEffect();x.send(lost=True)
  with self.assertRaises(ValueError):x.send()
  self.assertEqual(x.sends,1)
 def test_sent_unknown_restart_refusal(self):
  for state in ('SENT','UNKNOWN'):
   with self.assertRaises(ValueError):m.SideEffect(state).restart()
 def test_committed_reconciliation_no_new_send(self):
  x=m.SideEffect('UNKNOWN');self.assertEqual(x.reconcile('COMMITTED'),'CONFIRMED')
  with self.assertRaises(ValueError):x.send()
 def test_not_committed_requires_manual_approval(self):
  x=m.SideEffect('UNKNOWN');self.assertEqual(x.reconcile('NOT_COMMITTED'),'NOT_COMMITTED_MANUAL_APPROVAL_REQUIRED')
  with self.assertRaises(ValueError):x.send()
 def test_still_unknown_stops_one_reconcile_set(self):
  x=m.SideEffect('UNKNOWN');x.reconcile('STILL_UNKNOWN')
  with self.assertRaises(ValueError):x.reconcile('COMMITTED')
 def test_two_connections_contested_handoff_one_winner(self):
  with tempfile.TemporaryDirectory() as d:
   path=str(Path(d)/'probe.sqlite');c=m.db(path);m.execute(c,m.steps()[0]);c.close();barrier=threading.Barrier(2);result=[]
   def contender():
    con=sqlite3.connect(path,isolation_level=None);barrier.wait();result.append(con.execute(m.HANDOFF,m.steps()[1][2]).rowcount);con.close()
   ts=[threading.Thread(target=contender) for _ in range(2)]
   for t in ts:t.start()
   for t in ts:t.join()
   self.assertEqual(sorted(result),[0,1])
 def test_frozen_plan_exact_rows_and_budget(self):
  import json,hashlib
  raw=(Path(__file__).parents[1]/'serverless/durable-stage2-test-plan.json').read_bytes()
  self.assertEqual(hashlib.sha256(raw).hexdigest(),'230c1acee56c3be8a68cac3c29341675a67cc43d926f2047926982510fdc65b7')
  plan=json.loads(raw)
  def materialize(x):
   if isinstance(x,dict):return {k:materialize(v) for k,v in x.items()}
   if isinstance(x,list):return [materialize(v) for v in x]
   if isinstance(x,str) and x.startswith('T0'):return 100+(int(x[3:]) if len(x)>2 else 0)
   return x
  for s in plan['steps']:
   self.assertEqual(m.rows(self.c),materialize(s['expected_before_rows']))
   before=self.c.total_changes;self.c.execute(s['sql'],materialize(s['params']))
   self.assertEqual(self.c.total_changes-before,s['expected_changes'])
   self.assertEqual(m.rows(self.c),materialize(s['expected_after_rows']))
  self.assertEqual(self.c.total_changes,plan['budget']['successful_logical_row_changes'])
 def test_migration_raw_hash_and_top_level_ddl_only(self):
  import hashlib
  raw=(Path(__file__).parents[1]/'serverless/migrations/0003_durable_stage2_probe.sql').read_bytes()
  self.assertEqual(hashlib.sha256(raw).hexdigest(),'012eae70985512f4672546e8f773ed43392754fc95149192b4b0108daf836686')
  statements=[];pending=''
  for line in raw.decode().splitlines(True):
   pending+=line
   if sqlite3.complete_statement(pending):statements.append(pending);pending=''
  self.assertEqual(len(statements),9)
  clean=['\n'.join(l for l in s.splitlines() if not l.strip().startswith('--')).strip() for s in statements]
  self.assertEqual(sum(s.startswith('CREATE TABLE') for s in clean),3)
  self.assertEqual(sum(s.startswith('CREATE TRIGGER') for s in clean),6)
  self.assertTrue(all(s.startswith('CREATE ') for s in clean))
 def test_historical_receipts_hashes_unchanged(self):
  import json,hashlib
  root=Path(__file__).parents[1]
  for f in json.loads((root/'readiness/BACKEND_PREPARATION_IMMUTABLE_EVIDENCE_2026_10_03.json').read_text())['files']:
   self.assertEqual(hashlib.sha256((root/f['path']).read_bytes()).hexdigest(),f['sha256'])
