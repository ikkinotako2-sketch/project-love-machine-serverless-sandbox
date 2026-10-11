import unittest,json,copy,inspect
from pathlib import Path
try:
 from readiness import runtime_visibility_completion_executor as v
except ModuleNotFoundError:
 import runtime_visibility_completion_executor as v
ROOT=Path(__file__).resolve().parents[1]
def envlp(r,info=None):
 d={'success':True,'result':r}
 if info is not None:d['result_info']=info
 return json.dumps(d).encode()
def listing(rows):return envlp(rows,{'count':len(rows),'total_count':len(rows),'page':1,'per_page':50,'total_pages':1})
class Visibility(unittest.TestCase):
 def setUp(self):self.c=json.loads((ROOT/v.CENSUS).read_text());self.p=json.loads((ROOT/v.PRIOR).read_text());self.b=(ROOT/v.BOOTSTRAP).read_bytes();self.calls=[]
 def runinspect(self,replies=None,c=None):
  replies=replies or self.good()
  def t(m,p):self.calls.append((m,p));return replies[len(self.calls)-1]
  return v.inspect(t,self.c if c is None else c,self.b,self.p)
 def good(self):return [(200,envlp({'enabled':False,'previews_enabled':False}),{}),(200,listing([]),{}),(200,listing([]),{})]
 def test_exact_census(self):self.assertTrue(v.census_proof(self.c,self.b,self.p));self.assertEqual(v.sha(self.b),v.REMOTE_SHA)
 def test_size_only(self):self.assertFalse(v.census_proof(self.c,b'x'*len(self.b),self.p))
 def test_hash_only_unknown(self):c=copy.deepcopy(self.c);c['matched_path']='unknown';self.assertFalse(v.census_proof(c,self.b,self.p))
 def test_current_eight(self):
  for r in self.c['current']:self.assertEqual(v.sha((ROOT/r['path']).read_bytes()),r['sha256'])
 def test_bounded_history(self):self.assertEqual(len(self.c['historical']),17)
 def test_skip4(self):o=self.runinspect();self.assertEqual(o['requests_attempted'],3);self.assertTrue(o['pass']);self.assertFalse(o['source_freshly_revalidated'])
 def test_workersdev(self):r=self.good();r[0]=(200,envlp({'enabled':True,'previews_enabled':False}),{});o=self.runinspect(r);self.assertEqual(o['classification'],'STOP_UNEXPECTED_ACTIVE_RUNTIME');self.assertEqual(len(self.calls),1)
 def test_preview(self):self.assertRaises(v.Stop,v.subdomain,envlp({'enabled':False,'previews_enabled':True}))
 def test_missing_bool(self):self.assertRaises(v.Stop,v.subdomain,envlp({'enabled':False}))
 def test_target_domain(self):self.assertRaises(v.Stop,v.domains,listing([{'id':'x','service':v.WORKER,'enabled':True,'previews_enabled':False}]))
 def test_domain_preview(self):self.assertRaises(v.Stop,v.domains,listing([{'id':'x','service':v.WORKER,'enabled':False,'previews_enabled':True}]))
 def test_unrelated_domain(self):self.assertEqual(v.domains(listing([{'id':'x','service':'other','enabled':True,'previews_enabled':True}]))['custom_domain_count'],0)
 def test_disabled_target(self):self.assertRaises(v.Stop,v.domains,listing([{'id':'x','service':v.WORKER,'enabled':False,'previews_enabled':False}]))
 def test_domain_incomplete(self):self.assertRaises(v.Stop,v.domains,envlp([]))
 def test_zone403(self):r=self.good();r[2]=(403,b'',{});o=self.runinspect(r);self.assertEqual(o['reason_codes'],['UNVERIFIED_ZONE_PERMISSION']);self.assertEqual(len(self.calls),3)
 def test_zonepages2(self):d=json.loads(listing([]));d['result_info']['total_pages']=2;self.assertRaises(v.Stop,v.zones,json.dumps(d).encode())
 def test_zone0(self):self.assertEqual(v.zones(listing([]))['classic_route_count'],0)
 def test_zonepositive(self):r=self.good();r[2]=(200,listing([{'id':'a'*32,'account':{'id':v.ACCOUNT}}]),{});o=self.runinspect(r);self.assertEqual(o['reason_codes'],['ROUTE_INSPECTION_REQUIRED']);self.assertEqual(len(self.calls),3)
 def test_zone_account(self):self.assertRaises(v.Stop,v.zones,listing([{'id':'a'*32,'account':{'id':'b'*32}}]))
 def test_duplicate_zone(self):r={'id':'a'*32,'account':{'id':v.ACCOUNT}};self.assertRaises(v.Stop,v.zones,listing([r,r]))
 def test_strict_parked(self):self.assertTrue(v.strict_parked(b'export default {fetch(){return new Response("PARKED",{status:503});}};'))
 def test_unsupported(self):self.assertFalse(v.strict_parked(b'export default {fetch(){return fetch("https://example.com");}};'))
 def test_scheduled(self):self.assertFalse(v.strict_parked(b'export default {fetch(){return new Response("PARKED",{status:503});},scheduled(){}};'))
 def test_queue(self):self.assertFalse(v.strict_parked(b'export default {queue(){}};'))
 def test_source_memory_only(self):
  c=copy.deepcopy(self.c);c['exact_match']=False;r=self.good()+[(200,b'export default {fetch(){return new Response("PARKED",{status:503});}};',{'content_type':'text/javascript'})];o=self.runinspect(r,c);self.assertEqual(len(self.calls),4);self.assertTrue(o['parked_proven']);self.assertNotIn('Response',json.dumps(o));self.assertEqual(o['raw_retention'],0)
 def test_unknown_source(self):
  c=copy.deepcopy(self.c);c['exact_match']=False;r=self.good()+[(200,b'export default {fetch(){return fetch("x");}};',{'content_type':'text/javascript'})];o=self.runinspect(r,c);self.assertEqual(o['classification'],'BLOCKED_UNKNOWN_REMOTE_SOURCE')
 def test_no_eval(self):s=inspect.getsource(v.strict_parked);self.assertNotIn('eval(',s);self.assertNotIn('__import__',s)
 def test_methods(self):
  for m in ['POST','PUT','PATCH','DELETE']:self.assertRaises(v.Stop,v.RequestGate(lambda *a:None).get,m,v.ENDPOINTS[0])
 def test_forbidden_paths(self):
  for p in ['/d1/query','/workers/deploy','/zones/a/workers/routes']:self.assertRaises(v.Stop,v.RequestGate(lambda *a:None).get,'GET',p)
 def test_capability(self):self.assertRaises(v.Stop,v.AuthorizedTransport,'DO_NOT_LOG')
 def test_http_early_stop(self):
  for status in [401,403,404,429,500,302]:
   self.calls=[];o=self.runinspect([(status,b'SECRET_RAW_ERROR',{})]);self.assertEqual(len(self.calls),1);self.assertNotIn('SECRET_RAW_ERROR',json.dumps(o))
 def test_bound(self):self.assertRaises(v.Stop,v.RequestGate(lambda *a:(200,b'x'*(v.MAX+1),{})).get,'GET',v.ENDPOINTS[0])
 def test_timeout(self):
  def t(*a):raise TimeoutError('TOKEN')
  g=v.RequestGate(t);self.assertRaises(v.Stop,g.get,'GET',v.ENDPOINTS[0]);self.assertEqual(g.count,1);self.assertRaises(v.Stop,g.get,'GET',v.ENDPOINTS[1])
 def test_marker_absent(self):self.assertFalse((ROOT/v.MARKER).exists())
 def fixture(self):
  files={p:(ROOT/p).read_bytes() for p in v.PIN_FILES.values()};plan=json.loads(files[v.PLAN]);before='a'*40;after='b'*40;marker={k:v.sha(files[p]) for k,p in v.PIN_FILES.items()};marker.update(identity=v.IDENTITY,state='CONSUMED_BEFORE_REMOTE',prepared_commit_sha=before);env={'GITHUB_REPOSITORY':v.REPO,'GITHUB_REF':v.BRANCH,'GITHUB_EVENT_NAME':'push','GITHUB_RUN_ATTEMPT':'1','GITHUB_SHA':after,**{k:'true' for k in ['TEST_ONLY','DRY_RUN','NO_PUBLISH','EMERGENCY_STOP']}};event={'before':before,'after':after,'head_commit':{'id':after,'message':v.MESSAGE},'commits':[{}]};facts={'head':after,'parent':before,'prepared_parent':v.PARENT,'files':[v.MARKER],'marker_preexisted':False,'message':v.MESSAGE};return [env,event,facts,marker,plan,files]
 def test_gate_pass(self):v.validate_gate(*self.fixture())
 def test_prior_identity(self):a=self.fixture();a[3]['identity']='provider-neutral-runtime-remote-readonly-inspection-20261011-r1';self.assertRaises(v.Stop,v.validate_gate,*a)
 def test_attempt2(self):a=self.fixture();a[0]['GITHUB_RUN_ATTEMPT']='2';self.assertRaises(v.Stop,v.validate_gate,*a)
 def test_extra_file(self):a=self.fixture();a[2]['files'].append('x');self.assertRaises(v.Stop,v.validate_gate,*a)
 def test_parent(self):a=self.fixture();a[2]['prepared_parent']='c'*40;self.assertRaises(v.Stop,v.validate_gate,*a)
 def test_consumed(self):a=self.fixture();a[2]['marker_preexisted']=True;self.assertRaises(v.Stop,v.validate_gate,*a)
 def test_hash_drift(self):a=self.fixture();a[5][v.HELPER]+=b'x';self.assertRaises(v.Stop,v.validate_gate,*a)
 def test_limits(self):a=self.fixture();a[4]['maximum_writes']=1;a[5][v.PLAN]=json.dumps(a[4]).encode();a[3]['plan_sha256']=v.sha(a[5][v.PLAN]);self.assertRaises(v.Stop,v.validate_gate,*a)
 def test_secret_output(self):o=self.runinspect();self.assertFalse(o['secret_values_accessed']);self.assertEqual(o['secret_exposure'],0)
 def test_not_deploy_approval(self):o=self.runinspect();self.assertFalse(o['execution_approved']);self.assertFalse(o['launchable']);self.assertEqual(o['deploys'],0)
 def test_marker_trigger(self):s=(ROOT/v.WORKFLOW).read_text();self.assertIn("paths: ['"+v.MARKER+"']",s);self.assertIn('github.run_attempt == 1',s);self.assertNotIn('workflow_dispatch',s)
 def test_missing_secret_explicit_stop(self):
  import io,contextlib
  from unittest.mock import patch
  a=self.fixture()
  with patch.object(v,'load_gate',return_value=a[5]),patch.dict('os.environ',{},clear=True),patch.object(v,'AuthorizedTransport') as transport,contextlib.redirect_stdout(io.StringIO()) as output:
   v.main()
  transport.assert_not_called();o=json.loads(output.getvalue());self.assertEqual(o['reason_codes'],['CREDENTIAL_MISSING_STOP']);self.assertEqual(o['requests_attempted'],0)
 def test_four_max_and_no_reuse(self):
  g=v.RequestGate(lambda *a:(200,b'{}',{}))
  for p in v.ENDPOINTS:g.get('GET',p)
  self.assertEqual(g.count,4);self.assertRaises(v.Stop,g.get,'GET',v.ENDPOINTS[0])
if __name__=='__main__':unittest.main()
