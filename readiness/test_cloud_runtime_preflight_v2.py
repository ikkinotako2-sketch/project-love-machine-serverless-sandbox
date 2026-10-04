from oracle_bridge import require_guard
require_guard()
import contextlib
import io
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import cloud_runtime_preflight_v2 as v
import branch_marker_once as b
from one_shot_executor import Stop, IMAGE, FILTERS, ENCODERS, PREFLIGHT_ID, RENDER_ID
from test_one_shot_executor import registry, speakers

SECRET='secret-like token=ghp_TEST_DO_NOT_PRINT provider_body'
ENV={'GITHUB_ACTIONS':'true','RUNNER_ENVIRONMENT':'github-hosted','RUNNER_OS':'Linux','RUNNER_ARCH':'X64'}
OBS={'python':'3.12.15','ffmpeg':'6.1.1','ffprobe':'6.1.1','packages_match':True,
     'filters_match':True,'encoders_match':True,'font_match':True,'docker_available':True}


def outputs():
    versions={k:'7:6.1.1-3ubuntu5' for k in v.PACKAGES}
    versions.update({'fonts-noto-cjk':'1:20230817+repack1-3','libx264-164':'2:0.164.3108+git31e19f9-1','libass9':'1:0.17.1-2build1'})
    return {'python_version':'Python 3.12.15','ffmpeg_version':'ffmpeg version 6.1.1',
      'ffprobe_version':'ffprobe version 6.1.1','package_query':'\n'.join(k+'\t'+val for k,val in versions.items()),
      'filter_query':'\n'.join(' ... '+f+' V->V' for f in FILTERS),
      'encoder_query':'\n'.join(' V..... '+f+' encoder' for f in ENCODERS),
      'font_query':'Noto Sans CJK JP\n/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
      'docker_version':'28.0.4','docker_inspect':json.dumps([{'Os':'linux','Architecture':'amd64','RepoDigests':[IMAGE]}])}


def fake(fail=None, changes=None):
    data=outputs();data.update(changes or {});calls=[];logs=[]
    def raw(command,**kw):
        stage=next(s for s,c in v.COMMANDS.items() if list(c)==command);calls.append(stage)
        if stage==fail or isinstance(fail,set) and stage in fail:
            raise subprocess.CalledProcessError(7,command,output=SECRET,stderr=SECRET)
        return SimpleNamespace(stdout=data.get(stage,'ok'),returncode=0,stderr=SECRET)
    def log(stage,**kw):logs.append((stage,kw))
    def run(stage,**kw):return v.execute(stage,runner=raw,log=log,**kw)
    return run,calls,logs,log


def receipt():return {'identity':v.IDENTITY,'scope':'AUTOMATION_MONOTONIC_CONSUMPTION','consumed':True,'run_id':101}

def read(url):return registry() if url==v.old.REGISTRY_URL else '0.25.2' if url==v.old.VOICE_URLS['version'] else speakers()


