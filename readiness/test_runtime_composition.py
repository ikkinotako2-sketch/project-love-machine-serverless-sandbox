"""Successor composition invariants; no remote connector or deployment entrypoint."""
from oracle_bridge import require_guard
require_guard()
import hashlib,json,unittest
from pathlib import Path
from build_runtime_composition_bundle import expected_bundle
ROOT=Path(__file__).resolve().parents[1]
def read(path):return json.loads((ROOT/path).read_text())
def sha(path):return hashlib.sha256((ROOT/path).read_bytes()).hexdigest()
class CompositionArtifactTests(unittest.TestCase):
 def setUp(self):
  self.c=read('readiness/runtime-composition-contract.json');self.p=read('readiness/runtime-composition-plan.json');self.t=read('readiness/runtime-composition-target-manifest.json');self.a=read('readiness/runtime-composition-audit.json')
 def test_parent_and_historical_database_evidence(self):
  self.assertEqual(self.p['exact_parent_sha'],'626ea5c919749ee8dcff553cda7c9d6dcf8961af');self.assertEqual(self.c['database_evidence']['run'],38119266513);self.assertEqual(set(self.c['database_state'].values()),{'FULL_APPLIED'})
 def test_deterministic_bundle(self):
  one=expected_bundle().encode();two=expected_bundle().encode();self.assertEqual(one,two);self.assertEqual((ROOT/self.p['bundle']).read_bytes(),one);self.assertEqual(sha(self.p['bundle']),self.p['bundle_sha256'])
 def test_source_hash_manifest_actual_bytes(self):
  pins=read(self.p['source_manifest']);self.assertEqual(len(pins),12)
  for path,expected in pins.items():self.assertEqual(sha(path),expected,path)
 def test_all_legacy_audit_pins_unchanged(self):
  for path,expected in read('readiness/runtime-integration-plan.json')['source_sha256'].items():self.assertEqual(sha(path),expected,path)
 def test_revised_production_target_evidence_only(self):
  self.assertEqual(self.t['workflow_sha256'],sha('readiness/production-candidate/revised-source/.github/workflows/youtube-pipeline.yml'));self.assertEqual(self.t['sender_sha256'],sha('readiness/production-candidate/source/plm/entrypoints/yt_serverless_candidate.py'));self.assertIsNone(self.t['required_commit_sha']);self.assertFalse(self.t['approved']);self.assertFalse(self.t['launchable']);self.assertEqual(self.t['approval_status'],'CURRENT_PRODUCTION_TARGET_UNVERIFIED')
 def test_safe_defaults_and_legacy_inputs(self):
  flags=self.c['safe_defaults'];self.assertTrue(all(flags[x] for x in ('TEST_ONLY','DRY_RUN','NO_PUBLISH','EMERGENCY_STOP')));self.assertEqual(flags['serverless_context'],'');self.assertFalse(flags['serverless_guard']);pipeline=(ROOT/'readiness/production-candidate/revised-source/.github/workflows/youtube-pipeline.yml').read_text();adapter=(ROOT/'readiness/production-candidate/source/.github/workflows/youtube-adapter.yml').read_text();self.assertIn('default: ""',pipeline);self.assertIn("!cancelled() && needs.render.result == 'success'",pipeline);self.assertIn('default: false',adapter)
 def test_stopped_successor_config(self):
  c=read('serverless/youtube-connection/wrangler.runtime.stopped.json');self.assertEqual(c['main'],'runtime-bundle.mjs');self.assertFalse(c['workers_dev']);self.assertFalse(c['preview_urls']);self.assertEqual(c['routes'],[]);self.assertEqual(c['triggers']['crons'],[]);self.assertNotIn('queues',c);self.assertTrue(all(x=='true' for x in c['vars'].values()));self.assertEqual(c['d1_databases'][0]['database_id'],self.c['target_db_id'])
 def test_no_execution_marker_or_deploy_workflow(self):
  self.assertFalse((ROOT/'audit-evidence/consumed'/ (self.p['identity']+'.json')).exists());self.assertEqual(self.p['execution_marker'],'NOT_CREATED / NOT_CONSUMED');self.assertFalse(self.p['future_execution_workflow_created']);self.assertFalse(self.p['execution_launchable']);self.assertFalse(self.p['deploy_launchable'])
 def test_no_remote_budget(self):
  self.assertTrue(all(x==0 for x in self.p['side_effect_budget'].values()));self.assertEqual(self.p['maximum_remote_calls'],0);self.assertEqual(self.p['maximum_remote_writes'],0)
 def test_only_key_role_metadata_persisted(self):
  for role,meta in self.c['key_roles'].items():self.assertEqual(set(meta),{'required_env','purpose'})
  for artifact in [self.c,self.p,self.a,self.t]:self.assertNotIn('Authorization',json.dumps(artifact))
 def test_no_job_creation_and_explicit_preapproval(self):
  self.assertFalse(self.c['generation_adapter']['job_creation']);self.assertTrue(self.c['generation_adapter']['preexisting_approved_job_only'])
 def test_operation_descriptor_exact_fields(self):
  fields=self.c['operation_descriptor_fields'];self.assertEqual(len(fields),len(set(fields)));self.assertEqual(self.c['operation_gate']['run_attempt'],1);self.assertEqual(self.c['operation_gate']['max_lifetime_seconds'],300);self.assertTrue(self.c['operation_gate']['explicit_injection'])
 def test_no_hmac_provenance_claim(self):
  self.assertIn('NOT established',self.c['callback']['github_run_provenance']);self.assertEqual(self.a['remote_bundle_equality'],'UNVERIFIED')
 def test_next_readonly_target_before_activation(self):
  self.assertEqual(self.p['next_type'],'D');self.assertIn('CURRENT_PRODUCTION_TARGET_UNVERIFIED',self.a['remaining_blockers']);self.assertIn('LIVE_PLATFORM_GATES',self.a['remaining_blockers'])
 def test_dedicated_ci_offline_guard_no_secrets(self):
  s=(ROOT/'.github/workflows/plm-runtime-integration-offline.yml').read_text();self.assertIn('native_guard.c',s);self.assertIn('node_guard.mjs',s);self.assertIn('test-runtime-composition.mjs',s);self.assertNotIn('secrets.',s);self.assertNotIn('workflow_dispatch',s);self.assertNotIn('wrangler deploy',s)
if __name__=='__main__':unittest.main()
