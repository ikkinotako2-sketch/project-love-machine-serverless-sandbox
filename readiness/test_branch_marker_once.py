from oracle_bridge import require_guard
require_guard()
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import branch_marker_once as b
from one_shot_executor import RENDER_ID, Stop
PREFLIGHT_ID = b.PREFLIGHT_V3_ID

ROOT = Path(__file__).resolve().parents[1]
PARENT, LAUNCH = 'a'*40, 'b'*40


def setup(identity=PREFLIGHT_ID):
    kind,wf,plan=b.SPEC[identity]
    workflow=(ROOT/wf).read_bytes(); policy=(ROOT/plan).read_bytes()
    fixture=(ROOT/'readiness/manual_fixture/render-payload.canonical.json').read_bytes()
    marker=dict(identity=identity,kind=kind,approved_parent_sha=PARENT,
                workflow_sha256=b.digest(workflow),plan_sha256=b.digest(policy),fixture_sha256=b.digest(fixture),
                created_for_once_only=True,no_retry=True,no_resume=True)
    context=dict(repository=b.REPO,event='push',branch=b.BRANCH,sha=LAUNCH,
                 approved_parent_sha=PARENT,run_attempt=1,forced=False,deleted=False,created=False)
    commit=dict(sha=LAUNCH,parents=[{'sha':PARENT}],
                files=[{'filename':b.marker_path(identity),'status':'added'}])
    history=[{'sha':PARENT,'parents':[{'sha':b.BASELINE}]},{'sha':b.BASELINE,'parents':[]}]
    return dict(context=context,commit=commit,marker=marker,parent_marker=None,
                history_page=lambda page:history if page==1 else [], marker_history_page=lambda page:[],
                workflow=workflow,plan=policy,fixture=fixture,branch_tip=LAUNCH,identity=identity)


