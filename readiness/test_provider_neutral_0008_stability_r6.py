import unittest,json,copy,contextlib,io,ast,textwrap
from pathlib import Path
from unittest.mock import patch,Mock
from oracle_bridge import require_guard
require_guard()
import provider_neutral_0008_fresh_preflight_r6 as p
import provider_neutral_0008_migration_r2_once as m
import provider_neutral_0008_postcheck_r2_once as q
import provider_neutral_0008_stage_common_r2 as c
from test_provider_neutral_0008_fresh_preflight_r5 import fixtures,NOW,EXP,history_pages,ROOT
from test_provider_neutral_0008_stages import db,sql,complete,BOOK
HISTORY={'complete':True,'prior_send':0,'total':272,'pages':55}

def fixture(stable=1,post=False):
 b,a,original,_,_=fixtures();rows=[]
 if post:
  for spec in q.queries(b,a):
   row=copy.deepcopy(spec['expected'])
   for key in ('columns_json','indexes_json'):
    if key in row:row[key]=json.dumps(row[key])
   rows.append({'success':True,'result':[{'success':True,'results':[row],'meta':{'rows_written':0,'changes':0,'changed_db':False,'served_by_primary':True}}]})
  responses=copy.deepcopy(original[1:3])
 else:rows=original[4:15];responses=copy.deepcopy(original[:3])
 for n in range(1,4):
  before=hex(n)[2:]*32;after=before if n==stable else hex(n+4)[2:]*32
  responses.append({'success':True,'result':{'bookmark':before}});responses.extend(copy.deepcopy(rows));responses.append({'success':True,'result':{'bookmark':after}})
 calls=[]
 def transport(*args):calls.append(args);return 200,json.dumps(responses[len(calls)-1]).encode()
 return b,a,responses,transport,calls

def fresh(stable=1):
 b,a,r,t,calls=fixture(stable);return p.preflight(t,b,NOW,history=HISTORY)

