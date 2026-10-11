import unittest,json,hashlib,ast,copy,contextlib,io,os
from pathlib import Path
from unittest.mock import Mock,patch
from oracle_bridge import require_guard
require_guard()
import provider_neutral_0010_common as p
import provider_neutral_0010_r2_stage_gate as c
import provider_neutral_0010_migration_r2_once as m
import provider_neutral_0010_postcheck_r2_once as post
import test_provider_neutral_0010_stages as reference
NOW=reference.NOW
BOOK='00000001-00000002-00004e2f-0123456789abcdef'
def plan(stage='migration'):return json.loads(Path(c.paths(stage)['plan']).read_bytes())
def sql():return Path(p.SQL).read_bytes()
def marker(stage):
 cfg=c.paths(stage);pp=plan(stage);return {'identity':cfg['identity'],'state':'CONSUMED_BEFORE_REMOTE','prepared_commit_sha':'a'*40,'prerequisite_commit_sha':c.PARENT if stage=='migration' else 'b'*40,'prerequisite_run_id':38117642195 if stage=='migration' else 123,'candidate_raw_hashes':p.PINS,**{k:p.sha(Path(cfg[v]).read_bytes()) for k,v in [('workflow_sha256','workflow'),('helper_sha256','helper'),('plan_sha256','plan')]}}
def files(stage):
 cfg=c.paths(stage);pp=plan(stage);return {f:Path(f).read_bytes() for f in [cfg[k] for k in ('workflow','helper','schema','plan')]+list(pp['dependency_hashes'])+[p.SQL]}
def completion():return {'status':'complete','result':{'num_queries':4,'final_bookmark':BOOK}}
class DefectRegression(unittest.TestCase):
 def test_helper_plan_path_exact(self):
  self.assertEqual(m.SQL,p.SQL);self.assertEqual(post.SQL,p.SQL)
  for stage in c.CONFIG:self.assertTrue(c.validate_sql(plan(stage),sql(),helper_source=Path(c.paths(stage)['helper']).read_bytes()))
 def test_md5_actual_bytes(self):
  self.assertEqual(plan()['sql_md5'],hashlib.md5(sql()).hexdigest());self.assertEqual(plan()['sql_md5'],'d2bd1cab0afbabff17cdab7edb2eb9fc')
 def test_sha_actual_bytes(self):self.assertEqual(plan()['sql_sha256'],p.sha(sql()));self.assertEqual(p.sha(sql()),'79a88960393ad7030b60e707c9de67cceccb16f02d41f7bcf99f41c1f11ea336')
 def test_logical(self):self.assertEqual(plan()['logical_changes'],c.LOGICAL)
 def test_wrong_path_rejected(self):
  with self.assertRaisesRegex(p.Stop,'SQL_PATH_BINDING_STOP'):c.validate_sql(dict(plan(),sql_file='wrong.sql'),sql())
 def test_copied_md5_rejected(self):
  stale='16c26ee2cecb70fa6'+'d64bc51aa9ac45f'
  with self.assertRaisesRegex(p.Stop,'SQL_MD5_BINDING_STOP'):c.validate_sql(dict(plan(),sql_md5=stale),sql())
 def test_sha_rejected(self):
  with self.assertRaisesRegex(p.Stop,'SQL_SHA_BINDING_STOP'):c.validate_sql(dict(plan(),sql_sha256='0'*64),sql())
 def test_candidate_hash_rejected(self):
  with self.assertRaises(p.Stop):c.validate_sql(dict(plan(),candidate_raw_hashes={}),sql())
 def test_changed_bytes_rejected(self):
  with self.assertRaises(p.Stop):c.validate_sql(plan(),sql()+b' ')
 def test_logical_rejected(self):
  with self.assertRaisesRegex(p.Stop,'SQL_LOGICAL_BINDING_STOP'):c.validate_sql(dict(plan(),logical_changes={}),sql())
 def test_helper_path_rejected(self):
  with self.assertRaisesRegex(p.Stop,'HELPER_SQL_BINDING_STOP'):c.validate_sql(plan(),sql(),helper_sql='wrong.sql')
 def test_no_wrong_string_new_artifacts(self):
  forbidden='0010_youtube_'+'queue_result_proposal.sql';md5='16c26ee2cecb70fa6'+'d64bc51aa9ac45f'
  for stage in c.CONFIG:
   for kind in ('workflow','helper','plan','schema'):
    s=Path(c.paths(stage)[kind]).read_text();self.assertNotIn(forbidden,s);self.assertNotIn(md5,s)
 def test_runtime_main_metadata_bad_stops_before_any_transport(self):
  for change in ({'sql_file':'wrong.sql'},{'sql_md5':'0'*32},{'sql_sha256':'0'*64}):
   with patch.object(c,'local_gate',return_value=(marker('migration'),dict(plan(),**change))),patch.object(p,'live_transport') as read,patch.object(m,'LiveImport') as write,patch.object(c,'prerequisite') as gh,contextlib.redirect_stdout(io.StringIO()) as buf:
    self.assertEqual(m.main(),1);read.assert_not_called();write.assert_not_called();gh.assert_not_called();out=json.loads(buf.getvalue());self.assertEqual(out['cloudflare_read_only_calls'],0);self.assertEqual(out['side_effect_requests'],0)
