"""Fixed 004 resolver-only adapter. Metadata GET + gpgv + apt --simulate only.

Preparation is hard-disabled. No install, dpkg, apt update/download, media or Docker.
Never pass credentials to subprocesses; never emit raw stdout/stderr/provider bodies.
"""
import hashlib
import io
import json
import lzma
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path
import apt_transaction_v4 as t
from one_shot_executor import Stop, need
from branch_marker_once import cloud_launch_guard

ROOT=Path(__file__).resolve().parents[1]
IDENTITY='manual-fixture-runtime-preflight-20261005-004'
PLAN=ROOT/'readiness/cloud-runtime-preflight-v4-resolver-plan.json'
BASE='https://archive.ubuntu.com/ubuntu'
STAGES={'source':'RUNTIME_APT_SOURCE_FAILED','signature':'RUNTIME_APT_SIGNATURE_FAILED',
 'index':'RUNTIME_APT_INDEX_FAILED','inventory':'RUNTIME_APT_TRANSACTION_INCOMPLETE',
 'simulation':'RUNTIME_APT_SIMULATION_FAILED','transaction':'RUNTIME_APT_TRANSACTION_INCOMPLETE'}


def safe_stage(stage,return_code=None):
    need(stage in STAGES,'RUNTIME_APT_TRANSACTION_INCOMPLETE')
    line='stage='+stage
    if type(return_code) is int and -255<=return_code<=255:line+=' return_code='+str(return_code)
    print(line,flush=True)
    path=os.environ.get('GITHUB_STEP_SUMMARY')
    if path:
        with open(path,'a') as f:f.write(line+'\n')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args):raise Stop('RUNTIME_APT_SOURCE_FAILED')


def metadata_get(url,max_bytes,expected_sha,stage):
    need(url in (BASE+'/dists/noble/InRelease',BASE+'/project/ubuntu-archive-keyring.gpg',
        BASE+'/dists/noble/main/binary-amd64/Packages.xz',
        BASE+'/dists/noble/universe/binary-amd64/Packages.xz'),'RUNTIME_APT_SOURCE_FAILED')
    safe_stage(stage)
    try:
        request=urllib.request.Request(url,headers={'User-Agent':'plm-resolver-only'},method='GET')
        with urllib.request.build_opener(NoRedirect()).open(request,timeout=45) as response:
            need(response.status==200,STAGES[stage]);raw=response.read(max_bytes+1)
        need(len(raw)<=max_bytes and hashlib.sha256(raw).hexdigest()==expected_sha,STAGES[stage])
        return raw
    except Stop:raise
    except Exception:raise Stop(STAGES[stage]) from None


def command(stage,args,config=None):
    if stage=='simulation':
        plan=json.loads(PLAN.read_text());validate_source(plan)
        expected=['/usr/bin/apt-get','--simulate','--no-download','--no-install-recommends','install']+[
            n+'='+version for n,version in sorted(plan['root_constraints'].items())]
        need(args==expected,'RUNTIME_APT_SOURCE_FAILED')
    elif stage=='signature':
        need(len(args)==5 and args[:3]==['/usr/bin/gpgv','--status-fd=1','--keyring'] and
             re.fullmatch(r'/tmp/plm-resolver-004-[A-Za-z0-9_-]+/ubuntu-archive-keyring.gpg',args[3]) and
             args[4]==str(Path(args[3]).parent/'InRelease'),'RUNTIME_APT_SOURCE_FAILED')
    else:raise Stop('RUNTIME_APT_SOURCE_FAILED')
    safe_stage(stage)
    env={'PATH':'/usr/bin:/bin','LC_ALL':'C','LANG':'C','HOME':'/nonexistent'}
    if config:env['APT_CONFIG']=str(config)
    try:
        proc=subprocess.run(args,env=env,capture_output=True,timeout=120,check=False)
        safe_stage(stage,proc.returncode)
        need(proc.returncode==0,STAGES[stage]);need(len(proc.stdout)<=2_000_000,STAGES[stage])
        return proc.stdout.decode('utf-8')
    except Stop:raise
    except Exception:raise Stop(STAGES[stage]) from None


