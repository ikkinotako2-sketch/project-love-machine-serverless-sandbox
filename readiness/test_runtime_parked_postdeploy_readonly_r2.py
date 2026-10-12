"""Read-only postcheck and prerequisite ACK regressions; all HTTP mocked."""
import copy,json,unittest
from pathlib import Path
from unittest.mock import patch
try:
 from readiness import runtime_parked_postdeploy_readonly_r2 as p
 from readiness.test_runtime_parked_deploy_r2 import c,ROOT,NOW,Fake,files,fixture,raw
except ModuleNotFoundError:
 import runtime_parked_postdeploy_readonly_r2 as p
 from test_runtime_parked_deploy_r2 import c,ROOT,NOW,Fake,files,fixture,raw
class PostcheckTests(unittest.TestCase):
 def runit(self,change=None):t=Fake(post=True,change=change);return c.execute(p.SPEC,t,files(p.SPEC),NOW),t
 def prerequisite(self):
  marker={'prerequisite_run_id':42,'prerequisite_commit_sha':'c'*40}
  run={'id':42,'run_attempt':1,'status':'completed','conclusion':'success','event':'push','head_sha':'c'*40,'head_branch':c.BRANCH.split('/')[-1],'path':p.SPEC['deploy_workflow'],'repository':{'full_name':c.REPO}}
  jobs={'total_count':1,'jobs':[{'name':'deploy','run_id':42,'status':'completed','conclusion':'success','steps':[{'name':c.ACK,'status':'completed','conclusion':'success'}]}]};return marker,run,jobs,p.SPEC['deploy_workflow']
 def test_collect_exact_prepared_deploy_postcheck_chain(self):
  a=fixture(p.SPEC);marker=a[3];prepared=marker['prepared_commit_sha'];before=a[1]['before'];head=a[1]['after'];dp=p.SPEC['deploy_marker']
  dm={k:c.sha((ROOT/path).read_bytes()) for k,path in p.SPEC['deploy_pins'].items()};dm.update(identity=c.DEPLOY_ID,state='CONSUMED_BEFORE_REMOTE',prepared_commit_sha=prepared,operational_exclusion_attested=True)
  commands={('rev-parse','--is-shallow-repository'):'false',('merge-base',c.PARENT,prepared):c.PARENT,('rev-list','--count',c.PARENT+'..'+prepared):'1',('diff','--name-only',c.PARENT,prepared):'\n'.join(a[2]['preparation_files']),('rev-parse','HEAD'):head,('rev-parse','HEAD^'):before,('diff','--name-only',before,'HEAD'):p.SPEC['marker'],('log','-1','--format=%B'):p.SPEC['message'],('rev-parse',before+'^'):prepared,('diff','--name-only',prepared,before):dp,('log','-1','--format=%B',before):'PLM runtime parked deploy once '+c.DEPLOY_ID,('show',before+':'+dp):json.dumps(dm)}
  for path in p.SPEC['immutable']:
   for commit in (c.PARENT,prepared,'HEAD'):commands[('show',commit+':'+path)]=(ROOT/path).read_text()
  facts=c.collect_facts(p.SPEC,before,marker,lambda *x:commands[x],lambda x:False)
  c.validate_gate(p.SPEC,a[0],a[1],facts,marker,a[4])
 def test_gate_pass_real_preparation_plan(self):c.validate_gate(p.SPEC,*fixture(p.SPEC))
 def test_future_marker_absent(self):self.assertFalse((ROOT/p.SPEC['marker']).exists());self.assertFalse((ROOT/c.OLD_MARKER).exists())
 def test_deploy_marker_chain_required(self):a=fixture(p.SPEC);a[2]['deploy_marker_chain']=False;self.assertRaises(c.Stop,c.validate_gate,p.SPEC,*a)
 def test_prerequisite_commit_exact(self):a=fixture(p.SPEC);a[3]['prerequisite_commit_sha']='wrong';self.assertRaises(c.Stop,c.validate_gate,p.SPEC,*a)
 def test_prerequisite_actual_ACK_PASS(self):self.assertTrue(c.check_prerequisite(*self.prerequisite()))
 def test_prerequisite_attempt2_failed_running_wronghead_stop(self):
  for k,v in [('run_attempt',2),('conclusion','failure'),('status','in_progress'),('head_sha','wrong'),('path','wrong'),('id',43)]:a=self.prerequisite();a[1][k]=v;self.assertRaises(c.Stop,c.check_prerequisite,*a)
 def test_success_conclusion_without_ACK_stop(self):
  for v in ('skipped','failure',None):a=self.prerequisite();a[2]['jobs'][0]['steps'][0]['conclusion']=v;self.assertRaises(c.Stop,c.check_prerequisite,*a)
 def test_ambiguous_ACK_duplicate_rejected(self):a=self.prerequisite();a[2]['jobs'][0]['steps']*=2;self.assertRaises(c.Stop,c.check_prerequisite,*a)
 def test_job_run_provenance_exact(self):a=self.prerequisite();a[2]['jobs'][0]['run_id']=43;self.assertRaises(c.Stop,c.check_prerequisite,*a)
 def test_incomplete_jobs_rejected(self):a=self.prerequisite();a[2]['total_count']=2;self.assertRaises(c.Stop,c.check_prerequisite,*a)
 def test_exact7readonly_success(self):o,t=self.runit();self.assertEqual(o['classification'],c.POST_SUCCESS);self.assertEqual(o['requests_attempted'],7);self.assertEqual(o['script_writes_attempted'],0);self.assertEqual(t.calls,[('GET',x) for x in c.AUDIT_GETS]);self.assertTrue(o['safe_flags_exact'])
 def test_every_failure_readonly_stop(self):
  for index in range(7):o,t=self.runit((index,(403,b'SECRET_TEXT',{})));self.assertEqual(o['script_writes_attempted'],0);self.assertEqual(len(t.calls),index+1);self.assertNotEqual(o['classification'],c.POST_SUCCESS)
 def test_postsource_drift_rejected(self):o,t=self.runit((0,(200,(ROOT/'serverless/bootstrap-placeholder.mjs').read_bytes(),{'content_type':'application/javascript'})));self.assertNotEqual(o['classification'],c.POST_SUCCESS)
 def test_missing_safe_flags_stop(self):o,t=self.runit((1,(200,raw({'bindings':[{'type':'d1','name':'DB','id':'18050cf6-934e-4f3a-a1cd-5041bac1c35e'}]}),{})));self.assertNotEqual(o['classification'],c.POST_SUCCESS)
 def test_secret_binding_forbidden_no_value_output(self):o,t=self.runit((1,(200,raw({'bindings':[{'type':'secret_text','name':'UNKNOWN','text':'SECRET_TEXT'}]}),{})));self.assertNotIn('SECRET_TEXT',json.dumps(o));self.assertNotEqual(o['classification'],c.POST_SUCCESS)
 def test_no_write_credential_or_methods(self):self.assertRaises(c.Stop,c.Transport,'x','y',post=True,capability=c._CAPABILITY);b=c.Budget(True);self.assertRaises(c.Stop,b.admit,'PUT',c.old.PUT);self.assertRaises(c.Stop,b.admit,'GET',c.VERIFY)
 def test_secondwindow_extra_request_forbidden(self):_,t=self.runit();self.assertRaises(c.Stop,t.budget.admit,'GET',c.AUDIT_GETS[0])
 def test_no_side_effects(self):o,_=self.runit();self.assertTrue(all(o[k]==0 for k in c.ZERO));self.assertEqual(o['token_verify_GETs'],0)
 def test_workflow_prereqbeforeWorker_credentials(self):
  s=(ROOT/p.SPEC['workflow']).read_text();self.assertLess(s.index('load_gate()'),s.index('github.token'));self.assertLess(s.index('c.github_prerequisite'),s.index('secrets.PLM_CF_WORKER_API_TOKEN'));self.assertNotIn('secrets.PLM_CF_WORKER_DEPLOY_TOKEN',s);self.assertIn("if: steps.prerequisite.outputs.verified == 'true'",s);self.assertIn('actions: read',s)
 def test_main_refuses_missing_prerequisite_step_binding(self):
  with patch.object(p,'load_gate',return_value=(files(p.SPEC),fixture(p.SPEC)[3])),patch.object(c,'Transport') as t,patch('builtins.print') as out:p.main();t.assert_not_called();self.assertEqual(json.loads(out.call_args.args[0])['requests_attempted'],0)
 def test_GitHub_prerequisite_exact2GET_no_redirect(self):
  marker,run,jobs,_=self.prerequisite();responses=[json.dumps(run).encode(),json.dumps(jobs).encode()];sent=[]
  class Socket:
   def settimeout(self,x):pass
  class Response:
   status=200
   def __init__(self,body):self.body=body
   def read1(self,n):b=self.body[:n];self.body=self.body[n:];return b
  class Connection:
   def __init__(self,host,timeout):self.host=host;self.sock=Socket()
   def connect(self):pass
   def request(self,m,path,headers):sent.append((self.host,m,path))
   def getresponse(self):return Response(responses[len(sent)-1])
   def close(self):pass
  with patch('http.client.HTTPSConnection',Connection):self.assertTrue(c.github_prerequisite(p.SPEC,marker,'FIXTURE_GITHUB_READ'))
  self.assertEqual(sent,[('api.github.com','GET','/repos/'+c.REPO+'/actions/runs/42'),('api.github.com','GET','/repos/'+c.REPO+'/actions/runs/42/jobs?per_page=10')])
 def test_remote_js_never_evaluated(self):s=(ROOT/c.COMMON).read_text();self.assertNotIn('eval(',s);self.assertNotIn('exec(',s);self.assertNotIn('importlib',s)
if __name__=='__main__':unittest.main()
