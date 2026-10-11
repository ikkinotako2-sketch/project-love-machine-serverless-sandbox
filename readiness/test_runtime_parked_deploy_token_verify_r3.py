import copy,json,unittest
from pathlib import Path
from datetime import datetime,timezone
from unittest.mock import patch
try:
 from readiness import runtime_parked_deploy_token_verify_r3 as v
except ModuleNotFoundError:
 import runtime_parked_deploy_token_verify_r3 as v
ROOT=Path(__file__).resolve().parents[1];NOW=datetime(2026,10,11,tzinfo=timezone.utc)
def raw(r,**kw):return json.dumps({'success':True,'result':r,**kw}).encode()
class Fake:
 def __init__(self,verify_response=None,source=None):
  self.budget=v.RequestBudget();self.calls=[];self.responses=[verify_response or (200,raw({'status':'active','expires_on':'2026-10-17T23:59:59+00:00','id':'NOT_FOR_OUTPUT','creator':'PRIVATE_TEXT'}),{}),source or (200,(ROOT/v.BOOTSTRAP).read_bytes(),{'content_type':'application/javascript+module'})]
 def verified(self,c):self.budget.verified(c)
 def __call__(self,method,path):
  self.budget.admit(method,path);self.calls.append((method,path));r=self.responses[len(self.calls)-1]
  if isinstance(r,Exception):raise r
  return r