class MarkerGateTests(unittest.TestCase):
    def reject(self,kw,code):
        with self.assertRaisesRegex(Stop,code):b.launch_gate(**kw)

    def test_first_marker_addition_accepted(self):
        self.assertEqual(b.launch_gate(**setup())['scope'],'AUTOMATION_MONOTONIC_CONSUMPTION')
    def test_marker_parent_present(self):
        k=setup();k['parent_marker']={};self.reject(k,'CONSUMED_PARENT')
    def test_modified_rejected(self):
        k=setup();k['commit']['files'][0]['status']='modified';self.reject(k,'ONLY_ADDITION')
    def test_deleted_rejected(self):
        k=setup();k['commit']['files'][0]['status']='removed';self.reject(k,'ONLY_ADDITION')
    def test_delete_readd_history_rejected(self):
        k=setup();k['marker_history_page']=lambda page:[{'sha':b.BASELINE}] if page==1 else []
        self.reject(k,'CONSUMED_HISTORY')
    def test_second_launch_rejected(self):
        k=setup();k['parent_marker']=k['marker'];self.reject(k,'CONSUMED_PARENT')
    def test_rerun_rejected(self):
        k=setup();k['context']['run_attempt']=2;self.reject(k,'RERUN')
    def test_cancel_still_consumed(self):
        k=setup();k['parent_marker']={'conclusion':'cancelled'};self.reject(k,'CONSUMED_PARENT')
    def test_failure_still_consumed(self):
        k=setup();k['parent_marker']={'conclusion':'failure'};self.reject(k,'CONSUMED_PARENT')
    def test_success_still_consumed(self):
        k=setup();k['parent_marker']={'conclusion':'success'};self.reject(k,'CONSUMED_PARENT')
    def test_timeout_still_consumed(self):
        k=setup();k['parent_marker']={'conclusion':'timed_out'};self.reject(k,'CONSUMED_PARENT')
    def test_setup_failure_still_consumed(self):
        k=setup();k['parent_marker']={'conclusion':'setup_failure'};self.reject(k,'CONSUMED_PARENT')
    def test_unknown_still_consumed(self):
        k=setup();k['parent_marker']={'conclusion':None};self.reject(k,'CONSUMED_PARENT')
    def test_parent_mismatch(self):
        k=setup();k['commit']['parents']=[{'sha':'c'*40}];self.reject(k,'PARENT_MISMATCH')
    def test_marker_parent_mismatch(self):
        k=setup();k['marker']['approved_parent_sha']='c'*40;self.reject(k,'PARENT_MISMATCH')
    def test_merge_launch_rejected(self):
        k=setup();k['commit']['parents'].append({'sha':'c'*40});self.reject(k,'PARENT_MISMATCH')
    def test_unexpected_branch(self):
        k=setup();k['context']['branch']='main';self.reject(k,'UNEXPECTED_BRANCH')
    def test_unrelated_push(self):
        k=setup();k['commit']['files'][0]['filename']='readiness/unrelated.json';self.reject(k,'ONLY_ADDITION')
    def test_history_pagination_failure(self):
        k=setup()
        def fail(page):
            if page>1:raise TimeoutError()
            return [{'sha':PARENT,'parents':[{'sha':b.BASELINE}]},{'sha':b.BASELINE,'parents':[]}]
        k['history_page']=fail;self.reject(k,'PAGINATION_FAILURE')
    def test_history_gap(self):
        k=setup();k['history_page']=lambda p:[{'sha':PARENT,'parents':[{'sha':'c'*40}]},{'sha':b.BASELINE,'parents':[]}] if p==1 else []
        self.reject(k,'BLOCKED_HISTORY_CONTINUITY_LOST')
    def test_baseline_missing(self):
        k=setup();k['history_page']=lambda p:[{'sha':PARENT,'parents':[]}] if p==1 else []
        self.reject(k,'BLOCKED_HISTORY_CONTINUITY_LOST')
    def test_baseline_disconnected(self):
        k=setup();k['history_page']=lambda p:[{'sha':PARENT,'parents':[]},{'sha':b.BASELINE,'parents':[]}] if p==1 else []
        self.reject(k,'BLOCKED_HISTORY_CONTINUITY_LOST')
    def test_marker_identity_mismatch(self):
        k=setup();k['marker']['identity']=RENDER_ID;self.reject(k,'IDENTITY_MISMATCH')
    def test_workflow_hash_mismatch(self):
        k=setup();k['workflow']+=b'drift';self.reject(k,'WORKFLOW_SHA256_MISMATCH')
    def test_plan_hash_mismatch(self):
        k=setup();k['plan']+=b'drift';self.reject(k,'PLAN_SHA256_MISMATCH')
    def test_fixture_hash_mismatch(self):
        k=setup();k['fixture']+=b'drift';self.reject(k,'FIXTURE_SHA256_MISMATCH')
    def test_marker_only_diff(self):
        k=setup();k['commit']['files'].append({'filename':b.SPEC[PREFLIGHT_ID][1],'status':'modified'})
        self.reject(k,'ONLY_ADDITION')
    def test_markers_independent(self):
        for identity in (PREFLIGHT_ID,RENDER_ID):self.assertEqual(b.launch_gate(**setup(identity))['identity'],identity)
        self.assertNotEqual(b.marker_path(PREFLIGHT_ID),b.marker_path(RENDER_ID))
    def test_no_marker_files_created(self):
        for identity in (PREFLIGHT_ID,RENDER_ID):self.assertFalse((ROOT/b.marker_path(identity)).exists())
        self.assertTrue((ROOT/b.marker_path(b.PREFLIGHT_ID)).is_file())
        self.assertTrue((ROOT/b.marker_path(b.PREFLIGHT_V2_ID)).is_file())
    def test_force_push_stop(self):
        k=setup();k['context']['forced']=True;self.reject(k,'BLOCKED_HISTORY_CONTINUITY_LOST')
    def test_changed_branch_tip_stop(self):
        k=setup();k['branch_tip']='c'*40;self.reject(k,'BLOCKED_HISTORY_CONTINUITY_LOST')
    def test_marker_history_pagination_failure(self):
        k=setup()
        def fail(p):raise TimeoutError()
        k['marker_history_page']=fail;self.reject(k,'PAGINATION_FAILURE')
    def test_ambiguous_pages_stop(self):
        k=setup();k['history_page']=lambda p:None;self.reject(k,'AMBIGUOUS_HISTORY')
    def test_duplicate_page_stop(self):
        k=setup();k['history_page']=lambda p:[{'sha':PARENT}];self.reject(k,'AMBIGUOUS_HISTORY')
    def test_cycle_stop(self):
        k=setup();k['history_page']=lambda p:[{'sha':PARENT,'parents':[{'sha':b.BASELINE}]},{'sha':b.BASELINE,'parents':[{'sha':PARENT}]}] if p==1 else []
        self.reject(k,'BLOCKED_HISTORY_CONTINUITY_LOST')
    def test_false_flags_rejected(self):
        for field in ('created_for_once_only','no_retry','no_resume'):
            k=setup();k['marker'][field]=False;self.reject(k,'ONCE_FLAGS')
    def test_extra_timestamp_not_identity(self):
        k=setup();k['marker']['timestamp']='now';self.reject(k,'SCHEMA_MISMATCH')
    def test_read_permissions_only(self):
        s=(ROOT/b.SPEC[PREFLIGHT_ID][1]).read_text()
        self.assertIn('contents: read',s);self.assertIn('actions: read',s);self.assertNotIn(': write',s)
        self.assertIn('persist-credentials: false',s)
    def test_push_scope_exact(self):
        s=(ROOT/b.SPEC[PREFLIGHT_ID][1]).read_text()
        self.assertIn("branches: ['"+b.BRANCH+"']",s)
        self.assertIn("paths: ['"+b.marker_path(PREFLIGHT_ID)+"']",s)
        self.assertNotIn('on: workflow_dispatch',s)
    def test_schema_required_fields(self):
        schema=json.loads((ROOT/'readiness/branch-marker-schema.json').read_text())
        self.assertEqual(set(schema['required']),b.FIELDS);self.assertFalse(schema['additionalProperties'])
    def test_multi_page_complete_ancestry(self):
        k=setup();k['history_page']=lambda p:([{'sha':PARENT,'parents':[{'sha':b.BASELINE}]}] if p==1 else [{'sha':b.BASELINE,'parents':[]}] if p==2 else [])
        self.assertTrue(b.launch_gate(**k)['consumed'])
    def test_readonly_cli_guard_precedes_effect(self):
        import cloud_runtime_preflight as cloud
        calls=[]
        def fail():raise Stop('BLOCKED_HISTORY_CONTINUITY_LOST')
        with self.assertRaises(Stop):cloud.runtime_preflight({}, {},run=lambda *a,**kw:calls.append(a),read=lambda *a:calls.append(a),ledger_guard=fail)
        self.assertEqual(calls,[])

