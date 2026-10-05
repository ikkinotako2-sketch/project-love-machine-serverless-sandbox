from oracle_bridge import require_guard
require_guard()
import contextlib
import hashlib
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import apt_safe_fingerprint_v4h as h
ROOT=Path(__file__).resolve().parents[1]
SECRET='ghp_DO_NOT_ECHO token=SECRET /secret/path/private 9deadbeef'

def trusted(depends='dep, dep (>= 2)',installed=None):
    return h.context({'noble':{('root','1','amd64'):{'Depends':depends,'Pre-Depends':'dep (>= 2)','Conflicts':'dep (>= 2)','Breaks':'dep (<< 3)'},('dep','2','amd64'):{},('other','2','amd64'):{}}},installed or {})

class FingerprintTests(unittest.TestCase):
    def shape(self,line,stream='STDERR',section='UNKNOWN',parent=None):
        return h.fingerprint(line,trusted(),stream,section,parent)
    def reject(self,line,stream='STDERR',ctx=None):
        kwargs={'stderr':line,'stdout':''} if stream=='STDERR' else {'stderr':'','stdout':line}
        with contextlib.redirect_stdout(io.StringIO()) as out,self.assertRaises(h.DebugStop) as caught:
            h.parse_debug(ctx=ctx or trusted(),return_code=100,**kwargs)
        public=caught.exception.evidence()
        self.assertEqual(out.getvalue(),'');self.assertEqual(set(public),set(h.ENUMS)|set(h.BOOLS)|{'known_package_tokens_count'})
        for key,values in h.ENUMS.items():self.assertIn(public[key],values)
        for key in h.BOOLS:self.assertIs(type(public[key]),bool)
        self.assertIs(type(public['known_package_tokens_count']),int)
        self.assertLessEqual(public['known_package_tokens_count'],100)
        serialized=json.dumps(public)
        for value in (SECRET,'/secret/path','token=SECRET','ghp_',hashlib.sha256(line.encode()).hexdigest()):self.assertNotIn(value,serialized+str(caught.exception))
        return public
    def test_stdout_stream(self):self.assertEqual(self.reject(SECRET,'STDOUT')['stream'],'STDOUT')
    def test_stderr_stream(self):self.assertEqual(self.reject('E: '+SECRET)['stream'],'STDERR')
    def test_package_header_only(self):
        f=self.shape(' root :');self.assertEqual((f['prefix_class'],f['section'],f['suffix_family'],f['known_package_tokens_count']),('PACKAGE_HEADER','SHOW_BROKEN','SOURCE_CONFIRMED_PACKAGE_HEADER',1))
        self.assertTrue(f['has_parent_package']);self.assertFalse(f['has_dependency_package'])
        self.assertEqual(h.parse_debug('',trusted(),' root :',100)['conflicts'],[])
    def test_one_token_error_not_header(self):
        f=self.reject('E: root '+SECRET);self.assertEqual(f['known_package_tokens_count'],1);self.assertEqual(f['prefix_class'],'E_PREFIX');self.assertEqual(f['section'],'GLOBAL_ERROR');self.assertFalse(f['has_parent_package'])
    def test_zero_known_tokens(self):self.assertEqual(self.reject('E: '+SECRET)['known_package_tokens_count'],0)
    def test_two_known_tokens(self):self.assertEqual(self.reject('E: root dep '+SECRET)['known_package_tokens_count'],2)
    def test_count_bounded(self):self.assertEqual(self.shape('root '*500)['known_package_tokens_count'],100)
    def test_relation_continuation(self):
        f=self.shape('        Depends: dep (>= 2) '+SECRET,parent='root');self.assertEqual(f['prefix_class'],'RELATION_CONTINUATION');self.assertEqual(f['section'],'CONTINUATION');self.assertTrue(f['has_parent_package']);self.assertTrue(f['has_dependency_package'])
    def test_continuation_parse(self):
        r=h.parse_debug('',trusted(),' root :\n        Depends: dep (>= 2) but it is not installable',100);self.assertEqual(len(r['conflicts']),1)
    def test_continuation_missing_parent(self):self.assertEqual(self.reject(' Depends: dep (>= 2) '+SECRET)['fixed_reason'],'MISSING_PARENT_PACKAGE')
    def test_stream_parent_isolation(self):
        with self.assertRaises(h.DebugStop) as caught:h.parse_debug(' root :',trusted(),' Depends: dep (>= 2) but it is not installable',100)
        f=caught.exception.evidence();self.assertEqual(f['stream'],'STDOUT');self.assertFalse(f['has_parent_package'])
    def test_e_prefix(self):self.assertEqual(self.reject('E: root '+SECRET)['prefix_class'],'E_PREFIX')
    def test_w_prefix(self):self.assertEqual(self.reject('W: root '+SECRET)['prefix_class'],'W_PREFIX')
    def test_n_prefix(self):self.assertEqual(self.reject('N: root '+SECRET)['prefix_class'],'N_PREFIX')
    def test_d_prefix(self):self.assertEqual(self.reject('D: root '+SECRET)['prefix_class'],'D_PREFIX')
    def test_stdout_warning_stop(self):self.assertEqual(self.reject('W: root '+SECRET,'STDOUT')['prefix_class'],'W_PREFIX')
    def test_versioned_relation(self):
        f=self.shape(' root : Depends: dep (>= 2) '+SECRET);self.assertEqual(f['relation_token'],'DEPENDS');self.assertEqual(f['version_operator'],'GE');self.assertTrue(f['has_version_token'])
    def test_unversioned_relation(self):
        f=self.shape(' root : Depends: dep '+SECRET);self.assertEqual(f['version_operator'],'NONE');self.assertFalse(f['has_version_token'])
    def test_predepends_enum(self):self.assertEqual(self.shape(' root : Pre-Depends: dep (>= 2) '+SECRET)['relation_token'],'PREDEPENDS')
    def test_conflicts_enum(self):self.assertEqual(self.shape(' root : Conflicts: dep '+SECRET)['relation_token'],'CONFLICTS')
    def test_breaks_enum(self):self.assertEqual(self.shape(' root : Breaks: dep '+SECRET)['relation_token'],'BREAKS')
    def test_all_operators(self):
        for op,enum in (('=','EQ'),('>=','GE'),('<=','LE'),('<<','LT'),('>>','GT')):
            with self.subTest(op=op):self.assertEqual(self.shape(' root : Depends: dep ('+op+' 2) '+SECRET)['version_operator'],enum)
    def test_no_relation_enum(self):self.assertEqual(self.shape('E: root '+SECRET)['relation_token'],'NONE')
    def test_indent_none(self):self.assertEqual(self.shape('E: '+SECRET)['indent_bucket'],'NONE')
    def test_indent_small(self):self.assertEqual(self.shape('   E: '+SECRET)['indent_bucket'],'SMALL')
    def test_indent_large(self):self.assertEqual(self.shape(' '*20+'E: '+SECRET)['indent_bucket'],'LARGE')
    def test_indent_tab(self):self.assertEqual(self.shape('\tE: '+SECRET)['indent_bucket'],'SMALL')
    def test_source_suffix_not_installable(self):self.assertEqual(self.shape(' root : Depends: dep but it is not installable')['suffix_family'],'SOURCE_CONFIRMED_NOT_INSTALLABLE')
    def test_source_suffix_not_selected(self):self.assertEqual(self.shape(' root : Depends: dep but it is not going to be installed')['suffix_family'],'SOURCE_CONFIRMED_NOT_GOING_TO_BE_INSTALLED')
    def test_source_suffix_selected(self):self.assertEqual(self.shape(' root : Depends: dep but 2 is to be installed')['suffix_family'],'SOURCE_CONFIRMED_VERSION_TO_BE_INSTALLED')
    def test_source_suffix_installed(self):self.assertEqual(self.shape(' root : Depends: dep but 2 is installed')['suffix_family'],'SOURCE_CONFIRMED_VERSION_INSTALLED')
    def test_unknown_suffix(self):self.assertEqual(self.reject(' root : Depends: dep '+SECRET)['suffix_family'],'UNKNOWN')
    def test_suffix_extra_secret_not_confirmed(self):self.assertEqual(self.shape(' root : Depends: dep but it is not installable '+SECRET)['suffix_family'],'UNKNOWN')
    def test_locale_drift_error(self):self.assertEqual(self.reject('E: Paquets casses root '+SECRET)['suffix_family'],'UNKNOWN')
    def test_locale_drift_relation(self):self.assertEqual(self.reject(' root : Abhaengig: dep '+SECRET)['relation_token'],'NONE')
    def test_locale_drift_preamble(self):self.assertEqual(self.reject('Les paquets suivants '+SECRET,'STDOUT')['section'],'PREAMBLE')
    def test_secret_equivalence_lossy(self):
        self.assertEqual(self.shape('E: root arbitrary_private_payload_A'),self.shape('E: root unrelated_private_payload_B'))
    def test_unknown_fixed_reason_never_echoed(self):self.assertEqual(h.fingerprint('E: '+SECRET,trusted(),'STDERR',reason=SECRET)['fixed_reason'],'UNSUPPORTED_RELEVANT_USER_ERROR')
    def test_global_error_continuation(self):self.assertEqual(self.shape('   '+SECRET,section='GLOBAL_ERROR')['section'],'CONTINUATION')
    def test_resolver_debug_section(self):self.assertEqual(self.reject('Investigating '+SECRET)['section'],'RESOLVER_DEBUG')
    def test_line_bound(self):self.assertEqual(self.reject('E: '+'x'*2049)['fixed_reason'],'LINE_BOUND_EXCEEDED')
    def test_stderr_bound(self):self.assertEqual(self.reject('x'*65537)['fixed_reason'],'OUTPUT_BOUND_EXCEEDED')
    def test_stdout_bound(self):self.assertEqual(self.reject('x'*2000001,'STDOUT')['fixed_reason'],'OUTPUT_BOUND_EXCEEDED')
    def test_failure_schema_no_raw_hash_fields(self):
        f=self.reject('E: root '+SECRET);self.assertFalse(set(f)&{'raw','line','substring','path','exception','hash','sha256','stdout','stderr'})
    def test_unknown_E_still_stops(self):self.assertEqual(self.reject('E: '+SECRET)['fixed_reason'],'UNSUPPORTED_RELEVANT_USER_ERROR')
    def test_source_confirmed_summary_not_root_cause(self):self.assertEqual(h.parse_debug('E: Broken packages',trusted())['conflicts'],[])
    def test_source_fixture17_preserved(self):
        fixtures=json.loads((ROOT/'readiness/apt-user-error-v4g-source-fixtures.json').read_text())['fixtures'];self.assertEqual(len(fixtures),17)
        for item in fixtures:
            with self.subTest(item['family']):
                r=h.parse_debug(item['template_instance'] if item['stream']=='stderr' else '',trusted(installed={'dep':{'Version':'2'}}),item['template_instance'] if item['stream']=='stdout' else '',100)
                self.assertGreater(r['user_error_family_counts'][item['family']],0);self.assertFalse(r['proof']);self.assertFalse(r['install_authorized'])
    def test_unknown_stdout_in_showbroken(self):self.assertEqual(self.reject('The following packages have unmet dependencies:\n'+SECRET,'STDOUT')['section'],'SHOW_BROKEN')

