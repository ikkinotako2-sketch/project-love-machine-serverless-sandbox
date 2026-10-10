import ast,contextlib,io,json,unittest
from pathlib import Path
from unittest.mock import patch,Mock
from oracle_bridge import require_guard
require_guard()
import provider_neutral_0008_backend_token_verify as p
ROOT=Path(__file__).resolve().parents[1]
NOW=1791590400
EXP='2026-10-12T00:00:00Z'
def valid():return {'success':True,'result':{'id':'a'*32,'status':'active','expires_on':EXP},'unwanted':'secret-fixture'}
class VerifyTests(unittest.TestCase):
 def execute(self,status=200,payload=None,raw=None):
  calls=[]
  def send(*args):calls.append(args);return status,raw if raw is not None else json.dumps(valid() if payload is None else payload).encode()
  out=p.verify(send,NOW);self.assertEqual(calls,[('GET',p.VERIFY,None)]);self.assertEqual(out['cloudflare_calls'],1);self.assertEqual(out['d1_calls'],0);self.assertEqual(out['d1_writes'],0);return out
 def test_identity_parent(self):
  self.assertEqual(p.IDENTITY,'provider-neutral-0008-backend-token-verify-20261010-r1');self.assertEqual(p.PARENT,'a0097ad228cafa24b78c715965caef4dd8353c67')
 def test_success(self):
  out=self.execute();self.assertTrue(out['pass']);self.assertEqual(out['result'],'BACKEND_TOKEN_VERIFY_SUCCESS_STOP');self.assertEqual(out['token_id'],'a'*32);self.assertEqual(out['http_status'],200);self.assertFalse(out['scope_api_independently_verified'])
 def test_401(self):self.assertEqual(self.execute(401,raw=b'bad')['result'],'HTTP_401_STOP')
 def test_403(self):self.assertEqual(self.execute(403,raw=b'bad')['result'],'HTTP_403_STOP')
 def test_429(self):self.assertEqual(self.execute(429,raw=b'bad')['result'],'HTTP_429_STOP')
 def test_other_status(self):
  for status in (400,404,302,500,503,599):self.assertEqual(self.execute(status,raw=b'bad')['result'],'HTTP_'+str(status)+'_STOP')
 def test_codes_only(self):
  out=self.execute(401,payload={'success':False,'errors':[{'code':i,'message':'secret-fixture'} for i in range(12)]+[{'code':True},{'code':'10'}],'Authorization':'Bearer secret-fixture','email':'secret-fixture','ip':'secret-fixture'})
  self.assertEqual(out['cloudflare_error_codes'],list(range(8)));self.assertNotIn('secret-fixture',json.dumps(out));self.assertNotIn('Authorization',json.dumps(out))
 def test_nonjson(self):
  out=self.execute(403,raw=b'<html>secret-fixture</html>');self.assertEqual(out['cloudflare_error_codes'],[]);self.assertNotIn('secret-fixture',json.dumps(out))
 def test_oversize_error(self):
  out=self.execute(401,raw=b'x'*32769);self.assertEqual(out['error_body_status'],'OVERSIZE_NOT_RETAINED');self.assertEqual(out['http_status'],401)
 def test_expired(self):
  v=valid();v['result']['expires_on']='2020-01-01T00:00:00Z';self.assertFalse(self.execute(payload=v)['pass'])
 def test_finite_timezone_expiry(self):
  for value in (None,'','infinity','2026-10-12T00:00:00'):
   v=valid();v['result']['expires_on']=value;self.assertFalse(self.execute(payload=v)['pass'])
 def test_inactive(self):
  v=valid();v['result']['status']='inactive';self.assertEqual(self.execute(payload=v)['result'],'TOKEN_INACTIVE_STOP')
 def test_bad_id(self):
  for value in (None,'a'*31,'A'*32,123,'g'*32):
   v=valid();v['result']['id']=value;self.assertEqual(self.execute(payload=v)['result'],'TOKEN_ID_INVALID_STOP')
 def test_envelope(self):
  v=valid();v['success']=False;self.assertFalse(self.execute(payload=v)['pass'])
 def test_duplicate_json_and_success_size(self):
  for raw in (b'{"success":true,"success":true}',b'x'*262145):self.assertFalse(self.execute(raw=raw)['pass'])
 def test_gate_second_send(self):
  transport=Mock(return_value=(200,json.dumps(valid()).encode()));gate=p.Gate(transport);gate.call()
  with self.assertRaisesRegex(p.Stop,'SECOND_SEND_FORBIDDEN_STOP'):gate.call()
  transport.assert_called_once()
 def test_url_method_allowlist(self):
  for method,path,body in [('GET','/accounts/'+p.ACCOUNT+'/d1/database',None),('POST',p.VERIFY,None),('GET',p.VERIFY+'?x=1',None),('GET','/user/tokens/verify',None),('GET',p.VERIFY,{})]:
   transport=Mock();gate=p.Gate(transport)
   with self.assertRaises(p.Stop):gate.call(method,path,body)
   transport.assert_not_called();self.assertEqual(gate.count,0)
 def test_live_transport_single_and_exact(self):
  with patch.object(p,'bounded_http',return_value=(200,b'{}')) as http:
   send=p.live_transport('fixture');send('GET',p.VERIFY)
   with self.assertRaises(p.Stop):send('GET',p.VERIFY)
   http.assert_called_once_with('fixture')
 def test_live_transport_rejects_d1(self):
  with patch.object(p,'bounded_http') as http:
   send=p.live_transport('fixture')
   with self.assertRaises(p.Stop):send('GET','/accounts/'+p.ACCOUNT+'/d1/database')
   http.assert_not_called()
 def test_missing_secret(self):
  for value in (None,'',' ','bad\nvalue'):
   with self.assertRaisesRegex(p.Stop,'BACKEND_CREDENTIAL_MISSING_STOP'):p.live_transport(value)
 def test_main_missing_and_attempt(self):
  env={'GITHUB_REPOSITORY':p.REPO,'GITHUB_REF':'refs/heads/'+p.BRANCH,'GITHUB_EVENT_NAME':'push','GITHUB_RUN_ATTEMPT':'1',**{k:'true' for k in ('TEST_ONLY','DRY_RUN','NO_PUBLISH','EMERGENCY_STOP')}}
  for change,code in [({},'BACKEND_CREDENTIAL_MISSING_STOP'),({'GITHUB_RUN_ATTEMPT':'2'},'EXECUTION_CONTEXT_STOP')]:
   output=io.StringIO()
   with patch.dict('os.environ',dict(env,**change),clear=True),patch.object(p,'bounded_http') as http,contextlib.redirect_stdout(output):p.main()
   self.assertEqual(json.loads(output.getvalue())['gate_code'],code);http.assert_not_called()
 def test_timeout_no_retry(self):
  transport=Mock(side_effect=TimeoutError('secret-fixture'));out=p.verify(transport,NOW);self.assertEqual(out['result'],'TRANSPORT_UNKNOWN_NO_RETRY');self.assertNotIn('secret-fixture',json.dumps(out));transport.assert_called_once()
 def test_transport_bound_and_no_logs(self):
  for length,body,state in [('32769',b'','OVERSIZE_NOT_RETAINED'),(None,b'x'*32769,'OVERSIZE_NOT_RETAINED'),(None,b'{"success":false,"errors":[{"code":1000,"message":"secret-fixture"}]}','PARSED_CODES_ONLY')]:
   response=Mock(status=401);response.getheader.return_value=length;response.read.return_value=body;conn=Mock();conn.getresponse.return_value=response;stdout=io.StringIO()
   with patch('http.client.HTTPSConnection',return_value=conn) as connection,contextlib.redirect_stdout(stdout):
    with self.assertRaises(p.HTTPFailure) as error:p.bounded_http('token-fixture')
   connection.assert_called_once_with('api.cloudflare.com',timeout=15);conn.request.assert_called_once_with('GET','/client/v4'+p.VERIFY,headers={'Authorization':'Bearer token-fixture'});conn.close.assert_called_once();self.assertEqual(stdout.getvalue(),'');self.assertEqual(error.exception.metadata['error_body_status'],state);self.assertNotIn('fixture',str(error.exception.metadata))
   if length is None:response.read.assert_called_once_with(32769)
   else:response.read.assert_not_called()
 def test_marker_binding_and_consumed_rejection(self):
  files={x:(ROOT/x).read_bytes() for x in (p.PLAN,p.WORKFLOW,p.HELPER,p.SCHEMA)};plan=json.loads(files[p.PLAN]);before='a'*40
  marker={'identity':p.IDENTITY,'state':'CONSUMED_BEFORE_REMOTE','prepared_commit_sha':before,**{k:p.sha(files[path]) for k,path in [('workflow_sha256',p.WORKFLOW),('helper_sha256',p.HELPER),('plan_sha256',p.PLAN)]}}
  p.marker_check(marker,plan,before,files)
  for identity in plan['consumed_preflight_identities_forbidden']+['004H']:
   with self.assertRaises(p.Stop):p.marker_check(dict(marker,identity=identity),plan,before,files)
  with self.assertRaises(p.Stop):p.marker_check(dict(marker,helper_sha256='0'*64),plan,before,files)
 def test_marker_only_trigger(self):
  w=(ROOT/p.WORKFLOW).read_text();self.assertIn(p.MARKER,w);self.assertIn(p.MESSAGE,w);self.assertIn('github.run_attempt == 1',w);self.assertIn("git('diff','--name-only',before,'HEAD')==MARKER",w);self.assertIn("git('rev-parse',before+'^')==PARENT",w);self.assertNotIn('workflow_dispatch',w);self.assertNotIn('PLM_HISTORY',w);self.assertNotIn('PLM_CF_D1_READ_TOKEN',w);self.assertNotIn('upload-artifact',w);self.assertFalse((ROOT/p.MARKER).exists())
 def test_no_other_clients_or_operations(self):
  s=(ROOT/p.HELPER).read_text()
  for forbidden in ('/d1/','/workers/','youtube.com','api.github.com','sqlite3','fetch_history','/query','/import'):self.assertNotIn(forbidden,s)
  self.assertEqual(p.LIMITS['maximum_cloudflare_calls'],1)
  for k in ('d1_calls','maximum_writes','github_history_calls','worker_calls','youtube_calls','retry','rerun','resume','resend','fallback','redirect','automatic_rollback','raw_retention'):self.assertEqual(p.LIMITS[k],0)
 def test_diagnostic_unchanged_from_r4(self):
  old=(ROOT/'readiness/provider_neutral_0008_fresh_preflight_r4.py').read_text();new=(ROOT/p.HELPER).read_text()
  def funcs(s):return {n.name:ast.get_source_segment(s,n) for n in ast.parse(s).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
  a,b=funcs(old),funcs(new)
  for name in ('error_diagnostic','HTTPFailure','expiry','decode'):self.assertEqual(a[name],b[name])
 def test_expiry_checked_after_response(self):
  transport=Mock(return_value=(200,json.dumps(valid()).encode()));out=p.verify(transport,NOW,clock=lambda:NOW+86400*7);self.assertFalse(out['pass']);self.assertEqual(out['cloudflare_calls'],1)
if __name__=='__main__':unittest.main()
