import unittest,json,copy,sqlite3,contextlib,io,ast
from pathlib import Path
from unittest.mock import patch,Mock
from oracle_bridge import require_guard
require_guard()
import provider_neutral_0010_common as p
import provider_neutral_0010_stage_gate as c
import provider_neutral_0010_migration_once as m
from test_provider_neutral_0008_stages import db,BOOK
NOW=1791630000
HISTORY={'complete':True,'prior_send':0,'total':274,'pages':55}

def fixture(stable=1,post=False):
 b,a=p.load_candidate();state=a if post else b
 responses=[] if post else [{'success':True,'result':{'id':'a'*32,'status':'active','expires_on':'2099-10-17T23:59:59+00:00'}}]
 responses += [{'success':True,'result':[{'uuid':p.DB,'name':p.NAME}],'result_info':{'page':1,'count':1,'total_count':1,'per_page':100}},{'success':True,'result':{'uuid':p.DB,'name':p.NAME,'file_size':999999}}]
 for n in range(1,4):
  responses.append({'success':True,'result':{'bookmark':str(n)*32}})
  for q in p.queries(state):
   row=copy.deepcopy(q['expected'])
   for k in ('columns_json','indexes_json'):
    if k in row:row[k]=json.dumps(row[k])
   responses.append({'success':True,'result':[{'success':True,'results':[row],'meta':{'served_by_primary':True,'rows_written':0,'changes':0,'changed_db':False}}]})
  responses.append({'success':True,'result':{'bookmark':str(n if stable==n else n+3)*32}})
 calls=[]
 def send(*args):calls.append(args);return 200,json.dumps(responses[len(calls)-1]).encode()
 return state,responses,send,calls

def fresh():
 s,r,t,calls=fixture();return p.audit(t,s,history=HISTORY,now=NOW)
def complete():return {'status':'complete','result':{'num_queries':4,'final_bookmark':BOOK}}

class Candidate(unittest.TestCase):
 def test_pins(self):
  p.load_candidate();self.assertEqual(p.sha(Path(p.SQL).read_bytes()),p.SQL_SHA)
 def test_sqlite_dependency_and_additive_only(self):
  d,b,a=db();d.executescript(Path('serverless/migrations/0008_provider_neutral_roundtrip_backend.sql').read_text());d.executescript(Path('serverless/migrations/0009_youtube_queue_result_proposal.sql').read_text());pre=[dict(r) for r in d.execute("SELECT * FROM sqlite_master ORDER BY type,name")];before={t:[dict(r) for r in d.execute('SELECT * FROM '+p.ident(t))] for t in b['protected_rows']};n=d.total_changes
  d.executescript(Path(p.SQL).read_text());self.assertEqual(n,d.total_changes)
  for row in pre:self.assertIn(row,[dict(r) for r in d.execute('SELECT * FROM sqlite_master')])
  for t,rows in before.items():self.assertEqual(rows,[dict(r) for r in d.execute('SELECT * FROM '+p.ident(t))])
  _,after=p.load_candidate()
  for q in p.queries(after):p.compare(q,[dict(r) for r in d.execute(q['sql'],q['params'])],True)
  for t in ('plm_ytp_v1_binding',):
   d.execute('EXPLAIN INSERT INTO '+t+' DEFAULT VALUES').fetchall();d.execute('EXPLAIN DELETE FROM '+t).fetchall()
  self.assertFalse(d.execute("SELECT name FROM sqlite_master WHERE name LIKE 'plm_yt_checkpoint%'").fetchall())
 def test_sql_has_only_create_statements(self):
  sql=Path(p.SQL).read_text();current='';statements=[]
  for line in sql.splitlines(True):
   if line.lstrip().startswith('--'):continue
   current+=line
   if sqlite3.complete_statement(current):statements.append(current.strip());current=''
  self.assertEqual(len(statements),4)
  self.assertTrue(all(s.startswith(('CREATE TABLE plm_ytp_v1_','CREATE TRIGGER plm_ytp_v1_')) for s in statements))
  self.assertEqual(sum(s.startswith('CREATE TABLE') for s in statements),1)
  self.assertNotIn('DROP ',sql);self.assertNotIn('ALTER ',sql);self.assertNotIn('DELETE FROM',sql)
 def test_classifier(self):
  self.assertEqual(p.classifier(0,58),'NOT_APPLIED');self.assertEqual(p.classifier(4,62),'FULL_APPLIED')
  for c1,t in ((1,59),(3,61),(None,58),(0,59)):self.assertNotEqual(p.classifier(c1,t),'NOT_APPLIED')
 def test_partial_and_unexpected_schema_stop(self):
  for count,total in ((1,59),(4,62),(0,59),(None,58)):
   s,r,t,calls=fixture();r[4]['result'][0]['results'][0].update(candidate10=count,total=total);o=p.audit(t,s,history=HISTORY,now=NOW);self.assertFalse(o['pass']);self.assertEqual(len(calls),5)
 def test_0008_missing_stops(self):
  s,r,t,calls=fixture();r[4]['result'][0]['results'][0]['candidate']=0;self.assertFalse(p.audit(t,s,history=HISTORY,now=NOW)['pass'])