def source_config(directory,status,keyring):
    """Fresh private dirs; no inherited apt.conf, hooks, preferences or host sources."""
    d=Path(directory)
    need(re.fullmatch(r'/tmp/plm-resolver-004-[A-Za-z0-9_-]+',str(d)) is not None,'RUNTIME_APT_SOURCE_FAILED')
    for name in ('lists','lists/partial','cache','cache/archives','cache/archives/partial','logs','empty'):
        (d/name).mkdir(exist_ok=True)
    (d/'status').write_bytes(status);(d/'status').chmod(0o400)
    (d/'sources.list').write_text('deb [arch=amd64 signed-by='+str(keyring)+'] '+BASE+' noble main universe\n')
    (d/'empty.conf').write_text('');(d/'preferences').write_text('')
    config=d/'apt.conf'
    values={'Dir::Etc::main':str(d/'empty.conf'),'Dir::Etc::parts':str(d/'empty'),
        'Dir::Etc::sourcelist':str(d/'sources.list'),'Dir::Etc::sourceparts':str(d/'empty'),
        'Dir::Etc::preferences':str(d/'preferences'),'Dir::Etc::preferencesparts':str(d/'empty'),
        'Dir::Etc::trusted':str(keyring),'Dir::Etc::trustedparts':str(d/'empty'),
        'Dir::State::status':str(d/'status'),'Dir::State::lists':str(d/'lists'),
        'Dir::State::extended_states':str(d/'extended_states'),'Dir::Cache':str(d/'cache'),
        'Dir::Cache::pkgcache':'','Dir::Cache::srcpkgcache':'','Dir::Log':str(d/'logs'),
        'Dir::Bin::dpkg':'/bin/false','APT::Architecture':'amd64','APT::Architectures::':'amd64',
        'APT::Get::Simulate':'true','APT::Get::Download':'false','APT::Install-Recommends':'false',
        'APT::Install-Suggests':'false','Acquire::AllowInsecureRepositories':'false',
        'Acquire::AllowDowngradeToInsecureRepositories':'false','APT::Get::AllowUnauthenticated':'false',
        'Acquire::Retries':'0'}
    config.write_text(''.join(k+' '+json.dumps(v)+';\n' for k,v in values.items()))
    return config


def validate_source(plan):
    need(plan.get('identity')==IDENTITY and plan.get('runner')=='ubuntu-24.04' and
         plan.get('architecture')=='amd64' and plan.get('source')=={'repository':BASE,'suite':'noble',
         'pocket':'release','components':['main','universe'],'other_pockets':False},'RUNTIME_APT_SOURCE_FAILED')
    path=ROOT/plan['root_evidence_path'];raw=path.read_bytes()
    need(hashlib.sha256(raw).hexdigest()==plan['root_evidence_sha256'],'RUNTIME_APT_INDEX_FAILED')
    old=json.loads(raw);need(plan['signed_index']==old['signed_index'] and
         plan['root_constraints']=={p['name']:p['version'] for p in old['packages']},'RUNTIME_APT_INDEX_FAILED')
    return old


