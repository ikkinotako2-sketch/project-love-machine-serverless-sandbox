import copy,json,unittest
from pathlib import Path
from unittest.mock import patch
from readiness import runtime_parked_deploy_executor as v
ROOT=Path(__file__).resolve().parents[1]
def raw(result,**kw):return json.dumps({'success':True,'errors':[],'result':result,**kw}).encode()
class Fake:
 def __init__(self,alter=None,write=None):
  self.budget=v.RequestBudget();self.calls=[];self.rows=[(200,(ROOT/'serverless/bootstrap-placeholder.mjs').read_bytes(),{'content_type':'application/javascript+module'}),(200,raw({'enabled':False,'previews_enabled':False}),{}),(200,raw([]),{}),(200,raw([],result_info={'page':1,'per_page':50,'total_pages':0,'count':0}),{})];self.write=write or (200,raw({'id':v.WORKER}),{})
  if alter:
   for i,r in alter.items():self.rows[i]=r
 def preflight_complete(self,c):self.budget.preflight_complete(c)
 def __call__(self,method,path,*args):
  self.budget.admit(method,path);self.calls.append((method,path));r=self.rows[len(self.calls)-1] if method=='GET' else self.write
  if isinstance(r,Exception):raise r
  return r
class DeployTests(unittest.TestCase):
 def runit(self,alter=None,write=None):
  t=Fake(alter,write);return v.execute(t,(ROOT/v.BUNDLE).read_bytes(),(ROOT/v.CONFIG).read_bytes()),t
 def fixture(self):
  files={p:(ROOT/p).read_bytes() for p in v.PIN_FILES.values()};before='a'*40;after='b'*40
  marker={k:v.sha(files[p]) for k,p in v.PIN_FILES.items()};marker.update(identity=v.IDENTITY,state='CONSUMED_BEFORE_REMOTE',prepared_commit_sha=before,old_remote_source_sha256=v.OLD,expected_new_bundle_sha256=v.NEW)
  env={'GITHUB_REPOSITORY':v.REPO,'GITHUB_REF':v.BRANCH,'GITHUB_EVENT_NAME':'push','GITHUB_RUN_ATTEMPT':'1','GITHUB_SHA':after,**v.FLAGS};event={'before':before,'after':after,'head_commit':{'id':after,'message':v.MESSAGE},'commits':[{}]}
  facts={'full_history':True,'root':v.PARENT,'count':1,'preparation_files':sorted(v.PREPARATION_FILES),'head':after,'parent':before,'files':[v.MARKER],'message':v.MESSAGE,'marker_preexisted':False,'r4_parent_hash':v.IMMUTABLE[v.R4]};return [env,event,facts,marker,files]
 def test_exact_old_source_eligibility_stop_before_postcheck(self):
  o,t=self.runit();self.assertEqual(o['classification'],'PARKED_DEPLOY_ACK_STOP_BEFORE_POSTCHECK');self.assertEqual(t.calls,[('GET',p) for p in v.GETS]+[('PUT',v.PUT)]);self.assertEqual(o['script_writes_attempted'],1)
 def test_gate_pass(self):v.validate_gate(*self.fixture())
 def test_marker_absent(self):self.assertFalse((ROOT/v.MARKER).exists())
 def test_immutable_dependencies(self):
  for p,h in v.IMMUTABLE.items():self.assertEqual(v.sha((ROOT/p).read_bytes()),h)
 def test_exact_multipart(self):
  b=(ROOT/v.BUNDLE).read_bytes();body,typ=v.multipart(b,(ROOT/v.CONFIG).read_bytes());self.assertEqual(body.count(b),1);self.assertIn(b'application/javascript+module',body);self.assertEqual(len(v.upload_metadata()['bindings']),5);self.assertEqual(v.upload_metadata()['keep_bindings'],[])
 def test_source_mismatch_zero_write(self):self.assertEqual(self.runit({0:(200,b'export default {};',{'content_type':'application/javascript'})})[0]['script_writes_attempted'],0)
 def test_unparseable_zero_write(self):self.assertEqual(self.runit({0:(200,b'unknown',{'content_type':'text/plain'})})[0]['script_writes_attempted'],0)
 def test_workers_dev_zero_write(self):self.assertEqual(self.runit({1:(200,raw({'enabled':True,'previews_enabled':False}),{})})[0]['script_writes_attempted'],0)
 def test_previews_zero_write(self):self.assertEqual(self.runit({1:(200,raw({'enabled':False,'previews_enabled':True}),{})})[0]['script_writes_attempted'],0)
 def test_domain_zero_write(self):self.assertEqual(self.runit({2:(200,raw([{'service':v.WORKER,'id':'d'}]),{})})[0]['script_writes_attempted'],0)
 def test_zone_zero_write(self):self.assertEqual(self.runit({3:(200,raw([{'id':'a'*32,'account':{'id':v.ACCOUNT}}]),{})})[0]['script_writes_attempted'],0)
 def test_403_zero_write(self):o,t=self.runit({0:(403,b'raw private message',{})});self.assertEqual(o['script_writes_attempted'],0);self.assertEqual(len(t.calls),1);self.assertNotIn('private',json.dumps(o))
 def test_timeout_zero_write(self):o,t=self.runit({0:TimeoutError('private')});self.assertEqual(o['script_writes_attempted'],0);self.assertNotIn('private',json.dumps(o))
 def test_UNKNOWN_no_resend(self):
  for r in [TimeoutError('private'),(500,b'raw private',{}),(302,b'',{}),(200,raw({'id':'wrong'}),{}),(200,b'bad',{})]:
   o,t=self.runit(write=r);self.assertEqual(o['classification'],'DEPLOY_UNKNOWN_STOP_NO_RETRY');self.assertEqual(t.budget.writes,1);self.assertEqual(len(t.calls),5);self.assertEqual(o['retry'],0);self.assertNotIn('private',json.dumps(o))
 def test_second_write_and_postcheck_impossible(self):
  o,t=self.runit()
  for m,p in [('PUT',v.PUT),('GET',v.GETS[0]),('POST',v.PUT),('GET','/zones/other/workers/routes')]:self.assertRaises(v.Stop,t.budget.admit,m,p)
 def test_no_fifth_GET(self):
  b=v.RequestBudget()
  for p in v.GETS:b.admit('GET',p)
  self.assertRaises(v.Stop,b.admit,'GET',v.GETS[0])
 def test_only_ordered_GET(self):
  for p in v.GETS[1:]:self.assertRaises(v.Stop,v.RequestBudget().admit,'GET',p)
 def test_wrong_account_worker(self):
  for p in [v.GETS[0].replace(v.ACCOUNT,'a'*32),v.GETS[0].replace(v.WORKER,'other')]:self.assertRaises(v.Stop,v.RequestBudget().admit,'GET',p)
 def test_no_write_before_proof(self):self.assertRaises(v.Stop,v.RequestBudget().admit,'PUT',v.PUT)
 def test_capability_required(self):self.assertRaises(v.Stop,v.AuthorizedTransport,'read','write')
 def test_credentials_missing_same_or_invalid(self):
  for a,b in [('', 'write'),('read',''),('same','same'),('read\n','write')]:self.assertRaises(v.Stop,v.AuthorizedTransport,a,b,v._CAPABILITY)
 def test_nonparked_startup_and_live_bundle_mutations_rejected(self):
  b=(ROOT/v.BUNDLE).read_bytes();c=(ROOT/v.CONFIG).read_bytes()
  for x in [b+b'fetch("remote")',b+b'DB.prepare("DELETE").run()',b.replace(b'PARKED_RUNTIME_COMPOSITION',b'LIVE'),b.replace(v.DISABLED_LIVE,b'export function createLiveComposition(){return {};}')]:t=Fake();o=v.execute(t,x,c);self.assertEqual(t.calls,[])
 def test_config_all_mutations_rejected(self):
  c=copy.deepcopy(v.EXPECTED_CONFIG);mutants=[]
  for k,val in [('name','other'),('main','wrong'),('workers_dev',True),('preview_urls',True),('routes',['*']),('triggers',{'crons':['* * * * *']}),('bindings',[{'type':'secret_text'}])]:x=copy.deepcopy(c);x[k]=val;mutants.append(x)
  x=copy.deepcopy(c);x['d1_databases'][0]['database_id']='wrong';mutants.append(x)
  for k in v.FLAGS:x=copy.deepcopy(c);x['vars'][k]='false';mutants.append(x)
  for x in mutants:t=Fake();v.execute(t,(ROOT/v.BUNDLE).read_bytes(),json.dumps(x).encode());self.assertEqual(t.calls,[])
 def test_old_consumed_identity_rejected(self):
  for n in range(1,5):a=self.fixture();a[3]['identity']='provider-neutral-runtime-visibility-completion-20261011-r'+str(n);self.assertRaises(v.Stop,v.validate_gate,*a)
 def test_history_and_marker_chain_failures(self):
  for k,val in [('full_history',False),('root','wrong'),('count',0),('files',[v.MARKER,v.BUNDLE]),('marker_preexisted',True),('r4_parent_hash','wrong')]:a=self.fixture();a[2][k]=val;self.assertRaises(v.Stop,v.validate_gate,*a)
 def test_attempt_two_rejected(self):a=self.fixture();a[0]['GITHUB_RUN_ATTEMPT']='2';self.assertRaises(v.Stop,v.validate_gate,*a)
 def test_pins_drift_rejected(self):
  for p in v.PIN_FILES.values():a=self.fixture();a[4][p]+=b' ';self.assertRaises(v.Stop,v.validate_gate,*a)
 def test_safe_flags_explicit(self):
  for k in v.FLAGS:a=self.fixture();a[0][k]='false';self.assertRaises(v.Stop,v.validate_gate,*a)
 def test_workflow_local_gate_before_secret(self):s=(ROOT/v.WORKFLOW).read_text();self.assertLess(s.index('load_gate()'),s.index('secrets.PLM_CF_WORKER_DEPLOY_TOKEN'));self.assertIn('fetch-depth: 0',s);self.assertIn('persist-credentials: false',s);self.assertIn('contents: read',s);self.assertNotIn('workflow_dispatch',s)
 def test_shallow_rejected(self):self.assertRaises(v.Stop,v.collect_git_facts,'a'*40,lambda *a:'true',lambda _:False)
 def test_local_failure_no_credential_transport(self):
  with patch.object(v,'load_gate',side_effect=v.Stop('GATE_STOP')),patch.object(v,'AuthorizedTransport') as t,patch('builtins.print') as p:v.main();t.assert_not_called();self.assertIn('GATE_STOP',p.call_args[0][0])
 def test_postplan_readonly_no_marker(self):
  p=json.loads((ROOT/v.POSTPLAN).read_bytes());self.assertEqual(p['maximum_writes'],0);self.assertEqual(p['D1_requests'],0);self.assertTrue(all(x['method']=='GET' for x in p['requests']));self.assertFalse(p['execution_approved']);self.assertFalse((ROOT/'audit-evidence/consumed'/(p['identity']+'.json')).exists())
 def test_no_secret_or_exposure_write_metadata(self):
  s=json.dumps(v.upload_metadata())
  for k in ('secret','routes','workers_dev','queue'):self.assertNotIn(k,s)
 def test_numeric_diagnostics_only(self):self.assertEqual(v.numeric_errors(b'{"errors":[{"code":10000,"message":"token"},{"code":true},{"code":"text"}]}'),[10000])
 def test_side_effect_counters_zero(self):
  o,_=self.runit()
  for k in ('D1_requests','dispatches','YouTube_calls','retry','resume','resend','raw_retention','secret_exposure'):self.assertEqual(o[k],0)
 def test_plan_tamper_rejected_even_rebound(self):
  for key,value in [('maximum_script_writes',2),('maximum_prewrite_GET',5),('retry',1),('runtime_activation_approved',True)]:
   a=self.fixture();p=json.loads(a[4][v.PLAN]);p[key]=value;a[4][v.PLAN]=json.dumps(p).encode();a[3]['plan_sha256']=v.sha(a[4][v.PLAN]);self.assertRaises(v.Stop,v.validate_gate,*a)
 def test_wrong_prewrite_path_plan_rejected(self):
  a=self.fixture();p=json.loads(a[4][v.PLAN]);p['allowed_prewrite_requests'][0]['path']='/wrong';a[4][v.PLAN]=json.dumps(p).encode();a[3]['plan_sha256']=v.sha(a[4][v.PLAN]);self.assertRaises(v.Stop,v.validate_gate,*a)
 def test_marker_wrong_old_hash_rejected(self):a=self.fixture();a[3]['old_remote_source_sha256']='a'*64;self.assertRaises(v.Stop,v.validate_gate,*a)
 def test_marker_wrong_new_hash_rejected(self):a=self.fixture();a[3]['expected_new_bundle_sha256']='a'*64;self.assertRaises(v.Stop,v.validate_gate,*a)
 def test_shallow_full_history_fixture(self):
  mapping={('rev-parse','--is-shallow-repository'):'false',('merge-base',v.PARENT,'a'*40):v.PARENT,('rev-list','--count',v.PARENT+'..'+'a'*40):'1',('diff','--name-only',v.PARENT,'a'*40):'\n'.join(sorted(v.PREPARATION_FILES)),('rev-parse','HEAD'):'b'*40,('rev-parse','HEAD^'):'a'*40,('diff','--name-only','a'*40,'HEAD'):v.MARKER,('log','-1','--format=%B'):v.MESSAGE,('show',v.PARENT+':'+v.R4):(ROOT/v.R4).read_text()}
  f=v.collect_git_facts('a'*40,lambda *a:mapping[a],lambda _:False);a=self.fixture();a[2]=f;v.validate_gate(*a)
 def test_oversize_preflight_zero_write(self):o,t=self.runit({0:(200,b'x'*(v.MAX+1),{})});self.assertEqual(o['script_writes_attempted'],0)
 def test_domain_wrong_filter_zero_write(self):o,t=self.runit({2:(200,raw([{'id':'d','service':'other'}]),{})});self.assertEqual(o['script_writes_attempted'],0)
 def test_zone_incomplete_zero_write(self):o,t=self.runit({3:(200,raw([{'id':format(i,'032x'),'account':{'id':v.ACCOUNT}} for i in range(50)]),{})});self.assertEqual(o['script_writes_attempted'],0)
 def test_numerical_error_bound(self):self.assertEqual(len(v.numeric_errors(json.dumps({'errors':[{'code':i} for i in range(20)]}).encode())),8)
if __name__=='__main__':unittest.main()
