from oracle_bridge import require_guard
require_guard()
import ast
import copy
import json
import types
import unittest
from pathlib import Path
from fractions import Fraction
from one_shot_render_preflight import validate_offline,require_runtime_ready,load,ROOT,RENDER_ID

SOURCES=load('readiness/one-shot-render-sources.json')['sources']
PLAN=load('readiness/one-shot-render-plan.json')
PAYLOAD=load('readiness/manual_fixture/render-payload.canonical.json')


def functions(path,names,scope):
    tree=ast.parse(SOURCES[path]);selected=[x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name in names]
    if len(selected)!=len(names):raise ValueError('function_inventory_drift')
    exec(compile(ast.Module(body=selected,type_ignores=[]),path,'exec'),scope)
    return scope


def command_fixture():
    commands=[];subtitle_text={}
    class FakePath:
        def __init__(self,path):self.path=path
        def write_text(self,text,encoding):
            if self.path!='captions.ass':raise ValueError('unexpected_subtitle_path')
            subtitle_text[self.path]=text
    tree=ast.parse(SOURCES['render-worker/ffmpeg_builder.py'])
    constants={x.targets[0].id:ast.literal_eval(x.value)for x in tree.body if isinstance(x,ast.Assign) and isinstance(x.targets[0],ast.Name) and x.targets[0].id in ('DEFAULT_WIDTH','DEFAULT_HEIGHT','DEFAULT_FPS','PALETTES')}
    def record(command):commands.append(command);return types.SimpleNamespace(stderr='')
    scope={'json':json,'hashlib':__import__('hashlib'),'Path':FakePath,'os':types.SimpleNamespace(path=types.SimpleNamespace(isdir=lambda p:False,exists=lambda p:True,getsize=lambda p:20000)),
           '_probe_duration':lambda p:24.0,'_run':record,**constants}
    names=('_ass_time','_escape_ass','_caption_text','_write_ass','_asset_path','_captions_with_scene_emphasis','_fit_captions_to_audio','_visual_filters','_segments','build_video')
    functions('render-worker/ffmpeg_builder.py',names,scope)
    scope['build_video'](copy.deepcopy(PAYLOAD),audio_path='.preparation/render-output/'+RENDER_ID+'/audio.wav',output_path='.preparation/render-output/'+RENDER_ID+'/short.mp4')
    return commands,subtitle_text


def quality_fixture(change=None):
    data={'size':20000,'exists':True,'subtitle':'Dialogue: 0,test','luma':30,'mean_db':-20,
          'metadata':{'streams':[{'codec_type':'video','width':1080,'height':1920,'avg_frame_rate':'30/1','codec_name':'h264'},{'codec_type':'audio','codec_name':'aac'}],'format':{'duration':'24'}}}
    if change:change(data)
    calls=[]
    class FakePath:
        def __init__(self,path):pass
        def with_name(self,name):return self
        def is_file(self):return bool(data['subtitle'])
        def read_text(self,encoding):return data['subtitle']
    def record(cmd):
        calls.append(cmd)
        if cmd[0]=='ffprobe':return types.SimpleNamespace(stdout=json.dumps(data['metadata']),stderr='')
        if '-vf' in cmd:return types.SimpleNamespace(stdout='lavfi.signalstats.YAVG='+str(data['luma']),stderr='')
        return types.SimpleNamespace(stdout='',stderr='mean_volume: '+str(data['mean_db'])+' dB')
    scope={'json':json,'re':__import__('re'),'Fraction':Fraction,'Path':FakePath,
           'os':types.SimpleNamespace(path=types.SimpleNamespace(exists=lambda p:data['exists'],getsize=lambda p:data['size'])),'_run':record}
    functions('render-worker/quality_gate.py',('validate_video',),scope)
    return scope['validate_video']('workspace-output/short.mp4'),calls

