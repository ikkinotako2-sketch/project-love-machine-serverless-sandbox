"""Pure startup/config/policy/debug checks. No subprocess, socket or output APIs."""
import hashlib
import json
import re
from pathlib import Path
from functools import cmp_to_key
import apt_transaction_v4 as t
from one_shot_executor import need,Stop

CODES={stage:'RUNTIME_APT_'+code for stage,code in {
 'apt_binary':'BINARY_FAILED','apt_config':'CONFIG_FAILED','status_snapshot':'STATUS_FAILED',
 'lists_layout':'LISTS_LAYOUT_FAILED','index_visibility':'INDEX_VISIBILITY_FAILED',
 'root_policy':'ROOT_POLICY_FAILED','resolver_start':'RESOLVER_START_FAILED',
 'resolver_debug':'RESOLVER_DIAGNOSTIC_FAILED'}.items()}
BINARIES=('/usr/bin/apt-get','/usr/bin/apt-cache','/usr/bin/apt-config')
SUITES=('noble','noble-updates','noble-security')
REPO='https://archive.ubuntu.com/ubuntu'


def binary_version(binary,present,executable,return_code,raw):
    need(binary in BINARIES and present and executable and return_code==0,CODES['apt_binary'])
    first=raw.splitlines()[0] if isinstance(raw,str) and raw.splitlines() else ''
    m=re.fullmatch(r'apt ('+t.VERSION+r') \(amd64\)',first)
    need(m is not None and len(m[1])<=100,CODES['apt_binary'])
    return {'binary':Path(binary).name,'version':m[1],'architecture':'amd64'}


def config_expected(directory,keyring):
    root=Path(directory)
    return {'dir::state::status':str(root/'status'),'dir::state::lists':str(root/'lists'),
      'dir::etc::sourcelist':str(root/'sources.list'),'dir::etc::sourceparts':str(root/'empty'),
      'dir::etc::main':str(root/'empty.conf'),'dir::etc::parts':str(root/'empty'),
      'dir::etc::preferences':str(root/'preferences'),'dir::etc::preferencesparts':str(root/'empty'),
      'dir::etc::trusted':str(keyring),'dir::etc::trustedparts':str(root/'empty'),
      'dir::cache':str(root/'cache'),'dir::cache::pkgcache':'','dir::cache::srcpkgcache':'',
      'dir::bin::dpkg':'/bin/false','apt::architecture':'amd64','apt::architectures::':'amd64',
      'apt::install-recommends':'false','apt::install-suggests':'false','apt::get::download':'false',
      'apt::get::simulate':'true','acquire::retries':'0',
      'acquire::allowinsecurerepositories':'false','apt::get::allowunauthenticated':'false'}


def verify_config(raw,expected):
    need(isinstance(raw,str) and len(raw.encode())<=2_000_000,CODES['apt_config'])
    values={}
    for line in raw.splitlines():
        m=re.fullmatch(r'([A-Za-z0-9_:./-]+) ("(?:[^"\\]|\\.)*");',line)
        need(m is not None,CODES['apt_config']);key=m[1].lower()
        try:value=json.loads(m[2])
        except Exception:raise Stop(CODES['apt_config']) from None
        need(key not in values,CODES['apt_config']);values[key]=value
        if any(word in key for word in ('pre-invoke','post-invoke','pre-install-pkgs')):
            need(value=='',CODES['apt_config'])
    need(all(values.get(k)==v for k,v in expected.items()) and values.get('rootdir','')=='',CODES['apt_config'])
    # Only fixed key names and match flags; never echo observed paths or unknown values.
    return {'matched':True,'fields':sorted(expected),'dpkg':'/bin/false','architecture':'amd64'}


def verify_status(host_raw,private_raw,expected_sha):
    need(isinstance(host_raw,bytes) and host_raw==private_raw and
         hashlib.sha256(host_raw).hexdigest()==expected_sha,CODES['status_snapshot'])
    return {'matched':True,'sha256':expected_sha}


def verify_lists(files,expected):
    need(set(files)==set(expected),CODES['lists_layout'])
    for name,record in files.items():
        need(isinstance(record,dict) and record.get('regular') is True and record.get('symlink') is False and
             record.get('sha256')==expected[name],CODES['lists_layout'])
    return {'matched':True,'verified_file_count':len(expected)}


