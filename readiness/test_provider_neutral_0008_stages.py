import unittest,json,copy,sqlite3,contextlib,io,os
from pathlib import Path
from unittest.mock import patch,Mock
from oracle_bridge import require_guard
require_guard()
import provider_neutral_0008_fresh_preflight_r5 as p
import provider_neutral_0008_migration_once as m
import provider_neutral_0008_postcheck_once as q
import provider_neutral_0008_stage_common as c
from test_provider_neutral_0008_fresh_preflight_r5 import fixtures,NOW,EXP,ROOT,history_pages
BOOK='00000001-00000002-00004e2f-0123456789abcdef'
HISTORY={'complete':True,'prior_send':0,'total':0,'pages':1}
def fresh():
 b,a,r,t,calls=fixtures();return p.preflight(t,b,NOW,history=HISTORY)
def complete():return {'status':'complete','result':{'num_queries':16,'final_bookmark':BOOK}}
def sql():return (ROOT/m.SQL).read_bytes()
def db():
 b,a=p.load_candidate(ROOT);d=sqlite3.connect(':memory:');d.row_factory=sqlite3.Row
 for x in b['schema']:
  if x['type']=='table':d.execute(x['sql'])
 for table,rows in b['protected_rows'].items():
  for row in rows:d.execute('INSERT INTO '+p.ident(table)+' ('+','.join(p.ident(k) for k in row)+') VALUES ('+','.join('?' for _ in row)+')',list(row.values()))
 for x in b['schema']:
  if x['type']=='trigger':d.execute(x['sql'])
 return d,b,a
