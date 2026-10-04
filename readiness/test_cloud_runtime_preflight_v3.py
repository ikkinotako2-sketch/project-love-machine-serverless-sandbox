from oracle_bridge import require_guard
require_guard()
import copy
import json
from pathlib import Path
import unittest
import subprocess
import cloud_runtime_preflight_v3 as v
import branch_marker_once as b
from one_shot_executor import Stop, PREFLIGHT_ID, RENDER_ID

SECRET='secret-like token=ghp_TEST_NO_LOG'


def synthetic():
    """NOT Ubuntu evidence. Complete fake graph solely for no-effects invariants."""
    p=json.loads(v.PLAN_PATH.read_text())
    for root in p['packages']:
        root.update(sha256='a'*64,metadata_complete=True,depends=[],pre_depends=[])
    p['dependency_closure'].update(complete=True,entries=copy.deepcopy(p['packages']),
        base_image_inventory_verified=True,pre_dependencies_and_transitive_dependencies_verified=True,
        missing_direct_nodes=[],unresolved_alternatives=[])
    p['signed_index'].update(verified=True,inrelease_sha256='b'*64,package_indices=['SYNTHETIC'])
    return p


def fake(plan,fail=None,changes=None):
    nodes={r['name']:r for r in plan['dependency_closure']['entries']}
    receipts={name:{k:p[k] for k in ('version','architecture','filename','sha256','repository')} for name,p in nodes.items()}
    data={'marker_guard':{'identity':v.IDENTITY,'consumed':True},'runner_check':'github-hosted ubuntu-24.04 amd64',
      'python_version':'3.12.15','package_download':receipts,'package_versions':{name:p['version'] for name,p in nodes.items()},
      'ffmpeg_version':'6.1.1','ffprobe_version':'6.1.1'}
    data.update(changes or {})
    logs=[];calls=[]
    def effects(stage,*args):
        calls.append((stage,args))
        if stage==fail:raise subprocess.CalledProcessError(9,SECRET,output=SECRET,stderr=SECRET)
        return copy.deepcopy(data.get(stage,True))
    return v.OfflineOracle(plan,effects,log=lambda s,**kw:logs.append((s,kw))),calls,logs


