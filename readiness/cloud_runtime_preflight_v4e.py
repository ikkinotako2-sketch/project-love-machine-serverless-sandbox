"""004E scoped supplementary checks; no install, mutation, raw report or 005 handoff."""
import hashlib
import io
import json
import lzma
import os
from pathlib import Path
import re
import sys
import tempfile
from functools import cmp_to_key
import apt_startup_v4c as a
import apt_config_fields_v4d as f
import apt_scoped_config_v4e as e
import apt_transaction_v4 as t
import apt_diagnostic_v4b as diag
import cloud_runtime_preflight_v4 as v4
import cloud_runtime_preflight_v4b as b4
from branch_marker_once import cloud_launch_guard
from one_shot_executor import Stop,need

ROOT=Path(__file__).resolve().parents[1]
IDENTITY='manual-fixture-runtime-preflight-20261005-004e'
PLAN=ROOT/'readiness/cloud-runtime-preflight-v4e-scoped-plan.json'
CURRENT='apt_binary'
CURRENT_FIELD='CONFIG_INSPECTION'
PROGRESS={}


def stage(label,package=None,return_code=None):
    global CURRENT
    need(label in a.CODES and (package is None or package in plan_roots()),a.CODES['apt_config'])
    CURRENT=label;line='stage='+label
    if package:line+=' package='+package
    if type(return_code) is int and -255<=return_code<=255:line+=' return_code='+str(return_code)
    print(line,flush=True)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as f:f.write(line+'\n')


def plan_roots():return json.loads(PLAN.read_text())['root_constraints']


def validate_plan(plan):
    old=json.loads((ROOT/plan['root_evidence_path']).read_text())
    need(plan['identity']==IDENTITY and plan['repository']==a.REPO and tuple(plan['suites'])==a.SUITES and
         plan['components']==['main','universe'] and plan['dpkg_executable']=='/bin/false' and
         plan['root_constraints']=={p['name']:p['version'] for p in old['packages']} and
         hashlib.sha256((ROOT/plan['root_evidence_path']).read_bytes()).hexdigest()==plan['root_evidence_sha256'] and
         plan['signed_release_index']==old['signed_index'] and
         hashlib.sha256((ROOT/plan['prior_004b_evidence']).read_bytes()).hexdigest()==plan['prior_004b_evidence_sha256'],
         a.CODES['apt_config'])
    need(plan['fixed_stages']==list(a.CODES) and plan['limits']['total_simulations']==11 and
         plan['limits']['single_root_simulations']==10 and plan['limits']['combined_root_simulations']==1,
         a.CODES['apt_config'])
    return old


def command(label,args,config=None,roots=None,package=None):
    expected=[];roots=roots or plan_roots()
    if label=='apt_binary':expected=[[binary,'--version'] for binary in a.BINARIES]
    elif label=='apt_config':expected=[['/usr/bin/apt-config','dump']]+[['/usr/bin/apt-config','shell','PLM_VALUE',key] for field_id,key in f.FIELDS]+[['/usr/bin/apt-config','shell','PLM_VALUE','RootDir']]
    elif label=='index_visibility':expected=[['/usr/bin/apt-cache','policy',name] for name in sorted(roots)]
    elif label=='resolver_start':
        prefix=['/usr/bin/apt-get','--simulate','--no-download','--no-install-recommends',
                '-o','Debug::pkgProblemResolver=true','install']
        expected=[prefix+[name+'='+version] for name,version in sorted(roots.items())]
        expected.append(prefix+[name+'='+version for name,version in sorted(roots.items())])
    need(args in expected,a.CODES.get(label,a.CODES['apt_config']))
    env={'PATH':'/usr/bin:/bin','LC_ALL':'C','LANG':'C','HOME':'/nonexistent'}
    if label!='apt_binary':
        need(config is not None and Path(config).name=='apt.conf',a.CODES['apt_config'])
        v4.private_directory(Path(config).parent);env['APT_CONFIG']=str(config)
    stage(label,package)
    try:
        rc,out,err=b4._bounded_simulation(args,env)
        stage(label,package,rc)
        need(rc in ((0,100) if label=='resolver_start' else (0,)),a.CODES[label])
        return rc,out,err
    except Exception:
        if label=='apt_config':
            if CURRENT_FIELD in ('ROOT_DIR','CONFIG_INSPECTION'):raise e.ScopeStop(CURRENT_FIELD,'KEY_QUERY' if CURRENT_FIELD=='ROOT_DIR' else 'FILTERED_DUMP','DUMP_QUERY_FAILED') from None
            raise f.ConfigStop(CURRENT_FIELD,'QUERY_FAILED') from None
        raise Stop(a.CODES[label]) from None