class ReadProof(unittest.TestCase):
 def test_stability_all_positions(self):
  for post in (False,True):
   for n in (1,2,3):
    s,r,t,calls=fixture(n,post);o=p.audit(t,s,post,HISTORY,NOW);self.assertTrue(o['pass'],o);self.assertEqual(o['stable_window_number'],n);self.assertEqual(len(calls),(2+24*n) if post else (3+22*n));self.assertEqual(o['d1_writes'],0);self.assertEqual(o['0008'],'FULL_APPLIED');self.assertEqual(o['0010'],'FULL_APPLIED' if post else 'NOT_APPLIED');self.assertEqual(o['0009'],'FULL_APPLIED')
 def test_all_drift(self):
  for post,maxcalls in ((False,69),(True,74)):
   s,r,t,calls=fixture(None,post);o=p.audit(t,s,post,HISTORY,NOW);self.assertEqual(o['result'],'BOOKMARK_STABILITY_NOT_OBSERVED_STOP');self.assertEqual(len(calls),maxcalls);self.assertEqual(o['d1_writes'],0)
 def test_no_history_no_cloudflare(self):
  s,r,t,calls=fixture();o=p.audit(t,s,history=None,now=NOW);self.assertFalse(o['pass']);self.assertEqual(calls,[])
 def test_each_read_meta_strict(self):
  for field,val in (('rows_written',1),('rows_written',False),('changes',1),('changes',False),('changed_db',True),('served_by_primary',False)):
   s,r,t,calls=fixture();r[4]['result'][0]['meta'][field]=val;o=p.audit(t,s,history=HISTORY,now=NOW);self.assertFalse(o['pass']);self.assertEqual(len(calls),5)
 def test_protected_rows_drift(self):
  s,r,t,calls=fixture();r[5]['result'][0]['results'][0]['total']+=1;self.assertFalse(p.audit(t,s,history=HISTORY,now=NOW)['pass'])
 def test_new_rows_drift_postcheck(self):
  s,r,t,calls=fixture(post=True);r[14]['result'][0]['results'][0]['total']=1;self.assertFalse(p.audit(t,s,True,now=NOW)['pass'])
 def test_invalid_bookmark(self):
  s,r,t,calls=fixture();r[3]['result']['bookmark']=None;self.assertEqual(p.audit(t,s,history=HISTORY,now=NOW)['result'],'BOOKMARK_REQUIRED_STOP')
 def test_non200_sanitized(self):
  for status in (401,403,429,500):
   s,r,t,calls=fixture();fn=Mock(return_value=(status,b'{"success":false,"errors":[{"code":1000,"message":"secret-fixture"}]}'));o=p.audit(fn,s,history=HISTORY,now=NOW);self.assertEqual(o['result'],'HTTP_'+str(status)+'_STOP');self.assertEqual(o['cloudflare_error_codes'],[1000]);self.assertNotIn('secret-fixture',json.dumps(o));fn.assert_called_once()
 def test_timeout_no_retry(self):
  s,r,t,calls=fixture();fn=Mock(side_effect=TimeoutError('secret-fixture'));o=p.audit(fn,s,history=HISTORY,now=NOW);self.assertEqual(o['result'],'TRANSPORT_UNKNOWN_NO_RETRY');fn.assert_called_once();self.assertNotIn('secret-fixture',json.dumps(o))
 def test_token_rules(self):
  for v in ({'status':'inactive'},{'id':'ABC'},{'expires_on':None},{'expires_on':'2000-01-01T00:00:00Z'},{'expires_on':'2099-01-01T00:00:00'}):
   s,r,t,calls=fixture();r[0]['result'].update(v);self.assertFalse(p.audit(t,s,history=HISTORY,now=NOW)['pass']);self.assertEqual(len(calls),1)
 def test_credentials_missing_distinct(self):
  b,_=p.load_candidate()
  for read,back,code in ((None,'b','CREDENTIAL_MISSING_STOP'),('r',None,'BACKEND_CREDENTIAL_MISSING_STOP'),('same','same','CREDENTIAL_ROLES_NOT_DISTINCT_STOP')):
   with self.assertRaisesRegex(p.Stop,code):p.live_transport(read,back,b)
 def test_transport_exact_and_backend_verify_only(self):
  b,_=p.load_candidate();seq=p.request_specs(b);self.assertEqual(len(seq),69);self.assertEqual([x for x in seq if x[0]=='backend'],[('backend','GET',p.VERIFY,None)])
  for request in (('backend','POST',p.TARGET+'/query',{}),('read','DELETE',p.TARGET,None),('read','GET','/workers',None)):
   t=p.live_transport('read-fixture','backend-fixture',b)
   with self.assertRaises(p.Stop):t(*request)
 def test_post_no_backend(self):
  _,a=p.load_candidate();self.assertEqual(len(p.request_specs(a,True)),74)
  with self.assertRaises(p.Stop):p.live_transport('r','b',a,True)
 def test_raw_bookmarks_not_retained(self):
  o=fresh();self.assertNotIn('1'*32,json.dumps(o));self.assertNotIn('a'*32,json.dumps(o));self.assertEqual(o['raw_retention'],0)

