"""Fixed 002 candidate. Safe diagnostics; no generation/install/upload adapter.

001 code and receipt are preserved as forensic evidence. Every effect is behind
the primary 002 marker guard. Offline tests inject effects; no import effects.
"""
import json
import os
import re
import subprocess
from pathlib import Path
import cloud_runtime_preflight as old
from branch_marker_once import cloud_launch_guard
from one_shot_executor import Stop, need, FILTERS, ENCODERS, IMAGE, verify_speakers

ROOT = Path(__file__).resolve().parents[1]
IDENTITY = 'manual-fixture-runtime-preflight-20261004-002'
POLICY_PATH = ROOT/'readiness/cloud-runtime-preflight-v2-policy.json'
CONTAINER = 'plm-runtime-preflight-20261004-002'
PACKAGES = ('ffmpeg','fonts-noto-cjk','libavcodec60','libavfilter9',
            'libavformat60','libavutil58','libswresample4','libswscale7','libx264-164','libass9')
COMMANDS = {
    'python_version': ('python','--version'),
    'ffmpeg_version': ('ffmpeg','-version'),
    'ffprobe_version': ('ffprobe','-version'),
    'package_query': ('dpkg-query','-W','-f=${binary:Package}\t${Version}\n',*PACKAGES),
    'filter_query': ('ffmpeg','-hide_banner','-filters'),
    'encoder_query': ('ffmpeg','-hide_banner','-encoders'),
    'font_query': ('fc-match','-f','%{family}\n%{file}\n','Noto Sans CJK JP'),
    'docker_version': ('docker','version','--format','{{.Server.Version}}'),
    'docker_pull': ('docker','pull','--platform','linux/amd64',IMAGE),
    'docker_inspect': ('docker','image','inspect',IMAGE),
    'docker_start': ('docker','run','-d','--rm','--name',CONTAINER,'--platform','linux/amd64',
                     '-e','VV_DISABLE_MUTABLE_API=1','-p','127.0.0.1:50021:50021',IMAGE),
    'startup_wait': ('timeout','30','bash','-c','sleep 15'),
    'docker_cleanup': ('docker','rm','-f',CONTAINER),
}
CODES = {s:'RUNTIME_'+s.upper()+'_FAILED' for s in COMMANDS}
CODES.update(engine_version_get='RUNTIME_ENGINE_VERSION_GET_FAILED',
             speakers_get='RUNTIME_SPEAKERS_GET_FAILED', registry_get='RUNTIME_REGISTRY_GET_FAILED')


def emit(stage, *, result=None, return_code=None):
    """Fixed labels/enums only. Never command, exception, provider body or output."""
    need(stage in CODES or stage == 'runtime_gate', 'DIAGNOSTIC_STAGE_INVALID')
    need(result in (None,'pass','failed','mismatch'), 'DIAGNOSTIC_RESULT_INVALID')
    need(return_code is None or type(return_code) is int and -255 <= return_code <= 255,
         'DIAGNOSTIC_RETURN_CODE_INVALID')
    line = 'stage='+stage
    if result is not None: line += ' result='+result
    if return_code is not None: line += ' return_code='+str(return_code)
    print(line, flush=True)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a',encoding='utf-8') as out:
            out.write(line+'\n')


def failure(stage, error=None, log=emit, mismatch=False):
    rc = getattr(error,'returncode',None)
    rc = rc if type(rc) is int and -255 <= rc <= 255 else None
    log(stage,result='mismatch' if mismatch else 'failed',return_code=rc)
    raise Stop(CODES[stage]) from None


def execute(stage, *, timeout=30, runner=None, log=emit):
    need(stage in COMMANDS, 'RUNTIME_STAGE_INVALID')
    log(stage)  # flushed before spawn, so timeout/kill leaves last reached label
    try:
        result = (runner or subprocess.run)(list(COMMANDS[stage]),check=True,
                    capture_output=True,text=True,timeout=timeout)
        if result.returncode != 0:
            failure(stage,result,log)
        need(isinstance(result.stdout,str), CODES[stage])
    except Exception as error:
        failure(stage,error,log)
    log(stage,result='pass',return_code=0)
    return result.stdout  # internal only, never logged/saved


