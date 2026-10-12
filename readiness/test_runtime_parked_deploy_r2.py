"""Offline successor fixture: real local artifacts, mocked remote transport only."""
import copy,json,unittest
from pathlib import Path
from datetime import datetime,timezone
from unittest.mock import patch
try:
 from readiness import runtime_parked_successor_contract as c
 from readiness import runtime_parked_deploy_r2 as d
except ModuleNotFoundError:
 import runtime_parked_successor_contract as c
 import runtime_parked_deploy_r2 as d
ROOT=Path(__file__).resolve().parents[1];NOW=datetime(2026,10,12,tzinfo=timezone.utc)
def raw(r,**kw):return json.dumps({'success':True,'result':r,**kw}).encode()
def files(s):return {p:(ROOT/p).read_bytes() for p in s['pins'].values()}
def fixture(s):
 f=files(s);prepared='a'*40;before='c'*40 if s['post'] else prepared;head='b'*40
 marker={k:c.sha(f[p]) for k,p in s['pins'].items()};marker.update(identity=s['identity'],state='CONSUMED_BEFORE_REMOTE',prepared_commit_sha=prepared)
 if s['post']:marker.update(prerequisite_commit_sha=before,prerequisite_run_id=42)
 else:marker['operational_exclusion_attested']=True
 env={**c.FLAGS,'GITHUB_REPOSITORY':c.REPO,'GITHUB_REF':c.BRANCH,'GITHUB_EVENT_NAME':'push','GITHUB_RUN_ATTEMPT':'1','GITHUB_SHA':head};event={'before':before,'after':head,'head_commit':{'id':head,'message':s['message']},'commits':[{}]}
 facts={'full_history':True,'root':c.PARENT,'count':1,'preparation_files':json.loads(f[s['plan']])['preparation_files'],'head':head,'parent':before,'files':[s['marker']],'message':s['message'],'marker_preexisted':False,'old_deploy_absent':{k:True for k in ('root','prepared','head','worktree')},'historical_hashes':{p:{k:h for k in ('root','prepared','head')} for p,h in s['historical'].items()},'immutable_root_hashes':s['immutable'],'deploy_marker_chain':True}
 return env,event,facts,marker,f
class Fake:
 def __init__(self,post=False,change=None):
  self.budget=c.Budget(post);self.calls=[];self.responses=[];self.post=post
  if not post:self.responses.append((200,raw({'status':'active','expires_on':'2026-10-19T23:59:59Z','id':'SECRET_TOKEN_ID'}),{}))
  binding=[{'type':'d1','name':'DB','id':'18050cf6-934e-4f3a-a1cd-5041bac1c35e'}]+[{'type':'plain_text','name':k,'text':'true'} for k in c.FLAGS]
  source=(ROOT/c.BUNDLE).read_bytes() if post else (ROOT/'serverless/bootstrap-placeholder.mjs').read_bytes()
  self.responses += [(200,source,{'content_type':'application/javascript+module'}),(200,raw({'bindings':binding}),{}),(200,raw({'schedules':[]}),{}),(200,raw([],result_info={'count':0,'total_count':0,'page':1,'per_page':20,'total_pages':1}),{}),(200,raw({'enabled':False,'previews_enabled':False}),{}),(200,raw([]),{}),(200,raw([]),{})]
  if not post:self.responses.append((200,raw({'id':c.WORKER},errors=[]),{}))
  if change:
   index,value=change;self.responses[index]=value
 def permit(self,cap):self.budget.permit(cap)
 def __call__(self,m,p,*args):
  self.budget.admit(m,p);self.calls.append((m,p));r=self.responses[len(self.calls)-1]
  if isinstance(r,Exception):raise r
  return r
