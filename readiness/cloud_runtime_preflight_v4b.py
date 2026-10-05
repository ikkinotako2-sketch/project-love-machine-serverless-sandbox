"""004B: four named resolver diagnostics; no binaries, install or transaction proof.

Raw bounded process streams live only in memory and are immediately classified.
"""
import hashlib
import io
import json
import lzma
import os
from pathlib import Path
import re
import selectors
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request
import apt_diagnostic_v4b as d
import apt_transaction_v4 as t
import cloud_runtime_preflight_v4 as v4
from branch_marker_once import cloud_launch_guard
from one_shot_executor import Stop,need

ROOT=Path(__file__).resolve().parents[1]
IDENTITY='manual-fixture-runtime-preflight-20261005-004b'
PLAN=ROOT/'readiness/cloud-runtime-preflight-v4b-diagnostic-plan.json'
STAGES={'source':'RUNTIME_APT_SOURCE_INDEX_MISMATCH','inventory':'RUNTIME_APT_BROKEN_PACKAGES',
 'index':'RUNTIME_APT_INDEX_FAILED','signature':'RUNTIME_APT_SIGNATURE_FAILED',
 'simulation':'RUNTIME_APT_UNKNOWN_SOLVER_FAILURE'}


def stage(label,case=None,return_code=None):
    need(label in STAGES and (case is None or case in d.CASES),'RUNTIME_APT_UNKNOWN_SOLVER_FAILURE')
    safe='stage='+label
    if case:safe+=' case='+case
    if type(return_code) is int and -255<=return_code<=255:safe+=' return_code='+str(return_code)
    print(safe,flush=True)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as f:f.write(safe+'\n')


def validate_plan(plan):
    need(plan['identity']==IDENTITY and plan['repository']==d.REPO and
         plan['suites']==['noble','noble-updates','noble-security'] and plan['components']==['main','universe'] and
         plan['comparison_cases']==d.CASES and plan['max_simulations']==4 and plan['network_retries']==0,
         'RUNTIME_APT_SOURCE_INDEX_MISMATCH')
    raw=(ROOT/plan['root_evidence_path']).read_bytes()
    need(hashlib.sha256(raw).hexdigest()==plan['root_evidence_sha256'],'RUNTIME_APT_SOURCE_INDEX_MISMATCH')
    old=json.loads(raw)
    need(plan['root_constraints']=={p['name']:p['version'] for p in old['packages']} and
         plan['signed_release_index']==old['signed_index'],'RUNTIME_APT_SOURCE_INDEX_MISMATCH')
    return old


def metadata_get(url,limit,expected_hash=None):
    paths=['/project/ubuntu-archive-keyring.gpg']
    for suite in ('noble','noble-updates','noble-security'):
        paths.append('/dists/'+suite+'/InRelease')
        paths.extend('/dists/'+suite+'/'+component+'/binary-amd64/Packages.xz' for component in ('main','universe'))
    need(url in [d.REPO+p for p in paths],'RUNTIME_APT_SOURCE_INDEX_MISMATCH')
    try:
        request=urllib.request.Request(url,method='GET',headers={'User-Agent':'plm-004b-diagnostic'})
        with urllib.request.build_opener(v4.NoRedirect()).open(request,timeout=45) as response:
            need(response.status==200,'RUNTIME_APT_INDEX_FAILED');raw=response.read(limit+1)
        need(len(raw)<=limit and (expected_hash is None or hashlib.sha256(raw).hexdigest()==expected_hash),
             'RUNTIME_APT_INDEX_FAILED')
        return raw
    except Stop:raise
    except Exception:raise Stop('RUNTIME_APT_INDEX_FAILED') from None


def release_manifest(raw,suite):
    text=raw.decode('utf-8')
    fields={}
    for key in ('Origin','Label','Suite','Codename','Date','Architectures','Components'):
        values=re.findall(r'^'+key+r': ([^\n\r]+)$',text,re.M)
        need(len(values)==1,'RUNTIME_APT_SOURCE_INDEX_MISMATCH');fields[key]=values[0]
    need(fields['Origin']=='Ubuntu' and fields['Label']=='Ubuntu' and fields['Suite']==suite and
         fields['Codename']=='noble' and 'amd64' in fields['Architectures'].split() and
         all(x in fields['Components'].split() for x in ('main','universe')),'RUNTIME_APT_SOURCE_INDEX_MISMATCH')
    section=text.split('\nSHA256:\n')
    need(len(section)==2,'RUNTIME_APT_INDEX_FAILED');items=[]
    for component in ('main','universe'):
        path=component+'/binary-amd64/Packages.xz'
        matches=re.findall(r'^ ([0-9a-f]{64})\s+(\d+)\s+'+re.escape(path)+r'$',section[1],re.M)
        need(len(matches)==1,'RUNTIME_APT_INDEX_FAILED');sha,size=matches[0];size=int(size)
        need(0<size<=35_000_000,'RUNTIME_APT_INDEX_FAILED')
        items.append({'component':component,'path':path,'sha256':sha,'size':size})
    # Date is recorded only as a hash; no free-form release body goes into summary.
    return {'suite':suite,'repository':d.REPO,'inrelease_sha256':hashlib.sha256(raw).hexdigest(),
            'release_date_sha256':hashlib.sha256(fields['Date'].encode()).hexdigest(),'indices':items}