class History(unittest.TestCase):
 def pages(self,n):return [{'total_count':n,'workflow_runs':[{'id':i+1,'path':'offline.yml'} for i in range(start,min(start+5,n))]} for start in range(0,max(n,1),5)]
 def test_264(self):self.assertEqual(p.history_check(self.pages(264))['pages'],53)
 def test_500(self):self.assertTrue(p.history_check(self.pages(500))['complete'])
 def test_501(self):
  with self.assertRaises(p.Stop):p.history_check(self.pages(501))
 def test_drift_duplicate_incomplete(self):
  for mode in ('drift','dup','incomplete'):
   pages=self.pages(6)
   if mode=='drift':pages[1]['total_count']=7
   if mode=='dup':pages[1]['workflow_runs'][0]['id']=1
   if mode=='incomplete':pages[1]['workflow_runs']=[]
   with self.assertRaises(p.Stop):p.history_check(pages)
 def test_0008_execution_allowed_but0010_blocked(self):
  for name in ('migration-r2','fresh-readonly-r6','postcheck-r2','backend-token-verify'):
   self.assertTrue(p.history_check([{'total_count':1,'workflow_runs':[{'id':1,'path':'.github/workflows/plm-provider-neutral-0008-'+name+'-once.yml'}]}])['complete'])
  page={'total_count':1,'workflow_runs':[{'id':1,'path':c.paths('migration')['workflow']}]}
  with self.assertRaises(p.Stop):p.history_check([page])
  self.assertTrue(p.history_check([page],page['workflow_runs'][0])['complete'])
 def test_receipts_block(self):
  for word in ('sent','success','partial','unknown','failure','import','apply','migration','approved'):
   with self.assertRaises(p.Stop):p.prior_check(['audit-evidence/0010-'+word+'.json'])

