import copy,json,unittest
from pathlib import Path
from post_migration_readiness import evaluate_post_migration,REMOTE_BEHAVIOR
class PostMigrationGateTests(unittest.TestCase):
 def setUp(self):
  self.e=json.loads((Path(__file__).parent/'POST_MIGRATION_READ_ONLY_EVIDENCE_2026_10_03.json').read_text());self.flags={k:True for k in ('TEST_ONLY','DRY_RUN','NO_PUBLISH','EMERGENCY_STOP')}
 def test_schema_does_not_promote_any_remote_behavior(self):
  r=evaluate_post_migration(self.e,self.flags);self.assertTrue(r['remote_schema_pass']);self.assertFalse(r['live_ready']);self.assertFalse(r['posting_permitted']);self.assertEqual(set(r['backend']),set(REMOTE_BEHAVIOR));self.assertTrue(all(v['remote']=='UNVERIFIED' for v in r['backend'].values()))
 def test_empty_worker_list_with_unproved_visibility_cannot_prove_absence(self):
  r=evaluate_post_migration(self.e,self.flags);self.assertEqual(r['gates']['worker']['status'],'UNVERIFIED');self.assertEqual(r['gates']['worker_deploy']['status'],'BLOCKED')
 def test_false_or_missing_preconditions_cannot_keep_schema_pass(self):
  for key,val in [('schema','MISSING'),('row_count',1),('inventory','UNVERIFIED'),('other_d1_count',1),('time_travel','UNVERIFIED')]:
   e=copy.deepcopy(self.e);e['d1'][key]=val;self.assertFalse(evaluate_post_migration(e,self.flags)['remote_schema_pass'])
 def test_receipt_or_unsafe_flags_refuse(self):
  e=copy.deepcopy(self.e);e['receipt']['run_id']=0
  with self.assertRaises(ValueError):evaluate_post_migration(e,self.flags)
  with self.assertRaises(ValueError):evaluate_post_migration(self.e,{**self.flags,'EMERGENCY_STOP':False})