class Stages(unittest.TestCase):
 def test_old_identities_markers_immutable(self):
  self.assertEqual(len(p.PRIOR_PREFLIGHT_MARKERS),5)
  for path,h in p.PRIOR_PREFLIGHT_MARKERS.items():self.assertEqual(p.sha((ROOT/path).read_bytes()),h)
  p.prior_check(p.PRIOR_PREFLIGHT_MARKERS)
 def test_verify_history_allowed(self):
  path='.github/workflows/plm-provider-neutral-0008-backend-token-verify-once.yml'
  self.assertEqual(p.history_check([{'total_count':1,'workflow_runs':[{'id':38015883019,'path':path}]}])['prior_send'],0)
 def test_only_current_migration_history_exception(self):
  run={'id':123,'path':m.CONFIG['workflow']};page={'total_count':1,'workflow_runs':[run]}
  with self.assertRaises(p.Stop):p.history_check([page])
  self.assertTrue(p.history_check([page],run)['complete'])
  with self.assertRaises(p.Stop):p.history_check([page],dict(run,id=124))
  with self.assertRaises(p.Stop):p.history_check([page],dict(run,path='wrong'))
 def test_marker_bindings_and_no_markers(self):
  for stage in ('migration','postcheck'):
   cfg=c.paths(stage);plan=json.loads((ROOT/cfg['plan']).read_bytes());files={path:(ROOT/path).read_bytes() for path in [cfg[k] for k in ('workflow','helper','plan','schema')]+list(plan['dependency_hashes'])}
   marker={'identity':cfg['identity'],'state':'CONSUMED_BEFORE_REMOTE','prepared_commit_sha':'a'*40,'prerequisite_commit_sha':'b'*40,'prerequisite_run_id':1,'candidate_raw_hashes':p.PINS,**{k:p.sha(files[cfg[kind]]) for k,kind in [('workflow_sha256','workflow'),('helper_sha256','helper'),('plan_sha256','plan')]}}
   c.check_marker(stage,marker,plan,files);self.assertFalse((ROOT/cfg['marker']).exists())
   for change in ({'identity':p.IDENTITY},{'state':'RESUME'},{'helper_sha256':'0'*64},{'prerequisite_run_id':None},{'candidate_raw_hashes':{}}):
    with self.assertRaises(p.Stop):c.check_marker(stage,dict(marker,**change),plan,files)
   w=files[cfg['workflow']].decode();self.assertIn('github.run_attempt == 1',w);self.assertIn(cfg['marker'],w);self.assertNotIn('workflow_dispatch',w)
 def test_fresh_pre_gate_fail_zero_writes(self):
  for change in ({'pass':False},{'candidate_classification':'FULL_APPLIED'},{'candidate_classification':'PARTIAL_APPLIED'},{'candidate_classification':'STILL_UNKNOWN'},{'prior_send':1},{'protected_rows_exact':False},{'hashes':{}},{'inventory_complete':False},{'token_status':'inactive'},{'token_expires_at':'2020-01-01T00:00:00Z'}):
   transport=Mock();out=m.ImportRunner().run(sql(),dict(fresh(),**change),transport,lambda x:None,NOW);self.assertFalse(out['pass']);self.assertEqual(out['side_effect_requests'],0);transport.assert_not_called()
 def test_sql_hash(self):
  t=Mock();out=m.ImportRunner().run(sql()+b' ',fresh(),t,lambda x:None,NOW);self.assertFalse(out['pass']);t.assert_not_called()
 def test_upload_ingest_poll_once(self):
  events=[];calls=[];responses=[{'upload_url':'https://'+'a'*32+'.r2.cloudflarestorage.com/object?X-Amz-Signature=fixture','filename':'fixed.sql'},{'uploaded':True},{'at_bookmark':BOOK},complete()]
  def transport(action,fields):self.assertTrue(events);calls.append(action);return responses[len(calls)-1]
  runner=m.ImportRunner();out=runner.run(sql(),fresh(),transport,events.append,NOW)
  self.assertTrue(out['pass']);self.assertEqual(calls,['init','upload','ingest','poll']);self.assertEqual(out['side_effect_requests'],3);self.assertEqual(out['migration_executions'],1);self.assertEqual(out['query_mutations'],0);self.assertEqual([e['operation'] for e in events],['init','upload','ingest']);self.assertNotIn('fixture',json.dumps(out))
  again=runner.run(sql(),fresh(),transport,events.append,NOW);self.assertFalse(again['pass']);self.assertEqual(len(calls),4)
 def test_cached_init_no_ingest(self):
  t=Mock(return_value=complete());out=m.ImportRunner().run(sql(),fresh(),t,lambda x:None,NOW);self.assertTrue(out['pass']);t.assert_called_once();self.assertEqual(out['side_effect_requests'],1)
 def test_timeout_unknown_no_resend(self):
  t=Mock(side_effect=TimeoutError('secret-fixture'));r=m.ImportRunner();out=r.run(sql(),fresh(),t,lambda x:None,NOW);self.assertEqual(out['result'],'UNKNOWN_NO_RESEND_STOP');self.assertNotIn('fixture',json.dumps(out));self.assertEqual(out['side_effect_requests'],1);r.run(sql(),fresh(),t,lambda x:None,NOW);t.assert_called_once()
 def test_poll_budget(self):
  t=Mock(return_value={'at_bookmark':BOOK});out=m.ImportRunner().run(sql(),fresh(),t,lambda x:None,NOW);self.assertFalse(out['pass']);self.assertEqual(out['polls'],3);self.assertEqual(t.call_count,4)
 def test_ambiguous_import_states(self):
  for resp in ({},{'status':'error'},{'status':'complete','result':{'num_queries':17}},{'status':'running'},{'upload_url':'http://invalid'},{'success':False},{'error':'secret-fixture'}):
   out=m.ImportRunner().run(sql(),fresh(),Mock(return_value=resp),lambda x:None,NOW);self.assertEqual(out['result'],'UNKNOWN_NO_RESEND_STOP');self.assertNotIn('fixture',json.dumps(out))
 def test_upload_url_boundary(self):
  for u in ['http://example.com','https://example.com/?X-Amz-Signature=x','https://'+'a'*32+'.r2.cloudflarestorage.com:443/?X-Amz-Signature=x','https://token@'+'a'*32+'.r2.cloudflarestorage.com/?X-Amz-Signature=x']:
   with self.assertRaises(p.Stop):m.upload_url(u)
 def test_live_no_other_request(self):
  live=m.LiveImport('backend-fixture',sql())
  with patch.object(p,'bounded_http') as http:
   with self.assertRaises(p.Stop):live('query',{'sql':'DELETE'})
   with self.assertRaises(p.Stop):live('upload',{'url':'https://invalid','sql':sql()})
   http.assert_not_called()
 def test_live_timeout_latch(self):
  live=m.LiveImport('backend-fixture',sql())
  with patch.object(p,'bounded_http',side_effect=TimeoutError()) as http:
   with self.assertRaises(TimeoutError):live('init',{'etag':live.etag})
   with self.assertRaises(p.Stop):live('init',{'etag':live.etag})
   http.assert_called_once()
 def test_sqlite_full_postcheck(self):
  d,b,a=db();d.executescript(sql().decode())
  for spec in q.queries(b,a):q.compare(spec,[dict(row) for row in d.execute(spec['sql'],spec['params'])])
  d.close()
 def test_postcheck_partial_rejected(self):
  d,b,a=db();d.execute(next(x['sql'] for x in a['new']['schema'] if x['type']=='table'))
  spec=q.queries(b,a)[0]
  with self.assertRaises(p.Stop):q.compare(spec,[dict(row) for row in d.execute(spec['sql'])])
  d.close()
 def test_postcheck_protected_drift(self):
  d,b,a=db();d.executescript(sql().decode());d.execute("DELETE FROM plm_rt_v1_effect WHERE kind='GENERATION'")
  spec=next(x for x in q.queries(b,a) if x['kind']=='rows:plm_rt_v1_effect')
  with self.assertRaises(p.Stop):q.compare(spec,[dict(row) for row in d.execute(spec['sql'],spec['params'])])
  d.close()
 def test_postcheck_nonempty_and_index_drift(self):
  b,a=p.load_candidate(ROOT)
  for spec in q.queries(b,a)[11:]:
   row=copy.deepcopy(spec['expected']);row['total']+=1
   for k in ('columns_json','indexes_json'):
    if k in row:row[k]=json.dumps(row[k])
   with self.assertRaises(p.Stop):q.compare(spec,[row])
 def test_postcheck_full_mock_window(self):
  b,a=p.load_candidate(ROOT);responses=[{'success':True,'result':[{'uuid':p.DB,'name':p.NAME}],'result_info':{'page':1,'count':1,'total_count':1,'per_page':100}},{'success':True,'result':{'uuid':p.DB,'name':p.NAME,'file_size':250000}},{'success':True,'result':{'bookmark':BOOK}}]
  for spec in q.queries(b,a):
   row=copy.deepcopy(spec['expected'])
   for k in ('columns_json','indexes_json'):
    if k in row:row[k]=json.dumps(row[k])
   responses.append({'success':True,'result':[{'success':True,'results':[row],'meta':{'rows_written':0,'changes':0,'changed_db':False,'served_by_primary':True}}]})
  responses.append({'success':True,'result':{'bookmark':BOOK}})
  def run():
   queue=iter(responses);return q.postcheck(lambda *a:(200,json.dumps(next(queue)).encode()),b,a)
  out=run();self.assertTrue(out['pass']);self.assertEqual(out['read_calls'],21);self.assertEqual(out['d1_writes'],0)
  responses[-1]['result']['bookmark']='a'*32;self.assertEqual(run()['result'],'BOOKMARK_CHANGED_STOP');responses[-1]['result']['bookmark']=BOOK
  responses[3]['result'][0]['meta']['rows_written']=1;self.assertEqual(run()['result'],'READ_ONLY_RESPONSE_STOP')
 def test_postcheck_read_adapter_rejects_mutation(self):
  b,a=p.load_candidate(ROOT)
  with patch.object(p,'bounded_http') as http:
   t=q.live_transport('read-fixture',b,a)
   for request in [('POST',p.TARGET+'/import',{}),('POST',p.TARGET+'/query',{'sql':'DELETE FROM test_jobs'})]:
    with self.assertRaises(p.Stop):t(*request)
   http.assert_not_called()
 def test_no_backend_in_post_workflow(self):
  w=(ROOT/q.CONFIG['workflow']).read_text();self.assertNotIn(p.BACKEND_SECRET,w)
 def test_prerequisite_success_and_skipped_stop(self):
  marker={'prerequisite_run_id':123,'prerequisite_commit_sha':'a'*40}
  for stage,prev,step in [('migration','r5','Bounded readonly audit; stop before any migration'),('postcheck','migration','Run exact stage once')]:
   run={'id':123,'path':'.github/workflows/'+c.STAGES[prev][2]+'.yml','head_sha':'a'*40,'event':'push','run_attempt':1,'status':'completed','conclusion':'success'}
   jobs={'total_count':1,'jobs':[{'conclusion':'success','steps':[{'name':step,'conclusion':'success'}]}]}
   def transport(*args):return 200,json.dumps(jobs if '/jobs?' in args[1] else run).encode()
   self.assertTrue(c.prerequisite(stage,marker,'history-fixture',transport));jobs['jobs'][0]['steps'][0]['conclusion']='skipped'
   with self.assertRaises(p.Stop):c.prerequisite(stage,marker,'history-fixture',transport)
 def test_r5_read_adapter_second_verify_rejected(self):
  b,a=p.load_candidate(ROOT)
  with patch.object(p,'bounded_http',return_value=(200,b'{}')) as http:
   t=p.live_transport('read-fixture','backend-fixture',b);t('backend','GET',p.VERIFY,None)
   with self.assertRaises(p.Stop):t('backend','GET',p.VERIFY,None)
   self.assertEqual(http.call_count,1)
 def test_plan_budgets(self):
  for stage in ('migration','postcheck'):
   plan=json.loads((ROOT/c.paths(stage)['plan']).read_bytes())
   self.assertEqual(plan['0009'],'NOT_APPLIED');self.assertEqual(plan['0010'],'NOT_APPLIED')
   for key in ('retry','resend','resume','fallback','redirect','automatic_rollback','query_mutation'):self.assertEqual(plan[key],0)
  plan=json.loads((ROOT/m.CONFIG['plan']).read_bytes());self.assertEqual(plan['route'],'REST_IMPORT_SQL_FILE');self.assertEqual(plan['migration_execution_max'],1);self.assertEqual(plan['import_http_total_max'],6)