class Import(unittest.TestCase):
 def test_exact4_statements_ack(self):
  fn=Mock(return_value=complete());o=m.ImportRunner().run(Path(p.SQL).read_bytes(),fresh(),fn,lambda e:None,NOW);self.assertTrue(o['pass']);self.assertEqual(o['migration_executions'],1);self.assertEqual(o['result'],'0010_IMPORT_ACK_STOP_BEFORE_POSTCHECK')
 def test_upload_ingest(self):
  fn=Mock(side_effect=[{'upload_url':'https://'+'a'*32+'.r2.cloudflarestorage.com/sql?X-Amz-Signature=fixture','filename':'fixed.sql'},{'uploaded':True},complete()]);events=[];o=m.ImportRunner().run(Path(p.SQL).read_bytes(),fresh(),fn,events.append,NOW);self.assertTrue(o['pass']);self.assertEqual(o['side_effect_requests'],3);self.assertEqual([e['operation'] for e in events],['init','upload','ingest']);self.assertNotIn('fixture',json.dumps(o))
 def test_gate_failure_zero(self):
  for v in ({'pass':False},{'0008':'NOT_APPLIED'},{'0009':'NOT_APPLIED'},{'0010':'FULL_APPLIED'},{'candidate_classification':'FULL_APPLIED'},{'candidate_classification':'PARTIAL_APPLIED'},{'stable_window_found':False},{'prior_send':1},{'hashes':{}}):
   fn=Mock();o=m.ImportRunner().run(Path(p.SQL).read_bytes(),dict(fresh(),**v),fn,lambda e:None,NOW);self.assertEqual(o['side_effect_requests'],0);fn.assert_not_called()
 def test_old_sql_rejected(self):
  fn=Mock();o=m.ImportRunner().run(Path('serverless/migrations/0008_provider_neutral_roundtrip_backend.sql').read_bytes(),fresh(),fn,lambda e:None,NOW);fn.assert_not_called();self.assertFalse(o['pass'])
 def test_unknown_permanent_stop(self):
  fn=Mock(side_effect=TimeoutError('secret-fixture'));runner=m.ImportRunner();args=(Path(p.SQL).read_bytes(),fresh(),fn,lambda e:None,NOW);o=runner.run(*args);self.assertEqual(o['result'],'UNKNOWN_NO_RESEND_STOP');runner.run(*args);fn.assert_called_once();self.assertNotIn('fixture',json.dumps(o))
 def test_wrong_statement_count_unknown(self):
  fn=Mock(return_value={'status':'complete','result':{'num_queries':16,'final_bookmark':BOOK}});self.assertFalse(m.ImportRunner().run(Path(p.SQL).read_bytes(),fresh(),fn,lambda e:None,NOW)['pass'])

class Bindings(unittest.TestCase):
 def test_marker_hashes_and_old_identities_rejected(self):
  for stage in c.CONFIG:
   cfg=c.paths(stage);plan=json.loads(Path(cfg['plan']).read_bytes());files={f:Path(f).read_bytes() for f in [cfg[k] for k in ('workflow','helper','plan','schema')]+list(plan['dependency_hashes'])}
   marker={'identity':cfg['identity'],'state':'CONSUMED_BEFORE_REMOTE','prepared_commit_sha':'a'*40,'prerequisite_commit_sha':'b'*40,'prerequisite_run_id':1,'candidate_raw_hashes':p.PINS,**{k:p.sha(files[cfg[v]]) for k,v in [('workflow_sha256','workflow'),('helper_sha256','helper'),('plan_sha256','plan')]}}
   c.check_marker(stage,marker,plan,files)
   for identity in ('provider-neutral-0008-migration-20261010-r2','provider-neutral-0008-postcheck-20261010-r2','provider-neutral-0008-fresh-readonly-preflight-20261010-r6','provider-neutral-0009-migration-20261011-r1','provider-neutral-0009-postcheck-20261011-r1'):
    with self.assertRaises(p.Stop):c.check_marker(stage,dict(marker,identity=identity),plan,files)
   with self.assertRaises(p.Stop):c.check_marker(stage,dict(marker,helper_sha256='0'*64),plan,files)
   self.assertEqual(p.sha(Path(cfg['marker']).read_bytes()),'67f97b0eadb2697b8eec6a7f0c963c7d2191ecac023a575b48e82f59c420bffd') if stage=='preflight' else self.assertFalse(Path(cfg['marker']).exists())
 def test_workflow_exact(self):
  for stage in c.CONFIG:
   cfg=c.paths(stage);w=Path(cfg['workflow']).read_text();self.assertIn(cfg['marker'],w);self.assertIn(cfg['message'],w);self.assertIn('github.run_attempt == 1',w);self.assertNotIn('workflow_dispatch',w)
   if stage=='postcheck':self.assertNotIn(p.BACKEND_SECRET,w)
 def test_context_attempt(self):
  for attempt in ('2','3',''):
   with patch.dict('os.environ',{'GITHUB_REPOSITORY':p.REPO,'GITHUB_REF':'refs/heads/plm-offline-readiness-v1-20261002','GITHUB_EVENT_NAME':'push','GITHUB_RUN_ATTEMPT':attempt},clear=True):
    with self.assertRaisesRegex(p.Stop,'EXECUTION_CONTEXT_STOP'):c.local_gate('preflight')
 def test_sources_no_unwanted_calls(self):
  for f in [c.paths(s)['helper'] for s in c.CONFIG]:
   text=Path(f).read_text();ast.parse(text);self.assertNotIn('workflow_dispatch',text);self.assertNotIn('youtube.com',text);self.assertNotIn('/workers',text);self.assertNotIn('0008_provider_neutral_roundtrip_backend.sql',text);self.assertNotIn('0009_youtube_queue_result_proposal.sql',text)

