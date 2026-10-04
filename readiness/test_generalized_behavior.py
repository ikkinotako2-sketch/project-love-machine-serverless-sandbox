"""Replay frozen SQL candidate locally, including all rollback-on-ABORT expectations."""
import hashlib,json,sqlite3,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'serverless'
SHA='452fd980ba62164f71cfe3841ea7d399ef988c6e259945d5c67487a44eaf52c7'
class GeneralizedBehaviorCandidateTests(unittest.TestCase):
 def setUp(self):
  raw=(BASE/'generalized-behavior-test-plan.json').read_bytes();self.assertEqual(hashlib.sha256(raw).hexdigest(),SHA);self.p=json.loads(raw)
  self.db=sqlite3.connect(':memory:');self.db.row_factory=sqlite3.Row;self.db.execute('PRAGMA foreign_keys=ON')
  self.before=json.loads((BASE/'generalized-backend-before.json').read_text())
  for x in self.before['schema']:
   if x['type']=='table':self.db.execute(x['sql'])
  for t,rows in self.before['stage2_rows'].items():
   for r in rows:self.db.execute('INSERT INTO '+t+' ('+','.join(r)+') VALUES ('+','.join('?' for _ in r)+')',list(r.values()))
  r=self.before['atomicity_row'];self.db.execute('INSERT INTO backend_probe_v1 ('+','.join(r)+') VALUES ('+','.join('?' for _ in r)+')',list(r.values()))
  for x in self.before['schema']:
   if x['type']=='trigger':self.db.execute(x['sql'])
  self.db.executescript((BASE/'migrations/0007_generalized_roundtrip_backend.sql').read_text())
  self.schema=self.db.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').fetchall()
  self.old=self.old_snapshot();self.assertEqual(self.old,self.p['protected_before_after_rows'])
 def tearDown(self):self.db.close()
 def snapshot(self):return {t:[dict(r) for r in self.db.execute(sql)] for t,sql in self.p['readback_sql'].items()}
 def old_snapshot(self):return {t:[dict(r) for r in self.db.execute('SELECT * FROM '+t)] for t in [*self.before['stage2_rows'],'backend_probe_v1','test_jobs']}
 def replay(self):
  changes=0
  for s in self.p['steps']:
   with self.subTest(step=s['id']):
    self.assertEqual(self.snapshot(),s['before_rows']);before=self.db.total_changes;e=s['expected']
    if e['outcome']=='REJECTED':
     with self.assertRaises(sqlite3.IntegrityError) as exc:self.db.execute(s['sql'],s['params'])
     self.assertEqual(str(exc.exception),e['safe_error_token']);self.assertEqual(e['logical_changes'],0)
    else:
     self.db.execute(s['sql'],s['params']);self.assertEqual(self.db.total_changes-before,e['logical_changes'])
    self.assertEqual(self.snapshot(),s['after_rows']);self.assertEqual(self.old_snapshot(),self.old);self.assertEqual(self.db.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').fetchall(),self.schema)
    changes+=e['logical_changes']
  self.assertEqual(changes,18);self.assertEqual(self.snapshot(),self.p['expected_final_rows'])
 def test_full_33_step_replay_changes_and_preservation(self):self.replay()
 def test_callback_atomic_3_row_and_duplicate_conflicts(self):
  self.replay();cb=next(s for s in self.p['steps'] if s['id']=='callback_atomic_upload_confirm_job_succeeded');self.assertEqual(cb['expected']['logical_changes'],3)
  for t in ['plm_rt_v1_job','plm_rt_v1_effect','plm_rt_v1_callback']:self.assertNotEqual(cb['before_rows'][t],cb['after_rows'][t])
  self.assertEqual(self.p['expected_final_rows']['plm_rt_v1_job'][0]['state'],'SUCCEEDED')
 def test_exact_script_bytes_and_hash(self):
  self.replay();r=self.p['expected_final_rows']['plm_rt_v1_script'][0];self.assertEqual(hashlib.sha256(r['script_json'].encode()).hexdigest(),r['script_sha256']);self.assertTrue(json.loads(r['script_json'])['synthetic'])
 def test_one_identity_and_7_final_rows(self):
  self.replay();rows=self.p['expected_final_rows'];self.assertEqual(sum(map(len,rows.values())),7);self.assertEqual({r['job_id'] for rs in rows.values() for r in rs},{self.p['identity']['job_id']});self.assertEqual({r['kind'] for r in rows['plm_rt_v1_effect']},{'GENERATION','RENDER','UPLOAD'})
 def test_no_second_job_identity_for_unique_intent(self):
  duplicate=self.p['steps'][1];self.assertIn('ON CONFLICT(platform,account_id,intent_id) DO NOTHING',duplicate['sql']);self.assertEqual(duplicate['params'],self.p['steps'][0]['params']);self.assertEqual(duplicate['before_rows'],duplicate['after_rows'])
 def test_simulated_unknown_is_not_transport_unknown(self):
  unknown=next(s for s in self.p['steps'] if s['id']=='upload_unknown');self.assertEqual(unknown['expected']['outcome'],'APPLIED');self.assertEqual(unknown['expected']['logical_changes'],1)
  self.assertTrue(all(s['on_mismatch_timeout_unknown']=='STOP_NO_RESEND_ONE_READ_ONLY_RECONCILIATION' for s in self.p['steps']))
 def test_budget_and_no_disallowed_sql(self):
  self.assertEqual(len(self.p['steps']),self.p['budgets']['mutation_sends']);self.assertEqual(self.p['budgets']['runner'],1)
  for s in self.p['steps']:self.assertRegex(s['sql'],r'^(INSERT|UPDATE)');self.assertNotRegex(s['sql'],r'\b(DELETE|DROP|ALTER|REPLACE|RENAME)\b')
 def test_caller_hash_validation_is_required_not_db_attested(self):
  self.assertIn('script_sha256',str(self.p));self.assertEqual(self.p['future_upload'],{'privacyStatus':'private','notifySubscribers':False})