class Windows(unittest.TestCase):
 def check_window(self,n):
  b,a,r,t,calls=fixture(n);out=p.preflight(t,b,NOW,history=HISTORY)
  self.assertTrue(out['pass']);self.assertEqual(out['stable_window_number'],n);self.assertEqual(out['stability_windows_used'],n);self.assertTrue(out['stable_window_found']);self.assertEqual(len(calls),3+13*n);self.assertEqual(out['d1_calls'],2+13*n);self.assertEqual(out['d1_writes'],0);self.assertEqual(out['retry'],0)
  self.assertEqual([x['stable'] for x in out['stability_windows']],['NO']*(n-1)+['YES']);self.assertNotIn('bookmark',out)
 def test_first_stable(self):self.check_window(1)
 def test_second_stable(self):self.check_window(2)
 def test_third_stable(self):self.check_window(3)
 def test_all_drift(self):
  b,a,r,t,calls=fixture(None);out=p.preflight(t,b,NOW,history=HISTORY)
  self.assertFalse(out['pass']);self.assertEqual(out['result'],'BOOKMARK_STABILITY_NOT_OBSERVED_STOP');self.assertEqual(out['cloudflare_read_only_calls'],42);self.assertEqual(out['d1_calls'],41);self.assertFalse(out['stable_window_found']);self.assertEqual(out['stability_windows_used'],3);self.assertEqual(out['d1_writes'],0)
 def test_all_drift_migration_zero(self):
  send=Mock();out=m.ImportRunner().run(sql(),fresh(None),send,lambda x:None,NOW);self.assertFalse(out['pass']);self.assertEqual(out['side_effect_requests'],0);send.assert_not_called()
 def test_each_query_drift_or_write_stops_without_next_window(self):
  for index in (4,8,14,17,27,30,40):
   for change in ('row','write','primary','changes','changed'):
    b,a,r,t,calls=fixture(None);query=r[index]['result'][0]
    if change=='row':query['results'][0]['total']+=1
    elif change=='write':query['meta']['rows_written']=1
    elif change=='primary':query['meta']['served_by_primary']=False
    elif change=='changes':query['meta']['changes']=True
    else:query['meta']['changed_db']=True
    out=p.preflight(t,b,NOW,history=HISTORY);self.assertFalse(out['pass']);self.assertEqual(len(calls),index+1);self.assertNotEqual(out['result'],'BOOKMARK_STABILITY_NOT_OBSERVED_STOP')
 def test_invalid_bookmark_does_not_advance(self):
  for index in (3,15,16,28,29,41):
   b,a,r,t,calls=fixture(None);r[index]['result']['bookmark']=None;out=p.preflight(t,b,NOW,history=HISTORY);self.assertEqual(out['result'],'BOOKMARK_REQUIRED_STOP');self.assertEqual(len(calls),index+1)
 def test_http_failure_not_window_drift(self):
  for target in (0,3,15,16,28,29,41):
   b,a,r,t,calls=fixture(None)
   def send(*args):
    if len(calls)==target:calls.append(args);return 403,b'{"success":false,"errors":[{"code":10000,"message":"secret-fixture"}]}'
    return t(*args)
   out=p.preflight(send,b,NOW,history=HISTORY);self.assertEqual(out['result'],'HTTP_403_STOP');self.assertEqual(len(calls),target+1);self.assertNotIn('fixture',json.dumps(out))
 def test_timeout_no_retry(self):
  b,a,r,t,calls=fixture(None);send=Mock(side_effect=TimeoutError('secret-fixture'));out=p.preflight(send,b,NOW,history=HISTORY);self.assertEqual(out['result'],'TRANSPORT_UNKNOWN_NO_RETRY');send.assert_called_once();self.assertNotIn('fixture',json.dumps(out))
 def test_42_transport_budget(self):
  b,a,r,t,calls=fixture(None);sequence=p.request_specs(b);self.assertEqual(len(sequence),42);self.assertEqual(sum(x[0]=='backend' for x in sequence),1)
  with patch.object(p,'bounded_http',return_value=(200,b'{}')) as http:
   adapter=p.live_transport('read-fixture','backend-fixture',b)
   for request in sequence:adapter(*request)
   with self.assertRaises(p.Stop):adapter(*sequence[-1])
   self.assertEqual(http.call_count,42)
 def test_credential_separation(self):
  b,a=p.load_candidate(ROOT)
  for read,backend in [(None,'b'),('r',None),('same','same')]:
   with self.assertRaises(p.Stop):p.live_transport(read,backend,b)
 def test_no_mutation_adapter(self):
  b,a=p.load_candidate(ROOT)
  with patch.object(p,'bounded_http') as http:
   for args in [('backend','POST',p.TARGET+'/query',{}),('read','POST',p.TARGET+'/import',{}),('read','GET',p.ROOT+'/workers',None)]:
    with self.assertRaises(p.Stop):p.live_transport('r','b',b)(*args)
   http.assert_not_called()
 def test_expiry_rechecked_each_window(self):
  b,a,r,t,calls=fixture(None);clock=Mock(side_effect=[NOW,NOW,NOW,NOW+10*86400]);out=p.preflight(t,b,NOW,history=HISTORY,clock=clock);self.assertFalse(out['pass']);self.assertEqual(len(calls),16)
 def test_namespace_rejection(self):
  for value in (1,16,None):
   b,a,r,t,calls=fixture(None);r[4]['result'][0]['results'][0]['candidate']=value;out=p.preflight(t,b,NOW,history=HISTORY);self.assertFalse(out['pass']);self.assertEqual(len(calls),5)
 def test_history_complete_before_cf(self):
  b,a,r,t,calls=fixture()
  for history in (None,{'complete':False}):self.assertFalse(p.preflight(t,b,NOW,history=history)['pass'])
  self.assertEqual(calls,[]);self.assertEqual(p.HISTORY_PER_PAGE,5);self.assertEqual(p.history_check(history_pages(264))['pages'],53)
  with self.assertRaises(p.Stop):p.history_check(history_pages(501))
 def test_r5_consumed_allowed_history_not_reused(self):
  path='audit-evidence/consumed/provider-neutral-0008-fresh-readonly-preflight-20261010-r5.json';self.assertEqual(p.sha((ROOT/path).read_bytes()),p.PRIOR_PREFLIGHT_MARKERS[path]);p.prior_check([path]);self.assertEqual(len(p.PRIOR_PREFLIGHT_MARKERS),6)
  with self.assertRaises(p.Stop):p.prior_check(['audit-evidence/0008-migration-sent.json'])
 def test_result_no_bookmarks_secrets(self):
  output=io.StringIO()
  with contextlib.redirect_stdout(output):out=fresh(3)
  self.assertEqual(output.getvalue(),'')
  for value in ('1'*32,'4'*32,'5'*32,'7'*32,'Authorization','Bearer','secret-fixture'):self.assertNotIn(value,json.dumps(out))
 def test_candidate_pins_exact(self):p.load_candidate(ROOT)

