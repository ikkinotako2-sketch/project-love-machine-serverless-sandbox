from oracle_bridge import require_guard
require_guard()
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import apt_transaction_v4 as t
import cloud_runtime_preflight_v4 as v
import branch_marker_once as b
from one_shot_executor import Stop,PREFLIGHT_ID,RENDER_ID

SECRET='token=ghp_SECRET_SHOULD_NOT_APPEAR'


def meta(name,version='1',depends='',provides=''):
    return {'Package':name,'Version':version,'Architecture':'amd64','Filename':'pool/main/a/'+name+'/'+name+'_1_amd64.deb',
        'SHA256':'a'*64,'repository':t.REPO,'suite':'noble','pocket':'release','component':'main',
        'Depends':depends,'Pre-Depends':'','Provides':provides}


def fixture():
    installed={'base':{'Package':'base','Version':'1','Architecture':'amd64'}}
    values=[meta('root',depends='base (>= 1)'),meta('base')]
    index={(p['Package'],p['Version'],p['Architecture']):p for p in values}
    raw='Reading package lists...\nBuilding dependency tree...\nReading state information...\n0 upgraded, 1 newly installed, 0 to remove and 0 not upgraded.\nInst root (1 Ubuntu:24.04/noble [amd64])\nConf root (1 Ubuntu:24.04/noble [amd64])\n'
    return raw,installed,index,{'root':'1'}


def run(f):return t.transaction(*f,'b'*64,'c'*64)