class Integration(unittest.TestCase):
 def test_preflight_sqlite_exact(self):
  d,b,a=db();d.executescript(Path('serverless/migrations/0008_provider_neutral_roundtrip_backend.sql').read_text());d.executescript(Path('serverless/migrations/0009_youtube_queue_result_proposal.sql').read_text());before,_=p.load_candidate()
  for q in p.queries(before):p.compare(q,[dict(r) for r in d.execute(q['sql'],q['params'])],False)
 def test_full_postcheck_real_sqlite(self):
  d,b,a=db();d.executescript(Path('serverless/migrations/0008_provider_neutral_roundtrip_backend.sql').read_text());d.executescript(Path('serverless/migrations/0009_youtube_queue_result_proposal.sql').read_text());d.executescript(Path(p.SQL).read_text());s,r,original,calls=fixture(2,True)
  def transport(role,method,path,body):
   status,raw=original(role,method,path,body)
   if body:
    envelope=json.loads(raw);envelope['result'][0]['results']=[dict(x) for x in d.execute(body['sql'],body['params'])];raw=json.dumps(envelope).encode()
   return status,raw
  out=p.audit(transport,s,True,now=NOW);self.assertTrue(out['pass'],out);self.assertEqual(out['cloudflare_read_only_calls'],50)
 def test_prerequisite_exact_run(self):
  cfg=c.paths('migration');marker={'prerequisite_run_id':123,'prerequisite_commit_sha':'a'*40};run={'id':123,'path':c.paths('preflight')['workflow'],'head_sha':'a'*40,'event':'push','run_attempt':1,'status':'completed','conclusion':'success'};jobs={'total_count':1,'jobs':[{'conclusion':'success','steps':[{'name':'Run exact stage once','conclusion':'success'}]}]}
  for drift in ({},{'head_sha':'b'*40},{'run_attempt':2},{'conclusion':'failure'}):
   http=Mock(side_effect=[(200,json.dumps(dict(run,**drift)).encode()),(200,json.dumps(jobs).encode())])
   if drift:
    with self.assertRaises(p.Stop):c.prerequisite('migration',marker,'fixture',http)
   else:self.assertTrue(c.prerequisite('migration',marker,'fixture',http))
 def test_local_gate_marker_only_parent_chain(self):
  cfg=c.paths('preflight');plan=json.loads(Path(cfg['plan']).read_bytes());marker={'identity':cfg['identity'],'state':'CONSUMED_BEFORE_REMOTE','prepared_commit_sha':'a'*40,'prerequisite_commit_sha':p.PARENT,'prerequisite_run_id':38113308404,'candidate_raw_hashes':p.PINS,**{k:p.sha(Path(cfg[v]).read_bytes()) for k,v in [('workflow_sha256','workflow'),('helper_sha256','helper'),('plan_sha256','plan')]}}
  original=Path.read_bytes
  def rb(path):return json.dumps(marker).encode() if str(path)==cfg['marker'] else original(path)
  env={'GITHUB_REPOSITORY':p.REPO,'GITHUB_REF':'refs/heads/plm-offline-readiness-v1-20261002','GITHUB_EVENT_NAME':'push','GITHUB_RUN_ATTEMPT':'1','GITHUB_SHA':'b'*40,'PLM_APPROVED_BEFORE':'a'*40,**{k:'true' for k in ('TEST_ONLY','DRY_RUN','NO_PUBLISH','EMERGENCY_STOP')}}
  def git(*args):
   if args==('rev-parse','HEAD^'):return 'a'*40
   if args==('rev-parse','HEAD'):return 'b'*40
   if args==('rev-parse','a'*40+'^'):return p.PARENT
   if args[0]=='diff':return cfg['marker']
   if args[0]=='show':return cfg['message']
   if args[0]=='rev-list':return ''
   raise AssertionError(args)
  def show(args):return original(Path(args[2].split(':',1)[1]))
  with patch.dict('os.environ',env,clear=True),patch.object(Path,'read_bytes',rb),patch.object(c,'git',side_effect=git),patch.object(c.subprocess,'run',return_value=Mock(returncode=1)),patch.object(c.subprocess,'check_output',side_effect=show):
   self.assertEqual(c.local_gate('preflight')[0],marker)
   with patch.object(c,'git',side_effect=lambda *a:'wrong' if a[0]=='diff' else git(*a)):
    with self.assertRaisesRegex(p.Stop,'MARKER_ONLY_STOP'):c.local_gate('preflight')
 def test_migration_main_unstable_never_writes(self):
  s,r,t,calls=fixture(None)
  with patch.dict('os.environ',{p.READ_SECRET:'read-fixture',p.BACKEND_SECRET:'backend-fixture','PLM_HISTORY_GITHUB_TOKEN':'history-fixture','GITHUB_RUN_ID':'123'},clear=True),patch.object(c,'local_gate',return_value=({},{})),patch.object(c,'prerequisite',return_value=True),patch.object(p,'fetch_history',return_value=HISTORY),patch.object(p,'live_transport',return_value=t),patch.object(m,'LiveImport') as write,contextlib.redirect_stdout(io.StringIO()) as buf:
   self.assertEqual(m.main(),1);write.assert_not_called();out=json.loads(buf.getvalue());self.assertEqual(out['result'],'FRESH_PRE_GATE_STOP');self.assertEqual(out['side_effect_requests'],0);self.assertEqual(out['cloudflare_read_only_calls'],69)
 def test_postcheck_main_no_write_credential(self):
  import provider_neutral_0010_postcheck_once as post
  s,r,t,calls=fixture(post=True)
  with patch.dict('os.environ',{p.READ_SECRET:'read-fixture','PLM_HISTORY_GITHUB_TOKEN':'history-fixture'},clear=True),patch.object(c,'local_gate',return_value=({},{})),patch.object(c,'prerequisite',return_value=True),patch.object(p,'live_transport',return_value=t) as factory,contextlib.redirect_stdout(io.StringIO()) as buf:
   self.assertEqual(post.main(),0);self.assertIsNone(factory.call_args.args[1]);self.assertNotIn('fixture',buf.getvalue())