if __name__=='__main__':unittest.main()

class Integration(unittest.TestCase):
 def test_sqlite_all_three_stages(self):
  d,b,a=db();calls=[]
  def read(role,method,path,body):
   calls.append((role,method,path))
   if path==p.VERIFY:r={'id':'a'*32,'status':'active','expires_on':EXP}
   elif path==p.INVENTORY:return 200,json.dumps({'success':True,'result':[{'uuid':p.DB,'name':p.NAME}],'result_info':{'page':1,'per_page':100,'count':1,'total_count':1}}).encode()
   elif path==p.TARGET:r={'uuid':p.DB,'name':p.NAME,'file_size':b['database_size_bytes']}
   elif path.endswith('/bookmark'):r={'bookmark':BOOK}
   elif path.endswith('/query'):
    self.assertEqual(role,'read');self.assertTrue(body['sql'].startswith('SELECT '));start=d.total_changes
    rows=[dict(row) for row in d.execute(body['sql'],body['params'])];self.assertEqual(d.total_changes,start)
    r=[{'success':True,'results':rows,'meta':{'rows_written':0,'changes':0,'changed_db':False,'served_by_primary':True}}]
   else:raise AssertionError('nonallowlisted request')
   return 200,json.dumps({'success':True,'result':r}).encode()
  first=p.preflight(read,b,NOW,history=HISTORY);self.assertTrue(first['pass']);self.assertEqual(len(calls),16)
  pregate=p.preflight(read,b,NOW,history=HISTORY);self.assertTrue(pregate['pass']);self.assertEqual(len(calls),32)
  imports=[]
  def importer(action,fields):
   imports.append(action)
   if action=='init':return {'upload_url':'https://'+'a'*32+'.r2.cloudflarestorage.com/f?X-Amz-Signature=fixture','filename':'0008.sql'}
   if action=='upload':self.assertEqual(fields['sql'],sql());return {'uploaded':True}
   self.assertEqual(action,'ingest');d.executescript(sql().decode());return complete()
  receipt=m.ImportRunner().run(sql(),pregate,importer,lambda x:None,NOW);self.assertTrue(receipt['pass']);self.assertEqual(imports,['init','upload','ingest'])
  result=q.postcheck(lambda method,path,body:read('read',method,path,body),b,a);self.assertTrue(result['pass']);self.assertEqual(result['result'],'0008_POSTCHECK_SUCCESS_STOP');self.assertEqual(len(calls),53)
  again=p.preflight(read,b,NOW,history=HISTORY);self.assertFalse(again['pass']);transport=Mock();self.assertFalse(m.ImportRunner().run(sql(),again,transport,lambda x:None,NOW)['pass']);transport.assert_not_called();d.close()
 def test_post_unknown_no_secret(self):
  b,a=p.load_candidate(ROOT);transport=Mock(side_effect=TimeoutError('secret-fixture'));result=q.postcheck(transport,b,a);self.assertFalse(result['pass']);self.assertEqual(result['read_calls'],1);self.assertNotIn('fixture',json.dumps(result));transport.assert_called_once()
 def test_migration_sanitized_http(self):
  out=m.ImportRunner().run(sql(),fresh(),Mock(side_effect=p.HTTPFailure(403,b'{"success":false,"errors":[{"code":10000,"message":"secret-fixture"}]}')),lambda x:None,NOW)
  self.assertEqual(out['http_status'],403);self.assertEqual(out['cloudflare_error_codes'],[10000]);self.assertNotIn('fixture',json.dumps(out));self.assertEqual(out['import_http_calls'],1)
 def test_postcheck_candidate_schema_drift(self):
  d,b,a=db();d.executescript(sql().decode());d.execute('CREATE TABLE unexpected(id TEXT)');spec=q.queries(b,a)[0]
  with self.assertRaises(p.Stop):q.compare(spec,[dict(x) for x in d.execute(spec['sql'])])
  d.close()
 def test_transport_upload_no_auth_and_exact_bytes(self):
  u='https://'+'a'*32+'.r2.cloudflarestorage.com/f?X-Amz-Signature=fixture';live=m.LiveImport('backend-fixture',sql())
  envelope=json.dumps({'success':True,'result':{'upload_url':u,'filename':'0008.sql'}}).encode()
  with patch.object(p,'bounded_http',return_value=(200,envelope)):live('init',{'etag':live.etag})
  response=Mock(status=200);response.getheader.return_value='"'+live.etag+'"';conn=Mock();conn.getresponse.return_value=response
  with patch('http.client.HTTPSConnection',return_value=conn):self.assertEqual(live('upload',{'url':u,'sql':sql()}),{'uploaded':True})
  args,kwargs=conn.request.call_args;self.assertEqual(args[0],'PUT');self.assertEqual(kwargs['body'],sql());self.assertEqual(kwargs['headers'],{'Content-Type':'application/sql'});conn.close.assert_called_once()
 def test_workflow_static_syntax(self):
  import ast
  for stage in ('r5','migration','postcheck'):
   path=p.WORKFLOW if stage=='r5' else c.paths(stage)['workflow'];text=(ROOT/path).read_text()
   self.assertIn('on:\n  push:\n    branches: [plm-offline-readiness-v1-20261002]',text)
   self.assertNotIn('workflow_dispatch',text);self.assertIn('github.run_attempt == 1',text);self.assertIn('cancel-in-progress: false',text)
   code=text.split("python3 - <<'PY'\n",1)[1].split('          PY',1)[0]
   import textwrap
   ast.parse(textwrap.dedent(code))