def _bounded_simulation(args,env):
    """Private raw stream transport. Only the safe classifier result is public."""
    proc=subprocess.Popen(args,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
    buffers={'stdout':bytearray(),'stderr':bytearray()};limits={'stdout':2_000_000,'stderr':65536}
    deadline=time.monotonic()+120
    try:
        with selectors.DefaultSelector() as selector:
            for pipe,label in ((proc.stdout,'stdout'),(proc.stderr,'stderr')):
                os.set_blocking(pipe.fileno(),False);selector.register(pipe,selectors.EVENT_READ,label)
            while selector.get_map():
                need(time.monotonic()<deadline,'RUNTIME_APT_UNKNOWN_SOLVER_FAILURE')
                for key,events in selector.select(timeout=min(.5,max(0,deadline-time.monotonic()))):
                    data=os.read(key.fileobj.fileno(),65536)
                    if not data:selector.unregister(key.fileobj);continue
                    need(len(buffers[key.data])+len(data)<=limits[key.data],'RUNTIME_APT_UNKNOWN_SOLVER_FAILURE')
                    buffers[key.data].extend(data)
        rc=proc.wait(timeout=max(.01,deadline-time.monotonic()))
        return rc,bytes(buffers['stdout']).decode('utf-8'),bytes(buffers['stderr']).decode('utf-8')
    except BaseException:
        if proc.poll() is None:os.killpg(proc.pid,signal.SIGKILL);proc.wait(timeout=5)
        raise
    finally:
        proc.stdout.close();proc.stderr.close()


def simulation(case,plan,config,installed,indices,held,broken):
    need(case in d.CASES,'RUNTIME_APT_SOURCE_INDEX_MISMATCH');validate_plan(plan)
    args=['/usr/bin/apt-get','--simulate','--no-download','--no-install-recommends','install']+[
        n+'='+version for n,version in sorted(plan['root_constraints'].items())]
    env={'PATH':'/usr/bin:/bin','LC_ALL':'C','LANG':'C','HOME':'/nonexistent','APT_CONFIG':str(config)}
    stage('simulation',case)
    try:
        rc,out,err=_bounded_simulation(args,env);stage('simulation',case,rc)
        result=d.classify(rc,out,err,plan['root_constraints'],installed,indices,d.CASES[case],held=held,broken=broken)
        return result
    except Stop:raise
    except Exception:raise Stop('RUNTIME_APT_UNKNOWN_SOLVER_FAILURE') from None


def execute(plan,env):
    receipt=cloud_launch_guard(env,IDENTITY)
    need(receipt.get('identity')==IDENTITY and all(receipt.get(k) is True for k in
         ('consumed','allow','execution_approved','no_retry','no_resume')),'RUNTIME_APT_SOURCE_INDEX_MISMATCH')
    need(env.get('RUNNER_ENVIRONMENT')=='github-hosted' and env.get('ImageOS')=='ubuntu24' and
         env.get('RUNNER_ARCH')=='X64' and sys.version_info[:3]==(3,12,15),'RUNTIME_APT_SOURCE_INDEX_MISMATCH')
    need('ID=ubuntu' in Path('/etc/os-release').read_text() and
         'VERSION_ID="24.04"' in Path('/etc/os-release').read_text(),'RUNTIME_APT_SOURCE_INDEX_MISMATCH')
    temp=env.get('RUNNER_TEMP')
    need(isinstance(temp,str) and Path(temp).is_absolute() and Path(temp).is_dir() and
         temp==os.environ.get('RUNNER_TEMP'),'RUNTIME_APT_SOURCE_INDEX_MISMATCH')
    stage('source');old=validate_plan(plan)
    stage('inventory');status_path=Path('/var/lib/dpkg/status');status=status_path.read_bytes()
    installed,held,broken=d.inventory_snapshot(status.decode());inventory_hash=hashlib.sha256(status).hexdigest()
    with tempfile.TemporaryDirectory(prefix='plm-resolver-004-',dir=temp) as directory:
        base=Path(directory);pinned=plan['signed_release_index']
        stage('signature');key=metadata_get(pinned['keyring_source'],100_000,pinned['keyring_sha256'])
        key_path=base/'ubuntu-archive-keyring.gpg';key_path.write_bytes(key)
        indices={};manifests={};packages_bytes={};releases={}
        for suite in plan['suites']:
            stage('index');release=metadata_get(d.REPO+'/dists/'+suite+'/InRelease',1_000_000,
                pinned['inrelease_sha256'] if suite=='noble' else None)
            (base/'InRelease').write_bytes(release)
            stage('signature');sig=v4.command('signature',['/usr/bin/gpgv','--status-fd=1','--keyring',str(key_path),str(base/'InRelease')])
            need(any(x.startswith('[GNUPG:] VALIDSIG '+pinned['signing_key_fingerprint']+' ') for x in sig.splitlines()),
                 'RUNTIME_APT_SIGNATURE_FAILED')
            manifest=release_manifest(release,suite)
            if suite=='noble':
                need(manifest['indices']==pinned['package_indices'],'RUNTIME_APT_INDEX_FAILED')
            indices[suite]={};releases[suite]=release;manifests[suite]=manifest
            for item in manifest['indices']:
                stage('index');raw=metadata_get(d.REPO+'/dists/'+suite+'/'+item['path'],item['size'],item['sha256'])
                with lzma.open(io.BytesIO(raw)) as f:expanded=f.read(180_000_001)
                need(len(expanded)<=180_000_000,'RUNTIME_APT_INDEX_FAILED')
                records=t.index_records(expanded.decode(),item['component'])
                for p in records.values():p['suite']=suite;p['pocket']={'noble':'release','noble-updates':'updates','noble-security':'security'}[suite]
                need(not(set(indices[suite])&set(records)),'RUNTIME_APT_SOURCE_INDEX_MISMATCH')
                indices[suite].update(records);packages_bytes[(suite,item['component'])]=expanded
        for p in old['packages']:
            actual=indices['noble'].get((p['name'],p['version'],p['architecture']))
            need(actual is not None and actual['Filename']==p['filename'] and actual['SHA256']==p['sha256'],
                 'RUNTIME_APT_SOURCE_INDEX_MISMATCH')
        reports={}
        for case,suites in d.CASES.items():
            # Each source set is a different named diagnostic, never a rerun/retry.
            with tempfile.TemporaryDirectory(prefix='plm-resolver-004-',dir=temp) as case_dir:
                case_path=Path(case_dir);config=v4.source_config(case_path,status,key_path,temp)
                (case_path/'sources.list').write_text(''.join('deb [arch=amd64 signed-by='+str(key_path)+'] '+d.REPO+' '+suite+' main universe\n' for suite in suites))
                for suite in suites:
                    (case_path/('lists/archive.ubuntu.com_ubuntu_dists_'+suite+'_InRelease')).write_bytes(releases[suite])
                    for component in ('main','universe'):
                        (case_path/('lists/archive.ubuntu.com_ubuntu_dists_'+suite+'_'+component+'_binary-amd64_Packages')).write_bytes(packages_bytes[(suite,component)])
                reports[case]=simulation(case,plan,config,installed,indices,held,broken)
                need(status_path.read_bytes()==status,'RUNTIME_APT_SOURCE_INDEX_MISMATCH')
        report={'kind':'RESOLVER_DIAGNOSTIC_ONLY','identity':IDENTITY,'run_id':receipt['run_id'],
            'run_attempt':1,'launch_sha':receipt['launch_sha'],'inventory_sha256':inventory_hash,
            'signed_metadata':manifests,'cases':reports,'comparison':d.compare_reports(reports),
            'install_authorized':False,'transaction_proof':False,'package_binary_download':0,'package_install':0,
            'dpkg_mutation':0,'Docker':0,'VOICEVOX':0,'FFmpeg':0,'MP4':0,'artifact':0}
        output=json.dumps(report,sort_keys=True,ensure_ascii=True)
        print(output,flush=True)
        if env.get('GITHUB_STEP_SUMMARY'):
            with open(env['GITHUB_STEP_SUMMARY'],'a') as f:f.write('```json\n'+output+'\n```\n')
        return report


def main():
    try:
        execute(json.loads(PLAN.read_text()),os.environ)
        print('DIAGNOSTIC_EVIDENCE_COLLECTED_NOT_SOLVER_PROOF',flush=True)
    except Stop as error:
        allowed=set(d.CODES.values())|{'RUNTIME_APT_INDEX_FAILED','RUNTIME_APT_SIGNATURE_FAILED'}
        print(str(error) if str(error) in allowed else 'RUNTIME_APT_UNKNOWN_SOLVER_FAILURE',flush=True)
        raise SystemExit(1)
    except Exception:
        print('RUNTIME_APT_UNKNOWN_SOLVER_FAILURE',flush=True);raise SystemExit(1)


if __name__=='__main__':main()
