"""003 disabled package candidate and guarded offline oracle. NO live installer.

The real plan is incomplete. CLI always stops without network/process effects.
Synthetic test manifests exercise invariants; they do not certify Ubuntu closure.
"""
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlparse
from one_shot_executor import Stop, need
import cloud_runtime_preflight_v2 as v2

IDENTITY='manual-fixture-runtime-preflight-20261004-003'
ROOT=Path(__file__).resolve().parents[1]
PLAN_PATH=ROOT/'readiness/cloud-runtime-preflight-v3-package-plan.json'
APT_CODES={'apt_index':'RUNTIME_APT_INDEX_FAILED','package_download':'RUNTIME_PACKAGE_DOWNLOAD_FAILED',
 'package_hash':'RUNTIME_PACKAGE_HASH_FAILED','package_install':'RUNTIME_PACKAGE_INSTALL_FAILED',
 'package_versions':'RUNTIME_PACKAGE_VERSION_MISMATCH','dependency_closure':'RUNTIME_DEPENDENCY_CLOSURE_MISMATCH'}
RUNTIME_CODES=dict(v2.CODES)
CODES={**RUNTIME_CODES,**APT_CODES}
EXPECTED={k:'7:6.1.1-3ubuntu5' for k in ('ffmpeg','libavcodec60','libavfilter9','libavformat60',
 'libavutil58','libswresample4','libswscale7')}
EXPECTED.update({'fonts-noto-cjk':'1:20230817+repack1-3','libx264-164':'2:0.164.3108+git31e19f9-1',
 'libass9':'1:0.17.1-2build1'})


def roots(plan):
    packages=plan.get('packages')
    need(isinstance(packages,list) and len(packages)==len(EXPECTED),'RUNTIME_PACKAGE_VERSION_MISMATCH')
    need({p.get('name') for p in packages}==set(EXPECTED),'RUNTIME_PACKAGE_VERSION_MISMATCH')
    for p in packages:
        name=p['name'];version=EXPECTED[name]
        need(p.get('version')==version,'RUNTIME_PACKAGE_VERSION_MISMATCH')
        arch='all' if name=='fonts-noto-cjk' else 'amd64'
        need(p.get('architecture')==arch,'RUNTIME_PACKAGE_VERSION_MISMATCH')
        need(p.get('repository')=='https://archive.ubuntu.com/ubuntu' and p.get('suite')=='noble'
             and p.get('pocket')=='release' and p.get('component') in ('main','universe'),
             'RUNTIME_APT_INDEX_FAILED')
        fn=p.get('filename','')
        need(isinstance(fn,str) and fn.startswith('pool/'+p['component']+'/') and
             fn.endswith('/'+name+'_'+version.split(':')[-1]+'_'+arch+'.deb') and '..' not in fn,
             'RUNTIME_PACKAGE_DOWNLOAD_FAILED')
    need(plan.get('identity')==IDENTITY and plan.get('architecture')=='amd64' and
         plan.get('runner')=='ubuntu-24.04','RUNTIME_APT_INDEX_FAILED')
    need(plan.get('official_repositories')==['https://archive.ubuntu.com/ubuntu'] and
         plan.get('no_install_recommends') is True and plan.get('latest_fallback',False) is False,
         'RUNTIME_APT_INDEX_FAILED')
    return {p['name']:p for p in packages}


def validate_plan(plan):
    packages=roots(plan)
    closure=plan.get('dependency_closure',{})
    index=plan.get('signed_index',{})
    need(closure.get('complete') is True and closure.get('base_image_inventory_verified') is True and
         closure.get('pre_dependencies_and_transitive_dependencies_verified') is True and
         not closure.get('missing_direct_nodes') and not closure.get('unresolved_alternatives'),
         'BLOCKED_PACKAGE_DEPENDENCY_CLOSURE')
    need(index.get('verified') is True and re.fullmatch('[0-9a-f]{64}',index.get('inrelease_sha256') or '')
         and isinstance(index.get('package_indices'),list) and index['package_indices'],
         'RUNTIME_APT_INDEX_FAILED')
    entries=closure.get('entries')
    need(isinstance(entries,list) and entries,'RUNTIME_DEPENDENCY_CLOSURE_MISMATCH')
    nodes={p.get('name'):p for p in entries}
    need(len(nodes)==len(entries) and set(packages).issubset(nodes),'RUNTIME_DEPENDENCY_CLOSURE_MISMATCH')
    for name,p in nodes.items():
        need(isinstance(name,str) and re.fullmatch('[a-z0-9][a-z0-9+.-]*',name) and
             isinstance(p.get('version'),str) and re.fullmatch('[0-9][a-zA-Z0-9.+:~_-]*',p['version']),
             'RUNTIME_PACKAGE_VERSION_MISMATCH')
        need(p.get('repository')=='https://archive.ubuntu.com/ubuntu' and p.get('suite')=='noble' and
             p.get('pocket')=='release' and p.get('architecture') in ('amd64','all'), 'RUNTIME_APT_INDEX_FAILED')
        need(re.fullmatch('[0-9a-f]{64}',p.get('sha256') or '') is not None,'RUNTIME_PACKAGE_HASH_FAILED')
        need(p.get('metadata_complete') is True and isinstance(p.get('depends'),list) and
             isinstance(p.get('pre_depends'),list),'RUNTIME_DEPENDENCY_CLOSURE_MISMATCH')
        for dep in p['depends']+p['pre_depends']:
            need(isinstance(dep,dict) and dep.get('name') in nodes and
                 dep.get('selected_version')==nodes[dep['name']].get('version') and
                 dep.get('constraint_verified') is True and isinstance(dep.get('constraint'),str),
                 'RUNTIME_DEPENDENCY_CLOSURE_MISMATCH')
        if name in packages:
            need(all(p.get(k)==packages[name].get(k) for k in ('version','architecture','sha256','filename')),
                 'RUNTIME_PACKAGE_VERSION_MISMATCH')
    return nodes