class Migration(unittest.TestCase):
 def test_stable_pregate_required(self):
  for change in ({'stable_window_found':False},{'stable_window_number':4},{'stability_windows_used':2},{'candidate_classification':'FULL_APPLIED'},{'candidate_classification':'PARTIAL_APPLIED'},{'candidate_classification':'STILL_UNKNOWN'}):
   t=Mock();out=m.ImportRunner().run(sql(),dict(fresh(),**change),t,lambda x:None,NOW);self.assertEqual(out['side_effect_requests'],0);t.assert_not_called()
 def test_stable_then_max_one(self):
  for n in (1,2,3):
   runner=m.ImportRunner();t=Mock(return_value=complete());out=runner.run(sql(),fresh(n),t,lambda x:None,NOW);self.assertTrue(out['pass']);self.assertEqual(out['migration_executions'],1);self.assertEqual(out['query_mutations'],0);self.assertFalse(runner.run(sql(),fresh(n),t,lambda x:None,NOW)['pass']);t.assert_called_once()
 def test_unknown_no_resend(self):
  runner=m.ImportRunner();t=Mock(side_effect=TimeoutError('secret-fixture'));out=runner.run(sql(),fresh(),t,lambda x:None,NOW);self.assertEqual(out['result'],'UNKNOWN_NO_RESEND_STOP');self.assertEqual(out['retry'],0);runner.run(sql(),fresh(),t,lambda x:None,NOW);t.assert_called_once();self.assertNotIn('fixture',json.dumps(out))
 def test_exact_sql_only(self):
  t=Mock();out=m.ImportRunner().run(sql()+b' ',fresh(),t,lambda x:None,NOW);self.assertFalse(out['pass']);t.assert_not_called()
 def test_import_route_no_query_mutation(self):
  self.assertTrue(m.IMPORT.endswith('/import'));self.assertEqual(m.SQL,'serverless/migrations/0008_provider_neutral_roundtrip_backend.sql')
  for k in ('0009','0010'):self.assertNotIn(k, (ROOT/m.CONFIG['helper']).read_text())

class Postcheck(unittest.TestCase):
 def window(self,n):
  b,a,r,t,calls=fixture(n,True);out=q.postcheck(t,b,a);self.assertTrue(out['pass']);self.assertEqual(len(calls),2+19*n);self.assertEqual(out['stable_window_number'],n);self.assertEqual(out['stability_windows_used'],n);self.assertEqual(out['d1_writes'],0);self.assertEqual(out['candidate'],'FULL_APPLIED');self.assertNotIn('bookmark',out)
 def test_first_stable(self):self.window(1)
 def test_second_stable(self):self.window(2)
 def test_third_stable(self):self.window(3)
 def test_three_drifts(self):
  b,a,r,t,calls=fixture(None,True);out=q.postcheck(t,b,a);self.assertEqual(out['result'],'BOOKMARK_STABILITY_NOT_OBSERVED_STOP');self.assertEqual(len(calls),59);self.assertEqual(out['d1_writes'],0)
 def test_partial_unknown_rejected(self):
  for value in (1,0,None):
   b,a,r,t,calls=fixture(None,True);r[3]['result'][0]['results'][0]['candidate']=value;out=q.postcheck(t,b,a);self.assertFalse(out['pass']);self.assertEqual(len(calls),4)
 def test_rows_indexes_protected_metadata_fail(self):
  for index in (3,4,14,19,22,41):
   b,a,r,t,calls=fixture(None,True);r[index]['result'][0]['results'][0]['total']+=1;out=q.postcheck(t,b,a);self.assertFalse(out['pass']);self.assertEqual(len(calls),index+1)
 def test_write_metadata_stops(self):
  for index in (3,22,41):
   b,a,r,t,calls=fixture(None,True);r[index]['result'][0]['meta']['rows_written']=1;out=q.postcheck(t,b,a);self.assertEqual(out['result'],'READ_ONLY_RESPONSE_STOP');self.assertEqual(len(calls),index+1)
 def test_sqlite_exact_full(self):
  d,b,a=db();d.executescript(sql().decode())
  for spec in q.queries(b,a):q.compare(spec,[dict(x) for x in d.execute(spec['sql'],spec['params'])])
  d.close()
 def test_no_backend_credential(self):self.assertNotIn(p.BACKEND_SECRET,(ROOT/q.CONFIG['workflow']).read_text())

