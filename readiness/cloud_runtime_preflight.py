"""Hard-disabled GitHub-hosted metadata preflight candidate. NO generation.

All network/process effects are in explicit functions, never at import time.
The future approval must enable BOTH policy and environment. This module does
not install packages, synthesize audio, encode, upload, or change budgets.
"""
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import urllib.request

from one_shot_executor import (REPO, PREFLIGHT_ID, PREFLIGHT_WORKFLOW, IMAGE,
    IMAGE_DIGEST, INDEX_DIGEST, FILTERS, ENCODERS, RunContext, Stop, need,
    history_gate, verify_image, verify_speakers, verify_runtime)

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / 'readiness/cloud-runtime-preflight-policy.json'
REGISTRY_URL = 'https://hub.docker.com/v2/repositories/voicevox/voicevox_engine/tags/cpu-amd64-ubuntu24.04-0.25.2'
VOICE_URLS = {'version': 'http://127.0.0.1:50021/version',
              'speakers': 'http://127.0.0.1:50021/speakers'}
CONTAINER = 'plm-runtime-preflight-20261004-001'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise Stop('HTTP_REDIRECT_STOP')


def get_json(url):
    # Only read-only known official URLs or the two loopback metadata routes.
    need(url in VOICE_URLS.values() or url == REGISTRY_URL or
         re.fullmatch(r'https://api\.github\.com/repos/' + re.escape(REPO) +
                      r'/actions/(?:runs/[0-9]+|workflows/[0-9]+/runs\?per_page=100&page=[0-9]+)', url),
         'HTTP_ROUTE_NOT_ALLOWED')
    request = urllib.request.Request(url, method='GET', headers={
        'Accept': 'application/json', 'User-Agent': 'plm-read-only-runtime-preflight'})
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=20) as response:
            need(response.status == 200, 'HTTP_STATUS_STOP')
            raw = response.read(2 * 1024 * 1024 + 1)
        need(len(raw) <= 2 * 1024 * 1024, 'HTTP_BODY_TOO_LARGE')
        return json.loads(raw)
    except Exception:
        raise Stop('HTTP_METADATA_FAILURE_OR_UNKNOWN') from None


def process(command, timeout=30):
    try:
        result = subprocess.run(command, check=True, capture_output=True,
                                text=True, timeout=timeout)
        return result.stdout
    except Exception:
        raise Stop('RUNTIME_COMMAND_FAILURE_OR_UNKNOWN') from None


def approval_gate(policy, env):
    need(policy.get('allow') is True and policy.get('execution_approved') is True and
         policy.get('hard_disabled') is False and env.get('PLM_ALLOW') == 'true' and
         env.get('PLM_EXECUTION_APPROVED') == 'true', 'PREFLIGHT_DISABLED_NOT_APPROVED')
    need(env.get('GITHUB_ACTIONS') == 'true' and env.get('GITHUB_REPOSITORY') == REPO and
         env.get('RUNNER_ENVIRONMENT') == 'github-hosted' and env.get('RUNNER_OS') == 'Linux' and
         env.get('RUNNER_ARCH') == 'X64', 'CLOUD_RUNNER_REQUIRED')
    need(policy.get('identity') == PREFLIGHT_ID and policy.get('image') == IMAGE and
         policy.get('runner') == 'ubuntu-24.04' and policy.get('synthesis_max') == 0 and
         policy.get('encode_max') == 0 and policy.get('artifact_upload_max') == 0,
         'PREFLIGHT_POLICY_DRIFT')
    approved_head = env.get('PLM_APPROVED_HEAD_SHA', '')
    need(re.fullmatch('[0-9a-f]{40}', approved_head) and
         env.get('GITHUB_SHA') == approved_head, 'APPROVED_HEAD_UNBOUND')
    need(re.fullmatch('[1-9][0-9]*', env.get('PLM_ORIGINAL_WORKFLOW_ID', '')),
         'ORIGINAL_WORKFLOW_ID_UNBOUND')


