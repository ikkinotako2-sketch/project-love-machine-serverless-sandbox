from oracle_bridge import require_guard
require_guard()
import ast
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import apt_transaction_v4 as t
import cloud_runtime_preflight_v4 as v
import branch_marker_once as b
from one_shot_executor import Stop,RENDER_ID
from test_branch_marker_once import setup
from test_apt_transaction_v4 import fixture,run


class ActivationTests(unittest.TestCase):
    def test_no_static_authorization(self):
        plan=json.loads(v.PLAN.read_text());self.assertNotIn('execution_approved',plan);self.assertNotIn('hard_disabled',plan)
        text=(v.ROOT/b.SPEC[v.IDENTITY][1]).read_text()
        self.assertNotIn("      allow:",text);self.assertNotIn("      execution_approved:",text)
        self.assertEqual(text.count("if: steps.marker.outputs.allow == 'true' && steps.marker.outputs.execution_approved == 'true'"),2)
    def test_trigger_exact_and_scope(self):
        text=(v.ROOT/b.SPEC[v.IDENTITY][1]).read_text()
        self.assertIn("paths: ['"+b.marker_path(v.IDENTITY)+"']",text)
        self.assertIn("branches: ['"+b.BRANCH+"']",text)
        for expression in ("github.repository == '"+b.REPO+"'","github.event_name == 'push'","github.ref == 'refs/heads/"+b.BRANCH+"'"):
            self.assertIn(expression,text)
        for flag in ('TEST_ONLY','DRY_RUN','NO_PUBLISH','EMERGENCY_STOP'):self.assertIn(flag+": 'true'",text)
    def test_wrong_repository(self):
        k=setup(b.PREFLIGHT_V4C_ID);k['context']['repository']='other/repo'
        with self.assertRaisesRegex(Stop,'UNEXPECTED_BRANCH_OR_EVENT'):b.launch_gate(**k)
    def test_wrong_branch(self):
        k=setup(b.PREFLIGHT_V4C_ID);k['context']['branch']='main'
        with self.assertRaisesRegex(Stop,'UNEXPECTED_BRANCH_OR_EVENT'):b.launch_gate(**k)
    def test_wrong_event(self):
        k=setup(b.PREFLIGHT_V4C_ID);k['context']['event']='workflow_dispatch'
        with self.assertRaisesRegex(Stop,'UNEXPECTED_BRANCH_OR_EVENT'):b.launch_gate(**k)
    def test_marker_modified_deleted(self):
        for status in ('modified','removed'):
            k=setup(b.PREFLIGHT_V4C_ID);k['commit']['files'][0]['status']=status
            with self.assertRaisesRegex(Stop,'ONLY_ADDITION'):b.launch_gate(**k)
    def test_rerun(self):
        k=setup(b.PREFLIGHT_V4C_ID);k['context']['run_attempt']=2
        with self.assertRaisesRegex(Stop,'RERUN'):b.launch_gate(**k)
    def test_guard_failure_zero_process_and_network(self):
        for code in ('MARKER_MISSING','RERUN_REJECTED','BLOCKED_HISTORY_CONTINUITY_LOST'):
            with patch.object(v,'cloud_launch_guard',side_effect=Stop(code)),patch.object(v,'command') as process,patch.object(v,'metadata_get') as network:
                with self.assertRaisesRegex(Stop,code):v.execute(json.loads(v.PLAN.read_text()),{})
                process.assert_not_called();network.assert_not_called()
    def test_marker_absent_real_guard_rejects_before_runtime(self):
        self.assertTrue((v.ROOT/b.marker_path(v.IDENTITY)).exists())
        with patch.object(v,'cloud_launch_guard',side_effect=Stop('MARKER_MISSING')),patch.object(v,'bounded_process') as process:
            with self.assertRaisesRegex(Stop,'MARKER_MISSING'):v.execute(json.loads(v.PLAN.read_text()),{})
            process.assert_not_called()
    def test_static_true_cannot_bypass_guard(self):
        p=json.loads(v.PLAN.read_text());p['execution_approved']=True;p['allow']=True
        with patch.object(v,'cloud_launch_guard',side_effect=Stop('MARKER_MISSING')),patch.object(v,'command') as process:
            with self.assertRaisesRegex(Stop,'MARKER_MISSING'):v.execute(p,{'allow':'true','execution_approved':'true'})
            process.assert_not_called()
    def test_guard_pass_reaches_source_only_after_guard(self):
        order=[]
        def guard(*args):
            order.append('guard');return dict(identity=v.IDENTITY,consumed=True,allow=True,execution_approved=True,no_retry=True,no_resume=True)
        def source(*args):order.append('source');raise Stop('RUNTIME_APT_SOURCE_FAILED')
        env={'RUNNER_ENVIRONMENT':'github-hosted','RUNNER_OS':'Linux','RUNNER_ARCH':'X64','ImageOS':'ubuntu24'}
        with patch.object(v,'cloud_launch_guard',side_effect=guard),patch.object(v,'validate_source',side_effect=source),patch.object(v,'safe_stage'),patch.object(v.sys,'version_info',(3,12,15)),patch.object(Path,'read_text',return_value='ID=ubuntu\nVERSION_ID="24.04"'),patch.object(v,'command') as process,patch.object(v,'metadata_get') as network:
            with self.assertRaisesRegex(Stop,'RUNTIME_APT_SOURCE_FAILED'):v.execute({},env)
            self.assertEqual(order,['guard','source']);process.assert_not_called();network.assert_not_called()
    def test_guard_receipt_false_rejected(self):
        with patch.object(v,'cloud_launch_guard',return_value={'identity':v.IDENTITY,'consumed':True,'allow':False}),patch.object(v,'metadata_get') as network:
            with self.assertRaisesRegex(Stop,'RUNTIME_APT_SOURCE_FAILED'):v.execute({},{} )
            network.assert_not_called()
    def test_runner_temp_path_isolation(self):
        with tempfile.TemporaryDirectory() as base:
            good=Path(base)/'plm-resolver-004-test';good.mkdir()
            self.assertEqual(v.private_directory(good,base),good)
            with self.assertRaisesRegex(Stop,'SOURCE_FAILED'):v.private_directory('/tmp/plm-resolver-004-outside',base)
    def test_no_forbidden_adapters(self):
        tree=ast.parse(Path(v.__file__).read_text())
        imports={node.names[0].name for node in ast.walk(tree) if isinstance(node,ast.Import)}
        self.assertTrue(imports.isdisjoint({'docker','voicevox','ffmpeg','requests'}))
        funcs={node.name for node in ast.walk(tree) if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef))}
        self.assertTrue(funcs.isdisjoint({'install','download_package','synthesis','encode','docker_pull','docker_start'}))
        with self.assertRaisesRegex(Stop,'SOURCE_FAILED'):v.metadata_get(v.BASE+'/pool/main/a/a.deb',10,'a'*64,'index')
    def test_render_independent(self):
        self.assertNotEqual(b.marker_path(v.IDENTITY),b.marker_path(RENDER_ID));self.assertFalse((v.ROOT/b.marker_path(RENDER_ID)).exists())
    def test_blocked_never_emits_canonical_or_fingerprint(self):
        r=run(fixture());r['status']='BLOCKED';r['failure_code']='RUNTIME_APT_UNEXPECTED_UPGRADE'
        public=v.public_evidence(r);self.assertNotIn('transaction',public);self.assertNotIn('transaction_fingerprint',public)
    def test_pass_emits_canonical(self):
        r=run(fixture());self.assertIn('transaction_fingerprint',v.public_evidence(r))
    def test_bounded_process_no_capture_output(self):
        source=Path(v.__file__).read_text();self.assertNotIn('capture_output=True',source)
        for text in ('2_000_000','stderr_size<=65536','time.monotonic()+120','os.killpg'):self.assertIn(text,source)
    def test_absent_marker_actual_cloud_guard(self):
        k=setup(b.PREFLIGHT_V4C_ID)
        event={'before':k['context']['approved_parent_sha'],'after':k['context']['sha'],
               'ref':'refs/heads/'+b.BRANCH,'forced':False,'deleted':False,'created':False}
        with tempfile.TemporaryDirectory() as directory:
            event_path=Path(directory)/'event.json';event_path.write_text(json.dumps(event))
            env={'GITHUB_ACTIONS':'true','RUNNER_ENVIRONMENT':'github-hosted','RUNNER_OS':'Linux','RUNNER_ARCH':'X64',
                 'GITHUB_REPOSITORY':b.REPO,'GITHUB_EVENT_NAME':'push','GITHUB_REF':event['ref'],
                 'GITHUB_SHA':event['after'],'GITHUB_RUN_ATTEMPT':'1','GITHUB_EVENT_PATH':str(event_path)}
            def read(route,**kwargs):
                if route.startswith('/commits/'):
                    return {'files':[]} if 'page=2' in route else k['commit']
                if route.startswith('/contents/'):return None
                raise AssertionError('Unexpected read before absent-marker STOP')
            with self.assertRaisesRegex(Stop,'MARKER_MISSING'):b.cloud_launch_guard(env,b.PREFLIGHT_V4C_ID,read=read)
    def test_bounded_output_limit_stops_and_no_raw_exception(self):
        class Pipe:
            def fileno(self):return 1
            def close(self):pass
        class Proc:
            stdout=Pipe();stderr=Pipe();pid=123
            def poll(self):return None
            def wait(self,**kw):return -9
        class Key:fileobj=Pipe();data='stdout'
        class Selector:
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def register(self,*args):pass
            def get_map(self):return {'pipe':1}
            def select(self,**kwargs):return [(Key(),1)]
        with patch.object(v.subprocess,'Popen',return_value=Proc()),patch.object(v.selectors,'DefaultSelector',return_value=Selector()),patch.object(v.os,'set_blocking'),patch.object(v.os,'read',return_value=b'x'*65536),patch.object(v.os,'killpg') as kill:
            with self.assertRaisesRegex(Stop,'RUNTIME_APT_SIMULATION_FAILED'):v.bounded_process(['FAKE'],{})
            kill.assert_called_once()
