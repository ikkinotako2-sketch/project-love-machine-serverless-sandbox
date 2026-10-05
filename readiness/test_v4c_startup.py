from oracle_bridge import require_guard
require_guard()
import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import apt_startup_v4c as a
import cloud_runtime_preflight_v4c as v
import branch_marker_once as b
from one_shot_executor import Stop,RENDER_ID
from test_apt_transaction_v4 import meta
from test_branch_marker_once import setup

SECRET='ghp_SECRET_CREDENTIAL token=never-print'

def index():
    p=meta('root','1');p['suite']='noble'
    return {'noble':{('root','1','amd64'):p}}

def policy(candidate='1',version='1'):
    return 'root:\n  Installed: (none)\n  Candidate: '+candidate+'\n  Version table:\n     '+version+' 500\n        500 https://archive.ubuntu.com/ubuntu noble/main amd64 Packages\n'

class StartupTests(unittest.TestCase):
    def test_binary_missing(self):
        with self.assertRaisesRegex(Stop,'BINARY_FAILED'):a.binary_version(a.BINARIES[0],False,False,127,SECRET)
    def test_binary_nonexecutable(self):
        with self.assertRaisesRegex(Stop,'BINARY_FAILED'):a.binary_version(a.BINARIES[0],True,False,0,'apt 2.8.3 (amd64)')
    def test_binary_version_safe(self):
        self.assertEqual(a.binary_version(a.BINARIES[0],True,True,0,'apt 2.8.3 (amd64)\n'+SECRET),{'binary':'apt-get','version':'2.8.3','architecture':'amd64'})
    def test_binary_wrong_arch(self):
        with self.assertRaisesRegex(Stop,'BINARY_FAILED'):a.binary_version(a.BINARIES[0],True,True,0,'apt 2.8.3 (arm64)')
    def test_config_valid(self):
        expected=a.config_expected('/tmp/private','/tmp/private/key')
        raw='\n'.join(k+' '+json.dumps(val)+';' for k,val in expected.items())
        r=a.verify_config(raw,expected);self.assertTrue(r['matched']);self.assertNotIn('/tmp/private',json.dumps(r))
    def test_config_mismatch(self):
        with self.assertRaisesRegex(Stop,'CONFIG_FAILED'):a.verify_config('APT::Get::Download "true";',a.config_expected('/tmp/p','/tmp/p/key'))
    def test_host_source_leak(self):
        expected=a.config_expected('/tmp/p','/tmp/p/key');bad=dict(expected);bad['dir::etc::sourceparts']='/etc/apt/sources.list.d'
        with self.assertRaisesRegex(Stop,'CONFIG_FAILED'):a.verify_config('\n'.join(k+' '+json.dumps(x)+';' for k,x in bad.items()),expected)
    def test_config_hooks_rejected(self):
        expected=a.config_expected('/tmp/p','/tmp/p/key');raw='\n'.join(k+' '+json.dumps(x)+';' for k,x in expected.items())
        with self.assertRaisesRegex(Stop,'CONFIG_FAILED'):a.verify_config(raw+'\nDPkg::Pre-Invoke:: "'+SECRET+'";',expected)
    def test_config_raw_unknown_not_echoed(self):
        with self.assertRaises(Stop) as raised:a.verify_config(SECRET,{})
        self.assertNotIn(SECRET,str(raised.exception))
    def test_private_status_mismatch(self):
        with self.assertRaisesRegex(Stop,'STATUS_FAILED'):a.verify_status(b'original',b'changed',hashlib.sha256(b'original').hexdigest())
    def test_private_status_hash_mismatch(self):
        with self.assertRaisesRegex(Stop,'STATUS_FAILED'):a.verify_status(b'original',b'original','0'*64)
    def test_private_status_exact(self):
        self.assertTrue(a.verify_status(b'x',b'x',hashlib.sha256(b'x').hexdigest())['matched'])
    def test_lists_hash_mismatch(self):
        with self.assertRaisesRegex(Stop,'LISTS_LAYOUT_FAILED'):a.verify_lists({'Packages':{'regular':True,'symlink':False,'sha256':'bad'}},{'Packages':'good'})
    def test_lists_symlink(self):
        with self.assertRaisesRegex(Stop,'LISTS_LAYOUT_FAILED'):a.verify_lists({'Packages':{'regular':True,'symlink':True,'sha256':'same'}},{'Packages':'same'})
    def test_lists_extra_file(self):
        with self.assertRaisesRegex(Stop,'LISTS_LAYOUT_FAILED'):a.verify_lists({'leak':{}},{})
    def test_packages_exist_but_apt_invisible(self):
        p=a.parse_policy('root:\n  Installed: (none)\n  Candidate: (none)\n  Version table:\n','root',index(),{},'/tmp/status')
        with self.assertRaisesRegex(Stop,'INDEX_VISIBILITY_FAILED'):a.verify_visibility(p,'1')
    def test_root_exact_invisible(self):
        p=a.parse_policy(policy(),'root',index(),{},'/tmp/status')
        with self.assertRaisesRegex(Stop,'INDEX_VISIBILITY_FAILED'):a.verify_visibility(p,'2')
    def test_policy_valid(self):
        p=a.parse_policy(policy(),'root',index(),{},'/tmp/status');self.assertTrue(a.verify_visibility(p,'1')['exact_visible'])
    def test_policy_source_leak(self):
        with self.assertRaisesRegex(Stop,'INDEX_VISIBILITY_FAILED'):a.parse_policy(policy().replace(a.REPO,'https://ppa.invalid'),'root',index(),{},'/tmp/status')
    def test_policy_version_not_signed(self):
        with self.assertRaisesRegex(Stop,'INDEX_VISIBILITY_FAILED'):a.parse_policy(policy(version='2',candidate='2'),'root',index(),{},'/tmp/status')
    def test_policy_arch_mismatch(self):
        with self.assertRaisesRegex(Stop,'INDEX_VISIBILITY_FAILED'):a.parse_policy(policy().replace('amd64 Packages','arm64 Packages'),'root',index(),{},'/tmp/status')
    def test_root_candidate_mismatch(self):
        p=a.parse_policy(policy(candidate='(none)'),'root',index(),{},'/tmp/status')
        with self.assertRaisesRegex(Stop,'ROOT_POLICY_FAILED'):a.verify_root_policy(p,'1')
    def test_root_candidate_unindexed(self):
        with self.assertRaisesRegex(Stop,'ROOT_POLICY_FAILED'):a.parse_policy(policy(candidate='2'),'root',index(),{},'/tmp/status')
    def test_policy_installed_private_status(self):
        raw='root:\n  Installed: 1\n  Candidate: 1\n  Version table:\n *** 1 500\n        500 '+a.REPO+' noble/main amd64 Packages\n        100 /tmp/private/status\n'
        p=a.parse_policy(raw,'root',index(),{'root':{'Version':'1','Architecture':'amd64'}},'/tmp/private/status');self.assertEqual(p['installed_version'],'1')
    def test_policy_installed_host_status_rejected(self):
        raw='root:\n  Installed: 1\n  Candidate: 1\n  Version table:\n *** 1 100\n        100 /var/lib/dpkg/status\n'
        with self.assertRaisesRegex(Stop,'INDEX_VISIBILITY_FAILED'):a.parse_policy(raw,'root',index(),{'root':{'Version':'1','Architecture':'amd64'}},'/tmp/private/status')
    def test_resolver_not_entered(self):
        with self.assertRaisesRegex(Stop,'RESOLVER_START_FAILED'):a.solver_entered(100,'',SECRET)
    def test_resolver_entered_rc100(self):self.assertTrue(a.solver_entered(100,'','Starting pkgProblemResolver with broken count: 1\n')['entered'])
    def test_resolver_success_summary(self):self.assertTrue(a.solver_entered(0,'0 upgraded, 1 newly installed, 0 to remove and 0 not upgraded.\n','')['entered'])
    def test_debug_known_conflict(self):
        raw='Starting pkgProblemResolver with broken count: 1\n Broken root:amd64 Depends on dep:amd64 (>= 2)\nDone\n'
        r=a.parse_debug(raw,{'root','dep'},{'dep':{'Version':'1'}},{'dep':'1'},{('root','Depends','dep','>=','2')})
        self.assertEqual(r['conflicts'][0]['required_version_constraint'],{'operator':'>=','version':'2'});self.assertFalse(r['proof'])
    def test_debug_unknown_syntax_stop(self):
        with self.assertRaisesRegex(Stop,'RESOLVER_DIAGNOSTIC_FAILED') as raised:a.parse_debug(SECRET,set(),{},{},set())
        self.assertNotIn(SECRET,str(raised.exception))
    def test_debug_unsigned_constraint_stop(self):
        with self.assertRaisesRegex(Stop,'RESOLVER_DIAGNOSTIC_FAILED'):a.parse_debug(' Broken root:amd64 Depends on dep:amd64 (>= 2)',{'root','dep'},{},{},set())
    def test_debug_annotations_not_copied(self):
        r=a.parse_debug('Investigating (0) root:amd64 < '+SECRET+' >',{'root'},{},{},set());self.assertNotIn(SECRET,json.dumps(r))
    def test_debug_bounded(self):
        with self.assertRaisesRegex(Stop,'RESOLVER_DIAGNOSTIC_FAILED'):a.parse_debug('x'*65537,set(),{},{},set())
    def test_guard_failure_all_adapters_zero(self):
        with patch.object(v,'cloud_launch_guard',side_effect=Stop('MARKER_MISSING')),patch.object(v,'command') as process,patch.object(v,'load_indices') as network:
            with self.assertRaises(Stop):v.execute(json.loads(v.PLAN.read_text()),{})
        process.assert_not_called();network.assert_not_called()
    def test_command_raw_secret_never_logged(self):
        out=io.StringIO()
        with contextlib.redirect_stdout(out),patch.object(v.b4,'_bounded_simulation',return_value=(127,SECRET,SECRET)):
            with self.assertRaisesRegex(Stop,'BINARY_FAILED'):v.command('apt_binary',[a.BINARIES[0],'--version'])
        self.assertNotIn(SECRET,out.getvalue());self.assertIn('stage=apt_binary',out.getvalue());self.assertIn('return_code=127',out.getvalue())
    def test_command_exception_never_logged(self):
        out=io.StringIO()
        with contextlib.redirect_stdout(out),patch.object(v.b4,'_bounded_simulation',side_effect=RuntimeError(SECRET)):
            with self.assertRaisesRegex(Stop,'BINARY_FAILED') as raised:v.command('apt_binary',[a.BINARIES[0],'--version'])
        self.assertNotIn(SECRET,out.getvalue()+str(raised.exception))
    def test_install_command_adapter_absent(self):
        with patch.object(v.b4,'_bounded_simulation') as process:
            with self.assertRaises(Stop):v.command('resolver_start',['/usr/bin/apt-get','install','ffmpeg'])
        process.assert_not_called()
    def test_download_command_adapter_absent(self):
        with patch.object(v.b4,'_bounded_simulation') as process:
            with self.assertRaises(Stop):v.command('resolver_start',['/usr/bin/apt-get','download','ffmpeg'])
        process.assert_not_called()
    def test_plan_exact_roots_fixed(self):self.assertEqual(len(v.validate_plan(json.loads(v.PLAN.read_text()))['packages']),10)
    def test_plan_root_drift(self):
        p=json.loads(v.PLAN.read_text());p['root_constraints']['ffmpeg']='latest'
        with self.assertRaisesRegex(Stop,'CONFIG_FAILED'):v.validate_plan(p)
    def test_plan_simulation_limit(self):
        p=json.loads(v.PLAN.read_text());p['limits']['total_simulations']=12
        with self.assertRaisesRegex(Stop,'CONFIG_FAILED'):v.validate_plan(p)
    def test_codes_distinct(self):self.assertEqual(len(set(a.CODES.values())),8)
    def test_004_consumed(self):
        with self.assertRaisesRegex(Stop,'IDENTITY_CONSUMED_004'):b.cloud_launch_guard({},b.PREFLIGHT_V4_ID)
    def test_004b_consumed(self):
        with self.assertRaisesRegex(Stop,'IDENTITY_CONSUMED_004B'):b.cloud_launch_guard({},b.PREFLIGHT_V4B_ID)
    def test_next_identity_independent(self):
        self.assertTrue(b.launch_gate(**setup(b.PREFLIGHT_V4F_ID))['allow'])
    def test_004c_rerun_rejected(self):
        k=setup(b.PREFLIGHT_V4F_ID);k['context']['run_attempt']=2
        with self.assertRaises(Stop):b.launch_gate(**k)
    def test_005_absent(self):self.assertFalse(list((v.ROOT/'.github/workflows').glob('*v5*')))
    def test_render_marker_absent(self):self.assertFalse((v.ROOT/b.marker_path(RENDER_ID)).exists())
    def test_004c_marker_retained(self):self.assertTrue((v.ROOT/b.marker_path(b.PREFLIGHT_V4C_ID)).is_file())
    def test_frozen_evidence(self):
        p=json.loads(v.PLAN.read_text());e=json.loads((v.ROOT/p['prior_004b_evidence']).read_text())
        self.assertEqual(e['run_id'],37260939639);self.assertEqual(len(e['all_case_return_codes']),4)
        self.assertTrue(all(x==100 for x in e['all_case_return_codes'].values()))

    def test_wrong_branch(self):
        k=setup(b.PREFLIGHT_V4F_ID);k['context']['branch']='main'
        with self.assertRaises(Stop):b.launch_gate(**k)
    def test_wrong_repository(self):
        k=setup(b.PREFLIGHT_V4F_ID);k['context']['repository']='someone/else'
        with self.assertRaises(Stop):b.launch_gate(**k)
    def test_wrong_event(self):
        k=setup(b.PREFLIGHT_V4F_ID);k['context']['event']='workflow_dispatch'
        with self.assertRaises(Stop):b.launch_gate(**k)
    def test_marker_missing(self):
        k=setup(b.PREFLIGHT_V4F_ID);k['marker']=None
        with self.assertRaises(Stop):b.launch_gate(**k)
    def test_marker_modified(self):
        k=setup(b.PREFLIGHT_V4F_ID);k['commit']['files'][0]['status']='modified'
        with self.assertRaises(Stop):b.launch_gate(**k)
    def test_marker_deleted(self):
        k=setup(b.PREFLIGHT_V4F_ID);k['commit']['files'][0]['status']='removed'
        with self.assertRaises(Stop):b.launch_gate(**k)
    def test_workflow_readonly_trigger_gates(self):
        wf=(v.ROOT/b.SPEC[v.IDENTITY][1]).read_text()
        self.assertIn("paths: ['"+b.marker_path(v.IDENTITY)+"']",wf)
        self.assertIn("branches: ['"+b.BRANCH+"']",wf)
        self.assertIn('contents: read',wf);self.assertIn('actions: read',wf)
        self.assertNotIn('contents: write',wf);self.assertNotIn('workflow_dispatch',wf.split('#')[0])
        self.assertEqual(wf.count("if: steps.marker.outputs.allow == 'true' && steps.marker.outputs.execution_approved == 'true'"),2)
    def test_main_unknown_exception_safe(self):
        out=io.StringIO()
        with contextlib.redirect_stdout(out),patch.object(v,'PROGRESS',{}),patch.object(v,'execute',side_effect=RuntimeError(SECRET)):
            with self.assertRaises(SystemExit):v.main()
        self.assertNotIn(SECRET,out.getvalue());self.assertNotIn('Traceback',out.getvalue())
    def test_command_child_environment_no_credentials(self):
        with contextlib.redirect_stdout(io.StringIO()),patch.object(v.b4,'_bounded_simulation',return_value=(0,'apt 2.8.3 (amd64)','')) as process:
            v.command('apt_binary',[a.BINARIES[0],'--version'])
        self.assertEqual(set(process.call_args.args[1]),{'PATH','LC_ALL','LANG','HOME'})
    def test_main_preserves_partial_safe_evidence(self):
        out=io.StringIO()
        with contextlib.redirect_stdout(out),patch.object(v,'PROGRESS',{'apt_config':{'matched':True}}),patch.object(v,'execute',side_effect=Stop(a.CODES['index_visibility'])):
            with self.assertRaises(SystemExit):v.main()
        self.assertIn('"matched": true',out.getvalue());self.assertIn(a.CODES['index_visibility'],out.getvalue())
    def test_fake_guard_pass_full_pipeline_fixed_attempts(self):
        plan=json.loads(v.PLAN.read_text());roots=plan['root_constraints'];calls=[]
        status=b'Package: base\nVersion: 1\nArchitecture: amd64\nStatus: install ok installed\n'
        original_bytes=Path.read_bytes;original_text=Path.read_text
        def read_bytes(path):return status if str(path)=='/var/lib/dpkg/status' else original_bytes(path)
        def read_text(path,*args,**kwargs):
            return 'ID=ubuntu\nVERSION_ID="24.04"\n' if str(path)=='/etc/os-release' else original_text(path,*args,**kwargs)
        records={}
        for name,version in roots.items():
            p=meta(name,version);p['suite']='noble';records[(name,version,'amd64')]=p
        def fake_command(label,args,config=None,roots=None,package=None):
            calls.append((label,args))
            if label=='apt_binary':return 0,'apt 2.8.3 (amd64)\n',''
            if label=='apt_config':
                expected=a.config_expected(Path(config).parent,Path(config).parent/'ubuntu-archive-keyring.gpg')
                return 0,'\n'.join(k+' '+json.dumps(val)+';' for k,val in expected.items()),''
            if label=='index_visibility':
                name=args[-1];version=plan['root_constraints'][name]
                return 0,policy(version,version).replace('root:',name+':'),''
            return 0,'0 upgraded, 1 newly installed, 0 to remove and 0 not upgraded.\n','Starting pkgProblemResolver with broken count: 0\nDone\n'
        receipt=dict(identity=v.IDENTITY,consumed=True,allow=True,execution_approved=True,no_retry=True,no_resume=True,run_id='fake',launch_sha='a'*40)
        with tempfile.TemporaryDirectory() as temp,patch.dict(v.os.environ,{'RUNNER_TEMP':temp}),patch.object(v.sys,'version_info',(3,12,15)),patch.object(Path,'read_bytes',read_bytes),patch.object(Path,'read_text',read_text),patch.object(v,'cloud_launch_guard',return_value=receipt),patch.object(v,'command',side_effect=fake_command),patch.object(v,'load_indices',return_value=({'noble':records},{},{'matched':True})),contextlib.redirect_stdout(io.StringIO()):
            result=v.execute(plan,dict(RUNNER_TEMP=temp,RUNNER_ENVIRONMENT='github-hosted',ImageOS='ubuntu24',RUNNER_ARCH='X64'))
        requests=[tuple(args[7:]) for label,args in calls if label=='resolver_start']
        self.assertEqual(len(requests),11);self.assertEqual(len(set(requests)),11)
        self.assertEqual([len(x) for x in requests],[1]*10+[10])
        self.assertEqual(sum(label=='index_visibility' for label,args in calls),10)
        self.assertFalse(result['transaction_proof']);self.assertFalse(result['install_authorized'])
        self.assertNotIn('transaction_fingerprint',result)
