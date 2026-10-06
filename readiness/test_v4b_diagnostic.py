from oracle_bridge import require_guard
require_guard()
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import apt_diagnostic_v4b as d
import cloud_runtime_preflight_v4b as v
import branch_marker_once as b
from one_shot_executor import Stop,RENDER_ID
from test_apt_transaction_v4 import meta
from test_branch_marker_once import setup

SECRET='ghp_SUPER_SECRET token=do_not_emit'


def fake_index(versions=('1',),suite='noble'):
    result={}
    for version in versions:
        p=meta('root',version);p.update(suite=suite)
        result[('root',version,'amd64')]=p
    return result


def classify(out='',err='',version='1',installed=None,index=None,rc=100,**kwargs):
    return d.classify(rc,out,err,{'root':version},installed or {},index or {'noble':fake_index()},['noble'],**kwargs)


class V4BDiagnosticTests(unittest.TestCase):
    def test_exact_version_unavailable(self):
        r=classify(err="E: Version '1' for 'root' was not found",index={'noble':fake_index(('2',))})
        self.assertIn(d.CODES['exact_version'],r['failure_codes']);self.assertEqual(r['root_packages'][0]['candidate_version'],'2')
    def test_package_not_found(self):
        r=classify(err='E: Unable to locate package root',index={'noble':{}})
        self.assertEqual(r['failure_codes'],[d.CODES['not_found']])
    def test_dependency_unsatisfied(self):
        r=classify(err='root : Depends: root (>= 2) but it is not going to be installed')
        self.assertIn(d.CODES['dependency'],r['failure_codes']);self.assertEqual(r['dependency_packages'],['root'])
    def test_held_conflict(self):
        r=classify(err='root : Depends: root but held packages prevent changes',held=['root'])
        self.assertIn(d.CODES['held'],r['failure_codes'])
    def test_generic_held_broken_is_not_held_evidence(self):
        r=classify(err='E: Unable to correct problems, you have held broken packages.')
        self.assertEqual(r['failure_codes'],[d.CODES['unknown']])
    def test_downgrade_required(self):
        r=classify(installed={'root':{'Version':'2','Architecture':'amd64'}})
        self.assertIn(d.CODES['downgrade'],r['failure_codes'])
    def test_explicit_downgrade_message(self):
        self.assertIn(d.CODES['downgrade'],classify(out='The following packages will be DOWNGRADED:')['failure_codes'])
    def test_broken_inventory(self):
        self.assertIn(d.CODES['broken'],classify(broken=['root'])['failure_codes'])
    def test_source_visibility_mismatch(self):
        r=classify(err="E: Version '1' for 'root' was not found")
        self.assertIn(d.CODES['source'],r['failure_codes']);self.assertNotIn(d.CODES['exact_version'],r['failure_codes'])
    def test_source_package_visibility_mismatch(self):
        self.assertIn(d.CODES['source'],classify(err='E: Unable to locate package root')['failure_codes'])
    def test_unknown_failure(self):
        self.assertEqual(classify(err=SECRET)['failure_codes'],[d.CODES['unknown']])
    def test_all_eight_codes_are_distinct(self):self.assertEqual(len(set(d.CODES.values())),8)
    def test_no_raw_secret_in_report(self):
        for raw in (SECRET,'root : Depends: root '+SECRET,"E: Version '1' for 'root' was not found "+SECRET):
            report=classify(err=raw,out=SECRET);self.assertNotIn(SECRET,json.dumps(report));self.assertNotIn('token=',json.dumps(report))
    def test_unknown_dependency_name_not_echoed(self):
        r=classify(err='root : Depends: ghp-secret-token but it is not installable')
        self.assertNotIn('ghp-secret-token',json.dumps(r))
    def test_multi_signal_preserved_without_single_root_cause_claim(self):
        r=classify(err='root : Depends: root but held packages prevent changes',held=['root'],broken=['root'])
        self.assertIn(d.CODES['dependency'],r['failure_codes']);self.assertIn(d.CODES['held'],r['failure_codes']);self.assertIn(d.CODES['broken'],r['failure_codes'])
    def test_accepted_is_never_proof(self):
        r=classify(rc=0);self.assertEqual(r['status'],'SOLVER_ACCEPTED_NOT_TRANSACTION_PROOF')
        self.assertNotIn('transaction_fingerprint',r)
    def test_output_limit(self):
        with self.assertRaisesRegex(Stop,'UNKNOWN_SOLVER_FAILURE'):classify(err='x'*65537)
    def test_case_whitelist(self):
        with self.assertRaisesRegex(Stop,'SOURCE_INDEX_MISMATCH'):
            d.classify(100,'','',{'root':'1'},{},{},['noble-pro'])
    def test_ppa_metadata_rejected(self):
        index={'noble':fake_index()};index['noble'][('root','1','amd64')]['repository']='https://ppa.invalid'
        with self.assertRaisesRegex(Stop,'SOURCE_INDEX_MISMATCH'):classify(index=index)
    def test_foreign_architecture(self):
        index={'noble':{('root','1','arm64'):meta('root')}}
        with self.assertRaisesRegex(Stop,'SOURCE_INDEX_MISMATCH'):classify(index=index)
    def test_pockets_independent(self):
        indices={'noble':fake_index(),'noble-updates':fake_index(('2',),'noble-updates'),
                 'noble-security':fake_index(('3',),'noble-security')}
        reports={case:d.classify(100,'','',{'root':'1'},{},indices,suites) for case,suites in d.CASES.items()}
        compared=d.compare_reports(reports)
        self.assertFalse(compared['release_state_conflict_proven']);self.assertEqual(len(compared['root_candidate_differences']),3)
        self.assertEqual(reports['release_only']['root_packages'][0]['candidate_version'],'1')
        self.assertEqual(reports['release_updates_security']['root_packages'][0]['candidate_version'],'3')
        self.assertTrue(all(x['root_packages'][0]['expected_version']=='1' for x in reports.values()))
    def test_comparison_incomplete(self):
        with self.assertRaisesRegex(Stop,'SOURCE_INDEX_MISMATCH'):d.compare_reports({})
    def test_inventory_hold_is_explicit(self):
        text='Package: root\nVersion: 1\nArchitecture: amd64\nStatus: hold ok installed\n'
        installed,held,broken=d.inventory_snapshot(text);self.assertEqual(held,['root']);self.assertEqual(broken,[])
    def test_broken_state_preserved(self):
        text='Package: root\nVersion: 1\nArchitecture: amd64\nStatus: install ok installed\n\nPackage: broken\nVersion: 1\nArchitecture: amd64\nStatus: install reinstreq half-installed\n'
        self.assertEqual(d.inventory_snapshot(text)[2],['broken'])
    def test_live_plan_valid_roots_unchanged(self):
        p=json.loads(v.PLAN.read_text());self.assertEqual(len(v.validate_plan(p)['packages']),10)
    def test_plan_root_drift_stop(self):
        p=json.loads(v.PLAN.read_text());p['root_constraints']['ffmpeg']='latest'
        with self.assertRaisesRegex(Stop,'SOURCE_INDEX_MISMATCH'):v.validate_plan(p)
    def test_prohibited_suite_stop(self):
        p=json.loads(v.PLAN.read_text());p['suites'].append('noble-esm')
        with self.assertRaisesRegex(Stop,'SOURCE_INDEX_MISMATCH'):v.validate_plan(p)
    def test_guard_failure_zero_network_and_process(self):
        with patch.object(v,'cloud_launch_guard',side_effect=Stop('MARKER_MISSING')),patch.object(v,'metadata_get') as network,patch.object(v,'_bounded_simulation') as process:
            with self.assertRaisesRegex(Stop,'MARKER_MISSING'):v.execute(json.loads(v.PLAN.read_text()),{})
            network.assert_not_called();process.assert_not_called()
    def test_consumed_004_never_reusable(self):
        self.assertTrue((b.ROOT/b.marker_path(b.PREFLIGHT_V4_ID)).is_file())
        with self.assertRaisesRegex(Stop,'IDENTITY_CONSUMED_004'):b.cloud_launch_guard({},b.PREFLIGHT_V4_ID)
    def test_004h_consumed_003_and_render_unused(self):
        self.assertTrue((b.ROOT/b.marker_path(b.PREFLIGHT_V4H_ID)).is_file())
        for identity in (b.PREFLIGHT_V3_ID,RENDER_ID):self.assertFalse((b.ROOT/b.marker_path(identity)).exists())
    def test_new_marker_first_addition_and_rerun(self):
        k=setup(b.PREFLIGHT_V4H_ID);self.assertTrue(b.launch_gate(**k)['consumed']);k['context']['run_attempt']=2
        with self.assertRaisesRegex(Stop,'RERUN'):b.launch_gate(**k)
    def test_metadata_binary_url_refused(self):
        with self.assertRaisesRegex(Stop,'SOURCE_INDEX_MISMATCH'):v.metadata_get(d.REPO+'/pool/main/a/a.deb',100)
    def test_metadata_other_host_refused(self):
        with self.assertRaisesRegex(Stop,'SOURCE_INDEX_MISMATCH'):v.metadata_get('https://example.com/dists/noble/InRelease',100)
    def test_unknown_solver_exception_safe(self):
        with patch.object(v,'_bounded_simulation',side_effect=RuntimeError(SECRET)),patch.object(v,'stage'):
            with self.assertRaises(Stop) as c:v.simulation('release_only',json.loads(v.PLAN.read_text()),'/FAKE',{}, {},[],[])
            self.assertEqual(str(c.exception),'RUNTIME_APT_UNKNOWN_SOLVER_FAILURE');self.assertNotIn(SECRET,str(c.exception))
    def test_no_token_in_process_environment(self):
        with patch.object(v,'_bounded_simulation',return_value=(100,'',SECRET)) as process,patch.object(v,'stage'):
            r=v.simulation('release_only',json.loads(v.PLAN.read_text()),'/FAKE',{}, {'noble':{}},[],[])
        env=process.call_args.args[1];self.assertNotIn('GH_TOKEN',env)
        self.assertNotIn(SECRET,json.dumps(r));args=process.call_args.args[0]
        self.assertIn('--simulate',args);self.assertIn('--no-download',args);self.assertIn('--no-install-recommends',args)
        self.assertEqual(len([x for x in args if '=' in x]),10)
    def test_workflow_trigger_read_only(self):
        wf=(b.ROOT/b.SPEC[v.IDENTITY][1]).read_text();self.assertIn("paths: ['"+b.marker_path(v.IDENTITY)+"']",wf)
        self.assertIn('contents: read',wf);self.assertIn('actions: read',wf);self.assertNotIn('contents: write',wf)
        self.assertEqual(wf.count("if: steps.marker.outputs.allow == 'true' && steps.marker.outputs.execution_approved == 'true'"),2)
    def test_release_manifest_validation(self):
        text='Origin: Ubuntu\nLabel: Ubuntu\nSuite: noble-updates\nCodename: noble\nDate: fixed date\nArchitectures: amd64\nComponents: main universe\nSHA256:\n '+'a'*64+' 1 main/binary-amd64/Packages.xz\n '+'b'*64+' 2 universe/binary-amd64/Packages.xz\n'
        r=v.release_manifest(text.encode(),'noble-updates');self.assertEqual(r['suite'],'noble-updates')
        self.assertNotIn('fixed date',json.dumps(r))
        with self.assertRaisesRegex(Stop,'SOURCE_INDEX_MISMATCH'):v.release_manifest(text.replace('Origin: Ubuntu','Origin: Evil').encode(),'noble-updates')
    def test_prior_004_marker_blob_preserved(self):
        raw=(b.ROOT/b.marker_path(b.PREFLIGHT_V4_ID)).read_bytes();blob=b'blob '+str(len(raw)).encode()+b'\0'+raw
        self.assertEqual(hashlib.sha1(blob).hexdigest(),'274559c7b4d0295008740a9f555de8e802cccc91')
    def test_installed_release_update_coverage(self):
        installed={'root':{'Version':'2','Architecture':'amd64'}}
        indices={'noble':fake_index(),'noble-updates':fake_index(('2',),'noble-updates'),'noble-security':{}}
        old=d.inventory_coverage(installed,indices,['noble'])
        new=d.inventory_coverage(installed,indices,['noble','noble-updates'])
        self.assertEqual(old['case_exact_present_count'],0);self.assertEqual(new['case_exact_present_count'],1)
        self.assertEqual(old['release_absent_updates_or_security_present_count'],1)
    def test_unknown_installed_origin_not_asserted_prohibited(self):
        installed={'other':{'Version':'1','Architecture':'amd64'}}
        r=d.inventory_coverage(installed,{'noble':fake_index()},['noble'])
        self.assertEqual(r['index_recognized_installed_count'],0)
        self.assertNotIn('prohibited',json.dumps(r))
    def test_generic_held_line_cannot_classify_unrelated_named_package(self):
        r=classify(out='root is already the newest version (1).',err='E: Unable to correct problems, you have held broken packages.',held=['root'])
        self.assertNotIn(d.CODES['held'],r['failure_codes'])