class V2Tests(unittest.TestCase):
    def test_all_prerequisites_then_pull(self):
        run,calls,logs,log=fake()
        with patch.object(v.old.platform,'freedesktop_os_release',return_value={'ID':'ubuntu','VERSION_ID':'24.04'}):
            result=v.preflight(json.loads(v.POLICY_PATH.read_text()),ENV,guard=receipt,run=run,read=read,
                observe=lambda env,runner,logger:v.runtime_gate(env,runner,logger,font_exists=lambda p:True),log=log)
        self.assertEqual(calls[:8],list(v.COMMANDS)[:8]);self.assertEqual(calls[8],'docker_pull')
        self.assertEqual(result['speaker_match'],True)
        for key in ('synthesis','encode','mp4','artifact_upload','user_pc_execution'):self.assertEqual(result[key],0)
    def test_cleanup_does_not_mask_primary(self):
        run,calls,logs,log=fake(fail={'docker_start','docker_cleanup'})
        with self.assertRaisesRegex(Stop,'RUNTIME_DOCKER_START_FAILED'):
            v.preflight(json.loads(v.POLICY_PATH.read_text()),ENV,guard=receipt,run=run,read=read,observe=lambda *a:OBS,log=log)
        self.assertEqual(calls.count('docker_start'),1);self.assertEqual(calls.count('docker_cleanup'),1)
        self.assertIn(('docker_cleanup',{'result':'failed','return_code':7}),logs)
    def test_unknown_stderr_not_logged(self):
        run,calls,logs,log=fake(fail='ffmpeg_version')
        with self.assertRaisesRegex(Stop,'RUNTIME_FFMPEG_VERSION_FAILED') as e:run('ffmpeg_version')
        self.assertNotIn(SECRET,json.dumps(logs)+str(e.exception))
        self.assertEqual(logs[0],('ffmpeg_version',{}))
    def test_emit_safe_whitelist(self):
        output=io.StringIO()
        with contextlib.redirect_stdout(output):v.emit('ffmpeg_version',result='failed',return_code=7)
        self.assertEqual(output.getvalue(),'stage=ffmpeg_version result=failed return_code=7\n')
        with self.assertRaises(Stop):v.emit(SECRET)
    def test_timeout_maps_safe_and_no_retry(self):
        calls=[];logs=[]
        def raw(*args,**kw):calls.append(1);raise subprocess.TimeoutExpired(SECRET,30,output=SECRET,stderr=SECRET)
        with self.assertRaisesRegex(Stop,'RUNTIME_DOCKER_PULL_FAILED') as e:
            v.execute('docker_pull',runner=raw,log=lambda *a,**k:logs.append((a,k)))
        self.assertEqual(len(calls),1);self.assertNotIn(SECRET,str(e.exception)+str(logs))
    def test_stage_start_precedes_spawn(self):
        events=[]
        def raw(*a,**k):events.append('spawn');raise FileNotFoundError(SECRET)
        with self.assertRaises(Stop):v.execute('font_query',runner=raw,log=lambda s,**kw:events.append(s))
        self.assertEqual(events[:2],['font_query','spawn'])
    def test_no_arbitrary_command_or_credentials(self):
        with self.assertRaisesRegex(Stop,'RUNTIME_STAGE_INVALID'):v.execute(SECRET)
        for cmd in v.COMMANDS.values():self.assertNotIn('token',str(cmd).lower())
    def test_docker_inspect_mismatch(self):
        run,calls,logs,log=fake(changes={'docker_inspect':'[{"Os":"linux","Architecture":"arm64"}]'})
        with self.assertRaisesRegex(Stop,'RUNTIME_DOCKER_INSPECT_FAILED'):
            v.preflight(json.loads(v.POLICY_PATH.read_text()),ENV,guard=receipt,run=run,read=read,observe=lambda *a:OBS,log=log)
        self.assertNotIn('docker_start',calls)
    def test_cleanup_failure_only(self):
        run,calls,logs,log=fake(fail='docker_cleanup')
        with self.assertRaisesRegex(Stop,'RUNTIME_DOCKER_CLEANUP_FAILED'):
            v.preflight(json.loads(v.POLICY_PATH.read_text()),ENV,guard=receipt,run=run,read=read,observe=lambda *a:OBS,log=log)
    def test_guard_failure_zero_effects(self):
        run,calls,logs,log=fake()
        def guard():raise Stop('BLOCKED_HISTORY_CONTINUITY_LOST')
        with self.assertRaises(Stop):v.preflight(json.loads(v.POLICY_PATH.read_text()),ENV,guard=guard,run=run,read=read,log=log)
        self.assertEqual(calls,[])
    def test_001_always_consumed_before_network(self):
        with self.assertRaisesRegex(Stop,'IDENTITY_CONSUMED_001'):b.cloud_launch_guard({},identity=PREFLIGHT_ID,read=lambda *a: self.fail('API'))
    def test_001_marker_preserved_and_002_render_absent(self):
        root=v.ROOT
        marker=json.loads((root/b.marker_path(PREFLIGHT_ID)).read_text())
        self.assertEqual(marker['approved_parent_sha'],'4c9fb5130ef5dc7e99e6e4ae777a6ef3ebf36ac0')
        for identity in (v.IDENTITY,RENDER_ID):self.assertFalse((root/b.marker_path(identity)).exists())
        self.assertEqual(len({b.marker_path(i) for i in (PREFLIGHT_ID,v.IDENTITY,RENDER_ID)}),3)
    def test_new_workflow_exact_scope_readonly(self):
        s=(v.ROOT/b.SPEC[v.IDENTITY][1]).read_text()
        self.assertIn("paths: ['"+b.marker_path(v.IDENTITY)+"']",s)
        self.assertIn('contents: read',s);self.assertIn('actions: read',s);self.assertNotIn(': write',s)
        self.assertNotIn('upload-artifact@',s);self.assertNotIn('apt-get',s)
    def test_install_not_approved(self):
        p=json.loads(v.POLICY_PATH.read_text());p['package_install_approved']=True
        with self.assertRaisesRegex(Stop,'POLICY_DRIFT'):v.preflight(p,{},guard=lambda:self.fail('guard'))
    def test_no_generation_routes(self):
        for route in ('audio_query','synthesis'):
            with self.assertRaises(Stop):v.old.get_json('http://127.0.0.1:50021/'+route)


def command_failure(stage):
    def test(self):
        run,calls,logs,log=fake(fail=stage)
        with self.assertRaisesRegex(Stop,'^'+v.CODES[stage]+'$'):run(stage)
        self.assertEqual(calls,[stage]);self.assertNotIn(SECRET,str(logs))
    return test
for stage in v.COMMANDS:setattr(V2Tests,'test_command_failure_'+stage,command_failure(stage))


def observation_failure(stage,value):
    def test(self):
        run,calls,logs,log=fake(changes={stage:value})
        with patch.object(v.old.platform,'freedesktop_os_release',return_value={'ID':'ubuntu','VERSION_ID':'24.04'}):
            with self.assertRaisesRegex(Stop,'^'+v.CODES[stage]+'$'):
                v.preflight(json.loads(v.POLICY_PATH.read_text()),ENV,guard=receipt,run=run,read=read,
                  observe=lambda env,runner,logger:v.runtime_gate(env,runner,logger,font_exists=lambda p:True),log=log)
        self.assertNotIn('docker_pull',calls)
    return test
for stage,value in [('python_version','Python 3.12.14'),('ffmpeg_version','missing'),('ffprobe_version','missing'),('package_query',''),('filter_query',''),('encoder_query',''),('font_query','fallback'),('docker_version','')]:
    setattr(V2Tests,'test_mismatch_'+stage,observation_failure(stage,value))


def get_failure(stage):
    def test(self):
        events=[]
        def fail(url):events.append(url);raise RuntimeError(SECRET)
        with self.assertRaisesRegex(Stop,'^'+v.CODES[stage]+'$') as e:
            v.get(stage,read=fail,log=lambda *a,**kw:None)
        self.assertEqual(len(events),1);self.assertNotIn(SECRET,str(e.exception))
    return test
for stage in ('engine_version_get','speakers_get','registry_get'):setattr(V2Tests,'test_get_failure_'+stage,get_failure(stage))