class LocalChain(unittest.TestCase):
 def test_exact_chain_and_each_drift(self):
  original=Path.read_bytes
  prepared='a'*40;r5commit='b'*40;mcommit='c'*40;postcommit='d'*40
  def marker(stage):
   cfg=c.paths(stage);return {'identity':cfg['identity'],'state':'CONSUMED_BEFORE_REMOTE','prepared_commit_sha':prepared,'prerequisite_commit_sha':r5commit if stage=='migration' else mcommit,'prerequisite_run_id':123,'candidate_raw_hashes':p.PINS,**{key:p.sha((ROOT/cfg[kind]).read_bytes()) for key,kind in [('workflow_sha256','workflow'),('helper_sha256','helper'),('plan_sha256','plan')]}}
  r5={'identity':p.IDENTITY,'state':'CONSUMED_BEFORE_REMOTE','prepared_commit_sha':prepared,'candidate_raw_hashes':p.PINS,**{key:p.sha((ROOT/path).read_bytes()) for key,path in [('workflow_sha256',p.WORKFLOW),('helper_sha256',p.HELPER),('preflight_plan_sha256',p.PLAN)]}}
  for stage in ('migration','postcheck'):
   cfg=c.paths(stage);mk=marker(stage);previous=r5commit if stage=='migration' else mcommit;head=mcommit if stage=='migration' else postcommit
   lookup={('rev-parse','HEAD^'):previous,('rev-parse','HEAD'):head,('rev-parse',prepared+'^'):p.PARENT,('diff','--name-only',previous,'HEAD'):cfg['marker'],('show','-s','--format=%B','HEAD'):cfg['message'],('rev-list','--reverse',prepared+'..'+previous):r5commit if stage=='migration' else r5commit+'\n'+mcommit,('rev-parse',r5commit+'^'):prepared,('diff','--name-only',prepared,r5commit):p.MARKER,('show','-s','--format=%B',r5commit):p.MESSAGE,('show',r5commit+':'+p.MARKER):json.dumps(r5),('rev-parse',mcommit+'^'):r5commit,('diff','--name-only',r5commit,mcommit):m.CONFIG['marker'],('show','-s','--format=%B',mcommit):m.CONFIG['message'],('show',mcommit+':'+m.CONFIG['marker']):json.dumps(marker('migration'))}
   env={'GITHUB_REPOSITORY':p.REPO,'GITHUB_REF':'refs/heads/plm-offline-readiness-v1-20261002','GITHUB_EVENT_NAME':'push','GITHUB_RUN_ATTEMPT':'1','GITHUB_SHA':head,'PLM_APPROVED_BEFORE':previous,**{k:'true' for k in ('TEST_ONLY','DRY_RUN','NO_PUBLISH','EMERGENCY_STOP')}}
   def read(path):return json.dumps(mk).encode() if str(path)==cfg['marker'] else original(ROOT/path)
   with patch.dict(os.environ,env,clear=True),patch.object(c,'git',side_effect=lambda *args:lookup[args]),patch.object(c.subprocess,'run',return_value=Mock(returncode=1)),patch.object(Path,'read_bytes',read):
    c.local_gate(stage)
    with patch.dict(os.environ,{'GITHUB_RUN_ATTEMPT':'2'}):
     with self.assertRaises(p.Stop):c.local_gate(stage)
    key=('diff','--name-only',previous,'HEAD');old=lookup[key];lookup[key]+='\nunexpected.py'
    with self.assertRaises(p.Stop):c.local_gate(stage)
    lookup[key]=old
    key=('rev-parse',prepared+'^');lookup[key]='f'*40
    with self.assertRaises(p.Stop):c.local_gate(stage)
 def test_existing_marker_consumed_rejected(self):
  # The local pre-credential gate explicitly requires marker absence in the prior tree.
  source=(ROOT/'readiness/provider_neutral_0008_stage_common.py').read_text()
  self.assertIn("'ALREADY_CONSUMED_STOP'",source)