class Bounds(unittest.TestCase):
 def test_response_bound_no_raw_retention(self):
  s,r,t,calls=fixture();fn=Mock(return_value=(200,b'x'*(p.MAX_BYTES+1)));o=p.audit(fn,s,history=HISTORY,now=NOW);self.assertEqual(o['result'],'RESPONSE_BOUND_STOP');self.assertEqual(o['cloudflare_read_only_calls'],1);self.assertNotIn('xxxx',json.dumps(o))
 def test_poll3_only(self):
  fn=Mock(return_value={'at_bookmark':BOOK});o=m.ImportRunner().run(Path(p.SQL).read_bytes(),fresh(),fn,lambda e:None,NOW);self.assertEqual(o['polls'],3);self.assertEqual(o['side_effect_requests'],1);self.assertEqual(o['import_http_calls'],4);self.assertFalse(o['pass'])
 def test_trigger_update_dependencies_compile(self):
  d,b,a=db();d.executescript(Path('serverless/migrations/0008_provider_neutral_roundtrip_backend.sql').read_text());d.executescript(Path('serverless/migrations/0009_youtube_queue_result_proposal.sql').read_text());d.executescript(Path(p.SQL).read_text())
  for table,column in [('plm_ytp_v1_binding','bound_at')]:d.execute('EXPLAIN UPDATE '+table+' SET '+column+'=NULL').fetchall()

