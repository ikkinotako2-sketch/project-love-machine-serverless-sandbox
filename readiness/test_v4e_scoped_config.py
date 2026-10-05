from oracle_bridge import require_guard
require_guard()
import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import apt_scoped_config_v4e as e
import apt_config_fields_v4d as f
import cloud_runtime_preflight_v4e as v
import branch_marker_once as b
from one_shot_executor import Stop,RENDER_ID
from test_branch_marker_once import setup
SECRET='ghp_SUPER_SECRET token=never_print /secret/path'
ARCH='APT::Architectures "";\nAPT::Architectures:: "amd64";\nAPT::Architectures:: "amd64";\n'
UNKNOWN='Unknown::Defaults "unclosed '+SECRET+'\nUnknown::Regex "\\q";\nAPT::Architecture { unknown syntax '+SECRET+'\nBinary::apt-get::APT::Keep-Downloaded-Packages = '+SECRET+'\n'

class ScopedTests(unittest.TestCase):
    def reject(self,call,scope,reason):
        with self.assertRaises(e.ScopeStop) as raised:call()
        public=raised.exception.evidence();self.assertEqual(public['scope_id'],scope);self.assertEqual(public['fixed_reason'],reason)
        self.assertEqual(set(public),{'scope_id','syntax_kind','matched','fixed_reason'});self.assertNotIn(SECRET,str(raised.exception)+json.dumps(public))
    def test_large_unknown_defaults_ignore(self):self.assertTrue(all(x['matched'] for x in e.inspect(UNKNOWN*5000+ARCH)))
    def test_unknown_value_unsupported_escape_ignore(self):self.assertTrue(e.inspect(UNKNOWN+ARCH)[0]['matched'])
    def test_unknown_key_unknown_format_ignore(self):self.assertTrue(e.inspect('@UNKNOWN '+SECRET+'\n'+ARCH)[0]['matched'])
    def test_scalar_dump_not_authority(self):self.assertTrue(e.inspect('APT::Get::Download "true";\nAPT::Get::Download MALFORMED\n'+ARCH)[0]['matched'])
    def test_relevant_prefix_unknown_format_stop(self):self.reject(lambda:e.inspect(ARCH+'DPkg::Pre-Invoke = '+SECRET),'DPKG_HOOKS','RELEVANT_SCOPE_SYNTAX_UNSUPPORTED')
    def test_relevant_malformed_punctuation_stop(self):self.reject(lambda:e.inspect(ARCH+'APT::Update::Post-Invoke#bad '+SECRET),'APT_UPDATE_HOOKS','RELEVANT_SCOPE_SYNTAX_UNSUPPORTED')
    def test_relevant_escape_unsupported_stop(self):self.reject(lambda:e.inspect(ARCH+'RootDir "\\q";\n'),'ROOT_DIR','RELEVANT_SCOPE_SYNTAX_UNSUPPORTED')
    def test_anonymous_architecture(self):self.assertTrue(e.inspect(ARCH)[0]['matched'])
    def test_duplicate_amd64_not_scalar_duplicate(self):self.assertTrue(e.inspect(ARCH*2)[0]['matched'])
    def test_arm64_mixed_stop(self):self.reject(lambda:e.inspect(ARCH+'APT::Architectures:: "arm64";\n'),'ARCHITECTURES','REQUIRED_SCOPE_VALUE_MISMATCH')
    def test_arch_missing(self):self.reject(lambda:e.inspect(UNKNOWN),'ARCHITECTURES','REQUIRED_SCOPE_MISSING')
    def test_named_arch_list_stop(self):self.reject(lambda:e.inspect(ARCH+'APT::Architectures::named "amd64";\n'),'ARCHITECTURES','ARCH_LIST_UNSUPPORTED')
    def test_arch_scalar_parent_stop(self):self.reject(lambda:e.inspect('APT::Architectures "amd64";\n'+ARCH),'ARCHITECTURES','ARCH_LIST_UNSUPPORTED')
    def test_nonempty_dpkg_hook(self):self.reject(lambda:e.inspect(ARCH+'DPkg::Pre-Invoke:: "'+SECRET+'";\n'),'DPKG_HOOKS','FORBIDDEN_HOOK_PRESENT')
    def test_nonempty_post_hook(self):self.reject(lambda:e.inspect(ARCH+'DPkg::Post-Invoke::named "'+SECRET+'";\n'),'DPKG_HOOKS','FORBIDDEN_HOOK_PRESENT')
    def test_nonempty_preinstall_hook(self):self.reject(lambda:e.inspect(ARCH+'DPkg::Pre-Install-Pkgs:: "'+SECRET+'";\n'),'DPKG_HOOKS','FORBIDDEN_HOOK_PRESENT')
    def test_nonempty_apt_update_hook(self):self.reject(lambda:e.inspect(ARCH+'APT::Update::Pre-Invoke:: "'+SECRET+'";\n'),'APT_UPDATE_HOOKS','FORBIDDEN_HOOK_PRESENT')
    def test_nonempty_postsuccess_hook(self):self.reject(lambda:e.inspect(ARCH+'APT::Update::Post-Invoke-Success:: "'+SECRET+'";\n'),'APT_UPDATE_HOOKS','FORBIDDEN_HOOK_PRESENT')
    def test_empty_hooks_pass(self):self.assertTrue(all(x['matched'] for x in e.inspect(ARCH+'DPkg::Pre-Invoke "";\nDPkg::Pre-Invoke:: "";\nAPT::Update::Post-Invoke:: "";\n')))
    def test_absent_hooks_pass(self):self.assertTrue(e.inspect(ARCH)[2]['matched'])
    def test_rootdir_empty_dump(self):self.assertTrue(e.inspect(ARCH+'RootDir "";\n')[1]['matched'])
    def test_rootdir_empty_query(self):self.assertTrue(e.root_query("PLM_VALUE=''\n")['matched'])
    def test_rootdir_absent_query(self):self.assertTrue(e.root_query('')['matched'])
    def test_rootdir_host_path_stop(self):self.reject(lambda:e.inspect(ARCH+'RootDir "/etc/apt";\n'),'ROOT_DIR','HOST_SOURCE_LEAK')
    def test_rootdir_other_nonempty_stop(self):self.reject(lambda:e.root_query("PLM_VALUE='"+SECRET+"'\n"),'ROOT_DIR','REQUIRED_SCOPE_VALUE_MISMATCH')
    def test_rootdir_host_query_stop(self):self.reject(lambda:e.root_query("PLM_VALUE='/etc/apt'\n"),'ROOT_DIR','HOST_SOURCE_LEAK')
    def test_binary_source_override_stop(self):self.reject(lambda:e.inspect(ARCH+'Binary::apt-get::Dir::Etc::sourceparts "/etc/apt/sources.list.d";\n'),'BINARY_OVERRIDES','HOST_SOURCE_LEAK')
    def test_binary_config_override_stop(self):self.reject(lambda:e.inspect(ARCH+'Binary::apt-cache::Dir::Etc::main "/etc/apt/apt.conf";\n'),'BINARY_OVERRIDES','HOST_SOURCE_LEAK')
    def test_binary_flag_override_stop(self):self.reject(lambda:e.inspect(ARCH+'Binary::apt-config::APT::Get::Download "true";\n'),'BINARY_OVERRIDES','BINARY_OVERRIDE_CONFLICT')
    def test_binary_empty_leaf_shadow_stop(self):self.reject(lambda:e.inspect(ARCH+'Binary::apt-get::Dir::State::status "";\n'),'BINARY_OVERRIDES','BINARY_OVERRIDE_CONFLICT')
    def test_binary_hook_stop(self):self.reject(lambda:e.inspect(ARCH+'Binary::apt-get::DPkg::Pre-Install-Pkgs:: "'+SECRET+'";\n'),'BINARY_OVERRIDES','FORBIDDEN_HOOK_PRESENT')
    def test_unrelated_binary_defaults_ignore(self):self.assertTrue(e.inspect(ARCH+UNKNOWN)[4]['matched'])
    def test_empty_binary_parent_nodes_pass(self):self.assertTrue(e.inspect(ARCH+'Binary::apt-get "";\nBinary::apt-get::Dir::Etc "";\n')[4]['matched'])
    def test_dump_query_failed(self):self.reject(lambda:e.inspect(SECRET,100),'CONFIG_INSPECTION','DUMP_QUERY_FAILED')
    def test_dump_bounded(self):self.reject(lambda:e.inspect('x'*2000001),'CONFIG_INSPECTION','RELEVANT_SCOPE_SYNTAX_UNSUPPORTED')
    def test_safe_evidence_keys_only(self):
        report=e.inspect(UNKNOWN+ARCH)
        self.assertTrue(all(set(x)=={'scope_id','syntax_kind','matched','fixed_reason'} for x in report));self.assertNotIn(SECRET,json.dumps(report))
    def test_unknown_default_no_reason(self):self.assertTrue(all(x['fixed_reason'] is None for x in e.inspect(UNKNOWN+ARCH)))
    def test_004d_evidence_22_pass_fixed(self):
        plan=json.loads(v.PLAN.read_text());raw=(v.ROOT/plan['prior_004d_evidence']).read_bytes();evidence=json.loads(raw)
        self.assertEqual(hashlib.sha256(raw).hexdigest(),plan['prior_004d_evidence_sha256']);self.assertEqual(evidence['scalar_pass_count'],22)
        self.assertEqual(evidence['run_id'],37265615646);self.assertEqual(evidence['simulation_count'],0)
    def test_004d_consumed(self):
        with self.assertRaisesRegex(Stop,'IDENTITY_CONSUMED_004D'):b.cloud_launch_guard({},b.PREFLIGHT_V4D_ID)
    def test_current_unconsumed_identity_independent(self):self.assertTrue(b.launch_gate(**setup(b.PREFLIGHT_V4F_ID))['allow'])
    def test_004e_consumed_marker_retained(self):self.assertTrue((v.ROOT/b.marker_path(v.IDENTITY)).exists())
    def test_render_marker_absent(self):self.assertFalse((v.ROOT/b.marker_path(RENDER_ID)).exists())
    def test_005_absent(self):self.assertFalse(list((v.ROOT/'.github/workflows').glob('*v5*')))
    def test_guard_failure_zero_adapters(self):
        with patch.object(v,'cloud_launch_guard',side_effect=Stop('MARKER_MISSING')),patch.object(v,'command') as process,patch.object(v,'load_indices') as network:
            with self.assertRaises(Stop):v.execute(json.loads(v.PLAN.read_text()),{})
        process.assert_not_called();network.assert_not_called()
    def test_main_reports_safe_scope_only(self):
        with contextlib.redirect_stdout(io.StringIO()) as out,patch.object(v,'PROGRESS',{}),patch.object(v,'execute',side_effect=e.ScopeStop('DPKG_HOOKS','FILTERED_DUMP','FORBIDDEN_HOOK_PRESENT')):
            with self.assertRaises(SystemExit):v.main()
        self.assertIn('"scope_id": "DPKG_HOOKS"',out.getvalue());self.assertNotIn(SECRET,out.getvalue())
    def test_fake_pipeline_unknown_defaults_pass(self):self.pipeline(False)
    def test_fake_pipeline_relevant_failure_blocks_continuation(self):self.pipeline(True)
    def pipeline(self,relevant_failure):
        from test_apt_transaction_v4 import meta
        from test_v4c_startup import policy
        plan=json.loads(v.PLAN.read_text());roots=plan['root_constraints'];calls=[]
        status=b'Package: base\nVersion: 1\nArchitecture: amd64\nStatus: install ok installed\n'
        oldbytes=Path.read_bytes;oldtext=Path.read_text
        def read_bytes(path):return status if str(path)=='/var/lib/dpkg/status' else oldbytes(path)
        def read_text(path,*args,**kwargs):return 'ID=ubuntu\nVERSION_ID="24.04"\n' if str(path)=='/etc/os-release' else oldtext(path,*args,**kwargs)
        records={}
        for name,version in roots.items():
            p=meta(name,version);p['suite']='noble';records[(name,version,'amd64')]=p
        def command(label,args,config=None,roots=None,package=None):
            calls.append((label,args))
            if label=='apt_binary':return 0,'apt 2.8.3 (amd64)\n',''
            if label=='apt_config':
                if args[-1]=='dump':return 0,ARCH+UNKNOWN+('DPkg::Pre-Invoke = BAD' if relevant_failure else ''),SECRET
                if args[-1]=='RootDir':return 0,"PLM_VALUE=''\n",SECRET
                fid=dict((key,fid) for fid,key in f.FIELDS)[args[-1]];value=f.expected_scalars(Path(config).parent,Path(config).parent/'ubuntu-archive-keyring.gpg')[fid]
                return 0,"PLM_VALUE='"+value+"'\n",SECRET
            if label=='index_visibility':
                name=args[-1];version=plan['root_constraints'][name];return 0,policy(version,version).replace('root:',name+':'),''
            return 0,'0 upgraded, 1 newly installed, 0 to remove and 0 not upgraded.\n','Starting pkgProblemResolver with broken count: 0\nDone\n'
        receipt=dict(identity=v.IDENTITY,consumed=True,allow=True,execution_approved=True,no_retry=True,no_resume=True,run_id='fake',launch_sha='a'*40)
        with tempfile.TemporaryDirectory() as temp,patch.dict(v.os.environ,{'RUNNER_TEMP':temp}),patch.object(v.sys,'version_info',(3,12,15)),patch.object(Path,'read_bytes',read_bytes),patch.object(Path,'read_text',read_text),patch.object(v,'cloud_launch_guard',return_value=receipt),patch.object(v,'command',side_effect=command),patch.object(v,'load_indices',return_value=({'noble':records},{},{'matched':True})) as indices,contextlib.redirect_stdout(io.StringIO()) as out:
            env=dict(RUNNER_TEMP=temp,RUNNER_ENVIRONMENT='github-hosted',ImageOS='ubuntu24',RUNNER_ARCH='X64')
            if relevant_failure:
                self.reject(lambda:v.execute(plan,env),'DPKG_HOOKS','RELEVANT_SCOPE_SYNTAX_UNSUPPORTED');indices.assert_not_called()
                self.assertFalse(any(label=='resolver_start' for label,args in calls))
            else:
                report=v.execute(plan,env);indices.assert_called_once();self.assertTrue(report['completed_stages']['apt_config']['matched'])
                self.assertEqual(len(report['completed_stages']['apt_config']['checks']),22);self.assertEqual(sum(label=='resolver_start' for label,args in calls),11)
                self.assertFalse(report['transaction_proof']);self.assertFalse(report['install_authorized'])
            self.assertEqual(sum(label=='apt_config' for label,args in calls),24)
            self.assertNotIn(SECRET,out.getvalue());self.assertNotIn(temp,out.getvalue())
    def test_rootdir_query_malformed_safe(self):self.reject(lambda:e.root_query(SECRET),'ROOT_DIR','RELEVANT_SCOPE_SYNTAX_UNSUPPORTED')
    def test_workflow_readonly_exact_marker_guard(self):
        wf=(v.ROOT/b.SPEC[v.IDENTITY][1]).read_text()
        self.assertIn("paths: ['"+b.marker_path(v.IDENTITY)+"']",wf);self.assertIn('contents: read',wf);self.assertIn('actions: read',wf)
        self.assertNotIn('contents: write',wf);self.assertEqual(wf.count("if: steps.marker.outputs.allow == 'true' && steps.marker.outputs.execution_approved == 'true'"),2)
    def test_command_transport_failure_scope_safe(self):
        with contextlib.redirect_stdout(io.StringIO()) as out,patch.object(v,'CURRENT_FIELD','CONFIG_INSPECTION'),patch.object(v.v4,'private_directory'),patch.object(v.b4,'_bounded_simulation',side_effect=RuntimeError(SECRET)):
            self.reject(lambda:v.command('apt_config',['/usr/bin/apt-config','dump'],'/tmp/apt.conf'),'CONFIG_INSPECTION','DUMP_QUERY_FAILED')
        self.assertNotIn(SECRET,out.getvalue())
