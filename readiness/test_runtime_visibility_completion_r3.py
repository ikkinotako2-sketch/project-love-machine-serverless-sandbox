import unittest,json,copy,inspect
from pathlib import Path
try:
 from readiness import runtime_visibility_completion_r3_executor as v
except ModuleNotFoundError:
 import runtime_visibility_completion_r3_executor as v
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
 def test_disabled_target(self):self.assertRaises(v.Stop,v.domains,listing([{'id':'x','service':v.WORKER,'enabled':False,'previews_enabled':False}]))
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
 def fixture(self):
  files={p:(ROOT/p).read_bytes() for p in v.PIN_FILES.values()};plan=json.loads(files[v.PLAN]);before='a'*40;after='b'*40;marker={k:v.sha(files[p]) for k,p in v.PIN_FILES.items()};marker.update(identity=v.IDENTITY,state='CONSUMED_BEFORE_REMOTE',prepared_commit_sha=before);env={'GITHUB_REPOSITORY':v.REPO,'GITHUB_REF':v.BRANCH,'GITHUB_EVENT_NAME':'push','GITHUB_RUN_ATTEMPT':'1','GITHUB_SHA':after,**{k:'true' for k in ['TEST_ONLY','DRY_RUN','NO_PUBLISH','EMERGENCY_STOP']}};event={'before':before,'after':after,'head_commit':{'id':after,'message':v.MESSAGE},'commits':[{}]};facts={'head':after,'parent':before,'preparation_root_ancestor':True,'preparation_commit_count':3,'preparation_files':[v.HELPER,v.WORKFLOW,v.PLAN,v.SCHEMA,'readiness/test_runtime_visibility_completion_r3.py','.github/workflows/plm-runtime-integration-offline.yml','readiness/test_runtime_visibility_completion_r2.py'],'full_history':True,'r1_marker_in_parent_sha256':v.R1_MARKER_SHA,'r2_marker_in_parent_sha256':v.R2_MARKER_SHA,'files':[v.MARKER],'marker_preexisted':False,'message':v.MESSAGE};return [env,event,facts,marker,plan,files]
 def test_gate_pass(self):v.validate_gate(*self.fixture())
 def test_prior_identity(self):a=self.fixture();a[3]['identity']='provider-neutral-runtime-remote-readonly-inspection-20261011-r1';self.assertRaises(v.Stop,v.validate_gate,*a)
 def test_attempt2(self):a=self.fixture();a[0]['GITHUB_RUN_ATTEMPT']='2';self.assertRaises(v.Stop,v.validate_gate,*a)
 def test_extra_file(self):a=self.fixture();a[2]['files'].append('x');self.assertRaises(v.Stop,v.validate_gate,*a)
 def test_parent(self):a=self.fixture();a[2]['preparation_root_ancestor']=False;self.assertRaises(v.Stop,v.validate_gate,*a)
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
 def test_preparation_commit_bound(self):a=self.fixture();a[2]['preparation_commit_count']=4;self.assertRaises(v.Stop,v.validate_gate,*a)
 def test_preparation_cannot_change_consumed_marker(self):a=self.fixture();a[2]['preparation_files'].append('audit-evidence/consumed/old.json');self.assertRaises(v.Stop,v.validate_gate,*a)
 def test_checkout_full(self):
  import re
  s=(ROOT/v.WORKFLOW).read_text();self.assertEqual(re.findall(r'fetch-depth:\s*(\d+)',s),['0']);self.assertIn('ref: ${{ github.sha }}',s);self.assertIn('persist-credentials: false',s)
 def test_depth3_rejected(self):
  a=self.fixture();a[4]['checkout_fetch_depth']=3;a[5][v.PLAN]=json.dumps(a[4]).encode();a[3]['plan_sha256']=v.sha(a[5][v.PLAN]);self.assertRaises(v.Stop,v.validate_gate,*a)
 def test_shallow_fixture(self):
  seen=[]
  def git(*a):seen.append(a);return 'true'
  with self.assertRaisesRegex(v.Stop,'SHALLOW_REPOSITORY_STOP'):v.collect_git_facts('a'*40,git,lambda _:False)
  self.assertEqual(seen,[('rev-parse','--is-shallow-repository')])
 def test_full_history_fixture(self):
  a=self.fixture();b=a[1]['before'];seen=[]
  responses={('rev-parse','--is-shallow-repository'):'false',('merge-base',v.PARENT,b):v.PARENT,('rev-list','--count',v.PARENT+'..'+b):'1',('show',v.PARENT+':'+v.R1_MARKER):(ROOT/v.R1_MARKER).read_text(),('show',v.PARENT+':'+v.R2_MARKER):(ROOT/v.R2_MARKER).read_text(),('rev-parse','HEAD'):a[1]['after'],('rev-parse','HEAD^'):b,('diff','--name-only',v.PARENT,b):'\n'.join(a[2]['preparation_files']),('diff','--name-only',b,'HEAD'):v.MARKER,('log','-1','--format=%B'):v.MESSAGE}
  def git(*args):seen.append(args);return responses[args]
  facts=v.collect_git_facts(b,git,lambda _:False);self.assertTrue(facts['full_history']);self.assertTrue(facts['preparation_root_ancestor']);self.assertIn(('merge-base',v.PARENT,b),seen);self.assertIn(('rev-list','--count',v.PARENT+'..'+b),seen);self.assertIn(('diff','--name-only',v.PARENT,b),seen);a[2]=facts;v.validate_gate(*a)
 def test_r1_marker_immutable(self):self.assertEqual(v.sha((ROOT/v.R1_MARKER).read_bytes()),v.R1_MARKER_SHA)
 def test_r1_marker_drift_rejected(self):a=self.fixture();a[5][v.R1_MARKER]+=b'x';a[3]['r1_consumed_marker_sha256']=v.sha(a[5][v.R1_MARKER]);a[4]['r1_consumed_marker_sha256']=a[3]['r1_consumed_marker_sha256'];a[5][v.PLAN]=json.dumps(a[4]).encode();a[3]['plan_sha256']=v.sha(a[5][v.PLAN]);self.assertRaises(v.Stop,v.validate_gate,*a)
 def test_r1_visibility_identity_rejected(self):a=self.fixture();a[3]['identity']='provider-neutral-runtime-visibility-completion-20261011-r1';self.assertRaises(v.Stop,v.validate_gate,*a)
 def test_r1_failure_not_success(self):a=self.fixture();self.assertFalse(a[4]['r1_is_success_prerequisite']);self.assertEqual(a[4]['r1_historical_failure_run'],38130789006)
 def test_gate_failure_before_credential(self):
  from unittest.mock import patch
  import io,contextlib
  with patch.object(v,'load_gate',side_effect=v.Stop('SHALLOW_REPOSITORY_STOP')),patch.object(v,'AuthorizedTransport') as t,contextlib.redirect_stdout(io.StringIO()) as out:v.main()
  t.assert_not_called();o=json.loads(out.getvalue());self.assertEqual(o['requests_attempted'],0);self.assertEqual(o['reason_codes'],['SHALLOW_REPOSITORY_STOP'])
 def test_workflow_gate_before_secret(self):s=(ROOT/v.WORKFLOW).read_text();self.assertLess(s.index('Gate exact marker-only'),s.index('PLM_CF_WORKER_API_TOKEN:'))
 def stop_code(self,fn,raw,code):
  with self.assertRaisesRegex(v.Stop,'^'+code+'$'):fn(raw)
 def test_domain_absent_info_empty(self):self.assertTrue(v.domains(envlp([]))['custom_domains_complete'])
 def test_domain_absent_info_matching_row(self):self.stop_code(v.domains,envlp([{'id':'a','service':v.WORKER}]),'BLOCKED_TARGET_DOMAIN_PRESENT')
 def test_domain_unfiltered_total(self):self.assertEqual(v.domains(envlp([],{'count':0,'total_count':999}))['custom_domain_count'],0)
 def test_domain_count_bad(self):self.stop_code(v.domains,envlp([],{'count':1}),'BLOCKED_CUSTOM_DOMAIN_INCONSISTENT_METADATA')
 def test_domain_wrong_service(self):self.stop_code(v.domains,envlp([{'id':'a','service':'other'}]),'DOMAIN_FILTER_CONTRACT_STOP')
 def test_domain_duplicate(self):r={'id':'a','service':v.WORKER};self.stop_code(v.domains,envlp([r,r]),'DOMAIN_SHAPE_STOP')
 def test_domain_bad_info_type(self):self.stop_code(v.domains,envlp([],[]),'BLOCKED_CUSTOM_DOMAIN_INCONSISTENT_METADATA')
 def test_domain_bad_metadata(self):
  for i in [{'page':2},{'per_page':0},{'total_count':-1},{'total_count':True},{'total_pages':2},{'total_pages':0}]:self.stop_code(v.domains,envlp([],i),'BLOCKED_CUSTOM_DOMAIN_INCONSISTENT_METADATA')
 def test_domain_partial_metadata_valid(self):self.assertTrue(v.domains(envlp([],{'per_page':20,'page':1,'total_pages':1,'total_count':2000}))['custom_domains_complete'])
 def test_zone_missing_info(self):self.stop_code(v.zones,envlp([]),'BLOCKED_ZONE_PAGINATION_METADATA_MISSING')
 def test_zone_filtered_total_allowed(self):d=json.loads(listing([]));d['result_info']['total_count']=123;self.assertTrue(v.zones(json.dumps(d).encode())['classic_routes_complete'])
 def test_zone_count_mismatch(self):d=json.loads(listing([]));d['result_info']['count']=1;self.stop_code(v.zones,json.dumps(d).encode(),'BLOCKED_ZONE_PAGINATION')
 def test_zone_page_bad(self):d=json.loads(listing([]));d['result_info']['page']=2;self.stop_code(v.zones,json.dumps(d).encode(),'BLOCKED_ZONE_PAGINATION')
 def test_zone_optional_total_absent(self):d=json.loads(listing([]));del d['result_info']['total_count'];self.assertTrue(v.zones(json.dumps(d).encode())['zones_complete'])
 def test_zone_bad_metadata(self):
  for k,value in [('per_page',20),('total_pages',0),('count',True),('total_count',-1)]:
   d=json.loads(listing([]));d['result_info'][k]=value;self.stop_code(v.zones,json.dumps(d).encode(),'BLOCKED_ZONE_PAGINATION')
 def test_three_max(self):
  g=v.RequestGate(lambda *a:(200,b'{}',{}))
  for p in v.ENDPOINTS:g.get('GET',p)
  self.assertEqual(g.count,3);self.assertRaises(v.Stop,g.get,'GET',v.ENDPOINTS[0])
 def test_no_source_fallback(self):
  c=copy.deepcopy(self.c);c['exact_match']=False;o=self.runinspect(c=c);self.assertEqual(len(self.calls),3);self.assertFalse(o['pass']);self.assertFalse(o['source_freshly_revalidated'])
 def test_content_rejected(self):self.assertRaises(v.Stop,v.RequestGate(lambda *a:None).get,'GET',v.PREFIX+'/content/v2')
 def test_exact_endpoints(self):self.assertEqual(v.ENDPOINTS,(v.PREFIX+'/subdomain','/accounts/'+v.ACCOUNT+'/workers/domains?service='+v.WORKER,'/zones?account.id='+v.ACCOUNT+'&per_page=50&page=1'))
 def test_no_generic_parser(self):self.assertFalse(hasattr(v,'complete_list'));self.assertNotIn('content/v2',inspect.getsource(v))
 def test_r2_marker_immutable(self):self.assertEqual(v.sha((ROOT/v.R2_MARKER).read_bytes()),v.R2_MARKER_SHA)
 def test_r2_marker_drift_rejected(self):a=self.fixture();a[5][v.R2_MARKER]+=b'x';self.assertRaises(v.Stop,v.validate_gate,*a)
 def test_old_identities_rejected(self):
  for old in ['provider-neutral-runtime-visibility-completion-20261011-r1','provider-neutral-runtime-visibility-completion-20261011-r2']:
   a=self.fixture();a[3]['identity']=old;self.assertRaises(v.Stop,v.validate_gate,*a)
 def test_r3_marker_absent(self):self.assertFalse((ROOT/v.MARKER).exists())
 def test_r2_not_success_prerequisite(self):a=self.fixture();self.assertFalse(a[4]['r2_is_success_prerequisite']);self.assertEqual(a[4]['r2_historical_run'],38131868706)
 def test_read_only_limits(self):o=self.runinspect();self.assertTrue(o['pass']);self.assertEqual(o['requests_attempted'],3);self.assertTrue(all(o[k]==0 for k in ['writes','D1_requests','deploys','dispatches','uploads','YouTube_calls','retry','resume','redirect','fallback','raw_retention','secret_exposure']))
if __name__=='__main__':unittest.main()