def load_indices(plan,directory,old):
    """Only previously approved official index/keyring metadata URLs, no .deb."""
    stage('lists_layout');root=Path(directory);pinned=plan['signed_release_index']
    key=b4.metadata_get(pinned['keyring_source'],100000,pinned['keyring_sha256'])
    key_path=root/'ubuntu-archive-keyring.gpg';key_path.write_bytes(key)
    manifests={};indices={};expected={}
    for suite in a.SUITES:
        raw=b4.metadata_get(a.REPO+'/dists/'+suite+'/InRelease',1000000,
                            pinned['inrelease_sha256'] if suite=='noble' else None)
        release_path=root/'InRelease';release_path.write_bytes(raw)
        signature=v4.command('signature',['/usr/bin/gpgv','--status-fd=1','--keyring',str(key_path),str(release_path)])
        need(any(line.startswith('[GNUPG:] VALIDSIG '+pinned['signing_key_fingerprint']+' ') for line in signature.splitlines()),
             a.CODES['lists_layout'])
        manifest=b4.release_manifest(raw,suite)
        if suite=='noble':need(manifest['indices']==pinned['package_indices'],a.CODES['lists_layout'])
        manifests[suite]=manifest;indices[suite]={}
        filename='archive.ubuntu.com_ubuntu_dists_'+suite+'_InRelease'
        (root/'lists'/filename).write_bytes(raw);expected[filename]=hashlib.sha256(raw).hexdigest()
        for item in manifest['indices']:
            compressed=b4.metadata_get(a.REPO+'/dists/'+suite+'/'+item['path'],item['size'],item['sha256'])
            with lzma.open(io.BytesIO(compressed)) as f:expanded=f.read(180000001)
            need(len(expanded)<=180000000,a.CODES['lists_layout'])
            records=t.index_records(expanded.decode(),item['component'])
            for record in records.values():
                record['suite']=suite;record['pocket']={'noble':'release','noble-updates':'updates','noble-security':'security'}[suite]
            need(not(set(indices[suite])&set(records)),a.CODES['lists_layout']);indices[suite].update(records)
            filename='archive.ubuntu.com_ubuntu_dists_'+suite+'_'+item['component']+'_binary-amd64_Packages'
            (root/'lists'/filename).write_bytes(expanded);expected[filename]=hashlib.sha256(expanded).hexdigest()
    for p in old['packages']:
        actual=indices['noble'].get((p['name'],p['version'],p['architecture']))
        need(actual is not None and actual['Filename']==p['filename'] and actual['SHA256']==p['sha256'],a.CODES['lists_layout'])
    files={}
    for path in (root/'lists').iterdir():
        if path.name=='partial' and path.is_dir() and not path.is_symlink():continue
        files[path.name]={'regular':path.is_file(),'symlink':path.is_symlink(),
                         'sha256':hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None}
    return indices,manifests,a.verify_lists(files,expected)


def debug_context(indices,installed):
    known=set(installed);versions={};constraints=set()
    for records in indices.values():
        for (name,version,arch),p in records.items():
            known.add(name);versions.setdefault(name,set()).add(version)
            for field,kind in (('Depends','Depends'),('Pre-Depends','PreDepends'),('Conflicts','Conflicts'),('Breaks','Breaks')):
                try:groups=t.dependency_groups(p.get(field,''))
                except Stop:continue # Unsupported metadata grammar is not used as debug evidence.
                for group in groups:
                    for dep,operator,required in group:
                        if operator:constraints.add((name,kind,dep,operator,required))
    for name,p in installed.items():versions.setdefault(name,set()).add(p['Version'])
    candidates={name:max(values,key=cmp_to_key(t.version_compare)) for name,values in versions.items()}
    return known,candidates,constraints


