from oracle_bridge import require_guard
require_guard()
import contextlib
import hashlib
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import apt_config_fields_v4d as f
import cloud_runtime_preflight_v4d as v
import apt_startup_v4c as legacy
import branch_marker_once as b
from one_shot_executor import Stop,RENDER_ID
from test_branch_marker_once import setup
SECRET='ghp_SECRET token=never_echo /private/secret/path'


def dump():
    return '\n'.join(['APT "";','APT::Architecture "amd64";','APT::Architectures "";',
      'APT::Architectures:: "amd64";','APT::Architectures:: "amd64";',
      'APT::NeverAutoRemove "";','APT::NeverAutoRemove:: "^firmware-linux.*";',
      'APT::NeverAutoRemove:: "^linux-firmware$";','Dir "";','DPkg "";',
      'Unknown+Valid::Defaults "";','Unknown+Valid::Defaults:: "one";','Unknown+Valid::Defaults:: "two";'])+'\n'

class ConfigFieldTests(unittest.TestCase):
    def reject(self,call,field,reason):
        with self.assertRaises(f.ConfigStop) as raised:call()
        self.assertEqual(raised.exception.evidence(),{'field_id':field,'reason':reason,'matched':False})
        self.assertNotIn(SECRET,str(raised.exception)+json.dumps(raised.exception.evidence()))
    def test_legacy_parser_valid_list_duplicate_defect(self):
        with self.assertRaisesRegex(Stop,'CONFIG_FAILED'):legacy.verify_config(dump(),{})
        self.assertTrue(all(x['matched'] for x in f.inspection(dump())))
    def test_same_list_key_multiple_entries(self):self.assertTrue(f.inspection(dump())[0]['matched'])
    def test_empty_tree_parent_nodes(self):self.assertEqual(len(f.inspection(dump()+'Unrelated::Tree "";\n')),4)
    def test_unknown_valid_defaults(self):self.assertTrue(f.inspection(dump()+'Unrelated::Value "anything";\n')[0]['matched'])
    def test_unknown_list_repeat_not_scalar_duplicate(self):self.assertTrue(f.inspection(dump()+'Unknown::List:: "a";\nUnknown::List:: "b";\n')[0]['matched'])
    def test_required_scalar_duplicate(self):self.reject(lambda:f.inspection(dump()+'APT::Architecture "amd64";\n'),'ARCHITECTURE','SCALAR_DUPLICATE')
    def test_missing_list(self):self.reject(lambda:f.inspection('APT "";\n'),'ARCHITECTURES','FIELD_MISSING')
    def test_named_list_format_unsupported(self):self.reject(lambda:f.inspection(dump()+'APT::Architectures::named "amd64";\n'),'ARCHITECTURES','LIST_FORMAT_UNSUPPORTED')
    def test_scalar_architectures_unsupported(self):self.reject(lambda:f.inspection(dump().replace('APT::Architectures "";','APT::Architectures "amd64";')),'ARCHITECTURES','LIST_FORMAT_UNSUPPORTED')
    def test_architecture_wrong_value(self):self.reject(lambda:f.inspection(dump()+'APT::Architectures:: "arm64";\n'),'ARCHITECTURES','FIELD_VALUE_MISMATCH')
    def test_malformed_dump(self):self.reject(lambda:f.inspection(dump()+SECRET),'CONFIG_INSPECTION','MALFORMED_CONFIG_OUTPUT')
    def test_empty_hooks_allowed(self):self.assertTrue(f.inspection(dump()+'DPkg::Pre-Invoke "";\nDPkg::Pre-Invoke:: "";\n')[1]['matched'])
    def test_forbidden_hook(self):self.reject(lambda:f.inspection(dump()+'DPkg::Pre-Invoke:: "'+SECRET+'";\n'),'DPKG_HOOKS','FORBIDDEN_HOOK_PRESENT')
    def test_forbidden_named_hook(self):self.reject(lambda:f.inspection(dump()+'DPkg::Post-Invoke::named "'+SECRET+'";\n'),'DPKG_HOOKS','FORBIDDEN_HOOK_PRESENT')
    def test_apt_hook(self):self.reject(lambda:f.inspection(dump()+'APT::Update::Post-Invoke:: "'+SECRET+'";\n'),'DPKG_HOOKS','FORBIDDEN_HOOK_PRESENT')
    def test_rootdir_leak(self):self.reject(lambda:f.inspection(dump()+'RootDir "/etc/apt";\n'),'ROOT_DIR','HOST_SOURCE_LEAK')
    def test_binary_specific_host_source(self):self.reject(lambda:f.inspection(dump()+'Binary::apt-get::Dir::Etc::sourceparts "/etc/apt/sources.list.d";\n'),'BINARY_OVERRIDES','HOST_SOURCE_LEAK')
    def test_binary_specific_download_override(self):self.reject(lambda:f.inspection(dump()+'Binary::apt-get::APT::Get::Download "true";\n'),'BINARY_OVERRIDES','FIELD_VALUE_MISMATCH')
    def test_missing_scalar(self):self.reject(lambda:f.scalar_query('STATE_STATUS','',SECRET),'STATE_STATUS','FIELD_MISSING')
    def test_wrong_required_value(self):self.reject(lambda:f.scalar_query('STATE_STATUS',"PLM_VALUE='"+SECRET+"'\n",'/expected'),'STATE_STATUS','FIELD_VALUE_MISMATCH')
    def test_host_source_scalar(self):self.reject(lambda:f.scalar_query('SOURCE_PARTS',"PLM_VALUE='/etc/apt/sources.list.d'\n",'/expected'),'SOURCE_PARTS','HOST_SOURCE_LEAK')
    def test_query_failure(self):self.reject(lambda:f.scalar_query('STATE_LISTS',SECRET,SECRET,100),'STATE_LISTS','QUERY_FAILED')
    def test_scalar_duplicate_output(self):self.reject(lambda:f.scalar_query('DOWNLOAD',"PLM_VALUE='false'\nPLM_VALUE='false'\n",'false'),'DOWNLOAD','SCALAR_DUPLICATE')
    def test_shell_command_injection_not_evaluated(self):self.reject(lambda:f.scalar_query('CACHE_DIR',"PLM_VALUE='x'; echo "+SECRET,'x'),'CACHE_DIR','MALFORMED_CONFIG_OUTPUT')
    def test_shell_different_variable(self):self.reject(lambda:f.scalar_query('CACHE_DIR',"ATTACK='x'\n",'x'),'CACHE_DIR','MALFORMED_CONFIG_OUTPUT')
    def test_scalar_empty_expected_supported(self):self.assertTrue(f.scalar_query('PACKAGE_CACHE',"PLM_VALUE=''\n",'')['matched'])
    def test_unknown_field_safe_fixed_id(self):self.reject(lambda:f.scalar_query(SECRET,'',SECRET),'CONFIG_INSPECTION','MALFORMED_CONFIG_OUTPUT')
    def test_dump_bound(self):self.reject(lambda:f.inspection('x'*2000001),'CONFIG_INSPECTION','MALFORMED_CONFIG_OUTPUT')
    def test_scalar_bound(self):self.reject(lambda:f.scalar_query('SIMULATE','x'*65537,'true'),'SIMULATE','MALFORMED_CONFIG_OUTPUT')
    def test_reason_allowlist(self):self.assertEqual(len(set(f.REASONS)),8)
    def test_all_required_fields(self):
        self.assertEqual(len(f.FIELDS),22);self.assertIn(('DPKG_BINARY','Dir::Bin::dpkg'),f.FIELDS)
        self.assertEqual(len(f.expected_scalars('/tmp/private','/tmp/private/key')),22)
    def test_expected_values_not_in_evidence(self):
        r=f.scalar_query('STATE_STATUS',"PLM_VALUE='"+SECRET+"'\n",SECRET)
        self.assertEqual(r,{'field_id':'STATE_STATUS','matched':True});self.assertNotIn(SECRET,json.dumps(r))
    def test_fixed_query_count_and_supplement_after_scalars(self):
        expected=f.expected_scalars('/tmp/private','/tmp/private/key');calls=[]
        def command(label,args,config):
            calls.append(args)
            if args[-1]=='dump':return 0,dump(),''
            fid=dict((key,fid) for fid,key in f.FIELDS)[args[-1]]
            return 0,"PLM_VALUE='"+expected[fid]+"'\n",SECRET
        with contextlib.redirect_stdout(io.StringIO()) as out,patch.object(v,'command',side_effect=command),patch.object(v,'PROGRESS',{}):result=v.verify_fields('/tmp/private','/tmp/private/key','/tmp/private/apt.conf')
        self.assertEqual(len(calls),23);self.assertEqual(calls[-1],['/usr/bin/apt-config','dump'])
        self.assertTrue(result['matched']);self.assertNotIn('/tmp/private',out.getvalue());self.assertNotIn(SECRET,out.getvalue())
    def test_first_field_failure_stops_remaining_queries(self):
        with contextlib.redirect_stdout(io.StringIO()),patch.object(v,'command',return_value=(0,"PLM_VALUE='wrong'\n",SECRET)) as command,patch.object(v,'PROGRESS',{}):
            self.reject(lambda:v.verify_fields('/tmp/private','/tmp/private/key','/tmp/private/apt.conf'),'STATE_STATUS','FIELD_VALUE_MISMATCH')
        self.assertEqual(command.call_count,1)
    def test_guard_failure_no_process_or_metadata(self):
        with patch.object(v,'cloud_launch_guard',side_effect=Stop('MARKER_MISSING')),patch.object(v,'command') as process,patch.object(v,'load_indices') as metadata:
            with self.assertRaises(Stop):v.execute(json.loads(v.PLAN.read_text()),{})
        process.assert_not_called();metadata.assert_not_called()
    def test_main_safe_field_reason(self):
        with contextlib.redirect_stdout(io.StringIO()) as out,patch.object(v,'execute',side_effect=f.ConfigStop('SOURCE_LIST','HOST_SOURCE_LEAK')),patch.object(v,'PROGRESS',{}):
            with self.assertRaises(SystemExit):v.main()
        self.assertIn('"field_id": "SOURCE_LIST"',out.getvalue());self.assertIn('"reason": "HOST_SOURCE_LEAK"',out.getvalue());self.assertNotIn(SECRET,out.getvalue())
    def test_transport_failure_field_query_reason(self):
        with contextlib.redirect_stdout(io.StringIO()),patch.object(v,'CURRENT_FIELD','DOWNLOAD'),patch.object(v.v4,'private_directory'),patch.object(v.b4,'_bounded_simulation',return_value=(100,SECRET,SECRET)):
            self.reject(lambda:v.command('apt_config',['/usr/bin/apt-config','shell','PLM_VALUE','APT::Get::Download'],'/tmp/apt.conf'),'DOWNLOAD','QUERY_FAILED')
    def test_install_adapter_absent(self):
        with patch.object(v.b4,'_bounded_simulation') as process:
            with self.assertRaises(Stop):v.command('resolver_start',['/usr/bin/apt-get','install','ffmpeg'])
        process.assert_not_called()
    def test_consumed_004c(self):
        with self.assertRaisesRegex(Stop,'IDENTITY_CONSUMED_004C'):b.cloud_launch_guard({},b.PREFLIGHT_V4C_ID)
    def test_004d_independent(self):self.assertTrue(b.launch_gate(**setup(b.PREFLIGHT_V4H_ID))['allow'])
    def test_004d_marker_retained(self):self.assertTrue((v.ROOT/b.marker_path(v.IDENTITY)).exists())
    def test_render_marker_absent(self):self.assertFalse((v.ROOT/b.marker_path(RENDER_ID)).exists())
    def test_005_absent(self):self.assertFalse(list((v.ROOT/'.github/workflows').glob('*v5*')))
    def test_004c_evidence_frozen(self):
        plan=json.loads(v.PLAN.read_text());raw=(v.ROOT/plan['prior_004c_evidence']).read_bytes();e=json.loads(raw)
        self.assertEqual(hashlib.sha256(raw).hexdigest(),plan['prior_004c_evidence_sha256']);self.assertEqual(e['run_id'],37263821548)
        self.assertTrue(all(p=={'version':'2.8.3','return_code':0} for p in e['apt_binaries'].values()))
        self.assertEqual(e['apt_config_dump_return_code'],0)
    def test_workflow_read_only_output_gate(self):
        wf=(v.ROOT/b.SPEC[v.IDENTITY][1]).read_text()
        self.assertIn("paths: ['"+b.marker_path(v.IDENTITY)+"']",wf);self.assertIn('contents: read',wf);self.assertIn('actions: read',wf)
        self.assertNotIn('contents: write',wf);self.assertEqual(wf.count("if: steps.marker.outputs.allow == 'true' && steps.marker.outputs.execution_approved == 'true'"),2)
    def test_post_invoke_success_hook(self):self.reject(lambda:f.inspection(dump()+'APT::Update::Post-Invoke-Success:: "'+SECRET+'";\n'),'DPKG_HOOKS','FORBIDDEN_HOOK_PRESENT')
    def test_fake_pipeline_config_failure_blocks_indices_policy_solver(self):
        self.fake_pipeline(config_fail=True)
    def test_fake_pipeline_config_pass_allows_continuation(self):
        self.fake_pipeline(config_fail=False)
    def fake_pipeline(self,config_fail):
        import tempfile
        from test_apt_transaction_v4 import meta
        from test_v4c_startup import policy
        plan=json.loads(v.PLAN.read_text());roots=plan['root_constraints'];calls=[]
        status=b'Package: base\nVersion: 1\nArchitecture: amd64\nStatus: install ok installed\n'
        original_bytes=Path.read_bytes;original_text=Path.read_text
        def read_bytes(path):return status if str(path)=='/var/lib/dpkg/status' else original_bytes(path)
        def read_text(path,*args,**kwargs):
            return 'ID=ubuntu\nVERSION_ID="24.04"\n' if str(path)=='/etc/os-release' else original_text(path,*args,**kwargs)
        records={}
        for name,version in roots.items():
            p=meta(name,version);p['suite']='noble';records[(name,version,'amd64')]=p
        def command(label,args,config=None,roots=None,package=None):
            calls.append((label,args))
            if label=='apt_binary':return 0,'apt 2.8.3 (amd64)\n',''
            if label=='apt_config':
                if args[-1]=='dump':return 0,dump(),SECRET
                field_id=dict((key,field_id) for field_id,key in f.FIELDS)[args[-1]]
                value=f.expected_scalars(Path(config).parent,Path(config).parent/'ubuntu-archive-keyring.gpg')[field_id]
                return 0,"PLM_VALUE='"+('wrong' if config_fail else value)+"'\n",SECRET
            if label=='index_visibility':
                name=args[-1];version=plan['root_constraints'][name]
                return 0,policy(version,version).replace('root:',name+':'),''
            return 0,'0 upgraded, 1 newly installed, 0 to remove and 0 not upgraded.\n','Starting pkgProblemResolver with broken count: 0\nDone\n'
        receipt=dict(identity=v.IDENTITY,consumed=True,allow=True,execution_approved=True,no_retry=True,no_resume=True,run_id='fake',launch_sha='a'*40)
        with tempfile.TemporaryDirectory() as temp,patch.dict(v.os.environ,{'RUNNER_TEMP':temp}),patch.object(v.sys,'version_info',(3,12,15)),patch.object(Path,'read_bytes',read_bytes),patch.object(Path,'read_text',read_text),patch.object(v,'cloud_launch_guard',return_value=receipt),patch.object(v,'command',side_effect=command),patch.object(v,'load_indices',return_value=({'noble':records},{},{'matched':True})) as indices,contextlib.redirect_stdout(io.StringIO()) as out:
            env=dict(RUNNER_TEMP=temp,RUNNER_ENVIRONMENT='github-hosted',ImageOS='ubuntu24',RUNNER_ARCH='X64')
            if config_fail:
                self.reject(lambda:v.execute(plan,env),'STATE_STATUS','FIELD_VALUE_MISMATCH');indices.assert_not_called()
                self.assertFalse(any(label in ('index_visibility','resolver_start') for label,args in calls))
            else:
                result=v.execute(plan,env);indices.assert_called_once()
                self.assertTrue(result['completed_stages']['apt_config']['matched'])
                self.assertEqual(sum(label=='resolver_start' for label,args in calls),11)
                self.assertFalse(result['transaction_proof']);self.assertFalse(result['install_authorized'])
            self.assertNotIn(SECRET,out.getvalue());self.assertNotIn(temp,out.getvalue())
