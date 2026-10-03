import hashlib,json,sqlite3,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class ImportIsolationTests(unittest.TestCase):
 def test_nine_individual_local_results(self):
  e=json.loads((ROOT/'audit-evidence/stage3-ddl-individual-offline-20261003.json').read_text());self.assertEqual(len(e['rows']),9);self.assertTrue(all(r['sqlite_pass'] and r['local_d1_pass'] for r in e['rows']));self.assertFalse(e['credential_passed']);self.assertEqual(e['cloudflare_api_calls'],0);self.assertEqual(e['local_compatibility_date'],'2026-08-08')
 def test_file_identical_ddl_tokens_not_weakened(self):
  sql=(ROOT/'serverless/migrations/0005_durable_stage2_file_import.sql').read_text();old=json.loads((ROOT/'serverless/stage3-recovery-request.json').read_text());self.assertEqual(sql.splitlines()[1:],[x['sql'] for x in old['batch']]);db=sqlite3.connect(':memory:');db.executescript(sql);self.assertEqual(db.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='trigger'").fetchone()[0],6)
 def test_plan_byte_hashes_and_budget(self):
  raw=(ROOT/'serverless/stage3-import-plan.json').read_bytes();p=json.loads(raw);self.assertEqual(hashlib.sha256(raw).hexdigest(),'32e1d91c2907fd70bdd0a0d5e6379c7f24af9d04906ad8a265cce951aa694b14');self.assertEqual(hashlib.sha256((ROOT/'serverless'/p['sql_file']).read_bytes()).hexdigest(),p['sql_sha256']);self.assertEqual(p['side_effect_http_max'],3);self.assertEqual(p['poll_read_post_max'],3);self.assertEqual(p['sql_query_mutation_max'],0)