def execute(plan,env):
    need(plan.get('hard_disabled') is False and plan.get('execution_approved') is True,
         'BLOCKED_OFFLINE_PREPARATION_ONLY')
    # Independent primary marker recheck immediately before metadata effects.
    receipt=cloud_launch_guard(env,IDENTITY)
    need(receipt.get('consumed') is True,'RUNTIME_APT_SOURCE_FAILED')
    need(env.get('RUNNER_ENVIRONMENT')=='github-hosted' and env.get('RUNNER_OS')=='Linux' and
         env.get('RUNNER_ARCH')=='X64' and env.get('ImageOS')=='ubuntu24','RUNTIME_APT_SOURCE_FAILED')
    os_release=Path('/etc/os-release').read_text()
    need('ID=ubuntu' in os_release and 'VERSION_ID="24.04"' in os_release,'RUNTIME_APT_SOURCE_FAILED')
    need(sys.version_info[:3]==(3,12,15),'RUNTIME_PYTHON_VERSION_FAILED')
    safe_stage('source');old=validate_source(plan);signed=plan['signed_index']
    safe_stage('inventory');status_path=Path('/var/lib/dpkg/status');status=status_path.read_bytes()
    installed=t.inventory(status.decode());inventory_hash=hashlib.sha256(status).hexdigest()
    with tempfile.TemporaryDirectory(prefix='plm-resolver-004-',dir='/tmp') as directory:
        d=Path(directory)
        release=metadata_get(BASE+'/dists/noble/InRelease',1_000_000,signed['inrelease_sha256'],'index')
        key=metadata_get(signed['keyring_source'],100_000,signed['keyring_sha256'],'signature')
        (d/'InRelease').write_bytes(release);key_path=d/'ubuntu-archive-keyring.gpg';key_path.write_bytes(key)
        sig=command('signature',['/usr/bin/gpgv','--status-fd=1','--keyring',str(key_path),str(d/'InRelease')])
        need(any(line.startswith('[GNUPG:] VALIDSIG '+signed['signing_key_fingerprint']+' ') for line in sig.splitlines()),
             'RUNTIME_APT_SIGNATURE_FAILED')
        config=source_config(d,status,key_path);index={}
        (d/'lists/archive.ubuntu.com_ubuntu_dists_noble_InRelease').write_bytes(release)
        for item in signed['package_indices']:
            need(re.search(r'^ '+item['sha256']+r'\s+'+str(item['size'])+r'\s+'+re.escape(item['path'])+r'$',
                 release.decode(),re.M),'RUNTIME_APT_INDEX_FAILED')
            compressed=metadata_get(BASE+'/dists/noble/'+item['path'],item['size'],item['sha256'],'index')
            with lzma.open(io.BytesIO(compressed)) as f:expanded=f.read(180_000_001)
            need(len(expanded)<=180_000_000,'RUNTIME_APT_INDEX_FAILED')
            component=item['component'];records=t.index_records(expanded.decode(),component)
            need(not(set(index)&set(records)),'RUNTIME_APT_TRANSACTION_INCOMPLETE');index.update(records)
            (d/('lists/archive.ubuntu.com_ubuntu_dists_noble_'+component+'_binary-amd64_Packages')).write_bytes(expanded)
        for p in old['packages']:
            observed=index.get((p['name'],p['version'],p['architecture']))
            need(observed is not None and observed['Filename']==p['filename'] and observed['SHA256']==p['sha256'],
                 'RUNTIME_APT_INDEX_FAILED')
        args=['/usr/bin/apt-get','--simulate','--no-download','--no-install-recommends','install']+[
            n+'='+v for n,v in sorted(plan['root_constraints'].items())]
        raw=command('simulation',args,config)
        safe_stage('transaction');report=t.transaction(raw,installed,index,plan['root_constraints'],
            inventory_hash,signed['inrelease_sha256'])
        need(status_path.read_bytes()==status,'RUNTIME_APT_TRANSACTION_INCOMPLETE')
        report.update(identity=IDENTITY,run_id=receipt['run_id'],run_attempt=1,launch_sha=receipt['launch_sha'],
            runner='github-hosted ubuntu-24.04',package_binary_downloads=0,package_install=0,dpkg=0,
            docker=0,voicevox=0,ffmpeg=0,synthesis=0,encode=0,mp4=0,artifact=0)
        # Only validated names/versions/hashes/source and fixed reason strings are emitted.
        summary=json.dumps(report,sort_keys=True,ensure_ascii=True)
        print(summary,flush=True)
        if env.get('GITHUB_STEP_SUMMARY'):
            with open(env['GITHUB_STEP_SUMMARY'],'a') as f:f.write('```json\n'+summary+'\n```\n')
        return report


def main():
    try:
        report=execute(json.loads(PLAN.read_text()),os.environ)
        need(report['status']=='PASS',report['failure_code'])
    except Stop as error:
        code=str(error)
        if code not in t.CODES and code not in ('BLOCKED_OFFLINE_PREPARATION_ONLY','RUNTIME_PYTHON_VERSION_FAILED'):
            code='RUNTIME_APT_TRANSACTION_INCOMPLETE'
        print(code,flush=True);raise SystemExit(1)
    except Exception:
        print('RUNTIME_APT_TRANSACTION_INCOMPLETE',flush=True);raise SystemExit(1)


if __name__=='__main__':main()