class Binding(unittest.TestCase):
 def test_new_parent(self):self.assertEqual(c.PARENT,'1c1a7eb8e232f753e3c559c96d02cfe5baf90e1e')
 def test_marker_hash_contract(self):
  for stage in c.CONFIG:c.check_marker(stage,marker(stage),plan(stage),files(stage))
 def test_reuse_rejected(self):
  for old in ('provider-neutral-0010-migration-20261011-r1','provider-neutral-0010-postcheck-20261011-r1','provider-neutral-0010-fresh-readonly-preflight-20261011-r1'):
   with self.assertRaises(p.Stop):c.check_marker('migration',dict(marker('migration'),identity=old),plan(),files('migration'))
 def test_no_preflight_stage(self):
  with self.assertRaisesRegex(p.Stop,'IDENTITY_STAGE_STOP'):c.paths('preflight')
 def test_prerequisite_marker_exact(self):
  for change in ({'prerequisite_run_id':38117642196},{'prerequisite_commit_sha':'b'*40}):
   with self.assertRaisesRegex(p.Stop,'PREREQUISITE_BINDING_STOP'):c.check_marker('migration',dict(marker('migration'),**change),plan(),files('migration'))
 def test_prerequisite_remote_exact(self):
  mk=marker('migration');run={'id':38117642195,'path':'.github/workflows/plm-provider-neutral-0010-fresh-readonly-once.yml','head_sha':c.PARENT,'event':'push','run_attempt':1,'status':'completed','conclusion':'success'};jobs={'total_count':1,'jobs':[{'conclusion':'success','steps':[{'name':'Run exact stage once','conclusion':'success'}]}]}
  for drift in ({},{'run_attempt':2},{'head_sha':'b'*40},{'status':'in_progress'},{'conclusion':'failure'},{'path':'wrong.yml'}):
   http=Mock(side_effect=[(200,json.dumps(dict(run,**drift)).encode()),(200,json.dumps(jobs).encode())])
   if drift:
    with self.assertRaises(p.Stop):c.prerequisite('migration',mk,'fixture',http)
   else:self.assertTrue(c.prerequisite('migration',mk,'fixture',http));self.assertEqual(http.call_count,2)
 def test_bad_prerequisite_no_github_calls(self):
  http=Mock()
  with self.assertRaises(p.Stop):c.prerequisite('migration',dict(marker('migration'),prerequisite_run_id=1),'fixture',http)
  http.assert_not_called()
 def test_postcheck_requires_r2_migration_workflow(self):
  mk=marker('postcheck');run={'id':123,'path':'.github/workflows/plm-provider-neutral-0010-migration-once.yml','head_sha':mk['prerequisite_commit_sha'],'event':'push','run_attempt':1,'status':'completed','conclusion':'success'}
  with self.assertRaises(p.Stop):c.prerequisite('postcheck',mk,'fixture',Mock(return_value=(200,json.dumps(run).encode())))
 def test_workflows_marker_attempt_only(self):
  for stage in c.CONFIG:
   cfg=c.paths(stage);s=Path(cfg['workflow']).read_text();self.assertIn(cfg['marker'],s);self.assertIn(cfg['message'],s);self.assertIn('github.run_attempt == 1',s);self.assertNotIn('workflow_dispatch',s)
  self.assertNotIn(p.BACKEND_SECRET,Path(c.paths('postcheck')['workflow']).read_text())
 def test_attempt_two_rejected(self):
  with patch.dict(os.environ,{'GITHUB_RUN_ATTEMPT':'2'},clear=True):
   with self.assertRaises(p.Stop):c.local_gate('migration')
 def test_old_and_new_markers_absent(self):
  for version in ('r1','r2'):
   for stage in ('migration','postcheck'):self.assertFalse(Path('audit-evidence/consumed/provider-neutral-0010-'+stage+'-20261011-'+version+'.json').exists())
 def test_migration_local_chain_without_another_preflight(self):
  cfg=c.paths('migration');mk=marker('migration');original=Path.read_bytes
  def rb(path):return json.dumps(mk).encode() if str(path)==cfg['marker'] else original(path)
  env={'GITHUB_REPOSITORY':p.REPO,'GITHUB_REF':'refs/heads/plm-offline-readiness-v1-20261002','GITHUB_EVENT_NAME':'push','GITHUB_RUN_ATTEMPT':'1','GITHUB_SHA':'b'*40,'PLM_APPROVED_BEFORE':'a'*40,**{k:'true' for k in ('TEST_ONLY','DRY_RUN','NO_PUBLISH','EMERGENCY_STOP')}}
  def git(*args):
   if args==('rev-parse','HEAD^'):return 'a'*40
   if args==('rev-parse','HEAD'):return 'b'*40
   if args==('rev-parse','a'*40+'^'):return c.PARENT
   if args[0]=='diff':return cfg['marker']
   if args[0]=='show':return cfg['message']
   if args[0]=='rev-list':return ''
   raise AssertionError(args)
  def show(args):return original(Path(args[2].split(':',1)[1]))
  with patch.dict(os.environ,env,clear=True),patch.object(Path,'read_bytes',rb),patch.object(c,'git',side_effect=git),patch.object(c.subprocess,'run',return_value=Mock(returncode=1)),patch.object(c.subprocess,'check_output',side_effect=show):self.assertEqual(c.local_gate('migration')[0],mk)