class V3Tests(unittest.TestCase):
    def test_real_plan_blocked_before_install(self):
        p=json.loads(v.PLAN_PATH.read_text());runner,calls,logs=fake(p)
        with self.assertRaisesRegex(Stop,'BLOCKED_PACKAGE_DEPENDENCY_CLOSURE'):runner.execute()
        self.assertEqual([s for s,a in calls],['marker_guard','runner_check','python_version'])
    def test_synthetic_complete_order_and_no_actual_operations(self):
        p=synthetic();runner,calls,logs=fake(p);result=runner.execute()
        self.assertEqual(result['actual_operations'],0)
        stages=[s for s,a in calls]
        self.assertLess(stages.index('package_install'),stages.index('ffmpeg_version'))
        self.assertLess(stages.index('font_query'),stages.index('docker_pull'))
        args=next(a[0] for s,a in calls if s=='package_install')
        self.assertIn('--no-install-recommends',args)
        self.assertTrue(all('=' in a for a in args[6:]))
    def test_no_exact_version_rejected(self):
        p=synthetic();p['packages'][0]['version']=None
        with self.assertRaisesRegex(Stop,'VERSION_MISMATCH'):v.install_arguments(p)
    def test_ppa_rejected(self):
        p=synthetic();p['packages'][0]['repository']='https://ppa.launchpadcontent.net/example'
        with self.assertRaisesRegex(Stop,'APT_INDEX_FAILED'):v.validate_plan(p)
    def test_thirdparty_repo_rejected(self):
        p=synthetic();p['official_repositories']=['https://example.com/ubuntu']
        with self.assertRaisesRegex(Stop,'APT_INDEX_FAILED'):v.validate_plan(p)
    def test_latest_fallback_rejected(self):
        p=synthetic();p['latest_fallback']=True
        with self.assertRaisesRegex(Stop,'APT_INDEX_FAILED'):v.validate_plan(p)
    def test_sha_mismatch_stop(self):
        p=synthetic();runner,calls,logs=fake(p)
        old=runner.effects
        def effect(s,*args):
            val=old(s,*args)
            if s=='package_download':val['ffmpeg']['sha256']='c'*64
            return val
        runner.effects=effect
        with self.assertRaisesRegex(Stop,'PACKAGE_HASH_FAILED'):runner.execute()
        self.assertNotIn('package_install',[s for s,a in calls])
    def test_missing_dependency_stop(self):
        p=synthetic();p['dependency_closure']['entries'][0]['depends']=[{'name':'missing','selected_version':'1','constraint':'>=1','constraint_verified':True}]
        with self.assertRaisesRegex(Stop,'CLOSURE_MISMATCH'):v.validate_plan(p)
    def test_one_package_version_drift_stop(self):
        p=synthetic();p['dependency_closure']['entries'][0]['version']='7:6.1.1-3ubuntu6'
        with self.assertRaisesRegex(Stop,'VERSION_MISMATCH'):v.validate_plan(p)
    def test_install_failure_docker_zero_and_secret_hidden(self):
        p=synthetic();runner,calls,logs=fake(p,fail='package_install')
        with self.assertRaisesRegex(Stop,'PACKAGE_INSTALL_FAILED') as e:runner.execute()
        self.assertNotIn('docker_pull',[s for s,a in calls]);self.assertNotIn(SECRET,str(e.exception)+str(logs))
    def test_no_retry_or_resume(self):
        p=synthetic();runner,calls,logs=fake(p,fail='apt_index')
        with self.assertRaises(Stop):runner.execute()
        n=len(calls)
        with self.assertRaisesRegex(Stop,'ALREADY_CONSUMED'):runner.execute()
        self.assertEqual(len(calls),n)
    def test_001_002_consumed(self):
        for identity,code in [(PREFLIGHT_ID,'IDENTITY_CONSUMED_001'),(b.PREFLIGHT_V2_ID,'IDENTITY_CONSUMED_002')]:
            with self.assertRaisesRegex(Stop,code):b.cloud_launch_guard({},identity=identity,read=lambda *a:self.fail('read'))
    def test_marker_independence_and_absence(self):
        paths=[b.marker_path(i) for i in (PREFLIGHT_ID,b.PREFLIGHT_V2_ID,v.IDENTITY,RENDER_ID)]
        self.assertEqual(len(set(paths)),4)
        for path in paths[:2]:self.assertTrue((v.ROOT/path).is_file())
        for path in paths[2:]:self.assertFalse((v.ROOT/path).exists())
    def test_workflow_harddisabled_readonly_no_apt_exec(self):
        s=(v.ROOT/b.SPEC[v.IDENTITY][1]).read_text()
        self.assertIn('if: false',s);self.assertIn('contents: read',s);self.assertIn('actions: read',s)
        self.assertNotIn(': write',s);self.assertNotIn('apt-get',s);self.assertNotIn('upload-artifact@',s)
    def test_all_002_codes_retained(self):
        for stage,code in v.v2.CODES.items():self.assertEqual(v.CODES[stage],code)
    def test_all_package_codes(self):
        expected={'RUNTIME_APT_INDEX_FAILED','RUNTIME_PACKAGE_DOWNLOAD_FAILED','RUNTIME_PACKAGE_HASH_FAILED',
          'RUNTIME_PACKAGE_INSTALL_FAILED','RUNTIME_PACKAGE_VERSION_MISMATCH','RUNTIME_DEPENDENCY_CLOSURE_MISMATCH'}
        self.assertEqual(set(v.APT_CODES.values()),expected)


def stage_failure(stage,value=None):
    def test(self):
        p=synthetic();runner,calls,logs=fake(p,fail=stage if value is None else None,changes={} if value is None else {stage:value})
        with self.assertRaisesRegex(Stop,v.CODES[stage]):runner.execute()
        self.assertNotIn('docker_pull',[s for s,a in calls])
        self.assertNotIn(SECRET,str(logs))
    return test
for stage in ('apt_index','package_download','package_hash','package_install','package_versions','dependency_closure'):
    setattr(V3Tests,'test_failure_'+stage,stage_failure(stage))
for stage,value in [('ffmpeg_version','7.1'),('ffprobe_version','7.1'),('filter_query',False),('encoder_query',False),('font_query',False)]:
    setattr(V3Tests,'test_post_install_mismatch_'+stage,stage_failure(stage,value))
