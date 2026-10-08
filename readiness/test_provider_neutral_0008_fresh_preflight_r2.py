import copy,contextlib,io,json,sqlite3,unittest
from pathlib import Path
from unittest.mock import patch
from oracle_bridge import require_guard
require_guard()
import provider_neutral_0008_fresh_preflight_r2 as p
ROOT=Path(__file__).resolve().parents[1]
NOW=1791295200
EXP='2026-10-07T00:00:00Z'
def fixtures():
 b,a=p.load_candidate(ROOT);q=p.queries(b)
 rows=[]
 for spec in q:
  out=copy.deepcopy(spec['expected'])
  for k in ('columns_json','indexes_json'):
   if k in out:out[k]=json.dumps(out[k])
  rows.append({'success':True,'results':[out],'meta':{'served_by_primary':True,'rows_written':0,'changed_db':False,'changes':0}})
 bookmark={'bookmark':'00000001-00000002-00004e2f-0123456789abcdef'}
 results=[{'id':'a'*32,'status':'active','expires_on':EXP},[{'uuid':p.DB,'name':p.NAME}],{'uuid':p.DB,'name':p.NAME,'file_size':b['database_size_bytes']},bookmark]+[[r] for r in rows]+[bookmark]
 responses=[{'success':True,'result':copy.deepcopy(r),'unwanted':'never-retain-fixture'} for r in results]
 responses[1]['result_info']={'page':1,'count':1,'total_count':1,'per_page':100}
 calls=[]
 def transport(*args):calls.append(args);return 200,json.dumps(responses[len(calls)-1]).encode()
 return b,a,responses,transport,calls