class Runtime(unittest.TestCase):
 def test_max_one_unknown_no_resend(self):
  fn=Mock(side_effect=TimeoutError('fixture-secret'));runner=m.ImportRunner();args=(sql(),reference.fresh(),fn,lambda e:None,NOW,plan());out=runner.run(*args);self.assertEqual(out['result'],'UNKNOWN_NO_RESEND_STOP');self.assertEqual(out['migration_executions'],1);runner.run(*args);fn.assert_called_once();self.assertNotIn('fixture-secret',json.dumps(out))
 def test_correct4_ack(self):
  fn=Mock(return_value=completion());out=m.ImportRunner().run(sql(),reference.fresh(),fn,lambda e:None,NOW,plan());self.assertTrue(out['pass']);self.assertEqual(out['query_mutations'],0);self.assertTrue(out['postcheck_required']);self.assertEqual(out['identity'],'provider-neutral-0010-migration-20261011-r2')
 def test_import_md5_actual_sent(self):
  fn=Mock(return_value=completion());m.ImportRunner().run(sql(),reference.fresh(),fn,lambda e:None,NOW,plan());self.assertEqual(fn.call_args.args,('init',{'etag':hashlib.md5(sql()).hexdigest()}))
 def test_metadata_bad_runner_zero_send(self):
  for change in ({'sql_file':'wrong.sql'},{'sql_md5':'0'*32},{'sql_sha256':'0'*64}):
   fn=Mock();out=m.ImportRunner().run(sql(),reference.fresh(),fn,lambda e:None,NOW,dict(plan(),**change));fn.assert_not_called();self.assertEqual(out['side_effect_requests'],0)
 def test_pre_gate_fail_zero_send(self):
  for change in ({'pass':False},{'0008':'NOT_APPLIED'},{'0009':'NOT_APPLIED'},{'0010':'FULL_APPLIED'},{'stable_window_found':False},{'prior_send':1},{'unexpected_objects':1},{'candidate_rows':1},{'d1_writes':1},{'rows_written':1},{'changes':1},{'changed_db':True}):
   fn=Mock();out=m.ImportRunner().run(sql(),dict(reference.fresh(),**change),fn,lambda e:None,NOW,plan());fn.assert_not_called();self.assertEqual(out['side_effect_requests'],0)
 def test_post_read_only(self):
  state,responses,t,calls=reference.fixture(post=True)
  with patch.dict(os.environ,{p.READ_SECRET:'fixture','PLM_HISTORY_GITHUB_TOKEN':'fixture'},clear=True),patch.object(c,'local_gate',return_value=(marker('postcheck'),plan('postcheck'))),patch.object(c,'prerequisite',return_value=True),patch.object(p,'live_transport',return_value=t) as factory,contextlib.redirect_stdout(io.StringIO()) as buf:
   self.assertEqual(post.main(),0);self.assertIsNone(factory.call_args.args[1]);out=json.loads(buf.getvalue());self.assertEqual(out['d1_writes'],0);self.assertEqual(out['migration_executions'],0);self.assertEqual(out['identity'],'provider-neutral-0010-postcheck-20261011-r2')
 def test_no_other_stage_send(self):
  for raw in (Path('serverless/migrations/0008_provider_neutral_roundtrip_backend.sql').read_bytes(),Path('serverless/migrations/0009_youtube_queue_result_proposal.sql').read_bytes()):
   fn=Mock();out=m.ImportRunner().run(raw,reference.fresh(),fn,lambda e:None,NOW,plan());fn.assert_not_called();self.assertEqual(out['side_effect_requests'],0)
