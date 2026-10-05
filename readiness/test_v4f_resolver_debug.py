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
import apt_resolver_debug_v4f as d
import cloud_runtime_preflight_v4f as v
import branch_marker_once as b
import apt_config_fields_v4d as f
from one_shot_executor import Stop,RENDER_ID
from test_branch_marker_once import setup
SECRET='ghp_SUPER_SECRET token=DO_NOT_ECHO /secret/path'

def trusted(depends='dep (>= 2)',installed=None):
    records={('root','1','amd64'):{'Depends':depends,'Breaks':'dep (<< 3)'},
             ('dep','2','amd64'):{},('dep','3','amd64'):{},('other','2','amd64'):{}}
    return d.context({'noble':records},installed or {})

class DebugTests(unittest.TestCase):
    def reject(self,text,reason,ctx=None):
        with contextlib.redirect_stdout(io.StringIO()) as out,self.assertRaises(d.DebugStop) as caught:d.parse_debug(text,ctx or trusted())
        public=caught.exception.evidence();self.assertEqual(public['fixed_reason'],reason)
        self.assertEqual(set(public),{'syntax_family','relevance','known_package_tokens_count','fixed_reason'})
        self.assertEqual(out.getvalue(),'');self.assertNotIn(SECRET,str(caught.exception)+json.dumps(public))
        return public
    def test_source_derived_representative_families(self):
        fixtures=json.loads((v.ROOT/'readiness/apt-resolver-v4f-source-fixtures.json').read_text())['fixtures']
        ctx=trusted()
        for x in fixtures:
            with self.subTest(x['source_line']):
                report=d.parse_debug(x['line'],ctx);self.assertEqual(report['syntax_family_counts'][x['family']],1)
                self.assertFalse(report['proof']);self.assertFalse(report['install_authorized'])
    def test_existing_broken_grammar_preserved(self):
        r=d.parse_debug('Starting pkgProblemResolver with broken count: 1\n Broken root:amd64 Depends on dep:amd64 (>= 2)\nDone',trusted())
        self.assertEqual(r['conflicts'][0]['required_version'],'2')
    def test_existing_considering(self):self.assertTrue(d.parse_debug('  Considering dep:amd64 10 as a solution to root:amd64 -1',trusted())['parsed'])
    def test_existing_fixed_user_error(self):
        r=d.parse_debug(' root : Depends: dep (>= 2) but it is not going to be installed',trusted());self.assertEqual(len(r['conflicts']),1)
    def test_predepends_variant(self):self.assertTrue(d.parse_debug('Broken root:amd64 PreDepends on dep:amd64 (>= 2)',d.context({'noble':{('root','1','amd64'):{'Pre-Depends':'dep (>= 2)'},('dep','2','amd64'):{}}},{}))['parsed'])
    def test_unversioned(self):self.assertIsNone(d.parse_debug('Broken root Depends on dep',trusted('dep'))['conflicts'][0]['required_version'])
    def test_arch_suffix(self):self.assertTrue(d.parse_debug('Broken root:amd64 Depends on dep:all (>= 2)',trusted())['parsed'])
    def test_alternative_member_not_provider_proof(self):
        r=d.parse_debug('Broken root Depends on dep (>= 2)',trusted('dep (>= 2) | other (>= 2)'))
        self.assertIn('SIGNED_ALTERNATIVE_MEMBER_NOT_PROVIDER_PROOF',[x['fixed_reason'] for x in r['evidence']]);self.assertFalse(r['proof'])
    def test_known_benign_header(self):self.assertEqual(d.parse_debug('Show Scores',trusted())['evidence'][0]['syntax_family'],'BENIGN_DIAGNOSTIC')
    def test_unknown_benign_looking_not_unconditionally_ignored(self):self.reject('NOTICE harmless-looking '+SECRET,'UNSUPPORTED_RELEVANT_SYNTAX')
    def test_unknown_relevant_fingerprint(self):self.assertEqual(self.reject('Choosing root via dep '+SECRET,'UNSUPPORTED_RELEVANT_SYNTAX')['known_package_tokens_count'],2)
    def test_benign_family_suffix_not_ignored(self):self.reject('Show Scores '+SECRET,'UNSUPPORTED_RELEVANT_SYNTAX')
    def test_signed_constraint_mismatch(self):self.reject('Broken root Depends on dep (>= 3)','SIGNED_METADATA_MISMATCH')
    def test_unsigned_relation(self):self.reject('Broken root Conflicts on dep (>= 2)','SIGNED_METADATA_MISMATCH')
    def test_unknown_package(self):self.reject('Re-Instated unknown:amd64','UNKNOWN_PACKAGE_TOKEN')
    def test_unknown_dependency(self):self.reject('Broken root Depends on nonexistent (>= 2)','UNKNOWN_PACKAGE_TOKEN')
    def test_malformed_version(self):self.reject('Broken root Depends on dep (>= '+SECRET+')','UNSUPPORTED_RELEVANT_SYNTAX')
    def test_invalid_debian_version_even_if_trusted_context(self):
        ctx=trusted();ctx['versions']['root'].add('1_2')
        self.reject('Investigating (0) root:amd64 < none -> 1_2 @un uN >','PRETTY_PACKAGE_SYNTAX_UNSUPPORTED',ctx)
    def test_unverified_pretty_version(self):self.reject('Investigating (0) root:amd64 < none -> 999 @un uN >','UNVERIFIED_VERSION')
    def test_private_installed_version_authority(self):
        ctx=trusted(installed={'dep':{'Version':'2'}})
        r=d.parse_debug('Investigating (0) dep:amd64 < 2 | 3 @ii K >',ctx);self.assertTrue(r['parsed'])
    def test_wrong_installed_version(self):self.reject('Investigating (0) dep:amd64 < 2 | 3 @ii K >','INSTALLED_VERSION_MISMATCH')
    def test_pretty_secret_not_echoed(self):self.reject('Investigating (0) root:amd64 < '+SECRET+' >','PRETTY_PACKAGE_SYNTAX_UNSUPPORTED')
    def test_line_bound(self):self.reject('x'*2049,'LINE_BOUND_EXCEEDED')
    def test_output_bound(self):self.reject('x'*65537,'OUTPUT_BOUND_EXCEEDED')
    def test_unknown_flags(self):self.reject('Investigating (0) root:amd64 < none -> 1 @un SECRET >','PRETTY_PACKAGE_SYNTAX_UNSUPPORTED')
    def test_signed_breaks_selection(self):self.assertTrue(d.parse_debug('Upgrading dep due to Breaks field in root',trusted())['parsed'])
    def test_unsigned_breaks_selection(self):self.reject('Upgrading other due to Breaks field in root','SIGNED_METADATA_MISMATCH')
    def test_failure_summary_not_held_root_cause(self):
        r=d.parse_debug('E: Unable to correct problems, you have held broken packages.',trusted());self.assertEqual(r['conflicts'],[])
    def test_no_raw_fields(self):
        r=d.parse_debug('Broken root Depends on dep (>= 2)',trusted());self.assertFalse(set(r)&{'raw','stdout','stderr','line'})
    def test_frozen_004e(self):
        p=json.loads(v.PLAN.read_text());raw=(v.ROOT/p['prior_004e_evidence']).read_bytes();e=json.loads(raw)
        self.assertEqual(hashlib.sha256(raw).hexdigest(),p['prior_004e_evidence_sha256']);self.assertEqual(e['scalar_pass_count'],22)
        self.assertEqual(e['candidate_exact_matches'],10);self.assertEqual(e['simulation_count'],1);self.assertEqual(e['remaining_simulations'],0)
        self.assertEqual(e['run_id'],37285242354);self.assertEqual(e['first_failure_stage'],'resolver_debug');self.assertTrue(all(x=='PASS' for x in e['scopes'].values()))
    def test_source_provenance_hash(self):
        p=json.loads(v.PLAN.read_text());raw=(v.ROOT/p['parser_source_evidence']).read_bytes();self.assertEqual(hashlib.sha256(raw).hexdigest(),p['parser_source_evidence_sha256'])
        e=json.loads(raw);self.assertFalse(e['stable_grammar_claim']);self.assertFalse(e['runtime_source_fetch']);self.assertEqual(e['implementation'],'Ubuntu Noble apt 2.8.3')
    def test_004e_consumed_both_guards(self):
        with self.assertRaisesRegex(Stop,'IDENTITY_CONSUMED_004E'):b.cloud_launch_guard({},b.PREFLIGHT_V4E_ID)
        with self.assertRaisesRegex(Stop,'IDENTITY_CONSUMED_004E'):b.launch_gate(**setup(b.PREFLIGHT_V4E_ID))
    def test_current_unconsumed_identity_independent(self):self.assertTrue(b.launch_gate(**setup(b.PREFLIGHT_V4H_ID))['allow'])
    def test_004f_consumed_marker_retained(self):self.assertTrue((v.ROOT/b.marker_path(v.IDENTITY)).exists())
    def test_render_absent(self):self.assertFalse((v.ROOT/b.marker_path(RENDER_ID)).exists())
    def test_005_absent(self):self.assertFalse(list((v.ROOT/'.github/workflows').glob('*v5*')))
    def test_no_guard_no_apt(self):
        with patch.object(v,'cloud_launch_guard',side_effect=Stop('MARKER_MISSING')),patch.object(v,'command') as command,patch.object(v,'load_indices') as network:
            with self.assertRaises(Stop):v.execute(json.loads(v.PLAN.read_text()),{})
        command.assert_not_called();network.assert_not_called()
    def test_root_versions_unchanged(self):
        old=json.loads((v.ROOT/'readiness/cloud-runtime-preflight-v4e-scoped-plan.json').read_text());new=json.loads(v.PLAN.read_text())
        for k in ('root_constraints','root_evidence_sha256','signed_release_index','config_verification'):
            if k!='config_verification':self.assertEqual(old[k],new[k])
    def test_workflow_exact_scope(self):
        raw=(v.ROOT/b.SPEC[v.IDENTITY][1]).read_text();self.assertIn("paths: ['"+b.marker_path(v.IDENTITY)+"']",raw)
        self.assertIn('contents: read',raw);self.assertIn('actions: read',raw);self.assertNotIn('contents: write',raw);self.assertNotIn('actions: write',raw)
        self.assertIn("steps.marker.outputs.allow == 'true' && steps.marker.outputs.execution_approved == 'true'",raw)

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
    def test_first_unsupported_remaining_zero(self):
        calls,report,error=self.fake_pipeline('Starting pkgProblemResolver with broken count: 1\nUNKNOWN '+SECRET)
        self.assertIsInstance(error,d.DebugStop);sim=[x for x in calls if x[0]=='resolver_start'];self.assertEqual(len(sim),1);self.assertEqual(sim[0][1][-1],'ffmpeg=7:6.1.1-3ubuntu5');self.assertEqual(v.PROGRESS['resolver_start']['entered_count'],1)
    def test_first_parsed_rc100_remaining9_combined_once(self):
        calls,report,error=self.fake_pipeline('Starting pkgProblemResolver with broken count: 1\nDone\n')
        self.assertIsNone(error);sim=[x[1] for x in calls if x[0]=='resolver_start'];self.assertEqual(len(sim),11);self.assertEqual(len(set(tuple(x) for x in sim)),11)
        self.assertFalse(report['transaction_proof']);self.assertFalse(report['install_authorized']);self.assertEqual(report['package_install'],0)