def history_preflight(policy, env, read=get_json):
    approval_gate(policy, env)
    try:
        run_id = int(env['GITHUB_RUN_ID'])
        run = read(f'https://api.github.com/repos/{REPO}/actions/runs/{run_id}')
        context = RunContext(run_id, int(env['PLM_ORIGINAL_WORKFLOW_ID']), int(env['GITHUB_RUN_ATTEMPT']),
            int(env['GITHUB_RUN_NUMBER']), PREFLIGHT_ID, PREFLIGHT_WORKFLOW, env['GITHUB_SHA'],
            env['GITHUB_REPOSITORY'], env['GITHUB_EVENT_NAME'])
    except Exception:
        raise Stop('CURRENT_RUN_CONTEXT_UNKNOWN') from None
    need(run.get('workflow_id') == context.workflow_id and run.get('id') == run_id,
         'WORKFLOW_BINDING_MISMATCH')
    return history_gate(context,
        lambda page: read(f'https://api.github.com/repos/{REPO}/actions/workflows/'
                         f'{context.workflow_id}/runs?per_page=100&page={page}'),
        identity=PREFLIGHT_ID, path=PREFLIGHT_WORKFLOW)


def registry_metadata(reply):
    need(isinstance(reply, dict) and reply.get('name') == 'cpu-amd64-ubuntu24.04-0.25.2' and
         reply.get('digest') == INDEX_DIGEST, 'REGISTRY_INDEX_OR_TAG_MISMATCH')
    images = reply.get('images')
    need(isinstance(images, list), 'REGISTRY_METADATA_INVALID')
    found = [x for x in images if isinstance(x, dict) and x.get('os') == 'linux' and
             x.get('architecture') == 'amd64']
    need(len(found) == 1 and found[0].get('digest') == IMAGE_DIGEST, 'DIGEST_OR_PLATFORM_MISMATCH')
    metadata = {'reference': IMAGE, 'manifest_digest': found[0]['digest'],
                'os': found[0]['os'], 'architecture': found[0]['architecture']}
    verify_image(metadata)
    return metadata


def runtime_observation(env, run=process):
    need(platform.system() == 'Linux' and platform.machine() in ('x86_64', 'AMD64'),
         'CLOUD_RUNNER_REQUIRED')
    os_release = platform.freedesktop_os_release()
    need(os_release.get('ID') == 'ubuntu' and os_release.get('VERSION_ID') == '24.04',
         'CLOUD_RUNNER_REQUIRED')
    python = run(['python', '--version']).strip().removeprefix('Python ')
    ffmpeg = run(['ffmpeg', '-version'])
    ffprobe = run(['ffprobe', '-version'])
    packages = run(['dpkg-query', '-W', '-f=${binary:Package}\t${Version}\n',
                    'ffmpeg', 'fonts-noto-cjk', 'libavcodec60', 'libavfilter9',
                    'libavformat60', 'libavutil58', 'libswresample4', 'libswscale7',
                    'libx264-164', 'libass9'])
    package_versions = dict(line.split('\t', 1) for line in packages.strip().splitlines())
    base_versions = {k.split(':')[0]: v for k, v in package_versions.items()}
    filters = set(re.findall(r'^\s*[TSC.]{3}\s+(\w+)\s', run(['ffmpeg', '-hide_banner', '-filters']), re.M))
    encoders = set(re.findall(r'^\s*[VAS][A-Z.]{5}\s+(\w+)\s', run(['ffmpeg', '-hide_banner', '-encoders']), re.M))
    font = run(['fc-match', '-f', '%{family}\n%{file}\n', 'Noto Sans CJK JP']).strip().splitlines()
    docker = run(['docker', 'version', '--format', '{{.Server.Version}}']).strip()
    obs = {'runner': env.get('RUNNER_ENVIRONMENT'), 'os': 'ubuntu-24.04', 'architecture': 'amd64',
           'python': python, 'ffmpeg_package': base_versions.get('ffmpeg'),
           'font_package': base_versions.get('fonts-noto-cjk'),
           'ffmpeg_version': re.search(r'^ffmpeg version ([0-9.]+)', ffmpeg).group(1) if
                             re.search(r'^ffmpeg version ([0-9.]+)', ffmpeg) else None,
           'ffprobe_version': re.search(r'^ffprobe version ([0-9.]+)', ffprobe).group(1) if
                             re.search(r'^ffprobe version ([0-9.]+)', ffprobe) else None,
           'filters': sorted(filters), 'encoders': sorted(encoders),
           'font_family': font[0] if font else None,
           'font_verified': len(font) == 2 and font[1].startswith('/usr/share/fonts/opentype/noto/') and
                            Path(font[1]).is_file(),
           'docker_available': bool(docker), 'docker_server_version': docker,
           'package_versions': package_versions,
           # Core libav versions must match the exact ffmpeg candidate. External
           # codec/font rendering dependencies must be locked before real render.
           'codec_dependency_lock_verified': False,
           'libav_candidate_versions_match': all(base_versions.get(k) == '7:6.1.1-3ubuntu5' for k in
               ('libavcodec60','libavfilter9','libavformat60','libavutil58','libswresample4','libswscale7'))}
    verify_runtime(obs, require_codec_lock=False)
    return obs