def verify_fields(root,key_path,config):
    global CURRENT_FIELD
    checks=[];PROGRESS['apt_config']={'checks':checks,'matched':False}
    expected=f.expected_scalars(root,key_path)
    for field_id,key in f.FIELDS:
        CURRENT_FIELD=field_id
        emit({'stage':'apt_config','field_id':field_id,'status':'START'})
        rc,out,err=command('apt_config',['/usr/bin/apt-config','shell','PLM_VALUE',key],config)
        checks.append(f.scalar_query(field_id,out,expected[field_id],rc))
        emit({'stage':'apt_config',**checks[-1]})
    CURRENT_FIELD='ROOT_DIR'
    scopes=[];PROGRESS['apt_config']['scopes']=scopes
    emit({'scope_id':'ROOT_DIR','syntax_kind':'KEY_QUERY','matched':None,'fixed_reason':None})
    rc,out,err=command('apt_config',['/usr/bin/apt-config','shell','PLM_VALUE','RootDir'],config)
    scopes.append(e.root_query(out,rc));emit(scopes[-1])
    CURRENT_FIELD='CONFIG_INSPECTION'
    emit({'scope_id':CURRENT_FIELD,'syntax_kind':'FILTERED_DUMP','matched':None,'fixed_reason':None})
    rc,out,err=command('apt_config',['/usr/bin/apt-config','dump'],config)
    scopes.extend(e.inspect(out,rc))
    for scope in scopes[1:]:emit(scope)
    return {'checks':checks,'scopes':scopes,'matched':True,'runtime_compatibility':'OBSERVED_THIS_RUN_ONLY'}