class Bindings(unittest.TestCase):
 def test_new_markers_absent(self):
  for path in (p.MARKER,m.CONFIG['marker'],q.CONFIG['marker']):self.assertFalse((ROOT/path).exists())
 def test_r6_marker_rejects_old(self):
  files={path:(ROOT/path).read_bytes() for path in (p.WORKFLOW,p.HELPER,p.PLAN,p.SCHEMA)};plan=json.loads(files[p.PLAN]);marker={'identity':p.IDENTITY,'state':'CONSUMED_BEFORE_REMOTE','prepared_commit_sha':'a'*40,'candidate_raw_hashes':p.PINS,**{key:p.sha(files[path]) for key,path in [('workflow_sha256',p.WORKFLOW),('helper_sha256',p.HELPER),('preflight_plan_sha256',p.PLAN)]}}
  p.marker_check(marker,plan,'a'*40,files)
  for identity in ['provider-neutral-0008-fresh-readonly-preflight-20261010-r5','provider-neutral-0008-backend-token-verify-20261010-r1']:
   with self.assertRaises(p.Stop):p.marker_check(dict(marker,identity=identity),plan,'a'*40,files)
 def test_stage_markers_dependency_pins(self):
  for stage in ('migration','postcheck'):
   cfg=c.paths(stage);plan=json.loads((ROOT/cfg['plan']).read_bytes());files={path:(ROOT/path).read_bytes() for path in [cfg[k] for k in ('workflow','helper','plan','schema')]+list(plan['dependency_hashes'])};marker={'identity':cfg['identity'],'state':'CONSUMED_BEFORE_REMOTE','prepared_commit_sha':'a'*40,'prerequisite_commit_sha':'b'*40,'prerequisite_run_id':123,'candidate_raw_hashes':p.PINS,**{key:p.sha(files[cfg[kind]]) for key,kind in [('workflow_sha256','workflow'),('helper_sha256','helper'),('plan_sha256','plan')]}}
   c.check_marker(stage,marker,plan,files)
   with self.assertRaises(p.Stop):c.check_marker(stage,dict(marker,identity=cfg['identity'].replace('-r2','-r1')),plan,files)
 def test_stable_limits_pins(self):
  plan=json.loads((ROOT/p.PLAN).read_bytes());self.assertEqual(plan['maximum_stability_windows'],3);self.assertEqual(plan['maximum_cloudflare_read_only_calls'],42);self.assertEqual(plan['d1_read_token_audit_calls_max'],41);self.assertEqual(plan['maximum_writes'],0)
  self.assertEqual(len(plan['request_sequence']),42)
  for stage in ('migration','postcheck'):
   plan=json.loads((ROOT/c.paths(stage)['plan']).read_bytes());self.assertEqual(plan['maximum_stability_windows'],3)
   for key in ('retry','resend','resume','fallback','redirect','automatic_rollback','query_mutation'):self.assertEqual(plan[key],0)
 def test_workflow_static(self):
  for path in (p.WORKFLOW,m.CONFIG['workflow'],q.CONFIG['workflow']):
   text=(ROOT/path).read_text();self.assertIn('github.run_attempt == 1',text);self.assertNotIn('workflow_dispatch',text);self.assertIn('cancel-in-progress: false',text);ast.parse(textwrap.dedent(text.split("python3 - <<'PY'\n",1)[1].split('          PY',1)[0]))
 def test_r1_artifacts_unchanged(self):
  pins={'readiness/provider_neutral_0008_migration_once.py':'c62b2dab2dc9415e88f7b9d84aff22097cc175d0e58614e386f198e40e6ac80c','readiness/provider_neutral_0008_postcheck_once.py':'44cbbc6ea9319a6f8f5a61e227ee56aa5a59288957747c2c0203f109800de675','readiness/provider_neutral_0008_stage_common.py':'0db8bb9fc080203f452cc9ed6acf8664f24a8514d0d4d21b5b264ccd9340bb0e','readiness/provider_neutral_0008_fresh_preflight_r5.py':'a745fbe0cb728b2885c10a88d1214118153112db7ba611f7f0354ea49e137d1a'}
  for path,h in pins.items():self.assertEqual(p.sha((ROOT/path).read_bytes()),h)
  for stage in ('migration','postcheck'):self.assertFalse((ROOT/('audit-evidence/consumed/provider-neutral-0008-'+stage+'-20261010-r1.json')).exists())