class Isolation(unittest.TestCase):
 def test_0009_history_allowed_not0010(self):
  for stage in ('preflight','migration','postcheck'):
   name={'preflight':'fresh-readonly','migration':'migration','postcheck':'postcheck'}[stage]
   self.assertEqual(p.history_check([{'total_count':1,'workflow_runs':[{'id':1,'path':'.github/workflows/plm-provider-neutral-0009-'+name+'-once.yml'}]}])['prior_send'],0)
 def test_0009_missing_blocks(self):
  s,r,t,calls=fixture();r[4]['result'][0]['results'][0]['candidate9']=0;self.assertFalse(p.audit(t,s,history=HISTORY,now=NOW)['pass'])
 def test_old0009_sql_cannot_send(self):
  fn=Mock();o=m.ImportRunner().run(Path('serverless/migrations/0009_youtube_queue_result_proposal.sql').read_bytes(),fresh(),fn,lambda e:None,NOW);fn.assert_not_called();self.assertEqual(o['migration_executions'],0)
 def test_no_new_marker_and_expected_parent(self):
  self.assertEqual(p.PARENT,'dc13343915c7d3bdad14fc808fc9ae4eb2b2f46b')
  for stage in c.CONFIG:
   if stage=='preflight':self.assertEqual(p.sha(Path(c.paths(stage)['marker']).read_bytes()),'67f97b0eadb2697b8eec6a7f0c963c7d2191ecac023a575b48e82f59c420bffd')
   else:self.assertFalse(Path(c.paths(stage)['marker']).exists())
 def test_foreign_keys_and_immutable_triggers(self):
  d,b,a=db();d.execute('PRAGMA foreign_keys=ON')
  for f in ('serverless/migrations/0008_provider_neutral_roundtrip_backend.sql','serverless/migrations/0009_youtube_queue_result_proposal.sql',p.SQL):d.executescript(Path(f).read_text())
  fks=[dict(r) for r in d.execute('PRAGMA foreign_key_list(plm_ytp_v1_binding)')]
  self.assertEqual({r['table'] for r in fks},{'plm_ytq_v1_queue','plm_ytq_v1_outbox'})
  self.assertEqual(d.execute('PRAGMA foreign_key_check').fetchall(),[])
  with self.assertRaisesRegex(sqlite3.IntegrityError,'pipeline_unbound_dispatch'):
   d.execute("INSERT INTO plm_ytp_v1_binding VALUES('missing','missing','1','1',1,?,?,?,1)",('a'*64,'b'*64,'c'*64))

class Specification(unittest.TestCase):
 def test_marker_schema_pins(self):
  for stage in c.CONFIG:
   cfg=c.paths(stage);schema=json.loads(Path(cfg['schema']).read_bytes());self.assertEqual(schema['properties']['candidate_raw_hashes']['const'],p.PINS);self.assertEqual(schema['properties']['identity']['const'],cfg['identity'])
 def test_budgets_fixed(self):
  for stage,maximum,query_count in [('preflight',69,20),('migration',69,20),('postcheck',74,22)]:
   plan=json.loads(Path(c.paths(stage)['plan']).read_bytes());self.assertEqual(plan['maximum_read_only_calls'],maximum);self.assertEqual(plan['query_count_per_window'],query_count);self.assertEqual(plan['maximum_stability_windows'],3)
   self.assertEqual(plan['0008'],'FULL_APPLIED_REQUIRED');self.assertEqual(plan['0009'],'FULL_APPLIED_REQUIRED')
  plan=json.loads(Path(c.paths('migration')['plan']).read_bytes());self.assertEqual(plan['logical_changes'],{'tables':1,'triggers':3,'autoindexes':3,'ddl_statements':4,'new_rows':0});self.assertEqual(plan['maximum_cloudflare_calls_including_upload'],75)