def execute(plan,env):
    receipt=cloud_launch_guard(env,IDENTITY)
    need(receipt.get('identity')==IDENTITY and all(receipt.get(k) is True for k in
         ('consumed','allow','execution_approved','no_retry','no_resume')),a.CODES['apt_binary'])
    need(env.get('RUNNER_ENVIRONMENT')=='github-hosted' and env.get('ImageOS')=='ubuntu24' and
         env.get('RUNNER_ARCH')=='X64' and sys.version_info[:3]==(3,12,15),a.CODES['apt_binary'])
    need('ID=ubuntu' in Path('/etc/os-release').read_text() and 'VERSION_ID="24.04"' in Path('/etc/os-release').read_text(),
         a.CODES['apt_binary'])
    temp=env.get('RUNNER_TEMP')
    need(isinstance(temp,str) and Path(temp).is_absolute() and Path(temp).is_dir() and temp==os.environ.get('RUNNER_TEMP'),
         a.CODES['apt_config'])
    old=validate_plan(plan);roots=plan['root_constraints'];completed={}
    need(hashlib.sha256((ROOT/plan['prior_004c_evidence']).read_bytes()).hexdigest()==plan['prior_004c_evidence_sha256'] and plan['config_verification']['scalar_queries']==22 and plan['limits']['scalar_config_queries']==22,a.CODES['apt_config'])
    need(hashlib.sha256((ROOT/plan['prior_004d_evidence']).read_bytes()).hexdigest()==plan['prior_004d_evidence_sha256'] and plan['limits']['rootdir_queries']==1,a.CODES['apt_config'])
    global PROGRESS
    PROGRESS=completed
    for binary in a.BINARIES:
        stage('apt_binary');path=Path(binary)
        need(path.is_file() and os.access(path,os.X_OK),a.CODES['apt_binary'])
        rc,out,err=command('apt_binary',[binary,'--version'])
        completed.setdefault('apt_binary',[]).append(a.binary_version(binary,True,True,rc,out))
    with tempfile.TemporaryDirectory(prefix='plm-resolver-004-',dir=temp) as directory:
        root=Path(directory);status_path=Path('/var/lib/dpkg/status')
        stage('status_snapshot');host_status=status_path.read_bytes()
        status_hash=hashlib.sha256(host_status).hexdigest()
        stage('apt_config');key_path=root/'ubuntu-archive-keyring.gpg'
        config=v4.source_config(root,host_status,key_path,temp)
        (root/'sources.list').write_text(''.join('deb [arch=amd64 signed-by='+str(key_path)+'] '+a.REPO+' '+suite+' main universe\n' for suite in a.SUITES))
        completed['apt_config']=verify_fields(root,key_path,config)
        stage('status_snapshot')
        installed,held,broken=diag.inventory_snapshot(host_status.decode())
        need(not broken,a.CODES['status_snapshot'])
        completed['status_snapshot']=a.verify_status(status_path.read_bytes(),(root/'status').read_bytes(),status_hash)
        indices,manifests,layout=load_indices(plan,root,old);completed['lists_layout']=layout
        policies={}
        for name,version in sorted(roots.items()):
            rc,out,err=command('index_visibility',['/usr/bin/apt-cache','policy',name],config,roots,name)
            policy=a.parse_policy(out,name,indices,installed,root/'status')
            a.verify_visibility(policy,version);policies[name]=policy
        completed['index_visibility']={'root_count':len(policies),'all_exact_visible':True,'policies':list(policies.values())}
        stage('root_policy')
        completed['root_policy']=[a.verify_root_policy(policies[name],roots[name]) for name in sorted(roots)]
        known,candidates,constraints=debug_context(indices,installed)
        cases=[('single:'+name,{name:version}) for name,version in sorted(roots.items())]+[('combined',roots)]
        simulations=[]
        completed['resolver_debug']=simulations
        for case,selected in cases:
            args=['/usr/bin/apt-get','--simulate','--no-download','--no-install-recommends',
                  '-o','Debug::pkgProblemResolver=true','install']+[name+'='+version for name,version in sorted(selected.items())]
            package=next(iter(selected)) if len(selected)==1 else None
            rc,out,err=command('resolver_start',args,config,roots,package)
            entered=a.solver_entered(rc,out,err)
            stage('resolver_debug',package)
            debug=a.parse_debug(err,known,installed,candidates,constraints)
            simulations.append({'case':case,'entry':entered,'debug':debug})
            a.verify_status(status_path.read_bytes(),(root/'status').read_bytes(),status_hash)
        completed['resolver_start']={'entered_count':len(simulations),'max_count':11}
        completed['resolver_debug']=simulations
        report={'kind':'APT_STARTUP_DIAGNOSTIC_ONLY','identity':IDENTITY,'run_id':receipt['run_id'],
          'run_attempt':1,'launch_sha':receipt['launch_sha'],'completed_stages':completed,'signed_metadata':manifests,
          'transaction_proof':False,'install_authorized':False,'package_binary_download':0,'package_install':0,
          'dpkg_mutation':0,'Docker':0,'VOICEVOX':0,'FFmpeg':0,'MP4':0,'artifact':0}
        emit(report);return report


def emit(report):
    safe=json.dumps(report,sort_keys=True,ensure_ascii=True)
    print(safe,flush=True)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as f:f.write('```json\n'+safe+'\n```\n')


def main():
    try:
        execute(json.loads(PLAN.read_text()),os.environ)
        print('DIAGNOSTIC_EVIDENCE_COLLECTED_NOT_TRANSACTION_PROOF',flush=True)
    except Exception as error:
        code=str(error) if isinstance(error,Stop) and str(error) in a.CODES.values() else a.CODES[CURRENT]
        emit({'identity':IDENTITY,'status':'BLOCKED','stage':CURRENT,'failure_code':code,
              'completed_stages':PROGRESS,'config_failure':error.evidence() if isinstance(error,f.ConfigStop) else None,
              'scope_failure':error.evidence() if isinstance(error,e.ScopeStop) else None,
              'transaction_proof':False,'install_authorized':False})
        raise SystemExit(1)


if __name__=='__main__':main()
