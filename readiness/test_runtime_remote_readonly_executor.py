"""Guarded offline fixtures only; no execution marker or provider calls."""
from oracle_bridge import require_guard
require_guard()
import contextlib,io,json,unittest
from pathlib import Path
from unittest.mock import patch
import runtime_remote_readonly_executor as e
ROOT=Path(__file__).resolve().parents[1]
def raw(x):return json.dumps({'success':True,**x}).encode()
def settings(bind=None,**kw):return raw({'result':{'bindings':bind or [{'type':'d1','name':'DB','id':e.DB}],**kw}})
def schedules(n=0):return raw({'result':{'schedules':[{'cron':'* * * * *'}]*n}})
def queues(rows=None):
 rows=rows or [];return raw({'result':rows,'result_info':{'page':1,'per_page':100,'count':len(rows),'total_count':len(rows),'total_pages':1}})
def multipart(body,name='runtime-bundle.mjs'):
 return b'--safe\r\nContent-Disposition: form-data; name="metadata"\r\nContent-Type: application/json\r\n\r\n'+json.dumps({'main_module':name}).encode()+b'\r\n--safe\r\nContent-Disposition: form-data; name="'+name.encode()+b'"; filename="'+name.encode()+b'"\r\nContent-Type: application/javascript+module\r\n\r\n'+body+b'\r\n--safe--\r\n'
def fixtures():
 p=json.loads((ROOT/e.PLAN).read_bytes());paths=set(e.PIN_FILES.values())|{e.SCHEMA,'serverless/youtube-connection/runtime-bundle.mjs','serverless/youtube-connection/runtime.mjs'}|set(p['known_old_parked_source_files']);files={f:(ROOT/f).read_bytes() for f in paths};before='a'*40;after='b'*40
 env={k:'true' for k in ('TEST_ONLY','DRY_RUN','NO_PUBLISH','EMERGENCY_STOP')};env.update(GITHUB_REPOSITORY=e.REPO,GITHUB_REF=e.BRANCH,GITHUB_EVENT_NAME='push',GITHUB_RUN_ATTEMPT='1',GITHUB_SHA=after)
 event={'before':before,'after':after,'head_commit':{'id':after,'message':e.MESSAGE},'commits':[{'id':after}]};facts={'head':after,'parent':before,'prepared_parent':e.PARENT,'files':[e.MARKER],'marker_preexisted':False,'message':e.MESSAGE};marker={k:e.sha(files[path]) for k,path in e.PIN_FILES.items()};marker.update(identity=e.IDENTITY,state='CONSUMED_BEFORE_REMOTE',prepared_commit_sha=before,candidate_bundle_sha256=e.BUNDLE,candidate_runtime_source_sha256=e.SOURCE)
 return env,event,facts,marker,p,files