class AdapterTests(unittest.TestCase):
    def fake(self):
        k=setup()
        event=dict(before=PARENT,after=LAUNCH,ref='refs/heads/'+b.BRANCH,
                   forced=False,created=False,deleted=False)
        env=dict(GITHUB_ACTIONS='true',RUNNER_ENVIRONMENT='github-hosted',RUNNER_OS='Linux',
                 RUNNER_ARCH='X64',GITHUB_REPOSITORY=b.REPO,GITHUB_EVENT_NAME='push',GITHUB_REF=event['ref'],
                 GITHUB_SHA=LAUNCH,GITHUB_RUN_ATTEMPT='1',GITHUB_RUN_ID='101',GITHUB_EVENT_PATH='/in-memory-event')
        calls=[]
        def read(route,**kw):
            calls.append(route)
            if route.startswith('/contents/'):return None
            if route.startswith('/git/ref/'):return {'object':{'sha':LAUNCH}}
            if route.startswith('/actions/runs/'):
                return dict(head_sha=LAUNCH,event='push',run_attempt=1,path=b.SPEC[PREFLIGHT_ID][1],
                            head_branch=b.BRANCH,id=101,repository={'full_name':b.REPO})
            if route.startswith('/commits/'+LAUNCH):
                return k['commit'] if route.endswith('page=1') else {'files':[]}
            if '&path=' in route:return []
            if route.startswith('/commits?'):return k['history_page'](int(route.rsplit('=',1)[1]))
            raise AssertionError(route)
        original=Path.read_text
        def text(path,*a,**kw):
            if str(path)=='/in-memory-event':return json.dumps(event)
            if str(path).endswith(b.marker_path(PREFLIGHT_ID)):return json.dumps(k['marker'])
            return original(path,*a,**kw)
        isfile=Path.is_file
        def exists(path):
            return True if str(path).endswith(b.marker_path(PREFLIGHT_ID)) else isfile(path)
        return k,event,env,calls,read,text,exists

    def test_full_adapter_accepts_without_marker_write(self):
        k,event,env,calls,read,text,exists=self.fake()
        with patch.object(Path,'read_text',text),patch.object(Path,'is_file',exists):
            self.assertTrue(b.cloud_launch_guard(env,identity=PREFLIGHT_ID,read=read)['consumed'])
        self.assertTrue(all(r.startswith(('/commits','/contents/','/git/ref/','/actions/runs/')) for r in calls))
    def test_full_adapter_rejects_secondary_run_unknown(self):
        k,event,env,calls,read,text,exists=self.fake()
        def changed(route,**kw):return {} if route.startswith('/actions/runs/') else read(route,**kw)
        with patch.object(Path,'read_text',text),patch.object(Path,'is_file',exists):
            with self.assertRaisesRegex(Stop,'SECONDARY_RUN'):b.cloud_launch_guard(env,identity=PREFLIGHT_ID,read=changed)
    def test_full_adapter_rejects_extra_diff_page(self):
        k,event,env,calls,read,text,exists=self.fake()
        def changed(route,**kw):return {'files':[{'filename':'extra'}]} if route.startswith('/commits/'+LAUNCH) and route.endswith('page=2') else read(route,**kw)
        with patch.object(Path,'read_text',text),patch.object(Path,'is_file',exists):
            with self.assertRaisesRegex(Stop,'ONLY_ADDITION'):b.cloud_launch_guard(env,identity=PREFLIGHT_ID,read=changed)
    def test_full_adapter_rechecks_branch_tip(self):
        k,event,env,calls,read,text,exists=self.fake();tips=[]
        def changed(route,**kw):
            if route.startswith('/git/ref/'):
                tips.append(1)
                return {'object':{'sha':LAUNCH if len(tips)==1 else 'c'*40}}
            return read(route,**kw)
        with patch.object(Path,'read_text',text),patch.object(Path,'is_file',exists):
            with self.assertRaisesRegex(Stop,'CONTINUITY_LOST'):b.cloud_launch_guard(env,identity=PREFLIGHT_ID,read=changed)
    def test_wrong_event_before_api(self):
        k,event,env,calls,read,text,exists=self.fake();env['GITHUB_EVENT_NAME']='workflow_dispatch'
        with patch.object(Path,'read_text',text),patch.object(Path,'is_file',exists):
            with self.assertRaises(Stop):b.cloud_launch_guard(env,identity=PREFLIGHT_ID,read=read)
        self.assertEqual(calls,[])
    def test_no_local_runner_before_api(self):
        k,event,env,calls,read,text,exists=self.fake();env['GITHUB_ACTIONS']='false'
        with self.assertRaisesRegex(Stop,'CLOUD_RUNNER_REQUIRED'):b.cloud_launch_guard(env,identity=PREFLIGHT_ID,read=read)
        self.assertEqual(calls,[])
    def test_marker_render_oracle_uses_primary_guard(self):
        from test_one_shot_executor import FakeEffects,context
        from one_shot_executor import OfflineExecutor
        effects=FakeEffects()
        receipt=b.launch_gate(**setup(RENDER_ID))
        result=OfflineExecutor(context(),effects,consumption_gate=lambda:receipt).execute()
        self.assertEqual(result['history']['scope'],'AUTOMATION_MONOTONIC_CONSUMPTION')
        self.assertNotIn('history_page',[stage for stage,args in effects.calls])
    def test_marker_guard_failure_no_simulated_runtime(self):
        from test_one_shot_executor import FakeEffects,context
        from one_shot_executor import OfflineExecutor
        effects=FakeEffects()
        def fail():raise Stop('IDENTITY_CONSUMED_HISTORY')
        with self.assertRaises(Stop):OfflineExecutor(context(),effects,consumption_gate=fail).execute()
        self.assertEqual(effects.calls,[])