def runtime_preflight(policy, env, run=process, read=get_json, observe=runtime_observation):
    history = history_preflight(policy, env, read)
    metadata = registry_metadata(read(REGISTRY_URL))
    runtime = observe(env, run)  # version/availability checks only; NO install/encode
    verify_runtime(runtime, require_codec_lock=False)
    started = False
    try:
        run(['docker', 'pull', '--platform', 'linux/amd64', IMAGE], timeout=180)
        inspected = json.loads(run(['docker', 'image', 'inspect', IMAGE]))
        need(len(inspected) == 1 and inspected[0].get('Os') == 'linux' and
             inspected[0].get('Architecture') == 'amd64' and
             IMAGE in inspected[0].get('RepoDigests', []), 'PULLED_IMAGE_MISMATCH')
        # No restart policy, GPU, asset download, model warmup or mutable API.
        started = True  # even an unknown docker run outcome requires cleanup once
        run(['docker', 'run', '-d', '--rm', '--name', CONTAINER, '--platform', 'linux/amd64',
             '-e', 'VV_DISABLE_MUTABLE_API=1', '-p', '127.0.0.1:50021:50021', IMAGE], timeout=30)
        # Fixed bounded startup window; NOT an API retry loop.
        run(['timeout', '30', 'bash', '-c', 'sleep 15'], timeout=35)
        version = read(VOICE_URLS['version'])  # exactly one GET; timeout => STOP
        need(version == '0.25.2', 'ENGINE_VERSION_MISMATCH')
        speakers = read(VOICE_URLS['speakers'])  # exactly one GET; no body saved
        verify_speakers(version, speakers)
        return {'status': 'PASS_CLOUD_RUNTIME_METADATA_ONLY', 'identity': PREFLIGHT_ID,
                'run_id': history['run_id'], 'manifest_digest': metadata['manifest_digest'],
                'version': version, 'speaker_id': 1, 'character': 'ずんだもん', 'style': 'あまあま',
                'python': runtime['python'], 'ffmpeg_package': runtime['ffmpeg_package'],
                'font_package': runtime['font_package'], 'package_versions': runtime['package_versions'],
                'codec_dependency_lock_verified': False,
                'synthesis': 0, 'encode': 0, 'mp4': 0, 'artifact_upload': 0}
    finally:
        if started:
            run(['docker', 'rm', '-f', CONTAINER], timeout=20)  # cleanup only, once


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--history-only', action='store_true')
    args = parser.parse_args()
    try:
        policy = json.loads(POLICY_PATH.read_text())
        report = history_preflight(policy, os.environ) if args.history_only else runtime_preflight(policy, os.environ)
        text = json.dumps(report, ensure_ascii=False, sort_keys=True)
        print(text)
        if os.environ.get('GITHUB_STEP_SUMMARY'):
            with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as file:
                file.write(text + '\n')
    except Exception as error:
        print(str(error) if isinstance(error, Stop) else 'PREFLIGHT_FAILURE_OR_UNKNOWN')
        raise SystemExit(1)


if __name__ == '__main__':
    main()