def install_arguments(plan):
    nodes=validate_plan(plan)
    # Pure design value only, never executed by this module. All dependencies pinned.
    return ['apt-get','install','--no-install-recommends','--no-download','--no-remove','--no-upgrade']+[
        name+'='+nodes[name]['version'] for name in sorted(nodes)]


def verify_download_receipts(nodes,receipts):
    need(isinstance(receipts,dict) and set(receipts)==set(nodes),'RUNTIME_DEPENDENCY_CLOSURE_MISMATCH')
    for name,p in nodes.items():
        got=receipts[name]
        need(isinstance(got,dict) and got.get('sha256')==p['sha256'],'RUNTIME_PACKAGE_HASH_FAILED')
        need(all(got.get(k)==p.get(k) for k in ('version','architecture','filename')),
             'RUNTIME_PACKAGE_VERSION_MISMATCH')
        need(got.get('repository')=='https://archive.ubuntu.com/ubuntu','RUNTIME_PACKAGE_DOWNLOAD_FAILED')
    return True


class OfflineOracle:
    """In-memory stage simulation ONLY, requires irreversible no-exec/no-network guard."""
    def __init__(self,plan,effects,log=lambda stage,**kw:None):
        self.plan=plan;self.effects=effects;self.log=log;self.consumed=False;self.calls=[]
    def call(self,stage,*args):
        need(stage in CODES or stage in ('marker_guard','runner_check'),'OFFLINE_STAGE_INVALID')
        self.calls.append(stage);self.log(stage)
        try:return self.effects(stage,*args)
        except Exception as error:
            rc=getattr(error,'returncode',None)
            self.log(stage,result='failed',return_code=rc if type(rc)is int and -255<=rc<=255 else None)
            raise Stop(CODES.get(stage,'OFFLINE_GUARD_FAILED')) from None
    def execute(self):
        from oracle_bridge import require_guard
        require_guard()
        need(not self.consumed,'OFFLINE_ORACLE_ALREADY_CONSUMED');self.consumed=True
        receipt=self.call('marker_guard')
        need(receipt.get('identity')==IDENTITY and receipt.get('consumed') is True,'OFFLINE_GUARD_FAILED')
        need(self.call('runner_check')=='github-hosted ubuntu-24.04 amd64','CLOUD_RUNNER_REQUIRED')
        need(self.call('python_version')=='3.12.15',CODES['python_version'])
        nodes=validate_plan(self.plan) # incomplete real closure stops BEFORE any install stage
        need(self.call('apt_index') is True,CODES['apt_index'])
        downloads=self.call('package_download')
        self.call('package_hash');verify_download_receipts(nodes,downloads)
        need(self.call('package_install',install_arguments(self.plan)) is True,CODES['package_install'])
        installed=self.call('package_versions')
        need(installed=={name:p['version'] for name,p in nodes.items()},CODES['package_versions'])
        need(self.call('dependency_closure') is True,CODES['dependency_closure'])
        need(self.call('python_version')=='3.12.15',CODES['python_version'])
        for stage,expected in [('ffmpeg_version','6.1.1'),('ffprobe_version','6.1.1'),
                              ('package_query',True),('filter_query',True),('encoder_query',True),
                              ('font_query',True),('docker_version',True)]:
            need(self.call(stage)==expected,CODES[stage])
        # Simulate permitted metadata path ONLY after complete prerequisite gates.
        for stage in ('registry_get','docker_pull','docker_inspect','docker_start','startup_wait',
                      'engine_version_get','speakers_get','docker_cleanup'):
            need(self.call(stage) is True,CODES[stage])
        return {'status':'PASS_OFFLINE_SYNTHETIC_ORACLE_NOT_LIVE_READY','actual_operations':0,
                'identity':IDENTITY,'synthesis':0,'encode':0,'mp4':0,'artifact_upload':0}


def main():
    # No live downloader/index/installer/FFmpeg/Docker/HTTP adapters are present.
    try:validate_plan(json.loads(PLAN_PATH.read_text()))
    except Exception:
        print('BLOCKED_PACKAGE_DEPENDENCY_CLOSURE',flush=True)
        raise SystemExit(1)
    print('BLOCKED_V3_LIVE_INSTALLER_NOT_IMPLEMENTED',flush=True)
    raise SystemExit(1)


if __name__=='__main__':main()