if __name__=='__main__':unittest.main()

class StageIntegration(unittest.TestCase):
 def test_r2_exact_local_chain_attempt_and_scope(self):
  import test_provider_neutral_0008_stages as old
  with patch.multiple(old,p=p,m=m,q=q,c=c):
   case=old.LocalChain('test_exact_chain_and_each_drift');result=unittest.TestResult();case.run(result)
  self.assertTrue(result.wasSuccessful(),str(result.errors)+str(result.failures))
 def test_three_drift_migration_main_zero_side_effects(self):
  import os
  b,a,r,t,calls=fixture(None);output=io.StringIO()
  with patch.dict(os.environ,{p.READ_SECRET:'read-fixture',p.BACKEND_SECRET:'backend-fixture','PLM_HISTORY_GITHUB_TOKEN':'history-fixture','GITHUB_RUN_ID':'123'},clear=True),patch.object(c,'local_gate',return_value=({},{})),patch.object(c,'prerequisite',return_value=True),patch.object(p,'fetch_history',return_value=HISTORY),patch.object(p,'live_transport',return_value=t),patch.object(m,'LiveImport') as writer,patch.object(m.time,'time',return_value=NOW),contextlib.redirect_stdout(output):
   self.assertEqual(m.main(),1)
  writer.assert_not_called();out=json.loads(output.getvalue());self.assertEqual(out['result'],'FRESH_PRE_GATE_STOP');self.assertEqual(out['side_effect_requests'],0);self.assertEqual(out['cloudflare_read_only_calls'],42);self.assertNotIn('fixture',output.getvalue())
 def test_first_drift_sqlite_then_stable_post(self):
  d,b,a=db();d.executescript(sql().decode());counter=0;queries=0
  def transport(method,path,body):
   nonlocal counter,queries
   if path==p.INVENTORY:return 200,json.dumps({'success':True,'result':[{'uuid':p.DB,'name':p.NAME}],'result_info':{'page':1,'count':1,'total_count':1,'per_page':100}}).encode()
   if path==p.TARGET:r={'uuid':p.DB,'name':p.NAME,'file_size':300000}
   elif path.endswith('/bookmark'):
    counter+=1;r={'bookmark':('1' if counter==1 else '2')*32}
   else:
    self.assertTrue(body['sql'].startswith('SELECT '));start=d.total_changes;rows=[dict(x) for x in d.execute(body['sql'],body['params'])];self.assertEqual(d.total_changes,start);queries+=1;r=[{'success':True,'results':rows,'meta':{'rows_written':0,'changes':0,'changed_db':False,'served_by_primary':True}}]
   return 200,json.dumps({'success':True,'result':r}).encode()
  out=q.postcheck(transport,b,a);self.assertTrue(out['pass']);self.assertEqual(out['stability_windows_used'],2);self.assertEqual(queries,34);self.assertEqual(out['read_calls'],40);d.close()
