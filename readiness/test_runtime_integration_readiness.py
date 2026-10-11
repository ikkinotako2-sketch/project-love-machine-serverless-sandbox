"""Post-migration audit regression; memory SQLite only, no live connector."""
from oracle_bridge import require_guard
require_guard()
import hashlib,json,sqlite3,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads((ROOT/p).read_text())
def schema_pin(x):
 x=dict(x);sql=x.pop('sql');x['sql_sha256']=hashlib.sha256(sql.encode()).hexdigest() if sql is not None else None;return x
class RuntimeReadinessTests(unittest.TestCase):
 def setUp(self):
  self.c=read('readiness/runtime-integration-contract.json');self.a=read('readiness/runtime-integration-audit.json');self.p=read('readiness/runtime-integration-plan.json')
  self.db=sqlite3.connect(':memory:');self.db.row_factory=sqlite3.Row;self.db.execute('PRAGMA foreign_keys=ON')
  for n in ('0008_provider_neutral_roundtrip_backend.sql','0009_youtube_queue_result_proposal.sql','0010_youtube_pipeline_checkpoint_candidate.sql'):self.db.executescript((ROOT/'serverless/migrations'/n).read_text())
 def tearDown(self):self.db.close()
 def test_exact_parent_and_postcheck_evidence(self):
  self.assertEqual(self.c['parent'],'1dcbb0db8736527e15ef3ed6bab1f5ebbec4ce66');self.assertEqual(self.a['database_evidence']['run'],38119266513);self.assertEqual(self.a['database_evidence']['terminal'],'0010_POSTCHECK_SUCCESS_STOP')
 def test_every_source_hash_is_immutable(self):
  for p,h in self.c['source_sha256'].items():self.assertEqual(hashlib.sha256((ROOT/p).read_bytes()).hexdigest(),h,p)
 def test_exact_schema_and_columns(self):
  self.assertEqual([schema_pin(x) for x in self.db.execute('SELECT type,name,tbl_name,sql FROM sqlite_schema ORDER BY type,name')],self.c['schema']['objects'])
  for t,columns in self.c['schema']['columns'].items():self.assertEqual([dict(x) for x in self.db.execute('PRAGMA table_info('+t+')')],columns)
 def test_contract_matches_final_postcheck_snapshot(self):
  snapshot=read('readiness/provider-neutral-0010-after.json');names=set(self.c['schema']['columns'])
  expected=sorted((x for x in snapshot['schema'] if x['tbl_name'] in names),key=lambda x:(x['type'],x['name']))
  actual=[x for x in self.c['schema']['objects'] if x['type']!='index']
  self.assertEqual(actual,[schema_pin(x) for x in expected])
  for table in names:
   self.assertEqual(self.c['schema']['columns'][table],snapshot['columns'][table])
   self.assertEqual(snapshot['rows'][table],[])
 def test_all_fixed_runtime_sql_compiles_against_completed_schema(self):
  for name,sql in self.c['fixed_sql'].items():self.db.execute('EXPLAIN '+sql,[None]*sql.count('?')).fetchall()
 def test_exact_object_counts_and_no_fixture_rows(self):
  for ns,tables,triggers,indices in [('plm_rt_v2_',5,11,14),('plm_ytq_v1_',3,10,6),('plm_ytp_v1_',1,3,3)]:
   objects=[x for x in self.c['schema']['objects'] if x['tbl_name'].startswith(ns)]
   for typ,n in [('table',tables),('trigger',triggers),('index',indices)]:self.assertEqual(sum(x['type']==typ for x in objects),n)
   for x in objects:
    if x['type']=='table':self.assertEqual(self.db.execute('SELECT count(*) FROM '+x['name']).fetchone()[0],0)
 def test_mapping_all_nine_tables_and_query_keys(self):
  self.assertEqual(set(self.c['schema']['columns']),{x['object'] for x in self.c['mapping']})
  for row in self.c['mapping']:
   self.assertFalse(row['connected_entrypoint'])
   for verb in ['INSERT','SELECT','UPDATE']:
    for key in row[verb+'_query_keys']:self.assertIn(row['object'],self.c['fixed_sql'][key]);self.assertTrue(self.c['fixed_sql'][key].startswith(verb))
 def test_binding_attempt_and_immutability(self):
  sql=(ROOT/'serverless/migrations/0010_youtube_pipeline_checkpoint_candidate.sql').read_text()
  self.assertIn('CHECK(run_attempt=1)',sql);self.assertIn("pipeline_binding_immutable",sql);self.assertIn('o.payload_sha256=NEW.dispatch_payload_sha256',sql)
 def test_result_complete_is_trigger_enforced(self):
  sql=(ROOT/'serverless/migrations/0009_youtube_queue_result_proposal.sql').read_text()
  self.assertIn("UPDATE plm_ytq_v1_queue SET state='COMPLETE'",sql);self.assertIn("RAISE(ABORT,'ytq_result_atomicity')",sql)
  self.assertIn("saved.state==='COMPLETE'",(ROOT/'serverless/youtube-connection/connection.mjs').read_text())
 def sent_fixture(self):
  from test_youtube_queue_candidate import checkpoint
  from youtube_queue_candidate import SQLiteQueueCandidate,FLAGS
  entry=checkpoint(self.db,job='offline-binding');self.db.commit()
  client=SQLiteQueueCandidate(self.db,dict.fromkeys(FLAGS,True));client.enqueue(entry,104);client.claim(entry['job_id'],entry['owner'],1,1,1,105);r=client.reserve_dispatch(entry['job_id'],2,106);client.fake_send(r['dispatch_id'],lambda:204,107)
  payload=self.db.execute('SELECT payload_sha256 FROM plm_ytq_v1_outbox').fetchone()[0]
  return [entry['job_id'],r['dispatch_id'],'123','123',1,'a'*64,payload,'b'*64,108]
 def test_duplicate_binding_rejected_by_actual_schema(self):
  args=self.sent_fixture();self.db.execute('INSERT INTO plm_ytp_v1_binding VALUES (?,?,?,?,?,?,?,?,?)',args)
  with self.assertRaises(sqlite3.IntegrityError):self.db.execute('INSERT INTO plm_ytp_v1_binding VALUES (?,?,?,?,?,?,?,?,?)',args)
  self.assertEqual(self.db.execute('SELECT count(*) FROM plm_ytp_v1_binding').fetchone()[0],1)
 def test_binding_attempt_two_rejected_by_actual_schema(self):
  args=self.sent_fixture();args[4]=2
  with self.assertRaises(sqlite3.IntegrityError):self.db.execute('INSERT INTO plm_ytp_v1_binding VALUES (?,?,?,?,?,?,?,?,?)',args)
  self.assertEqual(self.db.execute('SELECT count(*) FROM plm_ytp_v1_binding').fetchone()[0],0)
 def test_wrong_dispatch_payload_rejected_by_actual_trigger(self):
  args=self.sent_fixture();args[6]='f'*64
  with self.assertRaises(sqlite3.IntegrityError):self.db.execute('INSERT INTO plm_ytp_v1_binding VALUES (?,?,?,?,?,?,?,?,?)',args)
  self.assertEqual(self.db.execute('SELECT count(*) FROM plm_ytp_v1_binding').fetchone()[0],0)
 def test_safe_defaults_and_no_execution_marker(self):
  self.assertTrue(all(self.p['safe_defaults'].values()));self.assertFalse(self.p['execution_launchable']);self.assertFalse(self.p['future_execution_workflow_created']);self.assertEqual(self.p['marker_state'],'NOT_CREATED_NOT_CONSUMED')
  self.assertFalse((ROOT/'audit-evidence/consumed'/ (self.p['identity']+'.json')).exists())
  self.assertTrue(all(v==0 for v in self.c['side_effects'].values()))
 def test_next_type_not_premature_deploy(self):
  self.assertEqual(self.p['next_type'],'B');self.assertEqual(self.a['readiness']['worker'],'BLOCKED_COMPOSITION');self.assertFalse(self.a['runtime_activation_launchable'])
 def test_legacy_snapshot_defaults_and_cancellation(self):
  p=(ROOT/'readiness/production-candidate/revised-source/.github/workflows/youtube-pipeline.yml').read_text();a=(ROOT/'readiness/production-candidate/source/.github/workflows/youtube-adapter.yml').read_text()
  self.assertIn('default: ""',p);self.assertIn("!cancelled() && needs.render.result == 'success'",p);self.assertIn('serverless_guard:',a);self.assertIn('default: false',a)
 def test_remote_worker_not_assumed_equal(self):
  self.assertTrue(any(b['id']=='LIVE_PLATFORM_GATES' for b in self.a['blockers']));self.assertNotIn('remote_worker_sha256',self.a)
 def test_old_target_and_missing_generation_are_explicit(self):
  ids={b['id'] for b in self.a['blockers']};self.assertIn('PRODUCTION_TARGET_NOT_PINNED',ids);self.assertIn('GENERATION_TO_QUEUE_UNCONNECTED',ids)
 def test_real_consumed_migration_receipt_blocks_resend(self):
  import provider_neutral_0010_common as p
  path='audit-evidence/consumed/provider-neutral-0010-migration-20261011-r2.json'
  with self.assertRaisesRegex(p.Stop,'PRIOR_EXECUTION_NO_RESEND_STOP'):p.prior_check([path],'not-this-consumed-marker.json')
 def test_consumed_markers_never_reset(self):
  for n in ('migration','postcheck'):
   obj=read('audit-evidence/consumed/provider-neutral-0010-'+n+'-20261011-r2.json');self.assertEqual(obj['state'],'CONSUMED_BEFORE_REMOTE')
  self.assertFalse((ROOT/'audit-evidence/consumed/provider-neutral-0010-migration-20261011-r1.json').exists())
if __name__=='__main__':unittest.main()