class TokenVerifyTests(unittest.TestCase):
 def runit(self,**kw):t=Fake(**kw);return v.inspect(t,NOW),t
 def fixture(self):
  files={p:(ROOT/p).read_bytes() for p in v.PINS.values()};before='a'*40;after='b'*40
  marker={k:v.sha(files[p]) for k,p in v.PINS.items()};marker.update(identity=v.IDENTITY,state='CONSUMED_BEFORE_REMOTE',prepared_commit_sha=before)
  env={'GITHUB_REPOSITORY':v.REPO,'GITHUB_REF':v.BRANCH,'GITHUB_EVENT_NAME':'push','GITHUB_RUN_ATTEMPT':'1','GITHUB_SHA':after,**v.FLAGS};event={'before':before,'after':after,'head_commit':{'id':after,'message':v.MESSAGE},'commits':[{}]}
  facts={'full_history':True,'root':v.PARENT,'count':1,'preparation_files':json.loads((ROOT/v.PLAN).read_bytes())['preparation_files'],'head':after,'parent':before,'files':[v.MARKER],'message':v.MESSAGE,'marker_preexisted':False,'deploy_marker_absent_root':True,'deploy_marker_absent_prepared':True,'deploy_marker_absent_head':True,'deploy_marker_absent_worktree':True,'r2_marker_hashes':{k:v.R2_HASH for k in ('root','prepared','head')},'deploy_ancestor':v.DEPLOY_PREPARED,'r1_marker_hashes':{k:v.R1_HASH for k in ('root','prepared','head')},'deploy_root_hashes':{p:v.IMMUTABLE[p] for p in (v.DEPLOY_PLAN,v.DEPLOY_EXECUTOR)}}
  return [env,event,facts,marker,files]
 def test_gate_pass(self):v.validate_gate(*self.fixture())
 def test_current_exact_dependencies(self):
  for p,h in v.IMMUTABLE.items():self.assertEqual(v.sha((ROOT/p).read_bytes()),h)
 def test_marker_both_absent(self):self.assertFalse((ROOT/v.MARKER).exists());self.assertFalse((ROOT/v.DEPLOY_MARKER).exists())
 def test_identity_independent(self):self.assertNotEqual(v.MARKER,v.DEPLOY_MARKER);self.assertIn('token-verify',v.IDENTITY)
 def test_missing_token_remote0(self):
  with patch.object(v,'load_gate'),patch.dict('os.environ',{v.SECRET:''}),patch('builtins.print') as p:v.main();o=json.loads(p.call_args[0][0]);self.assertEqual(o['requests_attempted'],0);self.assertEqual(o['reason_codes'],['DEPLOY_TOKEN_MISSING_STOP'])
 def test_active_exact_source_PASS(self):
  o,t=self.runit();self.assertEqual(o['classification'],'DEPLOY_TOKEN_ACTIVE_TARGET_READ_CONFIRMED');self.assertEqual(t.calls,[('GET',p) for p in v.GETS]);self.assertTrue(o['credential_active']);self.assertTrue(o['target_worker_read_verified']);self.assertFalse(o['source_drift'])
 def test_scope_claim_not_api_proven(self):
  o,_=self.runit();self.assertEqual(o['scope_attestation'],'OWNER_ATTESTED_SPECIFIED_WORKER_EDITOR');self.assertFalse(o['scope_api_verified']);self.assertFalse(o['write_capability_remote_tested']);self.assertFalse(o['deploy_authorized'])
 def test_disabled_get2_zero(self):o,t=self.runit(verify_response=(200,raw({'status':'disabled'}),{}));self.assertEqual(len(t.calls),1);self.assertFalse(o['credential_active'])
 def test_expired_get2_zero(self):o,t=self.runit(verify_response=(200,raw({'status':'active','expires_on':'2026-10-10T00:00:00Z'}),{}));self.assertEqual(len(t.calls),1);self.assertIn('TOKEN_EXPIRED_STOP',o['reason_codes'])
 def test_401_get2_zero(self):o,t=self.runit(verify_response=(401,b'PRIVATE_TEXT',{}));self.assertEqual(len(t.calls),1);self.assertEqual(o['classification'],'DEPLOY_TOKEN_VERIFY_BLOCKED')
 def test_403_get2_zero(self):o,t=self.runit(verify_response=(403,b'PRIVATE_TEXT',{}));self.assertEqual(len(t.calls),1)
 def test_timeout_no_retry(self):o,t=self.runit(verify_response=TimeoutError('PRIVATE_TEXT'));self.assertEqual(len(t.calls),1);self.assertNotIn('PRIVATE_TEXT',json.dumps(o));self.assertEqual(o['retry'],0)
 def test_redirect_no_follow(self):o,t=self.runit(verify_response=(302,b'',{}));self.assertEqual(len(t.calls),1);self.assertEqual(o['redirect'],0)
 def test_malformed_verify_STOP(self):
  for b in [b'bad',b'[]',raw({}),raw({'status':True}),b'{"success":false,"result":{"status":"active"}}',b'{"success":true,"result":{"status":"active","status":"active"}}']:
   o,t=self.runit(verify_response=(200,b,{}));self.assertEqual(len(t.calls),1);self.assertFalse(o['credential_active'])
 def test_invalid_expiry_STOP(self):
  for val in [None,42,'no','2026-10-17T23:59:59','2026-99-17T23:59:59Z']:
   o,t=self.runit(verify_response=(200,raw({'status':'active','expires_on':val}),{}));self.assertEqual(len(t.calls),1)
 def test_absent_expiry_allowed_not_claimed_finite(self):o,t=self.runit(verify_response=(200,raw({'status':'active'}),{}));self.assertEqual(len(t.calls),2);self.assertNotIn('expires_on',o)
 def test_not_before_future_STOP(self):o,t=self.runit(verify_response=(200,raw({'status':'active','not_before':'2026-10-12T00:00:00Z'}),{}));self.assertEqual(len(t.calls),1)
 def test_not_before_past_report_exact(self):o,t=self.runit(verify_response=(200,raw({'status':'active','not_before':'2026-10-10T00:00:00Z'}),{}));self.assertEqual(o['not_before'],'2026-10-10T00:00:00Z')
 def test_source_mismatch_not_credential_failure(self):
  o,t=self.runit(source=(200,b'export default {};',{'content_type':'application/javascript'}));self.assertEqual(o['classification'],'SOURCE_DRIFT_STOP_BEFORE_DEPLOY');self.assertTrue(o['credential_active']);self.assertTrue(o['target_worker_read']);self.assertTrue(o['source_drift'])
 def test_source_unparseable_STOP(self):o,t=self.runit(source=(200,b'PRIVATE_TEXT',{'content_type':'text/plain'}));self.assertEqual(o['classification'],'SOURCE_REPRESENTATION_UNVERIFIED_STOP');self.assertNotIn('PRIVATE_TEXT',json.dumps(o))
 def test_target_denied(self):o,t=self.runit(source=(403,b'PRIVATE_TEXT',{}));self.assertEqual(o['classification'],'DEPLOY_TOKEN_TARGET_READ_BLOCKED');self.assertTrue(o['credential_active']);self.assertFalse(o['target_worker_read_verified'])
 def test_target_timeout_no_retry(self):o,t=self.runit(source=TimeoutError('PRIVATE_TEXT'));self.assertEqual(o['classification'],'DEPLOY_TOKEN_TARGET_READ_BLOCKED');self.assertEqual(len(t.calls),2);self.assertEqual(o['retry'],0)
 def test_token_ID_private_fields_raw_never_logged(self):
  o,_=self.runit();s=json.dumps(o)
  for x in ['NOT_FOR_OUTPUT','PRIVATE_TEXT','Authorization','Bearer','source_response_sha256','source_response_bytes']:self.assertNotIn(x,s)
  self.assertEqual(o['raw_retention'],0);self.assertEqual(o['secret_exposure'],0)
 def test_numeric_errors_only(self):
  b=b'{"errors":[{"code":10000,"message":"PRIVATE_TEXT"},{"code":"PRIVATE_TEXT"},{"code":true}]}';o,t=self.runit(verify_response=(403,b,{}));self.assertEqual(o['cloudflare_error_codes'],[10000]);self.assertNotIn('PRIVATE_TEXT',json.dumps(o))
 def test_oversize_verify_GET2_zero(self):o,t=self.runit(verify_response=(200,b'x'*(v.MAX+1),{}));self.assertEqual(len(t.calls),1)
 def test_exact_2_GET_max(self):
  o,t=self.runit()
  for m,p in [('GET',v.GETS[0]),('GET',v.GETS[1]),('PUT',v.GETS[1]),('POST',v.GETS[0]),('DELETE',v.GETS[0])]:self.assertRaises(v.Stop,t.budget.admit,m,p)
 def test_order_and_unrelated_resources_rejected(self):
  for p in [v.GETS[1],v.GETS[0].replace(v.ACCOUNT,'a'*32),'/accounts/'+v.ACCOUNT+'/d1/database','/accounts/'+v.ACCOUNT+'/workers/scripts/other/content/v2']:self.assertRaises(v.Stop,v.RequestBudget().admit,'GET',p)
 def test_GET2_requires_active_proof(self):b=v.RequestBudget();b.admit('GET',v.GETS[0]);self.assertRaises(v.Stop,b.admit,'GET',v.GETS[1])
 def test_transport_requires_gate(self):self.assertRaises(v.Stop,v.AuthorizedTransport,'TEST_SENTINEL')
 def test_gate_failure_before_transport(self):
  with patch.object(v,'load_gate',side_effect=v.Stop('GATE_STOP')),patch.object(v,'AuthorizedTransport') as t,patch('builtins.print') as p:v.main();t.assert_not_called();self.assertEqual(json.loads(p.call_args[0][0])['requests_attempted'],0)
 def test_deploy_marker_anywhere_blocks(self):
  for k in ('deploy_marker_absent_root','deploy_marker_absent_prepared','deploy_marker_absent_head','deploy_marker_absent_worktree'):a=self.fixture();a[2][k]=False;self.assertRaises(v.Stop,v.validate_gate,*a)
 def test_deploy_dependency_commit_hash_drift_rejected(self):a=self.fixture();a[2]['deploy_root_hashes'][v.DEPLOY_PLAN]='wrong';self.assertRaises(v.Stop,v.validate_gate,*a)
 def test_source_dependency_drift_rejected(self):
  for p in v.PINS.values():a=self.fixture();a[4][p]+=b' ';self.assertRaises(v.Stop,v.validate_gate,*a)
 def test_consumed_identity_attempt2_rejected(self):
  a=self.fixture();a[2]['marker_preexisted']=True;self.assertRaises(v.Stop,v.validate_gate,*a)
  a=self.fixture();a[0]['GITHUB_RUN_ATTEMPT']='2';self.assertRaises(v.Stop,v.validate_gate,*a)
 def test_deploy_identity_cannot_verify(self):a=self.fixture();a[3]['identity']='provider-neutral-runtime-parked-deploy-20261011-r1';self.assertRaises(v.Stop,v.validate_gate,*a)
 def test_marker_only_and_history_required(self):
  for k,val in [('full_history',False),('root','wrong'),('files',[v.MARKER,v.DEPLOY_MARKER]),('count',0)]:a=self.fixture();a[2][k]=val;self.assertRaises(v.Stop,v.validate_gate,*a)
 def test_workflow_credentials_only_after_gate(self):
  s=(ROOT/v.WORKFLOW).read_text();self.assertIn('fetch-depth: 0',s);self.assertIn('persist-credentials: false',s);self.assertIn('contents: read',s);self.assertLess(s.index('load_gate()'),s.index('secrets.PLM_CF_WORKER_DEPLOY_TOKEN'));self.assertNotIn('PLM_CF_WORKER_API_TOKEN',s);self.assertNotIn('workflow_dispatch',s);self.assertNotIn(v.DEPLOY_MARKER,s)
 def test_all_forbidden_effects_zero(self):
  o,_=self.runit()
  for k in v.ZERO_KEYS:self.assertEqual(o[k],0)
  self.assertFalse(o['deploy_identity_consumed'])
 def test_shallow_git_rejected(self):self.assertRaises(v.Stop,v.collect_git_facts,'a'*40,lambda *a:'true',lambda _:False)
 def test_plan_request_budget_tamper_rejected(self):
  a=self.fixture();p=json.loads(a[4][v.PLAN]);p['maximum_GETs']=3;a[4][v.PLAN]=json.dumps(p).encode();a[3]['plan_sha256']=v.sha(a[4][v.PLAN]);self.assertRaises(v.Stop,v.validate_gate,*a)
 def test_transport_exact_secret_role_and_no_secret_output(self):
  class Socket:
   def settimeout(self,x):pass
  class Response:
   status=200
   def __init__(self,body,ctype):self.body=body;self.ctype=ctype
   def read1(self,n):b=self.body[:n];self.body=self.body[n:];return b
   def getheader(self,k):return self.ctype if k=='Content-Type' else None
  calls=[]
  class Connection:
   def __init__(self,host,timeout):self.sock=Socket();self.i=len(calls);self.host=host
   def connect(self):pass
   def request(self,m,p,headers):calls.append((self.host,m,p,headers))
   def getresponse(self):return Response(raw({'status':'active'}),'application/json') if self.i==0 else Response((ROOT/v.BOOTSTRAP).read_bytes(),'application/javascript+module')
   def close(self):pass
  with patch('http.client.HTTPSConnection',Connection):o=v.inspect(v.AuthorizedTransport('OFFLINE_TEST_SENTINEL',v._CAPABILITY),NOW)
  self.assertEqual(o['classification'],'DEPLOY_TOKEN_ACTIVE_TARGET_READ_CONFIRMED');self.assertEqual(len(calls),2)
  self.assertTrue(all(c[0]=='api.cloudflare.com' and c[1]=='GET' and c[3]['Authorization']=='Bearer OFFLINE_TEST_SENTINEL' for c in calls));self.assertNotIn('OFFLINE_TEST_SENTINEL',json.dumps(o))
 def test_full_history_fixture_gate(self):
  a=self.fixture();mapping={('rev-parse','--is-shallow-repository'):'false',('merge-base',v.PARENT,'a'*40):v.PARENT,('rev-list','--count',v.PARENT+'..'+'a'*40):'1',('diff','--name-only',v.PARENT,'a'*40):'\n'.join(json.loads((ROOT/v.PLAN).read_bytes())['preparation_files']),('rev-parse','HEAD'):'b'*40,('rev-parse','HEAD^'):'a'*40,('diff','--name-only','a'*40,'HEAD'):v.MARKER,('log','-1','--format=%B'):v.MESSAGE}
  mapping[('merge-base',v.DEPLOY_PREPARED,v.PARENT)]=v.DEPLOY_PREPARED
  for c in (v.PARENT,'a'*40,'HEAD'):
   mapping[('show',c+':'+v.R1_MARKER)]=(ROOT/v.R1_MARKER).read_text();mapping[('show',c+':'+v.R2_MARKER)]=(ROOT/v.R2_MARKER).read_text()
  for p in (v.DEPLOY_PLAN,v.DEPLOY_EXECUTOR):mapping[('show',v.DEPLOY_PREPARED+':'+p)]=(ROOT/p).read_text()
  a[2]=v.collect_git_facts('a'*40,lambda *args:mapping[args],lambda _:False);v.validate_gate(*a)
 def test_r1_identity_rejected(self):
  a=self.fixture();a[3]['identity']='provider-neutral-runtime-parked-deploy-token-verify-20261011-r1';self.assertRaises(v.Stop,v.validate_gate,*a)
 def test_r1_marker_immutable(self):
  self.assertEqual(v.sha((ROOT/v.R1_MARKER).read_bytes()),v.R1_HASH)
  for k in ('root','prepared','head'):
   a=self.fixture();a[2]['r1_marker_hashes'][k]='wrong';self.assertRaises(v.Stop,v.validate_gate,*a)
 def test_deploy_prepared_ancestor_required(self):
  a=self.fixture();a[2]['deploy_ancestor']='wrong';self.assertRaises(v.Stop,v.validate_gate,*a)
 def test_r2_identity_exact(self):self.assertEqual(v.IDENTITY,'provider-neutral-runtime-parked-deploy-token-verify-20261011-r3')
 def plan_fixture(self,transform):
  a=self.fixture();p=json.loads(a[4][v.PLAN]);transform(p);a[4][v.PLAN]=json.dumps(p).encode();a[3]['plan_sha256']=v.sha(a[4][v.PLAN]);return a
 def test_r2_identity_rejected(self):
  a=self.fixture();a[3]['identity']='provider-neutral-runtime-parked-deploy-token-verify-20261011-r2';self.assertRaises(v.Stop,v.validate_gate,*a)
 def test_r2_marker_immutable(self):
  self.assertEqual(v.sha((ROOT/v.R2_MARKER).read_bytes()),v.R2_HASH)
  for k in ('root','prepared','head'):
   a=self.fixture();a[2]['r2_marker_hashes'][k]='wrong';self.assertRaises(v.Stop,v.validate_gate,*a)
 def test_exact_plan_preparation_list_PASS(self):v.validate_gate(*self.fixture())
 def test_omitted_plan_file_STOP(self):self.assertRaisesRegex(v.Stop,'PREPARATION_HISTORY_STOP',v.validate_gate,*self.plan_fixture(lambda p:p['preparation_files'].pop()))
 def test_extra_plan_file_STOP(self):self.assertRaisesRegex(v.Stop,'PREPARATION_HISTORY_STOP',v.validate_gate,*self.plan_fixture(lambda p:p['preparation_files'].append('readiness/test_runtime_parked_deploy_token_verify.py')))
 def test_extra_actual_file_STOP(self):
  a=self.fixture();a[2]['preparation_files'].append('unexpected');self.assertRaisesRegex(v.Stop,'PREPARATION_HISTORY_STOP',v.validate_gate,*a)
 def test_order_normalized(self):
  a=self.fixture();a[2]['preparation_files'].reverse();v.validate_gate(*a)
  a=self.plan_fixture(lambda p:p['preparation_files'].reverse());v.validate_gate(*a)
 def test_duplicate_plan_path_STOP(self):self.assertRaises(v.Stop,v.validate_gate,*self.plan_fixture(lambda p:p['preparation_files'].append(p['preparation_files'][0])))
 def test_absolute_traversal_and_marker_paths_STOP(self):
  for path in ['/tmp/file','../file','readiness/../file',v.MARKER,v.R1_MARKER,v.R2_MARKER,v.DEPLOY_MARKER]:
   a=self.plan_fixture(lambda p:p['preparation_files'].append(path));a[2]['preparation_files'].append(path);self.assertRaisesRegex(v.Stop,'PREPARATION_HISTORY_STOP',v.validate_gate,*a)
 def test_r2_seven_actual_six_plan_STOP(self):
  a=self.plan_fixture(lambda p:p['preparation_files'].remove('readiness/test_runtime_parked_deploy_token_verify_r2.py'))
  self.assertEqual(len(a[2]['preparation_files']),7);self.assertEqual(len(json.loads(a[4][v.PLAN])['preparation_files']),6)
  self.assertRaisesRegex(v.Stop,'PREPARATION_HISTORY_STOP',v.validate_gate,*a)
 def test_exact_one_preparation_commit_required(self):
  for count in (0,2,3):a=self.fixture();a[2]['count']=count;self.assertRaises(v.Stop,v.validate_gate,*a)
 def test_no_separate_exact_python_allowlist(self):self.assertFalse(hasattr(v,'PREPARATION_FILES'))
if __name__=='__main__':unittest.main()
