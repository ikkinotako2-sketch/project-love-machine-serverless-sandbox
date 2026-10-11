"""Exact pinned production evidence and future read-only boundaries, no remote IO."""
from oracle_bridge import require_guard
require_guard()
import hashlib,json,unittest
from pathlib import Path
import runtime_remote_readonly_contract as remote
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads((ROOT/p).read_text())
class RuntimeTargetTests(unittest.TestCase):
 def setUp(self):
  self.e=read('readiness/runtime-target-readonly-inspection.json');self.m=read('readiness/runtime-target-pinned-manifest.json');self.p=read('readiness/runtime-remote-readonly-plan.json')
 def test_exact_candidate_merge_current_relation(self):
  self.assertEqual(self.e['candidate_commit'],'1d2f8f812dab936ae911a12c03886b3adea5415d');self.assertEqual(self.e['merge_commit'],'1ea540cd373dab6c4ff789619b357fb72828a75e');self.assertEqual(self.e['observed_current_main'],'387e1784c031d6dc47bda33566506a7f9f2b0172');self.assertIn(self.e['candidate_commit'],self.e['merge_parents']);self.assertEqual(self.e['compare']['ahead_by'],21);self.assertEqual(self.e['compare']['effective_changed_files'],['docs/COMMAND_CENTER.md']);self.assertEqual(self.e['compare']['code_target_drift'],0)
 def test_exact_three_files_and_real_bytes(self):
  mapping={'.github/workflows/youtube-pipeline.yml':'readiness/production-candidate/revised-source/.github/workflows/youtube-pipeline.yml','.github/workflows/youtube-adapter.yml':'readiness/production-candidate/source/.github/workflows/youtube-adapter.yml','plm/entrypoints/yt_serverless_candidate.py':'readiness/production-candidate/source/plm/entrypoints/yt_serverless_candidate.py'}
  self.assertEqual(sorted(self.e['files']),sorted(mapping));self.assertEqual(self.e['candidate_changed_files'],sorted(mapping));self.assertEqual(self.e['merge_changed_files'],sorted(mapping))
  for path,local in mapping.items():
   raw=(ROOT/local).read_bytes();f=self.e['files'][path];self.assertEqual(hashlib.sha256(raw).hexdigest(),f['sha256']);self.assertEqual(hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest(),f['git_blob_sha']);self.assertEqual(f['merge_blob_sha'],f['git_blob_sha']);self.assertTrue(f['sandbox_byte_equality']);self.assertTrue(f['current_equals_merge'])
 def test_safe_defaults_and_explicit_serverless_guard(self):
  s=(ROOT/'readiness/production-candidate/revised-source/.github/workflows/youtube-pipeline.yml').read_text();a=(ROOT/'readiness/production-candidate/source/.github/workflows/youtube-adapter.yml').read_text();self.assertIn('default: ""',s);self.assertIn('default: false',a)
  for stage in ('bind','render','result'):self.assertIn('yt_serverless_candidate '+stage,s)
  self.assertGreaterEqual(s.count("if: inputs.serverless_context != ''"),3)
  for flag in ('TEST_ONLY','DRY_RUN','NO_PUBLISH','EMERGENCY_STOP'):self.assertIn(flag+': ${{ vars.PLM_SERVERLESS_'+flag+" || 'true' }}",s)
  self.assertIn("!cancelled() && needs.render.result == 'success' && (inputs.serverless_context == '' || needs.checkpoint_render.result == 'success')",s)
 def test_sender_exact_run_hash_private_roles_https_no_retry(self):
  s=(ROOT/'readiness/production-candidate/source/plm/entrypoints/yt_serverless_candidate.py').read_text()
  for text in ("attempt=='1'","ctx['production_ref']==commit","hashlib.sha256(workflow_bytes).hexdigest()==ctx['workflow_sha256']","inputs['privacy_status']=='private'","inputs['notify_subscribers'] in (False,'false')","not hmac.compare_digest(stage_key,callback_key)","parsed.scheme=='https'","parsed.path==path","CALLBACK_UNKNOWN_NO_RETRY","Path(sentinel).open('x'"):
   self.assertIn(text,s)
 def test_pin_is_not_activation(self):
  self.assertEqual(self.m['required_commit_sha'],self.e['merge_commit']);self.assertEqual(self.m['target_status'],'PINNED_READONLY_NOT_EXECUTION_APPROVED');self.assertFalse(self.m['execution_approved']);self.assertFalse(self.m['launchable'])
 def test_no_mutable_fallback_or_dispatch_acceptance_claim(self):
  self.assertFalse(self.m['mutable_branch_fallback']);self.assertEqual(self.m['ref_mode'],'EXACT_IMMUTABLE_COMMIT_ONLY');self.assertEqual(self.m['immutable_ref_dispatch_acceptance'],'IMMUTABLE_REF_DISPATCH_ACCEPTANCE_UNVERIFIED');self.assertEqual(self.e['run_provenance_by_HMAC'],'NOT_PROVEN')
 def test_historical_only_e2e(self):
  self.assertEqual(self.e['historical_e2e']['run'],36153932146);self.assertEqual(self.e['historical_e2e']['new_uploads'],0);self.assertEqual(self.e['historical_e2e']['classification'],'HISTORICAL_ONLY_NOT_NEW_CANDIDATE_LIVE_E2E');self.assertEqual(self.e['OAuth'],'HISTORICALLY_CONFIRMED / CURRENTLY_UNVERIFIED')
 def test_old_unverified_manifest_unchanged(self):
  old=read('readiness/runtime-composition-target-manifest.json');self.assertEqual(old['approval_status'],'CURRENT_PRODUCTION_TARGET_UNVERIFIED');self.assertIsNone(old['required_commit_sha']);self.assertFalse(old['launchable'])
 def test_plan_get_allowlist_and_zero_side_effect_routes(self):
  for n,r in enumerate(self.p['allowed_requests'],1):self.assertTrue(remote.allowed_request(r['method'],r['path'],n))
  self.assertFalse(remote.allowed_request('POST',remote.ENDPOINTS[0],1));self.assertFalse(remote.allowed_request('GET',remote.ENDPOINTS[0],5));self.assertFalse(remote.allowed_request('GET','/accounts/'+remote.ACCOUNT+'/d1/database/'+remote.DB,1))
  for key in ('maximum_writes','maximum_D1_requests','maximum_deploys','maximum_dispatches','maximum_uploads','maximum_YouTube_calls','retry','resume','redirect','pagination_fallback','raw_retention'):self.assertEqual(self.p[key],0)
 def test_secret_value_property_never_accessed_or_retained(self):
  class NoSecret(dict):
   def get(self,k,*args):
    if k in ('value','text','material','secret'):raise AssertionError('SECRET_VALUE_READ')
    return super().get(k,*args)
  out=remote.metadata_only_bindings([NoSecret(type='secret_text',name='PLM_YOUTUBE_CHECKPOINT_KEY',value='DO_NOT_READ'),NoSecret(type='d1',name='DB',id=remote.DB)])
  self.assertTrue(out['db_binding_exact']);self.assertFalse(out['secret_values_accessed']);self.assertNotIn('DO_NOT_READ',json.dumps(out))
 def test_source_multipart_not_falsely_equal(self):
  self.assertEqual(remote.source_comparison(remote.BUNDLE_SHA,remote.BUNDLE_SHA,False),'UNVERIFIED_SOURCE_REPRESENTATION');self.assertEqual(remote.source_comparison(remote.BUNDLE_SHA,remote.BUNDLE_SHA,True),'YES')
 def test_visibility_and_active_classifications(self):
  self.assertEqual(remote.classify({'active':True}),'STOP_UNEXPECTED_ACTIVE_RUNTIME');self.assertEqual(remote.classify({}),'BLOCKED_REMOTE_VISIBILITY')
  x=dict.fromkeys(('exists','source_representation_proven','routes_complete','cron_complete','consumers_complete','binding_exact','parked_proven'),True);x.update(cron_count=0,consumer_count=0,route_count=0,candidate_equal='YES');self.assertEqual(remote.classify(x),'REMOTE_EXACT_PARKED');x['candidate_equal']='NO';x['known_old_parked_source']=True;self.assertEqual(remote.classify(x),'REMOTE_PARKED_OLD_SOURCE_DEPLOY_PREPARATION_REQUIRED');x['routes_complete']=False;self.assertEqual(remote.classify(x),'BLOCKED_REMOTE_VISIBILITY')
 def test_unknown_zone_quota_key_permissions_not_promoted(self):
  self.assertIsNone(self.p['routes']['zone_id']);self.assertEqual(self.p['routes']['requests'],0);self.assertEqual(self.p['quota']['status'],'UNVERIFIED_PERMISSION_LIMIT');self.assertIn('UNVERIFIED_PERMISSION_LIMIT',self.p['secret_key_readiness']);self.assertFalse(self.p['http_executor_created']);self.assertFalse(self.p['workflow_created']);self.assertFalse(self.p['launchable'])
 def test_marker_absent_and_independent_identity(self):
  self.assertEqual(self.p['identity'],remote.ID);self.assertEqual(self.p['marker']['state'],'NOT_CREATED / NOT_CONSUMED');self.assertTrue(not (ROOT/self.p['marker']['path']).exists() or hashlib.sha256((ROOT/self.p['marker']['path']).read_bytes()).hexdigest()=='9b44a5b5b604403679369334bfaec4ac4a40270ab9113b051e410f80eb4acb5f');self.assertFalse(self.p['marker']['identity_reuse']);self.assertEqual(hashlib.sha256((ROOT/self.p['marker']['schema_path']).read_bytes()).hexdigest(),self.p['marker']['schema_sha256']);self.assertIn('workflow_sha256',read(self.p['marker']['schema_path'])['required'])
 def test_helper_hash_and_no_network_entrypoint(self):
  b=(ROOT/self.p['helper']).read_bytes();self.assertEqual(hashlib.sha256(b).hexdigest(),self.p['helper_sha256']);self.assertNotIn(b'import http',b);self.assertNotIn(b'import os',b);self.assertNotIn(b'urllib',b)
if __name__=='__main__':unittest.main()
