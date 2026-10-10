import copy,contextlib,io,json,sqlite3,unittest
from pathlib import Path
from unittest.mock import patch
from oracle_bridge import require_guard
require_guard()
import provider_neutral_0008_fresh_preflight_r5 as p
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
class FreshPreflightR5Tests(unittest.TestCase):
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
  b,a,responses,transport,calls=fixtures();out=p.preflight(transport,b,NOW,history={'complete':True,'prior_send':0,'total':0,'pages':1})
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
  out=p.preflight(transport,b,NOW,history={'complete':True,'prior_send':0,'total':0,'pages':1});self.assertFalse(out['pass']);self.assertEqual(len(calls),5)
 def test_protected_row_or_schema_drift(self):
  for i in (4,5,9,14):
   b,a,responses,transport,calls=fixtures();responses[i]['result'][0]['results'][0]['total']+=1
   out=p.preflight(transport,b,NOW,history={'complete':True,'prior_send':0,'total':0,'pages':1});self.assertFalse(out['pass']);self.assertEqual(len(calls),i+1)
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
   out=p.preflight(transport,b,NOW,history={'complete':True,'prior_send':0,'total':0,'pages':1});self.assertFalse(out['pass']);self.assertEqual(len(calls),1)
 def test_token_expired_during_audit(self):
  b,a,r,t,c=fixtures();out=p.preflight(t,b,NOW,history={'complete':True,'prior_send':0,'total':0,'pages':1},clock=lambda:NOW+86400*3);self.assertFalse(out['pass'])
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
   out=p.preflight(t,b,NOW,history={'complete':True,'prior_send':0,'total':0,'pages':1});self.assertFalse(out['pass'])
 def test_inventory_ambiguous(self):
  b,a,r,t,c=fixtures();r[1]['result_info']['total_count']=2
  out=p.preflight(t,b,NOW,history={'complete':True,'prior_send':0,'total':0,'pages':1});self.assertFalse(out['pass']);self.assertEqual(len(c),2)
 def test_write_metadata_stop(self):
  b,a,r,t,c=fixtures();r[4]['result'][0]['meta']['rows_written']=1
  out=p.preflight(t,b,NOW,history={'complete':True,'prior_send':0,'total':0,'pages':1});self.assertFalse(out['pass']);self.assertEqual(len(c),5)
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
   out=p.preflight(t,b,NOW,history={'complete':True,'prior_send':0,'total':0,'pages':1});self.assertFalse(out['pass']);self.assertEqual(len(calls),1)
 def test_secret_never_logged(self):
  b,a,r,t,c=fixtures();stdout=io.StringIO()
  with contextlib.redirect_stdout(stdout):out=p.preflight(t,b,NOW,history={'complete':True,'prior_send':0,'total':0,'pages':1})
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
  for identity in ['provider-neutral-0008-fresh-readonly-preflight-20261008-r3','provider-neutral-0008-fresh-readonly-preflight-20261007-r2','provider-neutral-0008-fresh-readonly-preflight-20261006-r1','004H','youtube-worker-current-readonly-inspect-20261006-r1','youtube-cloudflare-credential-policy-readonly-20261006-r2']:
   with self.assertRaises(p.Stop):p.marker_check(dict(marker,identity=identity),plan,before,files)
  bad=copy.deepcopy(marker);bad['candidate_raw_hashes'][next(iter(p.PINS))]='0'*64
  with self.assertRaises(p.Stop):p.marker_check(bad,plan,before,files)
 def test_worker_migrations_marker_workflow(self):
  plan=json.loads((ROOT/p.PLAN).read_bytes());self.assertEqual(plan['worker_evidence']['bundle_equality'],'UNVERIFIED');self.assertEqual(plan['worker_evidence']['new_Worker_GETs'],0)
  for name in ('0009','0010'):self.assertEqual(plan['migrations'][name],'NOT_APPLIED')
  self.assertEqual(json.loads((ROOT/p.MARKER).read_bytes())['prepared_commit_sha'],'9a5baa706941dd8f9eafa243f9e815ea342a07f3');workflow=(ROOT/p.WORKFLOW).read_text();self.assertNotIn('workflow_dispatch',workflow);self.assertIn('github.run_attempt == 1',workflow);self.assertIn("git('diff','--name-only',before,'HEAD')==MARKER",workflow)
  self.assertNotIn('upload-artifact',workflow)


 def test_self_verified_metadata(self):
  b,a,r,t,c=fixtures();r[0]['result']['id']='b'*32;r[0]['result']['expires_on']='2026-10-09T00:00:00Z'
  out=p.preflight(t,b,NOW,history={'complete':True,'prior_send':0,'total':0,'pages':1})
  self.assertTrue(out['pass']);self.assertEqual(out['token_id'],'b'*32);self.assertEqual(out['token_type'],'ACCOUNT_OWNED');self.assertFalse(out['scope_api_independently_verified']);self.assertEqual(out['scope_status'],'OWNER_ATTESTED_D1_WRITE_ONLY_NOT_API_VERIFIED')
 def test_invalid_token_ids(self):
  for token_id in [None,'', 'A'*32, 'a'*31, 'a'*33, 'g'*32, 123]:
   b,a,r,t,c=fixtures();r[0]['result']['id']=token_id
   out=p.preflight(t,b,NOW,history={'complete':True,'prior_send':0,'total':0,'pages':1});self.assertEqual(out['result'],'TOKEN_ID_INVALID_STOP');self.assertEqual(len(c),1)
 def test_finite_expiry(self):
  for exp in [None,'','99999-12-31T00:00:00Z','2026-10-07T00:00:00','infinity']:
   b,a,r,t,c=fixtures();r[0]['result']['expires_on']=exp
   out=p.preflight(t,b,NOW,history={'complete':True,'prior_send':0,'total':0,'pages':1});self.assertFalse(out['pass']);self.assertEqual(len(c),1)
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
   with patch.dict('os.environ',e,clear=True),patch.object(Path,'read_bytes',fake_read),patch.object(p,'marker_check'),patch.object(Path,'rglob',return_value=[Path(x) for x in p.PRIOR_PREFLIGHT_MARKERS]),patch.object(p,'load_candidate',return_value=(before,{})),patch.object(p,'live_transport',return_value=lambda *a:None),patch.object(p,'bounded_http',return_value=(200,b'{"total_count":0,"workflow_runs":[]}')),patch.object(p,'preflight',return_value={'pass':True,'cloudflare_read_only_calls':0}) as preflight,contextlib.redirect_stdout(stdout):p.main()
   preflight.assert_called_once();self.assertTrue(json.loads(stdout.getvalue())['pass']);self.assertNotIn('fixture',stdout.getvalue())
 def test_owner_dependency_absent_from_runtime(self):
  for path in (p.HELPER,p.WORKFLOW,p.PLAN):
   self.assertNotIn('PLM_CF_D1_ROUNDTRIP_BACKEND_OWNER_EVIDENCE',(ROOT/path).read_text())
  self.assertFalse(json.loads((ROOT/p.PLAN).read_bytes())['owner_evidence_variable_required'])
 def test_marker_schema_and_parent(self):
  schema=json.loads((ROOT/p.SCHEMA).read_bytes());self.assertEqual(schema['properties']['identity']['const'],p.IDENTITY);self.assertFalse(schema['additionalProperties'])
  self.assertEqual(p.PARENT,'44f1454c0367645f42666abbda12840920116560')
  plan=json.loads((ROOT/p.PLAN).read_bytes());self.assertEqual(plan['marker']['state'],'NOT_CREATED_NOT_CONSUMED');self.assertEqual(plan['credential_design'],'VERIFY_SELF_METADATA_NO_MANUAL_TOKEN_ID')
 def test_plan_exact_query_request_manifest(self):
  plan=json.loads((ROOT/p.PLAN).read_bytes());before,_=p.load_candidate(ROOT)
  expected=[{'credential':role,'method':method,'path':path,'body_sha256':None if body is None else p.sha(p.canonical(body).encode())} for role,method,path,body in p.request_specs(before)]
  self.assertEqual(plan['request_sequence'],expected)
  for q,manifest in zip(p.queries(before),plan['readonly_queries']):self.assertEqual(p.sha(q['sql'].encode()),manifest['sql_sha256']);self.assertEqual(p.sha(p.canonical(q['params']).encode()),manifest['params_sha256'])
 def test_query_metadata_all_write_signals_rejected(self):
  for change in [{'changed_db':True},{'changes':1},{'served_by_primary':False},{'rows_written':False}]:
   b,a,r,t,c=fixtures();r[4]['result'][0]['meta'].update(change);out=p.preflight(t,b,NOW,history={'complete':True,'prior_send':0,'total':0,'pages':1});self.assertEqual(out['result'],'READ_ONLY_RESPONSE_STOP');self.assertEqual(len(c),5)
 def test_prior_migration_stops_before_cloudflare(self):
  b,a,r,t,c=fixtures();out=p.preflight(t,b,NOW,['audit-evidence/0008-migration-sent.json'],{'complete':True,'prior_send':0,'total':0,'pages':1});self.assertEqual(out['result'],'PRIOR_EXECUTION_NO_RESEND_STOP');self.assertEqual(c,[])
 def test_no_other_product_requests(self):
  b,_=p.load_candidate(ROOT)
  for role,method,path,body in p.request_specs(b):self.assertNotIn('/workers/',path);self.assertNotIn('/queues',path);self.assertNotIn('/routes',path);self.assertNotIn('/import',path)