class RenderPreparationTests(unittest.TestCase):
    def test_fixed_sources_fixture_and_safe_env_validate_offline(self):
        self.assertEqual(validate_offline()['offline_validation'],'PASS')
    def test_runtime_missing_digest_is_mandatory_stop(self):
        with self.assertRaisesRegex(ValueError,'BLOCKED_RENDER_RUNTIME_UNPINNED'):require_runtime_ready(PLAN)
    def test_version_tag_alone_or_unverified_digest_is_not_a_pin(self):
        for digest in ('0.25.2','cpu-latest','sha256:'+'a'*64,None):
            p=copy.deepcopy(PLAN);p['runtime']['voicevox_image_digest']=digest
            with self.assertRaisesRegex(ValueError,'BLOCKED_RENDER_RUNTIME_UNPINNED'):require_runtime_ready(p)
    def test_even_forged_runtime_gate_cannot_execute_renderer(self):
        p=copy.deepcopy(PLAN);p['runtime']['voicevox_image_digest']='sha256:'+'a'*64;p['runtime']['voicevox_image_digest_verified']=True;p['blockers']=[]
        with self.assertRaisesRegex(ValueError,'EXECUTOR_ABSENT'):require_runtime_ready(p)
    def test_drifted_fixture_refuses_before_runtime(self):
        from manual_fixture_boundary import normalize_manual,digest
        raw=json.loads((ROOT/'readiness/manual_fixture/manual-japanese-script-fixture-v1.json').read_text());raw['output']['narration']+='変更'
        self.assertNotEqual(normalize_manual(json.dumps(raw))['script_sha256'],PLAN['fixture_sha256']['script_sha256'])
    def test_import_dependency_inventory_is_stdlib_or_exact_local_modules(self):
        deps=set()
        for path,source in SOURCES.items():
            if not path.endswith('.py'):continue
            compile(source,path,'exec')
            for node in ast.walk(ast.parse(source)):
                if isinstance(node,ast.Import):deps.update(x.name for x in node.names)
                elif isinstance(node,ast.ImportFrom):deps.add(node.module)
        self.assertEqual(deps,{'json','os','traceback','hashlib','pathlib','subprocess','re','fractions','urllib.parse','urllib.request','ffmpeg_builder','quality_gate','voicevox'})
    def test_ffmpeg_command_is_constructed_without_process_or_encode(self):
        commands,_=command_fixture();self.assertEqual(len(commands),1);cmd=commands[0]
        self.assertEqual(cmd[0],'ffmpeg');self.assertEqual(cmd[cmd.index('-r')+1],'30')
        self.assertEqual(cmd[cmd.index('-c:v')+1],'libx264');self.assertEqual(cmd[cmd.index('-c:a')+1],'aac')
        self.assertEqual(cmd[-1],'.preparation/render-output/'+RENDER_ID+'/short.mp4')
        self.assertEqual(cmd.count('-i'),1);self.assertFalse(any('://' in str(x)for x in cmd))
        self.assertIn('crop=1080:1920',cmd[cmd.index('-filter_complex')+1])
    def test_ass_subtitles_exist_in_memory_only_and_caption_order_preserved(self):
        _,text=command_fixture();ass=text['captions.ass'];self.assertIn('PlayResX: 1080',ass);self.assertIn('PlayResY: 1920',ass)
        self.assertEqual(ass.count('Dialogue:'),3)
        positions=[ass.index(s['caption'].replace('一つ',r'{\c&H00D7FF&\fs78}一つ{\c&HFFFFFF&\fs68}').replace('置き場所',r'{\c&H00D7FF&\fs78}置き場所{\c&HFFFFFF&\fs68}').replace('余白',r'{\c&H00D7FF&\fs78}余白{\c&HFFFFFF&\fs68}')) for s in PAYLOAD['scenes']]
        self.assertEqual(positions,sorted(positions));self.assertIn('0:00:24.00',ass)
    def test_output_paths_and_checkout_are_fixed_workspace_children(self):
        for path in (PLAN['checkout_destination'],'.preparation/render-output/'+RENDER_ID+'/short.mp4'):
            self.assertFalse(Path(path).is_absolute());self.assertNotIn('..',Path(path).parts)
            self.assertTrue((ROOT/path).resolve().is_relative_to(ROOT))
    def test_no_audio_asset_provider_or_secret_in_env(self):
        env=load('readiness/one-shot-render-env.json');self.assertEqual(env['INPUT_SPEAKER'],'1');self.assertNotIn('asset',json.loads(env['INPUT_BGM_JSON']))
        for k,v in env.items():self.assertNotIn('TOKEN',k);self.assertNotIn('SECRET',k);self.assertNotIn('https://',v)
    def test_standard_runner_and_artifact_size_retention_are_bounded(self):
        self.assertEqual(PLAN['runner'],'ubuntu-24.04');self.assertFalse(PLAN['larger_runner']);self.assertTrue(PLAN['repository_public'])
        a=PLAN['artifact'];self.assertEqual(a['retention_days'],1);self.assertEqual(a['files'],['short.mp4','payload_snapshot.json','render-result.json'])
        self.assertFalse(a['raw_audio_uploaded']);self.assertFalse(PLAN['artifact_storage_zero_cost_verified'])
    def test_failures_consume_identity_with_no_retry_or_resend(self):
        for k in ('retry','resend','fallback','second_render','automatic_rollback'):self.assertEqual(PLAN[k],0)
        self.assertEqual(PLAN['run_attempt_max'],1);self.assertEqual(PLAN['prior_execution_required'],0);self.assertEqual(PLAN['reconciliation_max_sets'],1)
        self.assertIn('CONSUMED_ON_FIRST',PLAN['consumption'])
    def test_quality_exact_code_accepts_fixture_metadata(self):
        report,calls=quality_fixture();self.assertTrue(report['ok']);self.assertEqual(len(calls),3)
        self.assertEqual((report['width'],report['height'],report['fps']),(1080,1920,30))
    def test_quality_code_inclusive_boundaries_are_not_misreported(self):
        def change(d):d['size']=10000;d['luma']=25;d['mean_db']=-38;d['metadata']['format']['duration']='0.5'
        self.assertTrue(quality_fixture(change)[0]['ok'])
        self.assertEqual(PLAN['quality_gate']['one_shot_file_size_min_exclusive'],10000)
    def test_candidate_workflow_explicitly_checks_out_production_fixed_commit(self):
        text=(ROOT/'.github/workflows/plm-manual-fixture-render-prepared-once.yml').read_text()
        self.assertIn('ref: '+PLAN['production_sha'],text);self.assertIn('path: '+PLAN['checkout_destination'],text)
        self.assertIn('if: false',text);self.assertIn("allow: 'false'",text);self.assertIn("execution_approved: 'false'",text)
        commands='\n'.join(line for line in text.splitlines() if not line.lstrip().startswith('#'))
        self.assertNotIn('cpu-latest',commands);self.assertNotIn('docker run',commands);self.assertNotIn('/synthesis',commands)
    def test_speaker_is_not_substituted_or_relabelled(self):
        self.assertEqual(PLAN['speaker']['id'],1);self.assertEqual(PLAN['speaker']['expected_character'],'ずんだもん');self.assertEqual(PLAN['speaker']['expected_style'],'あまあま')
        self.assertFalse(PLAN['speaker']['style_change_allowed']);self.assertEqual(PLAN['speaker']['credit'],'VOICEVOX:ずんだもん')
    def test_operations_remain_zero(self):self.assertTrue(all(v==0 for v in PLAN['operations'].values()))


def quality_reject(change):
    def run(self):
        with self.assertRaises((ValueError,FileNotFoundError)):quality_fixture(change)
    return run
for name,change in {
 'missing_file':lambda d:d.update(exists=False),'too_small':lambda d:d.update(size=9999),
 'wrong_resolution':lambda d:d['metadata']['streams'][0].update(width=720),
 'wrong_fps':lambda d:d['metadata']['streams'][0].update(avg_frame_rate='2997/100'),
 'missing_audio':lambda d:d['metadata'].update(streams=d['metadata']['streams'][:1]),
 'duration_over':lambda d:d['metadata']['format'].update(duration='181'),
 'duration_under':lambda d:d['metadata']['format'].update(duration='0.4'),
 'missing_subtitle':lambda d:d.update(subtitle=''),
 'black_frame':lambda d:d.update(luma=24),
 'inaudible_audio':lambda d:d.update(mean_db=-39)
}.items():setattr(RenderPreparationTests,'test_quality_reject_'+name,quality_reject(change))