class ExecutorTests(unittest.TestCase):
 def inspect(self,status=200,bodies=None,meta=None):
  bodies=bodies or [(ROOT/'serverless/youtube-connection/runtime-bundle.mjs').read_bytes(),settings(),schedules(),queues()];seen=[]
  def t(method,path):
   seen.append((method,path));i=len(seen)-1;return (status if i==0 else 200),bodies[i],(meta or {'content_type':'application/javascript'}) if i==0 else {}
  out=e.inspect(t,set());return out,seen
 def test_exact_four_gets_no_activation(self):
  out,seen=self.inspect();self.assertEqual(seen,[('GET',p) for p in e.ENDPOINTS]);self.assertEqual(out['requests_attempted'],4);self.assertTrue(out['read_complete']);self.assertEqual(out['candidate_equal'],'YES');self.assertTrue(out['binding_exact']);self.assertEqual(out['consumer_count'],0);self.assertEqual(out['classification'],'BLOCKED_REMOTE_VISIBILITY');self.assertFalse(out['routes_complete'])
 def test_gated_transport_cannot_construct_without_gate(self):
  with self.assertRaisesRegex(e.Stop,'ONE_SHOT_GATE_REQUIRED'):e.AuthorizedTransport('SYNTHETIC_NOT_LIVE')
 def test_valid_marker_gate_offline_only(self):e.validate_gate(*fixtures())
 def test_missing_credential_explicit_stop(self):
  with self.assertRaisesRegex(e.Stop,'CREDENTIAL_MISSING_STOP'):e.authorize_transport(*fixtures())
 def test_marker_absent_in_preparation(self):self.assertFalse((ROOT/e.MARKER).exists())
 def test_fifth_request_rejected(self):
  g=e.FourGet(lambda *_:(200,b'x',{}))
  for p in e.ENDPOINTS:g.get('GET',p)
  with self.assertRaises(e.Stop):g.get('GET',e.ENDPOINTS[0])
 def test_attempt_two_rejected(self):
  args=fixtures();args[0]['GITHUB_RUN_ATTEMPT']='2'
  with self.assertRaisesRegex(e.Stop,'EXECUTION_CONTEXT_STOP'):e.validate_gate(*args)
 def test_marker_only_exact_parent_and_no_intervening_commit(self):
  for key,value in [('prepared_parent','d'*40),('files',[e.MARKER,'other']),('parent','c'*40),('marker_preexisted',True)]:
   with self.subTest(key=key):
    args=fixtures();args[2][key]=value
    with self.assertRaisesRegex(e.Stop,'MARKER_ONLY_CHAIN_STOP'):e.validate_gate(*args)
 def test_prepared_commit_marker_drift(self):
  args=fixtures();args[3]['prepared_commit_sha']='c'*40
  with self.assertRaisesRegex(e.Stop,'MARKER_BINDING_STOP'):e.validate_gate(*args)
 def test_all_hash_drifts_stop(self):
  for key,path in e.PIN_FILES.items():
   with self.subTest(key=key):
    args=fixtures();args[5][path]+=b'\n'
    with self.assertRaisesRegex(e.Stop,'SOURCE_HASH_DRIFT_STOP'):e.validate_gate(*args)
 def test_candidate_source_drift(self):
  args=fixtures();args[5]['serverless/youtube-connection/runtime.mjs']+=b'\n'
  with self.assertRaisesRegex(e.Stop,'CANDIDATE_OR_SCHEMA_DRIFT_STOP'):e.validate_gate(*args)
 def test_retry_resume_redirect_fallback_plan_rejected(self):
  for k in ('retry','resume','redirect','fallback','pagination_fallback'):
   args=fixtures();args[4][k]=1
   with self.assertRaisesRegex(e.Stop,'PLAN_LIMITS_STOP'):e.validate_gate(*args)
 def test_non_get_and_all_unapproved_urls_rejected(self):
  for method,path in [('POST',e.ENDPOINTS[0]),('PUT',e.ENDPOINTS[0]),('PATCH',e.ENDPOINTS[0]),('DELETE',e.ENDPOINTS[0]),('GET',e.ENDPOINTS[0].replace(e.ACCOUNT,'0'*32)),('GET',e.ENDPOINTS[0].replace(e.WORKER,'other')),('GET','/accounts/'+e.ACCOUNT+'/d1/database/'+e.DB),('GET',e.PREFIX+'/secrets')]:
   calls=[];g=e.FourGet(lambda *a:calls.append(a))
   with self.assertRaises(e.Stop):g.get(method,path)
   self.assertEqual(calls,[])
 def test_status_403_permission_stop_without_later_requests(self):
  out,seen=self.inspect(403);self.assertEqual(len(seen),1);self.assertIn('UNVERIFIED_PERMISSION_LIMIT',out['reason_codes']);self.assertEqual(out['http_statuses'],[403])
 def test_404_worker_absent(self):
  out,_=self.inspect(404);self.assertFalse(out['worker_exists']);self.assertIn('WORKER_ABSENT_STOP',out['reason_codes'])
 def test_429_5xx_redirect_no_retry(self):
  for status in (429,500,503,302,307):
   out,seen=self.inspect(status);self.assertEqual(len(seen),1);self.assertEqual(out['http_statuses'],[status]);self.assertEqual(out['retry'],0)
 def test_oversize_stops_without_later_get(self):
  out,seen=self.inspect(bodies=[b'x'*(e.MAX+1),settings(),schedules(),queues()]);self.assertEqual(len(seen),1);self.assertIn('RESPONSE_BOUND_STOP',out['reason_codes'])
 def test_transport_timeout_stops_once(self):
  seen=[]
  def t(*a):seen.append(a);raise TimeoutError('NOT_RETAINED')
  out=e.inspect(t,set());self.assertEqual(len(seen),1);self.assertEqual(out['reason_codes'],['TRANSPORT_UNKNOWN_NO_RETRY']);self.assertNotIn('NOT_RETAINED',json.dumps(out))
 def test_exact_multipart_module_not_raw_response_hash(self):
  body=(ROOT/'serverless/youtube-connection/runtime-bundle.mjs').read_bytes();wire=multipart(body);out=e.source_metadata(wire,{'content_type':'multipart/form-data; boundary=safe'},set());self.assertNotEqual(e.sha(wire),e.BUNDLE);self.assertEqual(out['source_module_sha256'],e.BUNDLE);self.assertEqual(out['candidate_equal'],'YES')
 def test_unproven_representation_never_equal(self):
  for rawbody,meta in [(b'not-js',{'content_type':'text/plain'}),(multipart(b'x'),{'content_type':'multipart/form-data; boundary=wrong'})]:
   out=e.source_metadata(rawbody,meta,set());self.assertFalse(out['source_representation_proven']);self.assertEqual(out['candidate_equal'],'UNVERIFIED_SOURCE_REPRESENTATION')
 def test_hash_mismatch_does_not_make_known_old(self):
  out=e.source_metadata(b'export default {}',{'content_type':'application/javascript'},set());self.assertEqual(out['candidate_equal'],'NO');self.assertFalse(out['known_old_parked_source']);self.assertFalse(out['parked_proven'])
 def test_known_old_requires_positive_pinned_identity(self):
  plan=fixtures()[4];path=next(iter(plan['known_old_parked_source_files']));body=(ROOT/path).read_bytes();out=e.source_metadata(body,{'content_type':'application/javascript'},set(plan['known_old_parked_source_files'].values()));self.assertTrue(out['known_old_parked_source']);self.assertTrue(out['parked_proven'])
 def test_wrong_d1_binding_not_exact(self):self.assertFalse(e.settings_metadata(settings([{'type':'d1','name':'DB','id':'0'*36}]))['binding_exact'])
 def test_secret_material_properties_never_accessed(self):
  class Secret(dict):
   def get(self,k,*a):
    if k in ('value','text','secret','material'):raise AssertionError('SECRET_READ')
    return super().get(k,*a)
  data={'success':True,'result':{'bindings':[Secret(type='secret_text',name='PLM_YOUTUBE_CHECKPOINT_KEY',value='NOT_READ')]}}
  with patch.object(e,'envelope',return_value=data):
   with self.assertRaisesRegex(e.Stop,'SETTINGS_SHAPE_STOP'):e.settings_metadata(b'fixture')
  out=e.settings_metadata(settings([{'type':'secret_text','name':'PLM_YOUTUBE_CHECKPOINT_KEY','value':'NOT_READ'}]))
  self.assertEqual(out['key_readiness'],'NAME_PRESENT_VALUE_UNVERIFIED');self.assertFalse(out['secret_values_accessed']);self.assertNotIn('NOT_READ',json.dumps(out))
 def test_active_schedule_stops_before_queues(self):
  out,seen=self.inspect(bodies=[b'x',settings(),schedules(1),queues()]);self.assertEqual(len(seen),3);self.assertEqual(out['classification'],'STOP_UNEXPECTED_ACTIVE_RUNTIME')
 def test_active_exposure_stops_before_schedule(self):
  out,seen=self.inspect(bodies=[b'x',settings(workers_dev=True),schedules(),queues()]);self.assertEqual(len(seen),2);self.assertEqual(out['classification'],'STOP_UNEXPECTED_ACTIVE_RUNTIME')
 def test_queue_zero_complete_nonempty_absence_unproven(self):
  out=e.queues_metadata(queues());self.assertTrue(out['consumers_complete']);self.assertEqual(out['consumer_count'],0);out=e.queues_metadata(queues([{'queue_id':'a'*32}]));self.assertFalse(out['consumers_complete']);self.assertIsNone(out['consumer_count'])
 def test_known_queue_consumer_active(self):
  out=e.queues_metadata(queues([{'consumers':[{'type':'worker','script_name':e.WORKER}]}]));self.assertTrue(out['active'])
 def test_incomplete_pagination_blocks(self):
  d=json.loads(queues());d['result_info']['total_count']=1
  with self.assertRaisesRegex(e.Stop,'UNVERIFIED_INCOMPLETE_PAGINATION'):e.queues_metadata(json.dumps(d).encode())
 def test_raw_body_never_printed_or_persisted(self):
  buf=io.StringIO()
  with contextlib.redirect_stdout(buf),patch.object(Path,'write_bytes',side_effect=AssertionError('RAW_WRITE')),patch.object(Path,'write_text',side_effect=AssertionError('RAW_WRITE')):out,_=self.inspect(bodies=[b'RAW_SECRET_SENTINEL',settings(),schedules(),queues()])
  self.assertEqual(buf.getvalue(),'');self.assertNotIn('RAW_SECRET_SENTINEL',json.dumps(out));self.assertEqual(out['raw_retention'],0)
 def test_zero_side_effect_fields(self):
  out,_=self.inspect()
  for k in ('writes','deploys','dispatches','uploads','D1_requests','YouTube_calls','retry','resume','redirect','raw_retention','secret_exposure'):self.assertEqual(out[k],0)
 def test_workflow_exact_marker_only_attempt_branch_and_no_write(self):
  text=(ROOT/e.WORKFLOW).read_text();self.assertIn("paths: ['"+e.MARKER+"']",text);self.assertIn('github.run_attempt == 1',text);self.assertIn('persist-credentials: false',text);self.assertIn('actions: read',text);self.assertNotIn('workflow_dispatch',text);self.assertNotIn('write',text);self.assertNotIn('upload-artifact',text)
 def test_gate_without_marker_has_no_network_factory(self):
  args=fixtures();args[3].clear()
  with patch.object(e,'AuthorizedTransport',side_effect=AssertionError('NETWORK_FACTORY')):
   with self.assertRaises(e.Stop):e.authorize_transport(*args)
 def test_live_transport_bounds_uses_only_get_and_closes(self):
  import http.client
  calls=[]
  class Response:
   status=403
   def read1(self,n):self.n=n;self.assertion=n<=e.ERROR_MAX+1;return b''
  class Conn:
   def __init__(self,host,timeout):calls.append((host,timeout))
   def request(self,m,p,headers):calls.append((m,p));self.headers=headers
   def getresponse(self):return Response()
   def close(self):calls.append('closed')
  args=fixtures();args[0]['PLM_CF_WORKER_API_TOKEN']='SYNTHETIC_OFFLINE_ONLY';t=e.authorize_transport(*args)
  with patch.object(http.client,'HTTPSConnection',Conn):out=e.inspect(t,set())
  self.assertEqual(out['requests_attempted'],1);self.assertEqual(calls[0],('api.cloudflare.com',15));self.assertEqual(calls[1],('GET','/client/v4'+e.ENDPOINTS[0]));self.assertEqual(calls[-1],'closed')
if __name__=='__main__':unittest.main()