def get(stage, *, read=old.get_json, log=emit):
    urls = {'registry_get':old.REGISTRY_URL, 'engine_version_get':old.VOICE_URLS['version'],
            'speakers_get':old.VOICE_URLS['speakers']}
    need(stage in urls,'RUNTIME_STAGE_INVALID')
    log(stage)
    try: value = read(urls[stage])
    except Exception: failure(stage,log=log)
    return value


def checked(stage, condition, log=emit):
    if not condition: failure(stage,log=log,mismatch=True)
    log(stage,result='pass')


def runtime_gate(env, run=execute, log=emit, font_exists=lambda p:Path(p).is_file()):
    need(env.get('GITHUB_ACTIONS') == 'true' and env.get('RUNNER_ENVIRONMENT') == 'github-hosted'
         and env.get('RUNNER_OS') == 'Linux' and env.get('RUNNER_ARCH') == 'X64',
         'CLOUD_RUNNER_REQUIRED')
    need(old.platform.system() == 'Linux' and old.platform.machine() in ('x86_64','AMD64'),
         'CLOUD_RUNNER_REQUIRED')
    release = old.platform.freedesktop_os_release()
    need(release.get('ID') == 'ubuntu' and release.get('VERSION_ID') == '24.04',
         'CLOUD_RUNNER_REQUIRED')
    py = run('python_version').strip().removeprefix('Python ')
    checked('python_version',py == '3.12.15',log)
    versions = {}
    for stage, name in (('ffmpeg_version','ffmpeg'),('ffprobe_version','ffprobe')):
        match = re.search(r'^'+name+r' version ([0-9.]+)',run(stage))
        checked(stage,match is not None and match.group(1) == '6.1.1',log)
        versions[name] = match.group(1)
    try:
        packages = dict(line.split('\t',1) for line in run('package_query').strip().splitlines())
        versions_by_name = {k.split(':')[0]:v for k,v in packages.items()}
    except Exception: failure('package_query',log=log)
    expected = {k:'7:6.1.1-3ubuntu5' for k in PACKAGES if k.startswith('libav') or k.startswith('libsw')}
    expected.update(ffmpeg='7:6.1.1-3ubuntu5', **{'fonts-noto-cjk':'1:20230817+repack1-3',
                    'libx264-164':'2:0.164.3108+git31e19f9-1','libass9':'1:0.17.1-2build1'})
    checked('package_query',all(versions_by_name.get(k)==v for k,v in expected.items()),log)
    filters = set(re.findall(r'^\s*[TSC.]{3}\s+(\w+)\s',run('filter_query'),re.M))
    checked('filter_query',FILTERS.issubset(filters),log)
    encoders = set(re.findall(r'^\s*[VAS][A-Z.]{5}\s+(\w+)\s',run('encoder_query'),re.M))
    checked('encoder_query',ENCODERS.issubset(encoders),log)
    font = run('font_query').strip().splitlines()
    checked('font_query',len(font)==2 and font[0]=='Noto Sans CJK JP' and
        font[1].startswith('/usr/share/fonts/opentype/noto/') and font_exists(font[1]),log)
    docker = run('docker_version').strip()
    checked('docker_version',re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+',docker) is not None,log)
    log('runtime_gate',result='pass')
    # All fields below are fixed expected values, not raw command outputs.
    return {'python':'3.12.15','ffmpeg':'6.1.1','ffprobe':'6.1.1',
            'packages_match':True,'filters_match':True,'encoders_match':True,'font_match':True,
            'docker_available':True}


def preflight(policy, env, *, guard=None, run=execute, read=old.get_json, observe=runtime_gate, log=emit):
    need(policy.get('identity')==IDENTITY and policy.get('image')==IMAGE and
         policy.get('package_install_approved') is False and
         all(policy.get(k)==0 for k in ('synthesis_max','encode_max','artifact_upload_max','automatic_retry')),
         'PREFLIGHT_V2_POLICY_DRIFT')
    receipt = (guard or (lambda:cloud_launch_guard(env,identity=IDENTITY)))()
    need(receipt.get('identity')==IDENTITY and receipt.get('consumed') is True and
         receipt.get('scope')=='AUTOMATION_MONOTONIC_CONSUMPTION','PRIMARY_MARKER_RECEIPT_REQUIRED')
    observation = observe(env,run,log)  # COMPLETE prerequisite gate before registry/pull
    need(all(observation.get(k) is True for k in ('packages_match','filters_match','encoders_match',
         'font_match','docker_available')) and observation.get('python')=='3.12.15' and
         observation.get('ffmpeg')=='6.1.1' and observation.get('ffprobe')=='6.1.1',
         'RUNTIME_GATE_INCOMPLETE')
    try: metadata = old.registry_metadata(get('registry_get',read=read,log=log))
    except Stop as error:
        if str(error)==CODES['registry_get']: raise
        failure('registry_get',log=log,mismatch=True)
    checked('registry_get',True,log)
    run('docker_pull',timeout=180)
    try:
        inspected = json.loads(run('docker_inspect'))
        ok = len(inspected)==1 and inspected[0].get('Os')=='linux' and \
             inspected[0].get('Architecture')=='amd64' and IMAGE in inspected[0].get('RepoDigests',[])
    except Stop: raise
    except Exception: failure('docker_inspect',log=log)
    checked('docker_inspect',ok,log)
    primary = None
    cleanup = None
    report = None
    try:
        run('docker_start')  # even unknown start outcome gets one cleanup attempt
        run('startup_wait',timeout=35)
        version = get('engine_version_get',read=read,log=log)
        checked('engine_version_get',version=='0.25.2',log)
        speakers = get('speakers_get',read=read,log=log)
        try: verify_speakers(version,speakers)
        except Exception: failure('speakers_get',log=log,mismatch=True)
        checked('speakers_get',True,log)  # raw speakers body never leaves memory
        report = {'status':'PASS_CLOUD_RUNTIME_PREFLIGHT','identity':IDENTITY,
           'run_id':receipt['run_id'],'digest':metadata['manifest_digest'],'version':'0.25.2',
           'speaker_id':1,'character':'ずんだもん','style':'あまあま','speaker_match':True,
           **observation,'synthesis':0,'encode':0,'mp4':0,'artifact_upload':0,'user_pc_execution':0}
    except Exception as error:
        # Untrusted adapters cannot inject arbitrary exception text into result.
        primary = error if isinstance(error,Stop) and str(error) in CODES.values() else Stop('RUNTIME_V2_UNKNOWN_STOP')
    finally:
        try: run('docker_cleanup',timeout=20)
        except Exception: cleanup = Stop(CODES['docker_cleanup'])
    if primary is not None: raise primary from None
    if cleanup is not None: raise cleanup from None
    return report


def main():
    try:
        report = preflight(json.loads(POLICY_PATH.read_text()),os.environ)
        text = json.dumps(report,ensure_ascii=False,sort_keys=True)
        print(text,flush=True)
        if os.environ.get('GITHUB_STEP_SUMMARY'):
            with open(os.environ['GITHUB_STEP_SUMMARY'],'a',encoding='utf-8') as out:out.write(text+'\n')
    except Exception as error:
        code = str(error) if isinstance(error,Stop) and (str(error) in CODES.values() or
          str(error) in ('BLOCKED_HISTORY_CONTINUITY_LOST','IDENTITY_CONSUMED_001','RERUN_REJECTED','IDENTITY_CONSUMED_PARENT','IDENTITY_CONSUMED_HISTORY','PREFLIGHT_V2_POLICY_DRIFT','PRIMARY_MARKER_RECEIPT_REQUIRED','RUNTIME_GATE_INCOMPLETE')) else 'RUNTIME_V2_UNKNOWN_STOP'
        print(code,flush=True)
        raise SystemExit(1)


if __name__=='__main__': main()