def history_pages(total):
 return [{'total_count':total,'workflow_runs':[{'id':i+1,'path':'.github/workflows/plm-offline-readiness.yml'} for i in range(start,min(start+5,total))]} for start in range(0,total,5)] or [{'total_count':0,'workflow_runs':[]}]

class HistoryR4Tests(unittest.TestCase):
 def fetch_fixture(self,pages):
  calls=[]
  def http(host,path,method,headers,body=None):
   calls.append((host,path,method,body));self.assertEqual((host,method,body),('api.github.com','GET',None));self.assertEqual(path,p.HISTORY+str(len(calls)))
   return 200,json.dumps(pages[len(calls)-1]).encode()
  with patch.object(p,'bounded_http',side_effect=http):out=p.fetch_history('fixture-only')
  return out,calls
 def test_exact_per_page_5(self):
  self.assertEqual(p.HISTORY,'/repos/'+p.REPO+'/actions/runs?per_page=5&page=');self.assertEqual(p.HISTORY_PER_PAGE,5);self.assertEqual(p.MAX_HISTORY_GETS,100);self.assertEqual(p.MAX_BYTES,262144)
  self.assertNotIn('per_page=20',(ROOT/p.HELPER).read_text());self.assertNotIn('per_page=20',(ROOT/p.PLAN).read_text())
 def test_264_runs_53_pages_complete(self):
  out,calls=self.fetch_fixture(history_pages(264));self.assertEqual(out,{'complete':True,'total':264,'pages':53,'prior_send':0});self.assertEqual(len(calls),53)
 def test_500_runs_100_pages_complete(self):
  out,calls=self.fetch_fixture(history_pages(500));self.assertEqual(out['pages'],100);self.assertEqual(out['total'],500);self.assertEqual(len(calls),100)
 def test_501_runs_incomplete_immediate_stop(self):
  with patch.object(p,'bounded_http',return_value=(200,json.dumps(history_pages(501)[0]).encode())) as http:
   with self.assertRaisesRegex(p.Stop,'HISTORY_INCOMPLETE_STOP'):p.fetch_history('fixture-only')
   self.assertEqual(http.call_count,1)
 def test_total_count_drift_stops(self):
  pages=history_pages(10);pages[1]['total_count']=11
  with patch.object(p,'bounded_http',side_effect=[(200,json.dumps(d).encode()) for d in pages]) as http:
   with self.assertRaisesRegex(p.Stop,'HISTORY_CHANGED_STOP'):p.fetch_history('fixture-only')
   self.assertEqual(http.call_count,2)
 def test_duplicate_run_id_stops(self):
  pages=history_pages(10);pages[1]['workflow_runs'][0]['id']=1
  with self.assertRaises(p.Stop):self.fetch_fixture(pages)
 def test_incomplete_last_page_stops(self):
  pages=history_pages(9);pages[-1]['workflow_runs'].pop()
  with self.assertRaisesRegex(p.Stop,'HISTORY_INCOMPLETE_STOP'):self.fetch_fixture(pages)
 def test_empty_last_page_stops(self):
  pages=history_pages(6);pages[-1]['workflow_runs']=[]
  with self.assertRaisesRegex(p.Stop,'HISTORY_INCOMPLETE_STOP'):self.fetch_fixture(pages)
 def test_oversize_page_stops_no_retry(self):
  with patch.object(p,'bounded_http',return_value=(200,b'x'*(p.MAX_BYTES+1))) as http:
   with self.assertRaisesRegex(p.Stop,'RESPONSE_BOUND_STOP'):p.fetch_history('fixture-only')
   self.assertEqual(http.call_count,1)
 def test_real_transport_size_boundary(self):
  from unittest.mock import Mock
  for content_length,body in [(str(p.MAX_BYTES+1),b''),(None,b'x'*(p.MAX_BYTES+1))]:
   response=Mock(status=200);response.getheader.return_value=content_length;response.read.return_value=body;conn=Mock();conn.getresponse.return_value=response
   with patch('http.client.HTTPSConnection',return_value=conn):
    with self.assertRaisesRegex(p.Stop,'RESPONSE_BOUND_STOP'):p.bounded_http('api.github.com',p.HISTORY+'1','GET',{})
   conn.request.assert_called_once();conn.close.assert_called_once()
   if content_length is None:response.read.assert_called_once_with(p.MAX_BYTES+1)
   else:response.read.assert_not_called()
 def test_five_large_entries_within_bound(self):
  page=history_pages(5)[0]
  for run in page['workflow_runs']:run['unused_metadata']='x'*50000
  raw=json.dumps(page).encode();self.assertLess(len(raw),p.MAX_BYTES)
  with patch.object(p,'bounded_http',return_value=(200,raw)):out=p.fetch_history('fixture-only')
  self.assertEqual(out['total'],5);self.assertNotIn('unused_metadata',json.dumps(out))
 def test_r1_r2_markers_allowed_and_unchanged(self):
  self.assertEqual(len(p.PRIOR_PREFLIGHT_MARKERS),5);p.prior_check(list(p.PRIOR_PREFLIGHT_MARKERS))
  for path,h in p.PRIOR_PREFLIGHT_MARKERS.items():self.assertEqual(p.sha((ROOT/path).read_bytes()),h)
  pages=[{'total_count':2,'workflow_runs':[{'id':37480012730,'path':'.github/workflows/plm-provider-neutral-0008-fresh-readonly-once.yml'},{'id':37745767546,'path':'.github/workflows/plm-provider-neutral-0008-fresh-readonly-r2-once.yml'}]}]
  self.assertEqual(p.history_check(pages)['prior_send'],0)
 def test_actual_migration_history_and_receipts_block(self):
  for kind in ['migration','import','apply','approved','sent','success','partial','unknown','failure','receipt']:
   with self.subTest(kind=kind):
    with self.assertRaisesRegex(p.Stop,'PRIOR_EXECUTION_NO_RESEND_STOP'):p.history_check([{'total_count':1,'workflow_runs':[{'id':1,'path':'.github/workflows/plm-provider-neutral-0008-'+kind+'.yml'}]}])
    with self.assertRaisesRegex(p.Stop,'PRIOR_EXECUTION_NO_RESEND_STOP'):p.prior_check(['audit-evidence/provider-neutral-0008-'+kind+'.json'])
  with self.assertRaises(p.Stop):p.prior_check(['audit-evidence/consumed/provider-neutral-0008-fresh-readonly-preflight-unknown.json'])
 def test_cloudflare_zero_until_history_complete(self):
  env={'GITHUB_REPOSITORY':p.REPO,'GITHUB_REF':'refs/heads/plm-offline-readiness-v1-20261002','GITHUB_EVENT_NAME':'push','GITHUB_RUN_ATTEMPT':'1','PLM_APPROVED_BEFORE':'1'*40,'PLM_HISTORY_GITHUB_TOKEN':'history-fixture',p.READ_SECRET:'read-fixture',p.BACKEND_SECRET:'backend-fixture',**{k:'true' for k in ('TEST_ONLY','DRY_RUN','NO_PUBLISH','EMERGENCY_STOP')}}
  original=Path.read_bytes
  def reader(path):return b'{}' if str(path)==p.MARKER else original(ROOT/path)
  before,_=p.load_candidate(ROOT)
  for pages,expected in [(history_pages(264),None),(history_pages(501),'HISTORY_INCOMPLETE_STOP'),([{'total_count':1,'workflow_runs':[]}],'HISTORY_INCOMPLETE_STOP')]:
   history_calls=[];cloudflare_calls=[];output=io.StringIO()
   def http(host,path,method,headers,body=None):
    self.assertEqual(host,'api.github.com');history_calls.append(path);return 200,json.dumps(pages[len(history_calls)-1]).encode()
   def cloudflare(*args):cloudflare_calls.append(args);raise AssertionError('unexpected network')
   def preflight(*args,**kwargs):
    self.assertEqual(len(history_calls),53);self.assertTrue(args[4]['complete']);return {'pass':True,'cloudflare_read_only_calls':0}
   with patch.dict('os.environ',env,clear=True),patch.object(Path,'read_bytes',reader),patch.object(p,'marker_check'),patch.object(Path,'rglob',return_value=[Path(x) for x in p.PRIOR_PREFLIGHT_MARKERS]),patch.object(p,'load_candidate',return_value=(before,{})),patch.object(p,'live_transport',return_value=cloudflare),patch.object(p,'bounded_http',side_effect=http),patch.object(p,'preflight',side_effect=preflight) as audit,contextlib.redirect_stdout(output):p.main()
   self.assertEqual(cloudflare_calls,[]);result=json.loads(output.getvalue());self.assertNotIn('fixture',output.getvalue())
   if expected:audit.assert_not_called();self.assertEqual(result['gate_code'],expected);self.assertEqual(result['cloudflare_read_only_calls'],0)
   else:audit.assert_called_once();self.assertTrue(result['pass'])
 def test_cloudflare_proof_functions_identical_to_r2(self):
  import ast
  old=(ROOT/'readiness/provider_neutral_0008_fresh_preflight_r2.py').read_text();new=(ROOT/p.HELPER).read_text()
  def functions(src):return {n.name:ast.get_source_segment(src,n) for n in ast.parse(src).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
  a,b=functions(old),functions(new)
  for name in ['load_candidate','queries','compare_query','classifier','decode','expiry','request_specs']:self.assertEqual(a[name],b[name],name)
 def test_r2_runtime_hashes_unchanged(self):
  for path,h in [('readiness/provider_neutral_0008_fresh_preflight_r2.py','49a4496f2f5034b6eaf2ea58be266240b63ea4f1f4143db0c5190d63a9e142b1'),('.github/workflows/plm-provider-neutral-0008-fresh-readonly-r2-once.yml','36b5496f26e379dc2de49fdac7a04089d2142c1d60a21229145980a92d50cca7'),('readiness/provider-neutral-0008-fresh-readonly-r2-plan.json','2d3aee45b8507fbefec88c897cd09722c3062fa91dd74b15a2c5ef0b06782f1f'),('readiness/provider-neutral-0008-fresh-readonly-r2-marker.schema.json','9052e868e60a79951762c92e53aaafdfd77d141e356ae4b079af6feb2b51596a')]:self.assertEqual(p.sha((ROOT/path).read_bytes()),h)



class HTTPDiagnosticR5Tests(unittest.TestCase):
 HISTORY={'complete':True,'prior_send':0,'total':264,'pages':53}
 def outcome(self,status,raw):
  b,_=p.load_candidate(ROOT);calls=[]
  def transport(*args):calls.append(args);return status,raw
  out=p.preflight(transport,b,NOW,history=self.HISTORY)
  self.assertEqual(len(calls),1);self.assertEqual(calls[0],('backend','GET',p.VERIFY,None));self.assertEqual(out['cloudflare_read_only_calls'],1);self.assertEqual(out['d1_writes'],0)
  self.assertTrue(out['history_complete']);self.assertEqual(out['history_total_runs'],264);self.assertEqual(out['history_pages'],53)
  return out
 def test_exact_400(self):self.assertEqual(self.outcome(400,b'bad')['result'],'HTTP_400_STOP')
 def test_exact_401(self):self.assertEqual(self.outcome(401,b'bad')['result'],'HTTP_401_STOP')
 def test_exact_403(self):self.assertEqual(self.outcome(403,b'bad')['result'],'HTTP_403_STOP')
 def test_exact_404(self):self.assertEqual(self.outcome(404,b'bad')['result'],'HTTP_404_STOP')
 def test_exact_429(self):self.assertEqual(self.outcome(429,b'bad')['result'],'HTTP_429_STOP')
 def test_exact_5xx_and_unknown_status(self):
  for status in (500,502,503,599,418,302,799):
   out=self.outcome(status,b'bad');self.assertEqual(out['result'],'HTTP_'+str(status)+'_STOP');self.assertEqual(out['http_status'],status)
 def test_numeric_codes_only_max8(self):
  raw=json.dumps({'success':False,'errors':[{'code':n,'message':'secret-fixture','documentation_url':'https://private.invalid'} for n in range(12)]+[{'code':True},{'code':'10000'},{'code':1.1}],'creator_email':'private-fixture','ip':'private-fixture','Authorization':'Bearer secret-fixture','value':'secret-fixture'}).encode()
  out=self.outcome(403,raw);self.assertEqual(out['cloudflare_error_codes'],list(range(8)));self.assertEqual(out['error_body_status'],'PARSED_CODES_ONLY')
  for text in ('secret-fixture','private-fixture','Authorization','message','documentation_url','creator_email'):self.assertNotIn(text,json.dumps(out))
 def test_nonintegers_not_codes(self):
  raw=json.dumps({'success':False,'errors':[{'code':True},{'code':'1'},{'code':1.0},{'code':None},{'code':10000}]}).encode()
  self.assertEqual(self.outcome(401,raw)['cloudflare_error_codes'],[10000])
 def test_non_json_status_preserved(self):
  out=self.outcome(502,b'<html>private-fixture</html>');self.assertEqual(out['http_status'],502);self.assertEqual(out['cloudflare_error_codes'],[]);self.assertNotIn('private-fixture',json.dumps(out))
 def test_malformed_envelopes_no_codes(self):
  for raw in [b'{"success":false,"errors":{}}',b'{"success":true,"errors":[{"code":1}]}',b'{"success":false,"errors":[{"code":1,"code":2}]}',b'[]',b'\xff']:
   self.assertEqual(self.outcome(400,raw)['cloudflare_error_codes'],[])
 def test_oversize_body_status_preserved(self):
  out=self.outcome(403,b'x'*(p.ERROR_BODY_MAX_BYTES+1));self.assertEqual(out['error_body_status'],'OVERSIZE_NOT_RETAINED');self.assertEqual(out['http_status'],403);self.assertEqual(out['cloudflare_error_codes'],[])
 def test_200_runs_full_preflight(self):
  b,a,r,t,c=fixtures();out=p.preflight(t,b,NOW,history=self.HISTORY);self.assertTrue(out['pass']);self.assertEqual(len(c),16);self.assertEqual(out['result'],'FRESH_PREFLIGHT_SUCCESS_STOP_BEFORE_MIGRATION');self.assertEqual(out['history_total_runs'],264);self.assertEqual(out['history_pages'],53)
 def test_200_invalid_verify_still_blocks(self):
  for change in [{'status':'inactive'},{'id':'invalid'},{'expires_on':None},{'expires_on':'2020-01-01T00:00:00Z'}]:
   b,a,r,t,c=fixtures();r[0]['result'].update(change);out=p.preflight(t,b,NOW,history=self.HISTORY);self.assertFalse(out['pass']);self.assertEqual(len(c),1)
  b,a,r,t,c=fixtures();r[0]['success']=False;out=p.preflight(t,b,NOW,history=self.HISTORY);self.assertFalse(out['pass']);self.assertEqual(len(c),1)
 def test_transport_error_body_bounded_and_not_logged(self):
  from unittest.mock import Mock
  cases=[(str(p.ERROR_BODY_MAX_BYTES+1),b'','OVERSIZE_NOT_RETAINED'),(None,b'x'*(p.ERROR_BODY_MAX_BYTES+1),'OVERSIZE_NOT_RETAINED'),('invalid',b'','INVALID_LENGTH_NOT_RETAINED'),(None,b'{"success":false,"errors":[{"code":10000,"message":"secret-fixture"}]}','PARSED_CODES_ONLY')]
  for length,body,state in cases:
   response=Mock(status=403);response.getheader.return_value=length;response.read.return_value=body;conn=Mock();conn.getresponse.return_value=response;stdout=io.StringIO()
   with patch('http.client.HTTPSConnection',return_value=conn),contextlib.redirect_stdout(stdout):
    with self.assertRaises(p.HTTPFailure) as error:p.bounded_http('api.cloudflare.com','/client/v4'+p.VERIFY,'GET',{'Authorization':'Bearer secret-fixture'})
   self.assertEqual(str(error.exception),'HTTP_403_STOP');self.assertEqual(error.exception.metadata['error_body_status'],state);self.assertNotIn('secret-fixture',str(error.exception.metadata));self.assertEqual(stdout.getvalue(),'');conn.request.assert_called_once();conn.close.assert_called_once()
   if length is None:response.read.assert_called_once_with(p.ERROR_BODY_MAX_BYTES+1)
   else:response.read.assert_not_called()
 def test_body_read_failure_preserves_status(self):
  from unittest.mock import Mock
  response=Mock(status=500);response.getheader.return_value=None;response.read.side_effect=TimeoutError('secret-fixture');conn=Mock();conn.getresponse.return_value=response
  with patch('http.client.HTTPSConnection',return_value=conn):
   with self.assertRaises(p.HTTPFailure) as error:p.bounded_http('api.cloudflare.com','/client/v4'+p.VERIFY,'GET',{})
  self.assertEqual(error.exception.metadata,{'http_status':500,'cloudflare_error_codes':[],'error_body_status':'READ_FAILED_NOT_RETAINED'});conn.close.assert_called_once()
 def test_live_adapter_http_failure_exact_one_send(self):
  from unittest.mock import Mock
  b,_=p.load_candidate(ROOT);response=Mock(status=401);response.getheader.return_value=None;response.read.return_value=b'{"success":false,"errors":[{"code":10000,"message":"secret-fixture"}]}';conn=Mock();conn.getresponse.return_value=response
  with patch('http.client.HTTPSConnection',return_value=conn):out=p.preflight(p.live_transport('read-fixture','backend-fixture',b),b,NOW,history=self.HISTORY)
  self.assertEqual(out['result'],'HTTP_401_STOP');self.assertEqual(out['cloudflare_error_codes'],[10000]);self.assertEqual(out['cloudflare_read_only_calls'],1);conn.request.assert_called_once();self.assertNotIn('fixture',json.dumps(out))
 def test_failure_gate_cannot_continue(self):
  b,_=p.load_candidate(ROOT);calls=[]
  def t(*args):calls.append(args);return 403,b'not-json'
  gate=p.Gate(t,p.request_specs(b))
  with self.assertRaises(p.HTTPFailure):gate.call(*gate.specs[0])
  with self.assertRaises(p.Stop):gate.call(*gate.specs[1])
  self.assertEqual(len(calls),1)
 def test_r3_marker_and_runtime_immutable(self):
  path='audit-evidence/consumed/provider-neutral-0008-fresh-readonly-preflight-20261008-r3.json';self.assertEqual(p.sha((ROOT/path).read_bytes()),p.PRIOR_PREFLIGHT_MARKERS[path]);p.prior_check([path])
  for path,h in [('readiness/provider_neutral_0008_fresh_preflight_r3.py','ba36164a216cefeeb4ba24882a2c3a0e3132966fa3ee198387273c61be833b12'),('.github/workflows/plm-provider-neutral-0008-fresh-readonly-r3-once.yml','e1b88c868de6ef76514518d9427c20d6a3c4a83368b9b0d4370c7b185fc85610'),('readiness/provider-neutral-0008-fresh-readonly-r3-plan.json','fc3a2494ab37a1447ce0c46ee041f2a6e6bb388a1144521a4e9276534ca93bfa'),('readiness/provider-neutral-0008-fresh-readonly-r3-marker.schema.json','74ceec6a2b77efa4a818a8baddc3827660f9d13fbf6310897951270a64ef9689')]:self.assertEqual(p.sha((ROOT/path).read_bytes()),h)
 def test_diagnostic_fixed_schema(self):
  plan=json.loads((ROOT/p.PLAN).read_bytes());self.assertEqual(plan['http_diagnostic'],'STATUS_ONLY_PLUS_NUMERIC_CF_ERROR_CODES');self.assertEqual(plan['error_body_max_bytes'],32768);self.assertEqual(plan['maximum_error_codes'],8);self.assertEqual(plan['error_raw_retention'],0)
if __name__=='__main__':unittest.main()