class TransactionV4Tests(unittest.TestCase):
    def test_complete_install_keep(self):
        r=run(fixture());self.assertEqual(r['status'],'PASS');self.assertEqual(r['transaction']['counts'],
            {'install_count':1,'upgrade_count':0,'downgrade_count':0,'keep_count':1,'remove_count':0})
        self.assertEqual([p['name'] for p in r['transaction']['packages']],['base','root'])
    def test_fingerprint_order_stable(self):
        f=fixture();g=copy.deepcopy(f);g[2].clear();g[2].update(reversed(list(f[2].items())))
        self.assertEqual(run(f)['transaction_fingerprint'],run(g)['transaction_fingerprint'])
    def test_fingerprint_covers_inventory(self):
        f=fixture();self.assertNotEqual(run(f)['transaction_fingerprint'],t.transaction(*f,'d'*64,'c'*64)['transaction_fingerprint'])
    def test_remove_rejected(self):
        f=list(fixture());f[0]+='Remv base [1]\n'
        with self.assertRaisesRegex(Stop,'RUNTIME_APT_REMOVE_PROPOSED'):run(f)
    def test_downgrade_rejected(self):
        f=list(fixture());f[1]['root']={'Version':'2','Architecture':'amd64'};f[0]=f[0].replace('Inst root (','Inst root [2] (')
        with self.assertRaisesRegex(Stop,'RUNTIME_APT_DOWNGRADE_PROPOSED'):run(f)
    def test_upgrade_blocked_with_reason(self):
        f=list(fixture());f[1]['root']={'Version':'0','Architecture':'amd64'}
        f[0]=f[0].replace('0 upgraded, 1 newly installed','1 upgraded, 0 newly installed').replace('Inst root (','Inst root [0] (')
        r=run(f);self.assertEqual(r['failure_code'],'RUNTIME_APT_UNEXPECTED_UPGRADE')
        self.assertEqual(r['upgrade_reasons'][0]['selected_version'],'1');self.assertIn('transaction_fingerprint',r)
    def test_version_drift_rejected(self):
        f=list(fixture());f[3]['root']='2'
        with self.assertRaisesRegex(Stop,'TRANSACTION_INCOMPLETE'):run(f)
    def test_source_mismatch(self):
        f=list(fixture());f[2][('root','1','amd64')]['repository']='https://ppa.invalid'
        with self.assertRaisesRegex(Stop,'TRANSACTION_SOURCE_MISMATCH'):run(f)
    def test_keep_source_unknown_rejected(self):
        f=list(fixture());del f[2][('base','1','amd64')]
        with self.assertRaisesRegex(Stop,'TRANSACTION_SOURCE_MISMATCH'):run(f)
    def test_invalid_architecture(self):
        f=list(fixture());f[0]=f[0].replace('[amd64]','[arm64]')
        with self.assertRaisesRegex(Stop,'TRANSACTION_INCOMPLETE'):run(f)
    def test_unpaired_configure(self):
        f=list(fixture());f[0]=f[0].split('Conf')[0]
        with self.assertRaisesRegex(Stop,'TRANSACTION_INCOMPLETE'):run(f)
    def test_duplicate_inst(self):
        f=list(fixture());f[0]+='Inst root (1 Ubuntu:24.04/noble [amd64])\n'
        with self.assertRaisesRegex(Stop,'TRANSACTION_INCOMPLETE'):run(f)
    def test_summary_mismatch(self):
        f=list(fixture());f[0]=f[0].replace('1 newly installed','2 newly installed')
        with self.assertRaisesRegex(Stop,'TRANSACTION_INCOMPLETE'):run(f)
    def test_raw_unknown_secret_is_not_exception(self):
        f=list(fixture());f[0]+=SECRET
        with self.assertRaises(Stop) as caught:run(f)
        self.assertEqual(str(caught.exception),'RUNTIME_APT_TRANSACTION_INCOMPLETE');self.assertNotIn(SECRET,str(caught.exception))
    def test_virtual_provider(self):
        f=list(fixture());f[2][('root','1','amd64')]['Depends']='virtual (= 1)';f[2][('base','1','amd64')]['Provides']='virtual (= 1)'
        r=run(f);self.assertEqual(r['transaction']['dependency_selections'][0]['selected_provider'],'base')
        self.assertTrue(r['transaction']['dependency_selections'][0]['virtual'])
    def test_unresolved_virtual(self):
        f=list(fixture());f[2][('root','1','amd64')]['Depends']='virtual'
        with self.assertRaisesRegex(Stop,'VIRTUAL_UNRESOLVED'):run(f)
    def test_alternative_ambiguous(self):
        f=list(fixture());f[2][('root','1','amd64')]['Depends']='base | root'
        with self.assertRaisesRegex(Stop,'ALTERNATIVE_AMBIGUOUS'):run(f)
    def test_unambiguous_alternative(self):
        f=list(fixture());f[2][('root','1','amd64')]['Depends']='base | missing'
        self.assertEqual(run(f)['status'],'PASS')
    def test_cycle_is_finite(self):
        f=list(fixture());f[2][('base','1','amd64')]['Depends']='root'
        self.assertEqual(len(run(f)['transaction']['packages']),2)
    def test_predepends_checked(self):
        f=list(fixture());f[2][('root','1','amd64')]['Pre-Depends']='missing'
        with self.assertRaisesRegex(Stop,'VIRTUAL_UNRESOLVED'):run(f)
    def test_version_order(self):
        for a,bv in [('1~rc1','1'),('1','1-1'),('1-2','1-10'),('6.1','7:6.1'),('1.0a','1.0+')]:
            self.assertLess(t.version_compare(a,bv),0);self.assertGreater(t.version_compare(bv,a),0)
        self.assertEqual(t.version_compare('1.01','1.1'),0)
    def test_constraints(self):
        self.assertTrue(t.satisfies('2','>=','1'));self.assertFalse(t.satisfies('2','<<','1'))
    def test_inventory_half_installed_stop(self):
        with self.assertRaisesRegex(Stop,'TRANSACTION_INCOMPLETE'):
            t.inventory('Package: base\nVersion: 1\nArchitecture: amd64\nStatus: install ok unpacked\n')
    def test_duplicate_index_stop(self):
        text='Package: base\nVersion: 1\nArchitecture: amd64\nFilename: pool/main/a/base/base.deb\nSHA256: '+'a'*64+'\n'
        with self.assertRaisesRegex(Stop,'TRANSACTION_INCOMPLETE'):t.index_records(text+'\n'+text,'main')
    def test_index_hash_field_required(self):
        with self.assertRaisesRegex(Stop,'INDEX_FAILED'):
            t.index_records('Package: base\nVersion: 1\nArchitecture: amd64\nFilename: pool/main/base.deb\n','main')
    def test_handoff_immutable(self):
        r=run(fixture());self.assertTrue(t.verify_handoff(r,r['transaction_fingerprint'],'b'*64,'c'*64))
        changed=copy.deepcopy(r);changed['transaction']['packages'][0]['version']='2'
        with self.assertRaisesRegex(Stop,'TRANSACTION_INCOMPLETE'):
            t.verify_handoff(changed,r['transaction_fingerprint'],'b'*64,'c'*64)
    def test_handoff_never_accepts_upgrade(self):
        r=run(fixture());r['status']='BLOCKED'
        with self.assertRaisesRegex(Stop,'TRANSACTION_INCOMPLETE'):t.verify_handoff(r,r['transaction_fingerprint'],'b'*64,'c'*64)
    def test_real_root_evidence_exact_and_003_blocked(self):
        plan=json.loads(v.PLAN.read_text());old=v.validate_source(plan)
        self.assertEqual(old['status'],'BLOCKED_PACKAGE_DEPENDENCY_CLOSURE');self.assertEqual(len(plan['root_constraints']),10)
    def test_ppa_plan_rejected(self):
        plan=json.loads(v.PLAN.read_text());plan['source']['repository']='https://ppa.invalid'
        with self.assertRaisesRegex(Stop,'SOURCE_FAILED'):v.validate_source(plan)
    def test_updates_not_mixed(self):
        plan=json.loads(v.PLAN.read_text());plan['source']['pocket']='updates'
        with self.assertRaisesRegex(Stop,'SOURCE_FAILED'):v.validate_source(plan)
    def test_index_evidence_drift(self):
        plan=json.loads(v.PLAN.read_text());plan['signed_index']['inrelease_sha256']='0'*64
        with self.assertRaisesRegex(Stop,'INDEX_FAILED'):v.validate_source(plan)
    def test_no_exact_root_rejected(self):
        plan=json.loads(v.PLAN.read_text());plan['root_constraints']['ffmpeg']='latest'
        with self.assertRaisesRegex(Stop,'INDEX_FAILED'):v.validate_source(plan)
    def test_preparation_cannot_execute(self):
        with patch.object(v,'cloud_launch_guard',side_effect=AssertionError('guard must not run')):
            with self.assertRaisesRegex(Stop,'BLOCKED_OFFLINE_PREPARATION_ONLY'):v.execute(json.loads(v.PLAN.read_text()),{})
    def test_non_simulation_command_forbidden(self):
        with self.assertRaisesRegex(Stop,'SOURCE_FAILED'):v.command('simulation',['/usr/bin/apt-get','install','ffmpeg'])
    def test_safe_command_failure_drops_secret(self):
        with patch.object(v.subprocess,'run',side_effect=RuntimeError(SECRET)),patch.object(v,'safe_stage'):
            with self.assertRaises(Stop) as caught:
                v.command('simulation',['/usr/bin/apt-get','--simulate','--no-download','--no-install-recommends','install']+[n+'='+version for n,version in sorted(json.loads(v.PLAN.read_text())['root_constraints'].items())])
        self.assertEqual(str(caught.exception),'RUNTIME_APT_SIMULATION_FAILED')
    def test_subprocess_environment_no_token(self):
        class R:returncode=0;stdout=b''
        with patch.object(v.subprocess,'run',return_value=R()) as mocked,patch.object(v,'safe_stage'):
            v.command('signature',['/usr/bin/gpgv','--status-fd=1','--keyring','/tmp/plm-resolver-004-test/ubuntu-archive-keyring.gpg','/tmp/plm-resolver-004-test/InRelease'])
        env=mocked.call_args.kwargs['env'];self.assertNotIn('GH_TOKEN',env);self.assertEqual(env['LC_ALL'],'C')
    def test_no_redirect(self):
        with self.assertRaisesRegex(Stop,'SOURCE_FAILED'):v.NoRedirect().redirect_request(None,None,None,None,None,None)
    def test_binary_download_forbidden(self):
        with self.assertRaisesRegex(Stop,'SOURCE_FAILED'):v.metadata_get(t.REPO+'/pool/main/ffmpeg.deb',100,'a'*64,'index')
    def test_safe_stage_whitelist(self):
        with self.assertRaisesRegex(Stop,'TRANSACTION_INCOMPLETE'):v.safe_stage(SECRET)
    def test_consumed_and_unused_markers(self):
        for n in (PREFLIGHT_ID,b.PREFLIGHT_V2_ID):
            self.assertTrue((b.ROOT/b.marker_path(n)).is_file())
            with self.assertRaisesRegex(Stop,'IDENTITY_CONSUMED'):b.cloud_launch_guard({},n)
        for n in (b.PREFLIGHT_V3_ID,v.IDENTITY,RENDER_ID):self.assertFalse((b.ROOT/b.marker_path(n)).exists())
    def test_workflow_hard_disabled_read_only(self):
        text=(b.ROOT/b.SPEC[v.IDENTITY][1]).read_text()
        self.assertIn('if: false',text);self.assertIn('contents: read',text);self.assertIn('actions: read',text)
        self.assertNotIn('contents: write',text);self.assertNotIn('workflow_dispatch',text.split('#')[0])
    def test_003_evidence_unmodified(self):
        for path,sha in [('readiness/cloud-runtime-preflight-v3-package-plan.json','93d7b33e187fda831ac1e8c60ec80a62741659f64c1c760e37ab3a4c31f03a12'),
                         ('readiness/runtime-preflight-v3-package-index-evidence.json','977f40ca6856655b24ca2647a423f85c0d9db5a79c8acfec5e67180b6cd9ce44'),
                         ('.github/workflows/plm-cloud-runtime-preflight-v3-once.yml','8f859eb6ce788942c82b7a3a0764df082ebb354e0b5a0247470257a03bce1ffe')]:
            self.assertEqual(hashlib.sha256((b.ROOT/path).read_bytes()).hexdigest(),sha)
    def test_metadata_hash_mismatch(self):
        class Response:
            status=200
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def read(self,n):return b'wrong'
        with patch.object(v.urllib.request,'build_opener') as mocked,patch.object(v,'safe_stage'):
            mocked.return_value.open.return_value=Response()
            with self.assertRaisesRegex(Stop,'RUNTIME_APT_INDEX_FAILED'):
                v.metadata_get(t.REPO+'/dists/noble/InRelease',100,'a'*64,'index')
    def test_signature_command_failure_safe(self):
        with patch.object(v.subprocess,'run',side_effect=RuntimeError(SECRET)),patch.object(v,'safe_stage'):
            with self.assertRaisesRegex(Stop,'RUNTIME_APT_SIGNATURE_FAILED'):
                v.command('signature',['/usr/bin/gpgv','--status-fd=1','--keyring',
                    '/tmp/plm-resolver-004-test/ubuntu-archive-keyring.gpg','/tmp/plm-resolver-004-test/InRelease'])
    def test_command_option_injection_rejected(self):
        args=['/usr/bin/apt-get','--simulate','--no-download','--no-install-recommends','install']+[
            n+'='+version for n,version in sorted(json.loads(v.PLAN.read_text())['root_constraints'].items())]
        args+=['-o','APT::Get::Simulate=false']
        with self.assertRaisesRegex(Stop,'SOURCE_FAILED'):v.command('simulation',args)
    def test_private_sources_and_no_hooks(self):
        with tempfile.TemporaryDirectory(prefix='plm-resolver-004-',dir='/tmp') as directory:
            p=v.source_config(directory,b'private inventory',Path(directory)/'ubuntu-archive-keyring.gpg')
            text=p.read_text();self.assertIn('Dir::Etc::parts',text);self.assertIn('Dir::Etc::sourceparts',text)
            self.assertIn('Dir::Bin::dpkg "/bin/false"',text)
            self.assertNotIn('/etc/apt/sources.list',text);self.assertNotIn('/var/lib/dpkg/status',text)
            self.assertEqual((Path(directory)/'sources.list').read_text().split()[-3:],['noble','main','universe'])
    def test_004_marker_history_and_rerun(self):
        from test_branch_marker_once import setup
        k=setup(v.IDENTITY);self.assertTrue(b.launch_gate(**k)['consumed'])
        k['context']['run_attempt']=2
        with self.assertRaisesRegex(Stop,'RERUN'):b.launch_gate(**k)
        k=setup(v.IDENTITY);k['marker_history_page']=lambda page:[{'sha':b.BASELINE}] if page==1 else []
        with self.assertRaisesRegex(Stop,'CONSUMED_HISTORY'):b.launch_gate(**k)
    def test_004_marker_diff_and_parent(self):
        from test_branch_marker_once import setup
        k=setup(v.IDENTITY);k['commit']['files'].append({'filename':'readiness/other','status':'modified'})
        with self.assertRaisesRegex(Stop,'ONLY_ADDITION'):b.launch_gate(**k)
        k=setup(v.IDENTITY);k['parent_marker']={}
        with self.assertRaisesRegex(Stop,'CONSUMED_PARENT'):b.launch_gate(**k)
    def test_004_history_gap(self):
        from test_branch_marker_once import setup
        k=setup(v.IDENTITY);k['history_page']=lambda page:[]
        with self.assertRaisesRegex(Stop,'BLOCKED_HISTORY_CONTINUITY_LOST'):b.launch_gate(**k)