def parse_policy(raw,name,indices,installed,private_status):
    need(re.fullmatch(t.NAME,name) and isinstance(raw,str) and len(raw.encode())<=2_000_000,
         CODES['index_visibility'])
    lines=raw.splitlines();need(lines and lines[0] in (name+':',name+':amd64:'),CODES['index_visibility'])
    installed_value=None;candidate=None;seen_installed=seen_candidate=table=False
    versions={};current=None
    for line in lines[1:]:
        if not line:continue
        m=re.fullmatch(r'  Installed: ('+t.VERSION+r'|\(none\))',line)
        if m:
            need(not seen_installed,CODES['index_visibility']);seen_installed=True
            installed_value=None if m[1]=='(none)' else m[1];continue
        m=re.fullmatch(r'  Candidate: ('+t.VERSION+r'|\(none\))',line)
        if m:
            need(not seen_candidate,CODES['index_visibility']);seen_candidate=True
            candidate=None if m[1]=='(none)' else m[1];continue
        if line=='  Version table:':need(not table,CODES['index_visibility']);table=True;continue
        m=re.fullmatch(r' (?:\*\*\* |    )('+t.VERSION+r') (\d+)',line)
        if m:
            need(table and m[1] not in versions and int(m[2]) in (100,500),CODES['index_visibility'])
            current=m[1];versions[current]=[];continue
        m=re.fullmatch(r'        (\d+) https://archive\.ubuntu\.com/ubuntu (noble(?:-updates|-security)?)/(main|universe) amd64 Packages',line)
        if m:
            need(current is not None and int(m[1])==500,CODES['index_visibility'])
            suite,component=m[2],m[3]
            records=[p for (n,v,a),p in indices.get(suite,{}).items() if n==name and v==current and a in ('amd64','all')]
            need(len(records)==1 and records[0]['component']==component and records[0]['repository']==REPO and
                 records[0]['suite']==suite,CODES['index_visibility'])
            versions[current].append({'repository':REPO,'suite':suite,'component':component,
                                      'architecture':records[0]['Architecture']});continue
        if line=='        100 '+str(private_status):
            need(current==installed.get(name,{}).get('Version'),CODES['index_visibility'])
            versions[current].append({'repository':'PRIVATE_STATUS','suite':'installed','component':None,
                                      'architecture':installed[name]['Architecture']});continue
        raise Stop(CODES['index_visibility'])
    need(seen_installed and seen_candidate and table and installed_value==installed.get(name,{}).get('Version') and
         all(sources for sources in versions.values()),CODES['index_visibility'])
    need(candidate is None or candidate in versions,CODES['root_policy'])
    return {'package':name,'installed_version':installed_value,'candidate_version':candidate,
            'visible_versions':[{'version':v,'sources':versions[v]} for v in sorted(versions)]}


def verify_visibility(policy,expected_version):
    rows=[row for row in policy['visible_versions'] if row['version']==expected_version and
          any(source['repository']==REPO for source in row['sources'])]
    need(len(rows)==1,CODES['index_visibility'])
    return {'package':policy['package'],'expected_version':expected_version,'exact_visible':True}


def verify_root_policy(policy,expected_version):
    versions=[p['version'] for p in policy['visible_versions']]
    need(versions and policy['candidate_version']==max(versions,key=cmp_to_key(t.version_compare)),CODES['root_policy'])
    return {**policy,'expected_version':expected_version,'candidate_matches_verified_default_policy':True}


def solver_entered(return_code,stdout,stderr):
    need(type(return_code) is int and return_code in (0,100),CODES['resolver_start'])
    markers=re.findall(r'^Starting (?:2 )?pkgProblemResolver with broken count: (\d+)$',stderr,re.M)
    summary=re.findall(r'^(\d+) upgraded, (\d+) newly installed, (\d+) to remove and (\d+) not upgraded\.$',stdout,re.M)
    need(markers or (return_code==0 and len(summary)==1),CODES['resolver_start'])
    return {'entered':True,'return_code':return_code,'entry_basis':'FIXED_RESOLVER_TRACE' if markers else 'SUCCESS_WITH_SIMULATION_TOTALS'}


def parse_debug(raw,known,installed,candidates,constraints):
    """Small explicitly supported grammar; unsupported syntax STOP without echo."""
    need(isinstance(raw,str) and len(raw.encode())<=65536,CODES['resolver_debug']);conflicts=[]
    for line in raw.splitlines():
        if not line:continue
        if re.fullmatch(r'Starting (?:2 )?pkgProblemResolver with broken count: \d+',line) or line=='Done':continue
        m=re.fullmatch(r'\s*Broken ('+t.NAME+r'):amd64 (Depends|PreDepends|Conflicts|Breaks) on ('+t.NAME+r'):amd64 \(('+r'>=|<=|=|<<|>>'+r') ('+t.VERSION+r')\)',line)
        if m:
            package,kind,dependency,operator,required=m.groups()
            need(package in known and dependency in known and (package,kind,dependency,operator,required) in constraints,
                 CODES['resolver_debug'])
            conflicts.append({'package':package,'dependency':dependency,'required_version_constraint':{'operator':operator,'version':required},
                'installed_version':installed.get(dependency,{}).get('Version'),'candidate_version':candidates.get(dependency),
                'conflict_type':kind.upper()})
            need(len(conflicts)<=100,CODES['resolver_debug']);continue
        m=re.fullmatch(r'Investigating \([0-9]+\) ('+t.NAME+r'):amd64 < [^<>\n]{1,250} >',line)
        if m:
            need(m[1] in known,CODES['resolver_debug']);continue
        m=re.fullmatch(r'  Considering ('+t.NAME+r'):amd64 [0-9]+ as a solution to ('+t.NAME+r'):amd64 [-0-9]+',line)
        if m:
            need(m[1] in known and m[2] in known,CODES['resolver_debug']);continue
        # Fixed user-facing dependency messages, checked against signed control metadata.
        m=re.fullmatch(r' ('+t.NAME+r') : (Depends|PreDepends|Conflicts|Breaks): ('+t.NAME+r') \((>=|<=|=|<<|>>) ('+t.VERSION+r')\) but it is not going to be installed',line)
        if m:
            package,kind,dependency,operator,required=m.groups()
            need((package,kind,dependency,operator,required) in constraints,CODES['resolver_debug'])
            conflicts.append({'package':package,'dependency':dependency,'required_version_constraint':{'operator':operator,'version':required},
                'installed_version':installed.get(dependency,{}).get('Version'),'candidate_version':candidates.get(dependency),
                'conflict_type':kind.upper()});continue
        if line in ('E: Unable to correct problems, you have held broken packages.',
                    'E: Error, pkgProblemResolver::Resolve generated breaks, this may be caused by held packages.'):
            continue
        raise Stop(CODES['resolver_debug'])
    return {'parsed':True,'conflicts':conflicts,'proof':False}