class PreparationTests(unittest.TestCase):
    def plan(self):return json.loads((ROOT/'readiness/cloud-runtime-preflight-v4h-safe-fingerprint-plan.json').read_text())
    def test_004g_frozen_exact(self):
        p=self.plan();raw=(ROOT/p['prior_004g_evidence']).read_bytes();e=json.loads(raw)
        self.assertEqual(hashlib.sha256(raw).hexdigest(),p['prior_004g_evidence_sha256'])
        self.assertEqual(e['run_id'],37323926824);self.assertEqual(e['launch_sha'],'36d04fe4526553a81f1ae5ddc1a4acfa65fbf6e0');self.assertEqual(e['run_attempt'],1)
        self.assertEqual(e['scalar_pass_count'],22);self.assertTrue(all(x=='PASS' for x in e['scopes'].values()));self.assertEqual(e['status_snapshot'],'PASS')
        self.assertEqual(e['private_lists_verified'],9);self.assertEqual(e['candidate_exact_matches'],10);self.assertEqual(e['simulation_count'],1);self.assertEqual(e['remaining_simulations_executed'],0);self.assertEqual(e['ffmpeg_single_return_code'],100);self.assertTrue(e['solver_entry_confirmed'])
        self.assertEqual(e['unsupported_fingerprint'],dict(syntax_family='UNSUPPORTED_RELEVANT_USER_ERROR',relevance='DEPENDENCY_DECISION_OR_UNKNOWN',known_package_tokens_count=1,fixed_reason='UNSUPPORTED_RELEVANT_USER_ERROR'))
        self.assertEqual(e['raw_line_retention'],0);self.assertEqual(e['raw_stdout_retention'],0);self.assertEqual(e['raw_stderr_retention'],0);self.assertFalse(e['transaction_proof']);self.assertFalse(e['install_authorized'])
    def test_fingerprint_schema_exact(self):
        p=self.plan();raw=(ROOT/p['fingerprint_schema']).read_bytes();s=json.loads(raw);self.assertEqual(hashlib.sha256(raw).hexdigest(),p['fingerprint_schema_sha256']);self.assertFalse(s['additionalProperties'])
        self.assertEqual(set(s['required']),set(h.ENUMS)|set(h.BOOLS)|{'known_package_tokens_count'})
        for key,values in h.ENUMS.items():self.assertEqual(s['properties'][key]['enum'],list(values))
    def test_004g_consumed_both_guards(self):
        import branch_marker_once as b
        from one_shot_executor import Stop
        from test_branch_marker_once import setup
        with self.assertRaisesRegex(Stop,'IDENTITY_CONSUMED_004G'):b.cloud_launch_guard({},b.PREFLIGHT_V4G_ID)
        with self.assertRaisesRegex(Stop,'IDENTITY_CONSUMED_004G'):b.launch_gate(**setup(b.PREFLIGHT_V4G_ID))
    def test_004h_independent(self):
        import branch_marker_once as b
        from test_branch_marker_once import setup
        self.assertTrue(b.launch_gate(**setup(b.PREFLIGHT_V4H_ID))['allow'])
    def test_004h_marker_absent(self):self.assertFalse((ROOT/'audit-evidence/consumed/manual-fixture-runtime-preflight-20261005-004h.json').exists())
    def test_render_marker_absent(self):self.assertFalse((ROOT/'audit-evidence/consumed/manual-fixture-render-20261004-001.json').exists())
    def test_005_absent(self):self.assertFalse(list((ROOT/'.github/workflows').glob('*v5*')))
    def test_root_config_pockets_command_unchanged(self):
        old=json.loads((ROOT/'readiness/cloud-runtime-preflight-v4g-user-error-plan.json').read_text());new=self.plan()
        for key in ('root_constraints','root_evidence_sha256','signed_release_index','config_verification','suites','repository','limits','debug_options','fixed_stages'):self.assertEqual(old[key],new[key])
        old=(ROOT/'readiness/cloud_runtime_preflight_v4g.py').read_text();new=(ROOT/'readiness/cloud_runtime_preflight_v4h.py').read_text()
        for name in ('command','verify_fields','load_indices'):
            a=old.index('def '+name+'(');z=old.index('\n\ndef ',a);b=new.index('def '+name+'(');y=new.index('\n\ndef ',b);self.assertEqual(old[a:z],new[b:y])
    def test_workflow_marker_only_readonly(self):
        raw=(ROOT/'.github/workflows/plm-cloud-runtime-preflight-v4h-once.yml').read_text();self.assertIn("paths: ['audit-evidence/consumed/manual-fixture-runtime-preflight-20261005-004h.json']",raw);self.assertNotIn('workflow_dispatch:',raw);self.assertNotIn('contents: write',raw);self.assertNotIn('upload-artifact@',raw);self.assertNotIn('actions/cache@',raw)
    def test_guard_failure_zero_adapters(self):
        import cloud_runtime_preflight_v4h as v
        from one_shot_executor import Stop
        with patch.object(v,'cloud_launch_guard',side_effect=Stop('MARKER_MISSING')),patch.object(v,'command') as command,patch.object(v,'load_indices') as network:
            with self.assertRaises(Stop):v.execute(self.plan(),{})
        command.assert_not_called();network.assert_not_called()
    def test_first_unknown_only_one_fake_input(self):
        import cloud_runtime_preflight_v4h as v
        import test_v4g_user_error as old
        case=old.UserErrorTests()
        with patch.object(old,'v',v),patch.object(old,'d',h):calls,report,error=case.fake_pipeline('Starting pkgProblemResolver with broken count: 1\nE: root '+SECRET)
        self.assertIsInstance(error,h.DebugStop);self.assertEqual(sum(x[0]=='resolver_start' for x in calls),1);self.assertEqual(v.PROGRESS['resolver_start']['last_case'],'single:ffmpeg');self.assertEqual(error.evidence()['stream'],'STDERR')
    def test_first_safe_only11_distinct_fake_inputs(self):
        import cloud_runtime_preflight_v4h as v
        import test_v4g_user_error as old
        with patch.object(old,'v',v),patch.object(old,'d',h):calls,report,error=old.UserErrorTests().fake_pipeline('Starting pkgProblemResolver with broken count: 1\nDone\nE: Broken packages')
        self.assertIsNone(error);inputs=[tuple(x[1]) for x in calls if x[0]=='resolver_start'];self.assertEqual(len(inputs),11);self.assertEqual(len(set(inputs)),11);self.assertFalse(report['transaction_proof']);self.assertFalse(report['install_authorized'])