class FreshPreflightR2Tests(unittest.TestCase):
 def test_four_raw_hashes(self):
  p.load_candidate(ROOT)
  for path,h in p.PINS.items():self.assertEqual(p.sha((ROOT/path).read_bytes()),h)
 def test_query_sqlite_e2e_exact(self):
  b,_=p.load_candidate(ROOT);conn=sqlite3.connect(':memory:');conn.row_factory=sqlite3.Row
  for row in b['schema']:
   if row['type']=='table':conn.execute(row['sql'])
  for t,rows in b['protected_rows'].items():
   for row in rows:
    conn.execute('INSERT INTO '+p.ident(t)+' ('+','.join(p.ident(k) for k in row)+') VALUES ('+','.join('?' for _ in row)+')',list(row.values()))
  for row in b['schema']:
   if row['type']=='trigger':conn.execute(row['sql'])
  for q in p.queries(b):p.compare_query(q,[dict(row) for row in conn.execute(q['sql'],q['params']).fetchall()])
  # A real deleted protected row must fail the same readonly SQL proof.
  conn.execute('DELETE FROM plm_rt_v1_effect WHERE kind=?',('GENERATION',))
  spec=next(q for q in p.queries(b) if q['kind']=='rows:plm_rt_v1_effect')
  with self.assertRaises(p.Stop):p.compare_query(spec,[dict(row) for row in conn.execute(spec['sql'],spec['params']).fetchall()])
  conn.close()
 def test_success_bound(self):
  b,a,responses,transport,calls=fixtures();out=p.preflight(transport,b,NOW,history={'complete':True,'prior_send':0})
  self.assertTrue(out['pass']);self.assertEqual(len(calls),16);self.assertEqual(out['candidate_classification'],'NOT_APPLIED');self.assertEqual(out['worker_bundle_equality'],'UNVERIFIED')
 def test_classification_reject(self):
  self.assertEqual(p.classifier(0),'NOT_APPLIED')
  for value,total,expected in [(16,45,'FULL_APPLIED'),(1,30,'PARTIAL_APPLIED'),(None,None,'STILL_UNKNOWN')]:self.assertEqual(p.classifier(value,total),expected)
  q=p.queries(p.load_candidate(ROOT)[0])[0]
  for value in (16,1,None):
   row=dict(q['expected'],candidate=value)
   with self.assertRaises(p.Stop):p.compare_query(q,[row])
 def test_second_application_stop(self):
  b,a,responses,transport,calls=fixtures();responses[4]['result'][0]['results'][0]['candidate']=16
  out=p.preflight(transport,b,NOW,history={'complete':True,'prior_send':0});self.assertFalse(out['pass']);self.assertEqual(len(calls),5)
 def test_protected_row_or_schema_drift(self):
  for i in (4,5,9,14):
   b,a,responses,transport,calls=fixtures();responses[i]['result'][0]['results'][0]['total']+=1
   out=p.preflight(transport,b,NOW,history={'complete':True,'prior_send':0});self.assertFalse(out['pass']);self.assertEqual(len(calls),i+1)
 def test_deleted_changed_row_count(self):
  q=p.queries(p.load_candidate(ROOT)[0])[1];self.assertIn('r0',q['expected'])
  for value in (0,2):
   row=copy.deepcopy(q['expected']);row['r0']=value
   for k in ('columns_json','indexes_json'):row[k]=json.dumps(row[k])
   with self.assertRaises(p.Stop):p.compare_query(q,[row])
 def test_metadata_drift(self):
  q=p.queries(p.load_candidate(ROOT)[0])[1];row=copy.deepcopy(q['expected']);row['columns_json']='[]';row['indexes_json']=json.dumps(row['indexes_json'])
  with self.assertRaises(p.Stop):p.compare_query(q,[row])
 def test_readonly_sql_no_raw_rows(self):
  b,_=p.load_candidate(ROOT)
  for q in p.queries(b):
   self.assertTrue(q['sql'].startswith('SELECT '));self.assertNotIn('SELECT * FROM "',q['sql']);self.assertNotIn('FROM "_cf_KV"',q['sql'])
   self.assertLessEqual(len(q['params']),100);self.assertLessEqual(len(q['sql'].encode()),100000)
 def test_backend_verify_only(self):
  b,_=p.load_candidate(ROOT);calls=[];gate=p.Gate(lambda *a:calls.append(a),p.request_specs(b))
  with self.assertRaises(p.Stop):gate.call('backend','POST',p.TARGET+'/query',{'sql':'SELECT 1','params':[]})
  self.assertEqual(calls,[])
  with patch.object(p,'bounded_http') as http:
   send=p.live_transport('read-fixture','backend-fixture',b)
   with self.assertRaises(p.Stop):send('backend','POST',p.TARGET+'/query',{'sql':'SELECT 1','params':[]})
   http.assert_not_called()
 def test_read_mutation_rejected(self):
  b,_=p.load_candidate(ROOT)
  with patch.object(p,'bounded_http') as http:
   send=p.live_transport('read-fixture','backend-fixture',b)
   for method,path,body in [('POST',p.TARGET+'/query',{'sql':'DELETE FROM test_jobs','params':[]}),('POST',p.TARGET+'/import',{}),('DELETE',p.TARGET,None)]:
    with self.assertRaises(p.Stop):send('read',method,path,body)
   http.assert_not_called()
 def test_inactive_expiry_binding(self):
  for change in ({'status':'inactive'},{'expires_on':None},{'expires_on':'2026-01-01T00:00:00Z'},{'id':'BAD'},{'expires_on':'not-a-timestamp'}):
   b,a,responses,transport,calls=fixtures();responses[0]['result'].update(change)
   out=p.preflight(transport,b,NOW,history={'complete':True,'prior_send':0});self.assertFalse(out['pass']);self.assertEqual(len(calls),1)
 def test_token_expired_during_audit(self):
  b,a,r,t,c=fixtures();out=p.preflight(t,b,NOW,history={'complete':True,'prior_send':0},clock=lambda:NOW+86400*3);self.assertFalse(out['pass'])
 def test_prior_send_consumed_stop(self):
  for name in ['audit-evidence/provider-neutral-backend-sent-x.json','audit-evidence/0008-unknown-receipt.json','audit-evidence/consumed/provider-neutral-0008-old.json']:
   with self.assertRaises(p.Stop):p.prior_check([name])
 def test_history_complete_and_no_prior(self):
  self.assertEqual(p.history_check([{'total_count':0,'workflow_runs':[]}])['prior_send'],0)
  for pages in [[{'total_count':1,'workflow_runs':[]}],[{'total_count':1,'workflow_runs':[{'id':1,'path':'.github/workflows/plm-provider-neutral-backend-migration-once.yml'}]}]]:
   with self.assertRaises(p.Stop):p.history_check(pages)
 def test_bookmark_required_unchanged(self):
  for i,bookmark in [(3,None),(15,'0'*32)]:
   b,a,r,t,c=fixtures();r[i]['result']['bookmark']=bookmark
   out=p.preflight(t,b,NOW,history={'complete':True,'prior_send':0});self.assertFalse(out['pass'])
 def test_inventory_ambiguous(self):
  b,a,r,t,c=fixtures();r[1]['result_info']['total_count']=2
  out=p.preflight(t,b,NOW,history={'complete':True,'prior_send':0});self.assertFalse(out['pass']);self.assertEqual(len(c),2)
 def test_write_metadata_stop(self):
  b,a,r,t,c=fixtures();r[4]['result'][0]['meta']['rows_written']=1
  out=p.preflight(t,b,NOW,history={'complete':True,'prior_send':0});self.assertFalse(out['pass']);self.assertEqual(len(c),5)
 def test_response_bounds_duplicate(self):
  for raw in (b'x'*(p.MAX_BYTES+1),b'{"success":true,"success":true}'):
   with self.assertRaises(p.Stop):p.decode(raw)
 def test_timeout_no_retry(self):
  b,_=p.load_candidate(ROOT);calls=[]
  def t(*args):calls.append(args);raise TimeoutError('never-retain-fixture')
  gate=p.Gate(t,p.request_specs(b))
  with self.assertRaisesRegex(p.Stop,'TRANSPORT_UNKNOWN_NO_RETRY'):gate.call(*gate.specs[0])
  with self.assertRaises(p.Stop):gate.call(*gate.specs[1])
  self.assertEqual(len(calls),1)
 def test_http_error_stops(self):
  b,_=p.load_candidate(ROOT)
  for status in (403,404,302):
   calls=[]
   def t(*a):calls.append(a);return status,b'never-retain-fixture'
   out=p.preflight(t,b,NOW,history={'complete':True,'prior_send':0});self.assertFalse(out['pass']);self.assertEqual(len(calls),1)
 def test_secret_never_logged(self):
  b,a,r,t,c=fixtures();stdout=io.StringIO()
  with contextlib.redirect_stdout(stdout):out=p.preflight(t,b,NOW,history={'complete':True,'prior_send':0})
  self.assertEqual(stdout.getvalue(),'');self.assertNotIn('never-retain-fixture',json.dumps(out));self.assertNotIn('protected_rows',out)
 def test_credential_missing(self):
  b,_=p.load_candidate(ROOT)
  for read,backend in [(None,'fixture'),('fixture',None),('',''),('same-fixture','same-fixture')]:
   with self.assertRaises(p.Stop):p.live_transport(read,backend,b)
 def test_request_budget(self):
  b,a,r,t,c=fixtures();gate=p.Gate(t,p.request_specs(b))
  for spec in gate.specs:gate.call(*spec)
  with self.assertRaises(p.Stop):gate.call(*gate.specs[0])
  self.assertEqual(gate.count,16);self.assertEqual(sum(s[0]=='read' for s in gate.specs),15)
 def test_marker_binding(self):
  files={path:(ROOT/path).read_bytes() for path in (p.PLAN,p.WORKFLOW,p.HELPER,p.SCHEMA)};plan=json.loads(files[p.PLAN]);before='1'*40
  marker={'identity':p.IDENTITY,'state':'CONSUMED_BEFORE_REMOTE','prepared_commit_sha':before,'candidate_raw_hashes':p.PINS,**{key:p.sha(files[path]) for key,path in [('workflow_sha256',p.WORKFLOW),('helper_sha256',p.HELPER),('preflight_plan_sha256',p.PLAN)]}}
  p.marker_check(marker,plan,before,files)
  for identity in ['provider-neutral-0008-fresh-readonly-preflight-20261006-r1','004H','youtube-worker-current-readonly-inspect-20261006-r1','youtube-cloudflare-credential-policy-readonly-20261006-r2']:
   with self.assertRaises(p.Stop):p.marker_check(dict(marker,identity=identity),plan,before,files)
  bad=copy.deepcopy(marker);bad['candidate_raw_hashes'][next(iter(p.PINS))]='0'*64
  with self.assertRaises(p.Stop):p.marker_check(bad,plan,before,files)
 def test_worker_migrations_marker_workflow(self):
  plan=json.loads((ROOT/p.PLAN).read_bytes());self.assertEqual(plan['worker_evidence']['bundle_equality'],'UNVERIFIED');self.assertEqual(plan['worker_evidence']['new_Worker_GETs'],0)
  for name in ('0009','0010'):self.assertEqual(plan['migrations'][name],'NOT_APPLIED')
  self.assertEqual(json.loads((ROOT/p.MARKER).read_bytes())['prepared_commit_sha'],'2b74f39310bc5dc5a050096434644126673f301e');workflow=(ROOT/p.WORKFLOW).read_text();self.assertNotIn('workflow_dispatch',workflow);self.assertIn('github.run_attempt == 1',workflow);self.assertIn("git('diff','--name-only',before,'HEAD')==MARKER",workflow)
  self.assertNotIn('upload-artifact',workflow)


 def test_self_verified_metadata(self):
  b,a,r,t,c=fixtures();r[0]['result']['id']='b'*32;r[0]['result']['expires_on']='2026-10-09T00:00:00Z'
  out=p.preflight(t,b,NOW,history={'complete':True,'prior_send':0})
  self.assertTrue(out['pass']);self.assertEqual(out['token_id'],'b'*32);self.assertEqual(out['token_type'],'ACCOUNT_OWNED');self.assertFalse(out['scope_api_independently_verified']);self.assertEqual(out['scope_status'],'OWNER_ATTESTED_D1_WRITE_ONLY_NOT_API_VERIFIED')
 def test_invalid_token_ids(self):
  for token_id in [None,'', 'A'*32, 'a'*31, 'a'*33, 'g'*32, 123]:
   b,a,r,t,c=fixtures();r[0]['result']['id']=token_id
   out=p.preflight(t,b,NOW,history={'complete':True,'prior_send':0});self.assertEqual(out['result'],'TOKEN_ID_INVALID_STOP');self.assertEqual(len(c),1)
 def test_finite_expiry(self):
  for exp in [None,'','99999-12-31T00:00:00Z','2026-10-07T00:00:00','infinity']:
   b,a,r,t,c=fixtures();r[0]['result']['expires_on']=exp
   out=p.preflight(t,b,NOW,history={'complete':True,'prior_send':0});self.assertFalse(out['pass']);self.assertEqual(len(c),1)
 def test_r1_consumption_is_not_migration(self):
  p.prior_check([p.PRIOR_PREFLIGHT_MARKER])
  proof=p.history_check([{'total_count':1,'workflow_runs':[{'id':37480012730,'path':'.github/workflows/plm-provider-neutral-0008-fresh-readonly-once.yml'}]}])
  b,a,r,t,c=fixtures();out=p.preflight(t,b,NOW,[p.PRIOR_PREFLIGHT_MARKER],proof);self.assertTrue(out['pass'])
 def test_r1_evidence_exact_and_immutable(self):
  self.assertEqual(p.sha((ROOT/p.PRIOR_PREFLIGHT_MARKER).read_bytes()),p.PRIOR_PREFLIGHT_MARKER_SHA256)
  for path,h in [('readiness/provider_neutral_0008_fresh_preflight.py','da7383336a1752aad9e307cc49bbcbfa9c265920d9b018fec775d730ec7abff1'),('.github/workflows/plm-provider-neutral-0008-fresh-readonly-once.yml','4c2fd33811b999cb295098b9bdc133c52db56d687365860d73ee0df11b2f6072'),('readiness/provider-neutral-0008-fresh-readonly-plan.json','9347e579c68dd4e4a262af88da3ff39f9e9f2496c06ce28f41d4e2e910e323e9'),('readiness/provider-neutral-0008-fresh-readonly-marker.schema.json','166a3fea74ecd6aa59cd948432563598845885b5f18eb8c09e11341b15cec565')]:self.assertEqual(p.sha((ROOT/path).read_bytes()),h)
 def test_explicit_missing_credentials_before_any_io(self):
  env={'GITHUB_REPOSITORY':p.REPO,'GITHUB_REF':'refs/heads/plm-offline-readiness-v1-20261002','GITHUB_EVENT_NAME':'push','GITHUB_RUN_ATTEMPT':'1',**{k:'true' for k in ('TEST_ONLY','DRY_RUN','NO_PUBLISH','EMERGENCY_STOP')}}
  cases=[({},'BACKEND_CREDENTIAL_MISSING_STOP'),({p.BACKEND_SECRET:'backend-fixture'},'CREDENTIAL_MISSING_STOP'),({p.BACKEND_SECRET:'same-fixture',p.READ_SECRET:'same-fixture'},'CREDENTIAL_ROLES_NOT_DISTINCT_STOP')]
  for creds,code in cases:
   output=io.StringIO()
   with patch.dict('os.environ',dict(env,**creds),clear=True),patch.object(p,'bounded_http') as http,patch.object(Path,'read_bytes') as reader,contextlib.redirect_stdout(output):p.main()
   http.assert_not_called();reader.assert_not_called();out=json.loads(output.getvalue());self.assertEqual(out['gate_code'],code);self.assertEqual(out['cloudflare_read_only_calls'],0);self.assertNotIn('fixture',output.getvalue())
 def test_malformed_owner_variable_has_no_execution_effect(self):
  env={'GITHUB_REPOSITORY':p.REPO,'GITHUB_REF':'refs/heads/plm-offline-readiness-v1-20261002','GITHUB_EVENT_NAME':'push','GITHUB_RUN_ATTEMPT':'1','PLM_APPROVED_BEFORE':'1'*40,'PLM_HISTORY_GITHUB_TOKEN':'history-fixture',p.READ_SECRET:'read-fixture',p.BACKEND_SECRET:'backend-fixture',**{k:'true' for k in ('TEST_ONLY','DRY_RUN','NO_PUBLISH','EMERGENCY_STOP')}}
  original=Path.read_bytes;plan_bytes=(ROOT/p.PLAN).read_bytes();prior_bytes=(ROOT/p.PRIOR_PREFLIGHT_MARKER).read_bytes()
  def fake_read(path):
   if str(path)==p.MARKER:return b'{}'
   if str(path)==p.PRIOR_PREFLIGHT_MARKER:return prior_bytes
   return original(ROOT/path)
  before,_=p.load_candidate(ROOT)
  for value in [None,'','{malformed','{"token_id":"bad"}']:
   e=dict(env)
   if value is not None:e['PLM_CF_D1_ROUNDTRIP_BACKEND_OWNER_EVIDENCE']=value
   stdout=io.StringIO()
   with patch.dict('os.environ',e,clear=True),patch.object(Path,'read_bytes',fake_read),patch.object(Path,'rglob',return_value=[Path(p.PRIOR_PREFLIGHT_MARKER)]),patch.object(p,'marker_check'),patch.object(p,'load_candidate',return_value=(before,{})),patch.object(p,'live_transport',return_value=lambda *a:None),patch.object(p,'bounded_http',return_value=(200,b'{"total_count":0,"workflow_runs":[]}')),patch.object(p,'preflight',return_value={'pass':True,'cloudflare_read_only_calls':0}) as preflight,contextlib.redirect_stdout(stdout):p.main()
   preflight.assert_called_once();self.assertTrue(json.loads(stdout.getvalue())['pass']);self.assertNotIn('fixture',stdout.getvalue())
 def test_owner_dependency_absent_from_runtime(self):
  for path in (p.HELPER,p.WORKFLOW,p.PLAN):
   self.assertNotIn('PLM_CF_D1_ROUNDTRIP_BACKEND_OWNER_EVIDENCE',(ROOT/path).read_text())
  self.assertFalse(json.loads((ROOT/p.PLAN).read_bytes())['owner_evidence_variable_required'])
 def test_marker_schema_and_parent(self):
  schema=json.loads((ROOT/p.SCHEMA).read_bytes());self.assertEqual(schema['properties']['identity']['const'],p.IDENTITY);self.assertFalse(schema['additionalProperties'])
  self.assertEqual(p.PARENT,'0a1d29b92044e0d315a23184e14f2596dd719fcc')
  plan=json.loads((ROOT/p.PLAN).read_bytes());self.assertEqual(plan['marker']['state'],'NOT_CREATED_NOT_CONSUMED');self.assertEqual(plan['credential_design'],'VERIFY_SELF_METADATA_NO_MANUAL_TOKEN_ID')
 def test_plan_exact_query_request_manifest(self):
  plan=json.loads((ROOT/p.PLAN).read_bytes());before,_=p.load_candidate(ROOT)
  expected=[{'credential':role,'method':method,'path':path,'body_sha256':None if body is None else p.sha(p.canonical(body).encode())} for role,method,path,body in p.request_specs(before)]
  self.assertEqual(plan['request_sequence'],expected)
  for q,manifest in zip(p.queries(before),plan['readonly_queries']):self.assertEqual(p.sha(q['sql'].encode()),manifest['sql_sha256']);self.assertEqual(p.sha(p.canonical(q['params']).encode()),manifest['params_sha256'])
 def test_query_metadata_all_write_signals_rejected(self):
  for change in [{'changed_db':True},{'changes':1},{'served_by_primary':False},{'rows_written':False}]:
   b,a,r,t,c=fixtures();r[4]['result'][0]['meta'].update(change);out=p.preflight(t,b,NOW,history={'complete':True,'prior_send':0});self.assertEqual(out['result'],'READ_ONLY_RESPONSE_STOP');self.assertEqual(len(c),5)
 def test_prior_migration_stops_before_cloudflare(self):
  b,a,r,t,c=fixtures();out=p.preflight(t,b,NOW,['audit-evidence/0008-migration-sent.json'],{'complete':True,'prior_send':0});self.assertEqual(out['result'],'PRIOR_EXECUTION_NO_RESEND_STOP');self.assertEqual(c,[])
 def test_no_other_product_requests(self):
  b,_=p.load_candidate(ROOT)
  for role,method,path,body in p.request_specs(b):self.assertNotIn('/workers/',path);self.assertNotIn('/queues',path);self.assertNotIn('/routes',path);self.assertNotIn('/import',path)
if __name__=='__main__':unittest.main()