class DeployTests(unittest.TestCase):
 def runit(self,change=None):t=Fake(change=change);return c.execute(d.SPEC,t,files(d.SPEC),NOW),t
 def test_collect_git_facts_full_onecommit_future_chain(self):
  a=fixture(d.SPEC);marker=a[3];prepared=marker['prepared_commit_sha'];before=a[1]['before'];head=a[1]['after']
  commands={('rev-parse','--is-shallow-repository'):'false',('merge-base',c.PARENT,prepared):c.PARENT,('rev-list','--count',c.PARENT+'..'+prepared):'1',('diff','--name-only',c.PARENT,prepared):'\n'.join(a[2]['preparation_files']),('rev-parse','HEAD'):head,('rev-parse','HEAD^'):before,('diff','--name-only',before,'HEAD'):d.SPEC['marker'],('log','-1','--format=%B'):d.SPEC['message']}
  for path in d.SPEC['immutable']:
   for commit in (c.PARENT,prepared,'HEAD'):commands[('show',commit+':'+path)]=(ROOT/path).read_text()
  facts=c.collect_facts(d.SPEC,before,marker,lambda *x:commands[x],lambda x:False)
  c.validate_gate(d.SPEC,a[0],a[1],facts,marker,a[4])
 def test_expiry_rechecked_immediately_before_write(self):
  t=Fake()
  with patch.object(c,'datetime') as clock:
   clock.now.side_effect=[NOW,datetime(2026,10,20,tzinfo=timezone.utc)]
   o=c.execute(d.SPEC,t,files(d.SPEC))
  self.assertEqual(o['script_writes_attempted'],0);self.assertEqual(len(t.calls),8);self.assertIn('TOKEN_EXPIRED_STOP',o['reason_codes'])
 def test_gate_pass_exact_plan(self):c.validate_gate(d.SPEC,*fixture(d.SPEC))
 def test_exact_one_preparation_commit(self):
  for count in (0,2,12):a=fixture(d.SPEC);a[2]['count']=count;self.assertRaises(c.Stop,c.validate_gate,d.SPEC,*a)
 def test_actual_diff_missing_extra_stop(self):
  for fn in (lambda x:x[:-1],lambda x:sorted(x+['unexpected.py']),lambda x:x+[x[-1]],lambda x:['../escape']):
   a=fixture(d.SPEC);a[2]['preparation_files']=fn(a[2]['preparation_files']);self.assertRaises(c.Stop,c.validate_gate,d.SPEC,*a)
 def test_plan_list_duplicate_traversal_marker_stop(self):
  for x in [['a','a'],['../escape'],['audit-evidence/consumed/unapproved.json'],['z','a'],['/absolute'],['a\\b']]:self.assertRaises(c.Stop,c.filelist,x)
 def test_deploy_and_future_markers_absent(self):self.assertFalse((ROOT/c.OLD_MARKER).exists());self.assertFalse((ROOT/d.SPEC['marker']).exists())
 def test_historical_consumed_exact_unchanged(self):
  for p,h in d.SPEC['historical'].items():self.assertEqual(c.sha((ROOT/p).read_bytes()),h)
 def test_historical_marker_drift_stop(self):
  a=fixture(d.SPEC);a[2]['historical_hashes']=copy.deepcopy(a[2]['historical_hashes']);p=next(iter(a[2]['historical_hashes']));a[2]['historical_hashes'][p]['head']='bad';self.assertRaises(c.Stop,c.validate_gate,d.SPEC,*a)
 def test_old_identities_rejected(self):
  for identity in [c.old.IDENTITY,*[json.loads((ROOT/p).read_bytes())['identity'] for p in d.SPEC['historical']]]:
   a=fixture(d.SPEC);a[3]['identity']=identity;self.assertRaises(c.Stop,c.validate_gate,d.SPEC,*a)
 def test_operational_exclusion_explicit_required(self):
  for value in (False,None,'true'):
   a=fixture(d.SPEC);a[3]['operational_exclusion_attested']=value;self.assertRaises(c.Stop,c.validate_gate,d.SPEC,*a)
 def test_attempt2_rejected(self):a=fixture(d.SPEC);a[0]['GITHUB_RUN_ATTEMPT']='2';self.assertRaises(c.Stop,c.validate_gate,d.SPEC,*a)
 def test_marker_preexisted_rejected(self):a=fixture(d.SPEC);a[2]['marker_preexisted']=True;self.assertRaises(c.Stop,c.validate_gate,d.SPEC,*a)
 def test_old_deploy_marker_anywhere_stop(self):
  for k in ('root','prepared','head','worktree'):a=fixture(d.SPEC);a[2]['old_deploy_absent'][k]=False;self.assertRaises(c.Stop,c.validate_gate,d.SPEC,*a)
 def test_shallow_rejected(self):self.assertRaises(c.Stop,c.collect_facts,d.SPEC,'a'*40,{'prepared_commit_sha':'a'*40},lambda *a:'true',lambda s:False)
 def test_full_history_required(self):a=fixture(d.SPEC);a[2]['full_history']=False;self.assertRaises(c.Stop,c.validate_gate,d.SPEC,*a)
 def test_source_hash_drift_gate_stop(self):
  for p in d.SPEC['pins'].values():a=fixture(d.SPEC);a[4][p]+=b' ';self.assertRaises(c.Stop,c.validate_gate,d.SPEC,*a)
 def test_success_exact9_requests_onePUT(self):
  o,t=self.runit();self.assertEqual(o['classification'],c.ACK);self.assertEqual(o['requests_attempted'],9);self.assertEqual(o['audit_GETs'],7);self.assertEqual(o['token_verify_GETs'],1);self.assertEqual(o['script_writes_attempted'],1);self.assertEqual(t.calls[-1],('PUT',c.old.PUT));self.assertTrue(o['postcheck_required'])
 def test_each_pre_gate_failure_writes0(self):
  for i in range(8):o,t=self.runit((i,(403,b'{"errors":[{"code":10000,"message":"SECRET_TEXT"}]}',{})));self.assertEqual(o['script_writes_attempted'],0);self.assertEqual(len(t.calls),i+1);self.assertEqual(o['classification'],'FRESH_PRE_GATE_STOP');self.assertNotIn('SECRET_TEXT',json.dumps(o))
 def test_fresh_token_inactive_stop(self):o,t=self.runit((0,(200,raw({'status':'disabled'}),{})));self.assertEqual(len(t.calls),1);self.assertEqual(o['script_writes_attempted'],0)
 def test_finite_future_expiry_required(self):
  for r in [{'status':'active'},{'status':'active','expires_on':'2026-10-11T00:00:00Z'},{'status':'active','expires_on':'bad'}]:o,t=self.runit((0,(200,raw(r),{})));self.assertEqual(o['script_writes_attempted'],0);self.assertEqual(len(t.calls),1)
 def test_source_drift_before_write(self):o,t=self.runit((1,(200,b'export default {};',{'content_type':'application/javascript'})));self.assertEqual(o['script_writes_attempted'],0);self.assertIn('SOURCE_DRIFT_STOP_NO_DEPLOY',o['reason_codes'])
 def test_wrongDB_rejected(self):o,t=self.runit((2,(200,raw({'bindings':[{'type':'d1','name':'DB','id':'wrong'}]}),{})));self.assertEqual(o['script_writes_attempted'],0)
 def test_unsafe_flags_rejected(self):o,t=self.runit((2,(200,raw({'bindings':[{'type':'d1','name':'DB','id':'18050cf6-934e-4f3a-a1cd-5041bac1c35e'},{'name':'DRY_RUN','type':'plain_text','text':'false'}]}),{})));self.assertEqual(o['script_writes_attempted'],0)
 def test_cron_active_stop(self):o,t=self.runit((3,(200,raw({'schedules':[{'cron':'* * * * *'}]}),{})));self.assertEqual(o['script_writes_attempted'],0)
 def test_queues_incomplete_stop(self):o,t=self.runit((4,(200,raw([]),{})));self.assertEqual(o['script_writes_attempted'],0)
 def test_workersdev_active_stop(self):o,t=self.runit((5,(200,raw({'enabled':True,'previews_enabled':False}),{})));self.assertEqual(o['script_writes_attempted'],0)
 def test_domain_present_stop(self):o,t=self.runit((6,(200,raw([{'id':'x','service':c.WORKER}]),{})));self.assertEqual(o['script_writes_attempted'],0)
 def test_zone_present_stop(self):o,t=self.runit((7,(200,raw([{'id':'a'*32,'account':{'id':c.ACCOUNT}}]),{})));self.assertEqual(o['script_writes_attempted'],0)
 def test_UNKNOWN_no_resend(self):
  for value in (TimeoutError('SECRET_TEXT'),(500,b'SECRET_TEXT',{}),(200,b'{}',{}),(200,raw({'id':'wrong'},errors=[]),{})):
   o,t=self.runit((8,value));self.assertEqual(o['classification'],'DEPLOY_UNKNOWN_STOP_NO_RETRY');self.assertEqual(o['script_writes_attempted'],1);self.assertEqual(len(t.calls),9);self.assertEqual(o['resend'],0);self.assertEqual(o['rollback'],0)
 def test_second_write_or_other_methods_impossible(self):
  _,t=self.runit()
  for m,p in [('PUT',c.old.PUT),('POST',c.old.PUT),('PATCH',c.old.PUT),('DELETE',c.old.PUT),('GET',c.VERIFY)]:self.assertRaises(c.Stop,t.budget.admit,m,p)
 def test_put_requires_preflight_capability(self):b=c.Budget(False);self.assertRaises(c.Stop,b.admit,'PUT',c.old.PUT);self.assertRaises(c.Stop,b.permit,object())
 def test_credential_distinct_required(self):self.assertRaises(c.Stop,c.Transport,'SAME','SAME',capability=c._CAPABILITY)
 def test_missing_credentials_remote0(self):
  for read,write in [(None,'x'),('x',None),('','x')]:self.assertRaises(c.Stop,c.Transport,read,write,capability=c._CAPABILITY)
 def test_transport_requires_local_gate(self):self.assertRaises(c.Stop,c.Transport,'x','y')
 def test_no_secrets_raw_tokenID_emitted(self):
  o,_=self.runit();s=json.dumps(o)
  for val in ('SECRET_TOKEN_ID','SECRET_TEXT','Authorization','Bearer','source_response_sha256','source_response_bytes'):self.assertNotIn(val,s)
  for k in c.ZERO:self.assertEqual(o[k],0)
 def test_gate_failure_before_secret_transport(self):
  with patch.object(d,'load_gate',side_effect=c.Stop('LOCAL_GATE_STOP')),patch.object(c,'Transport') as t,patch('builtins.print') as p:d.main();t.assert_not_called();self.assertEqual(json.loads(p.call_args.args[0])['requests_attempted'],0)
 def test_workflow_marker_only_credentials_aftergate(self):
  s=(ROOT/d.SPEC['workflow']).read_text();self.assertIn('fetch-depth: 0',s);self.assertIn('persist-credentials: false',s);self.assertNotIn('workflow_dispatch',s);self.assertLess(s.index('load_gate()'),s.index('secrets.PLM_CF_WORKER_DEPLOY_TOKEN'));self.assertIn("if: steps.replacement.outputs.acknowledged == 'true'",s);self.assertNotIn(c.OLD_MARKER,s)
 def test_actual_transport_roles_exact_no_extra_target(self):
  sent=[];fake=Fake();responses=list(fake.responses)
  class Socket:
   def settimeout(self,x):pass
  class Response:
   def __init__(self,data):self.status,self.raw,self.meta=data
   def read1(self,n):b=self.raw[:n];self.raw=self.raw[n:];return b
   def getheader(self,k):return self.meta.get('content_type','') if k=='Content-Type' else None
  class Connection:
   def __init__(self,host,timeout):self.sock=Socket();self.host=host
   def connect(self):pass
   def request(self,m,path,body=None,headers=None):sent.append((self.host,m,path,headers['Authorization']))
   def getresponse(self):return Response(responses[len(sent)-1])
   def close(self):pass
  with patch('http.client.HTTPSConnection',Connection):
   t=c.Transport('FIXTURE_READ_ONLY','FIXTURE_DEPLOY_ONLY',capability=c._CAPABILITY);o=c.execute(d.SPEC,t,files(d.SPEC),NOW)
  self.assertEqual(o['classification'],c.ACK);self.assertEqual(len(sent),9)
  self.assertEqual(sent[0][3],'Bearer FIXTURE_DEPLOY_ONLY');self.assertEqual(sent[-1][3],'Bearer FIXTURE_DEPLOY_ONLY')
  self.assertTrue(all(r[3]=='Bearer FIXTURE_READ_ONLY' for r in sent[1:-1]));self.assertTrue(all(r[0]=='api.cloudflare.com' for r in sent));self.assertNotIn('FIXTURE_',json.dumps(o))
 def test_expected_metadata_parked(self):
  m=c.old.upload_metadata();self.assertEqual(m['keep_bindings'],[]);self.assertEqual(m['main_module'],'runtime-bundle.mjs');self.assertEqual(len(m['bindings']),5)
if __name__=='__main__':unittest.main()
