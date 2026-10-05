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
import apt_user_error_v4g as d
import cloud_runtime_preflight_v4g as v
import apt_config_fields_v4d as f
import branch_marker_once as b
from one_shot_executor import Stop,RENDER_ID
from test_branch_marker_once import setup
SECRET='ghp_SUPER_SECRET token=DO_NOT_ECHO /secret/path'

def trusted(installed=None,depends='dep, dep (>= 2)'):
    return d.context({'noble':{('root','1','amd64'):{'Depends':depends,'Pre-Depends':'dep (>= 2)','Conflicts':'dep (>= 2)','Breaks':'dep (<< 3)'},('dep','2','amd64'):{},('dep','3','amd64'):{},('other','2','amd64'):{}}},installed or {})

class UserErrorTests(unittest.TestCase):
    def reject(self,stderr='',stdout='',reason=None,ctx=None):
        with contextlib.redirect_stdout(io.StringIO()) as out,self.assertRaises(d.DebugStop) as caught:d.parse_debug(stderr,ctx or trusted(),stdout,100)
        public=caught.exception.evidence();self.assertEqual(out.getvalue(),'');self.assertNotIn(SECRET,str(caught.exception)+json.dumps(public))
        self.assertEqual(set(public),{'syntax_family','relevance','known_package_tokens_count','fixed_reason'})
        if reason:self.assertEqual(public['fixed_reason'],reason)
        return public
    def test_source_template_fixtures_not_runtime(self):
        data=json.loads((v.ROOT/'readiness/apt-user-error-v4g-source-fixtures.json').read_text())
        self.assertIn('not raw runtime',data['basis'])
        for x in data['fixtures']:
            with self.subTest(family=x['family'],source_line=x['source_line']):
                r=d.parse_debug(x['template_instance'] if x['stream']=='stderr' else '',trusted({'dep':{'Version':'2'}}),x['template_instance'] if x['stream']=='stdout' else '',100)
                self.assertGreater(r['user_error_family_counts'][x['family']],0);self.assertFalse(r['proof']);self.assertFalse(r['install_authorized'])
    def test_27_004f_source_fixtures_preserved(self):
        from test_v4f_resolver_debug import trusted as old_trusted
        fixtures=json.loads((v.ROOT/'readiness/apt-resolver-v4f-source-fixtures.json').read_text())['fixtures'];self.assertEqual(len(fixtures),27)
        self.assertEqual(hashlib.sha256((v.ROOT/'readiness/apt-resolver-v4f-source-fixtures.json').read_bytes()).hexdigest(),'cdb68bd85477e52063c0b5c08ba882b23dc5ff9bee2a63695c590f6bd6cfd54e')
        for x in fixtures:
            with self.subTest(x['source_line']):self.assertTrue(d.parse_debug(x['line'],old_trusted())['parsed'])
    def test_versioned_depends(self):self.assertEqual(d.parse_debug(' root : Depends: dep (>= 2) but it is not going to be installed',trusted())['conflicts'][0]['required_version'],'2')
    def test_unversioned_depends(self):self.assertIsNone(d.parse_debug(' root : Depends: dep but it is not installable',trusted())['conflicts'][0]['version_operator'])
    def test_predepends(self):self.assertTrue(d.parse_debug(' root : PreDepends: dep (>= 2) but it is not installable',trusted())['parsed'])
    def test_not_installable(self):self.assertEqual(d.parse_debug(' root : Depends: dep but it is not installable',trusted())['user_error_family_counts']['DEPENDENCY_NOT_INSTALLABLE'],1)
    def test_not_going_to_be_installed(self):self.assertEqual(d.parse_debug(' root : Depends: dep but it is not going to be installed',trusted())['user_error_family_counts']['DEPENDENCY_NOT_GOING_TO_BE_INSTALLED'],1)
    def test_version_is_to_be_installed(self):self.assertEqual(d.parse_debug(' root : Depends: dep (>= 2) but 2 is to be installed',trusted())['user_error_family_counts']['DEPENDENCY_VERSION_TO_BE_INSTALLED'],1)
    def test_conflicts_private_installed(self):
        r=d.parse_debug(' root : Conflicts: dep (>= 2) but 2 is installed',trusted({'dep':{'Version':'2'}}));self.assertEqual(r['conflicts'][0]['installed_version'],'2')
    def test_breaks(self):self.assertEqual(d.parse_debug(' root : Breaks: dep (<< 3) but 2 is to be installed',trusted())['conflicts'][0]['relation_kind'],'Breaks')
    def test_summary_only_no_conflict(self):self.assertEqual(d.parse_debug('E: Broken packages',trusted())['conflicts'],[])
    def test_held_summary_not_held_root_cause(self):self.assertEqual(d.parse_debug('E: Unable to correct problems, you have held broken packages.',trusted())['conflicts'],[])
    def test_one_known_token_package_header_no_conflict(self):
        r=d.parse_debug(' root :',trusted());self.assertEqual(r['conflicts'],[]);self.assertEqual(r['evidence'][0]['package'],'root')
    def test_one_known_token_source_loop_summary_no_conflict(self):
        r=d.parse_debug('E: Internal Error, pkgProblemResolver::ResolveByKeep is looping on package root.',trusted());self.assertEqual(r['conflicts'],[])
    def test_two_package_dependency_line(self):
        row=d.parse_debug(' root : Depends: dep (>= 2) but it is not installable',trusted())['conflicts'][0];self.assertEqual((row['package'],row['dependency_package']),('root','dep'))
    def test_unknown_package(self):self.reject(' unknown : Depends: dep but it is not installable',reason='UNKNOWN_PACKAGE_TOKEN')
    def test_unknown_dependency(self):self.reject(' root : Depends: unknown but it is not installable',reason='UNKNOWN_PACKAGE_TOKEN')
    def test_signed_metadata_mismatch(self):self.reject(' root : Depends: dep (>= 3) but it is not installable',reason='SIGNED_METADATA_MISMATCH')
    def test_malformed_version(self):self.reject(' root : Depends: dep (>= 1_2) but it is not installable',reason='MALFORMED_VERSION')
    def test_unknown_selected_version(self):self.reject(' root : Depends: dep (>= 2) but 999 is to be installed',reason='UNVERIFIED_VERSION')
    def test_wrong_installed_version(self):self.reject(' root : Conflicts: dep (>= 2) but 2 is installed',reason='INSTALLED_VERSION_MISMATCH')
    def test_locale_drift_error(self):self.reject('E: Paquets casses '+SECRET,reason='UNSUPPORTED_RELEVANT_USER_ERROR')
    def test_locale_drift_dependency(self):self.reject(' root : Abhaengig: dep but it is not installable',reason='MISSING_RELATION_TOKEN')
    def test_locale_drift_wrapper(self):self.reject(stdout='Les paquets suivants ont des dependances non satisfaites:',reason='UNSUPPORTED_USER_OUTPUT_PREAMBLE')
    def test_unknown_E_not_ignored(self):self.reject('E: '+SECRET,reason='UNSUPPORTED_RELEVANT_USER_ERROR')
    def test_secret_suffix(self):self.reject(' root : Depends: dep (>= 2) '+SECRET,reason='UNSUPPORTED_DEPENDENCY_SUFFIX')
    def test_missing_dep_token(self):self.reject(' root : Depends: ',reason='MISSING_DEPENDENCY_TOKEN')
    def test_missing_parent(self):self.reject(' Depends: dep (>= 2) but it is not installable',reason='MISSING_PARENT_PACKAGE')
    def test_continuation_depends(self):
        text=' root : Depends: dep (>= 2) but it is not installable\n        Breaks: dep (<< 3) but 2 is to be installed'
        self.assertEqual(len(d.parse_debug(text,trusted())['conflicts']),2)
    def test_alternative_continuation(self):
        text=' root : Depends: dep (>= 2) but it is not installable or\n                 other (>= 2) but it is not going to be installed'
        r=d.parse_debug(text,trusted(depends='dep (>= 2) | other (>= 2)'));self.assertEqual(len(r['conflicts']),2);self.assertFalse(r['proof'])
    def test_alternative_incomplete(self):self.reject(' root : Depends: dep (>= 2) but it is not installable or',ctx=trusted(depends='dep (>= 2) | other (>= 2)'),reason='ALTERNATIVE_INCOMPLETE')
    def test_unsig_alternative_stop(self):self.reject(' root : Depends: dep (>= 2) but it is not installable or',reason='SIGNED_ALTERNATIVE_MISMATCH')
    def test_both_streams_bounded_no_output(self):
        stdout='Reading package lists... Done\nBuilding dependency tree...\nReading state information... Done\nThe following packages have unmet dependencies:\n root : Depends: dep (>= 2) but it is not installable\n'
        r=d.parse_debug('Starting pkgProblemResolver with broken count: 1\nDone\nE: Broken packages',trusted(),stdout,100);self.assertEqual(len(r['conflicts']),1)
    def test_unrelated_stdout_not_proof(self):
        r=d.parse_debug('Starting pkgProblemResolver with broken count: 0\nDone',trusted(),SECRET,0);self.assertNotIn(SECRET,json.dumps(r));self.assertFalse(r['proof'])
    def test_unknown_line_in_user_section_stop(self):self.reject(stdout='The following packages have unmet dependencies:\n'+SECRET,reason='UNSUPPORTED_RELEVANT_USER_ERROR')
    def test_unknown_non_dependency_prefix_rc100_stop(self):self.reject(stdout=SECRET,reason='UNSUPPORTED_USER_OUTPUT_PREAMBLE')
    def test_version_unavailable_known_constraint(self):
        r=d.parse_debug("E: Version '2' for 'dep' was not found",trusted());self.assertEqual(r['conflicts'],[])
    def test_version_unavailable_unknown_stop(self):self.reject("E: Version '999' for 'dep' was not found",reason='UNVERIFIED_VERSION')
    def test_raw_fields_absent(self):
        r=d.parse_debug(' root : Depends: dep but it is not installable',trusted());self.assertNotIn('raw',json.dumps(r));self.assertFalse(set(r)&{'stdout','stderr','line','exception'})
    def test_004f_fingerprint_exact_frozen(self):
        p=json.loads(v.PLAN.read_text());raw=(v.ROOT/p['prior_004f_evidence']).read_bytes();e=json.loads(raw)
        self.assertEqual(hashlib.sha256(raw).hexdigest(),p['prior_004f_evidence_sha256']);self.assertEqual(e['run_id'],37301763286)
        self.assertEqual(e['unsupported_fingerprint'],dict(syntax_family='USER_FACING_DEPENDENCY_ERROR',relevance='DEPENDENCY_DECISION_OR_UNKNOWN',known_package_tokens_count=1,fixed_reason='UNSUPPORTED_RELEVANT_SYNTAX'))
        self.assertEqual(e['scalar_pass_count'],22);self.assertEqual(e['private_lists_verified'],9);self.assertEqual(e['candidate_exact_matches'],10)
        self.assertEqual(e['simulation_count'],1);self.assertEqual(e['ffmpeg_single_return_code'],100);self.assertFalse(e['raw_stderr_available']);self.assertIsNone(e['dependency_conflict_observed'])
    def test_source_immutable_hash(self):
        p=json.loads(v.PLAN.read_text());raw=(v.ROOT/p['user_error_source_evidence']).read_bytes();e=json.loads(raw)
        self.assertEqual(hashlib.sha256(raw).hexdigest(),p['user_error_source_evidence_sha256']);self.assertFalse(e['stable_public_grammar']);self.assertFalse(e['source_fetch_in_offline_CI']);self.assertFalse(e['source_fetch_in_runtime'])
        self.assertTrue(all('?id='+e['source_commit'] in x['url'] and len(x['sha256'])==64 for x in e['files']))
    def test_config_source_roots_policy_layout_command_unchanged(self):
        old=json.loads((v.ROOT/'readiness/cloud-runtime-preflight-v4f-debug-plan.json').read_text());new=json.loads(v.PLAN.read_text())
        for k in ('root_constraints','root_evidence_sha256','signed_release_index','config_verification','suites','repository','limits','debug_options','fixed_stages'):self.assertEqual(old[k],new[k])
        oldcode=(v.ROOT/'readiness/cloud_runtime_preflight_v4f.py').read_text();newcode=(v.ROOT/'readiness/cloud_runtime_preflight_v4g.py').read_text()
        for name in ('command','verify_fields','load_indices'):
            pattern='def '+name+'(';a=oldcode.index(pattern);z=oldcode.index('\n\ndef ',a);x=newcode.index(pattern);y=newcode.index('\n\ndef ',x);self.assertEqual(oldcode[a:z],newcode[x:y])
        self.assertIn("'LC_ALL':'C'",newcode)
    def test_004f_consumed_both_guards(self):
        with self.assertRaisesRegex(Stop,'IDENTITY_CONSUMED_004F'):b.cloud_launch_guard({},b.PREFLIGHT_V4F_ID)
        with self.assertRaisesRegex(Stop,'IDENTITY_CONSUMED_004F'):b.launch_gate(**setup(b.PREFLIGHT_V4F_ID))
    def test_004g_independent(self):self.assertTrue(b.launch_gate(**setup(b.PREFLIGHT_V4G_ID))['allow'])
    def test_004g_marker_absent(self):self.assertFalse((v.ROOT/b.marker_path(v.IDENTITY)).exists())
    def test_render_marker_absent(self):self.assertFalse((v.ROOT/b.marker_path(RENDER_ID)).exists())
    def test_005_absent(self):self.assertFalse(list((v.ROOT/'.github/workflows').glob('*v5*')))
    def test_guard_failure_zero_adapters(self):
        with patch.object(v,'cloud_launch_guard',side_effect=Stop('MARKER_MISSING')),patch.object(v,'command') as process,patch.object(v,'load_indices') as network:
            with self.assertRaises(Stop):v.execute(json.loads(v.PLAN.read_text()),{})
        process.assert_not_called();network.assert_not_called()

    def fake_pipeline(self,first_debug):
        from test_apt_transaction_v4 import meta
        from test_v4c_startup import policy
        plan=json.loads(v.PLAN.read_text());roots=plan['root_constraints'];calls=[]
        status=b'Package: base\nVersion: 1\nArchitecture: amd64\nStatus: install ok installed\n'
        original_bytes=Path.read_bytes;original_text=Path.read_text
        def read_bytes(path):return status if str(path)=='/var/lib/dpkg/status' else original_bytes(path)
        def read_text(path,*args,**kwargs):return 'ID=ubuntu\nVERSION_ID="24.04"\n' if str(path)=='/etc/os-release' else original_text(path,*args,**kwargs)
        records={}
        for name,version in roots.items():
            p=meta(name,version);p['suite']='noble';records[(name,version,'amd64')]=p
        def command(label,args,config=None,roots=None,package=None):
            calls.append((label,args))
            if label=='apt_binary':return 0,'apt 2.8.3 (amd64)\n',''
            if label=='apt_config':
                if args[-1]=='dump':return 0,'APT::Architectures "";\nAPT::Architectures:: "amd64";\n',''
                if args[-1]=='RootDir':return 0,"PLM_VALUE=''\n",''
                fid=dict((key,fid) for fid,key in f.FIELDS)[args[-1]];value=f.expected_scalars(Path(config).parent,Path(config).parent/'ubuntu-archive-keyring.gpg')[fid]
                return 0,"PLM_VALUE='"+value+"'\n",''
            if label=='index_visibility':
                name=args[-1];version=plan['root_constraints'][name];return 0,policy(version,version).replace('root:',name+':'),''
            number=sum(x[0]=='resolver_start' for x in calls)
            return 100,'',first_debug if number==1 else 'Starting pkgProblemResolver with broken count: 1\nDone\n'
        receipt=dict(identity=v.IDENTITY,consumed=True,allow=True,execution_approved=True,no_retry=True,no_resume=True,run_id='fake',launch_sha='a'*40)
        with tempfile.TemporaryDirectory() as temp,patch.dict(v.os.environ,{'RUNNER_TEMP':temp}),patch.object(v.sys,'version_info',(3,12,15)),patch.object(Path,'read_bytes',read_bytes),patch.object(Path,'read_text',read_text),patch.object(v,'cloud_launch_guard',return_value=receipt),patch.object(v,'command',side_effect=command),patch.object(v,'load_indices',return_value=({'noble':records},{},{'matched':True})),contextlib.redirect_stdout(io.StringIO()) as out:
            try:report=v.execute(plan,dict(RUNNER_TEMP=temp,RUNNER_ENVIRONMENT='github-hosted',ImageOS='ubuntu24',RUNNER_ARCH='X64'));error=None
            except d.DebugStop as error_value:report=None;error=error_value
        self.assertNotIn(SECRET,out.getvalue());return calls,report,error
    def test_first_unsupported_stops_remaining(self):
        calls,report,error=self.fake_pipeline('Starting pkgProblemResolver with broken count: 1\nE: '+SECRET)
        self.assertIsInstance(error,d.DebugStop);self.assertEqual(sum(x[0]=='resolver_start' for x in calls),1)
        self.assertEqual(v.PROGRESS['resolver_start']['last_case'],'single:ffmpeg')
    def test_first_summary_safe_rc100_then_remaining9_and_combined(self):
        calls,report,error=self.fake_pipeline('Starting pkgProblemResolver with broken count: 1\nDone\nE: Broken packages')
        self.assertIsNone(error);sim=[tuple(x[1]) for x in calls if x[0]=='resolver_start'];self.assertEqual(len(sim),11);self.assertEqual(len(set(sim)),11)
        self.assertFalse(report['transaction_proof']);self.assertFalse(report['install_authorized']);self.assertEqual(report['package_install'],0)
