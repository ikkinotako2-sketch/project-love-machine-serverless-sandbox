"""Pure bounded diagnostic classification; raw solver output NEVER leaves this API."""
import re
from functools import cmp_to_key
from apt_transaction_v4 import NAME, VERSION, version_compare, control_records
from one_shot_executor import need

CASES={'release_only':['noble'],'release_updates':['noble','noble-updates'],
       'release_security':['noble','noble-security'],
       'release_updates_security':['noble','noble-updates','noble-security']}
REPO='https://archive.ubuntu.com/ubuntu'
CODES={k:'RUNTIME_APT_'+v for k,v in {
 'exact_version':'EXACT_VERSION_UNAVAILABLE','dependency':'DEPENDENCY_UNSATISFIED',
 'held':'HELD_CONFLICT','downgrade':'DOWNGRADE_REQUIRED','broken':'BROKEN_PACKAGES',
 'source':'SOURCE_INDEX_MISMATCH','not_found':'PACKAGE_NOT_FOUND','unknown':'UNKNOWN_SOLVER_FAILURE'}.items()}


def inventory_snapshot(text):
    installed={};held=[];broken=[]
    for p in control_records(text):
        name=p.get('Package','');version=p.get('Version');arch=p.get('Architecture')
        need(re.fullmatch(NAME,name) and (version is None or re.fullmatch(VERSION,version)) and
             arch in ('amd64','all'),'RUNTIME_APT_BROKEN_PACKAGES')
        status=p.get('Status','').split()
        need(len(status)==3,'RUNTIME_APT_BROKEN_PACKAGES')
        if status[1:] == ['ok','installed'] and status[0] in ('install','hold'):
            need(name not in installed,'RUNTIME_APT_BROKEN_PACKAGES');installed[name]=p
            if status[0]=='hold':held.append(name)
        elif status[1:] not in (['ok','config-files'],['ok','not-installed']):broken.append(name)
    need(installed,'RUNTIME_APT_BROKEN_PACKAGES')
    return installed,sorted(held),sorted(set(broken))


def package_evidence(roots,installed,indices,suites):
    """Index candidate is not claimed to be the actual APT policy candidate."""
    result=[]
    for name,expected in sorted(roots.items()):
        need(re.fullmatch(NAME,name) and re.fullmatch(VERSION,expected),'RUNTIME_APT_SOURCE_INDEX_MISMATCH')
        versions=[]
        for suite in suites:
            for key,p in indices.get(suite,{}).items():
                if key[0]!=name:continue
                n,version,arch=key
                need(re.fullmatch(VERSION,version) and arch in ('amd64','all') and p['repository']==REPO and
                     p['suite']==suite and p['component'] in ('main','universe'),'RUNTIME_APT_SOURCE_INDEX_MISMATCH')
                versions.append({'version':version,'architecture':arch,'suite':suite,'component':p['component']})
        versions.sort(key=lambda x:(x['suite'],x['version'],x['architecture']))
        need(len(versions)<=100,'RUNTIME_APT_SOURCE_INDEX_MISMATCH')
        highest=max((x['version'] for x in versions),key=cmp_to_key(version_compare),default=None)
        result.append({'package':name,'expected_version':expected,'installed_version':installed.get(name,{}).get('Version'),
            'candidate_version':highest,'candidate_kind':'HIGHEST_VERIFIED_INDEX_VERSION_NOT_APT_POLICY',
            'exact_available':any(x['version']==expected for x in versions),'available_versions':versions})
    return result


def inventory_coverage(installed,indices,suites):
    """Missing index entry is absence of evidence, never proof of a forbidden host source."""
    rows=[];new_pocket_matches=0
    for name,p in sorted(installed.items()):
        version=p['Version'];arch=p['Architecture']
        need(re.fullmatch(NAME,name) and re.fullmatch(VERSION,version) and arch in ('amd64','all'),
             'RUNTIME_APT_SOURCE_INDEX_MISMATCH')
        presence={suite:(name,version,arch) in indices.get(suite,{}) for suite in ('noble','noble-updates','noble-security')}
        if not any(presence.values()):continue
        present=any(presence[suite] for suite in suites)
        if not presence['noble'] and (presence['noble-updates'] or presence['noble-security']):new_pocket_matches+=1
        rows.append({'package':name,'installed_version':version,'architecture':arch,
                     'signed_index_presence':presence,'present_in_case':present})
    return {'index_recognized_installed_count':len(rows),'case_exact_present_count':sum(r['present_in_case'] for r in rows),
            'release_absent_updates_or_security_present_count':new_pocket_matches,
            'sample':rows[:100],'sample_truncated':len(rows)>100,
            'interpretation':'Signed metadata coverage only; does not prove dependency satisfaction or package origin'}


def classify(return_code,stdout,stderr,roots,installed,indices,suites,*,held=(),broken=(),source_verified=True):
    need(type(return_code) is int and -255<=return_code<=255,'RUNTIME_APT_UNKNOWN_SOLVER_FAILURE')
    need(isinstance(stdout,str) and isinstance(stderr,str) and len(stdout.encode())<=2_000_000 and
         len(stderr.encode())<=65536,'RUNTIME_APT_UNKNOWN_SOLVER_FAILURE')
    need(suites in list(CASES.values()),'RUNTIME_APT_SOURCE_INDEX_MISMATCH')
    evidence=package_evidence(roots,installed,indices,suites);coverage=inventory_coverage(installed,indices,suites);codes=set();signals=set()
    # No captured arbitrary substrings, stderr lines or exception text enter report.
    raw=stdout+'\n'+stderr
    if not source_verified:codes.add(CODES['source']);signals.add('SOURCE_VERIFICATION_FAILED')
    for p in evidence:
        if not p['available_versions']:codes.add(CODES['not_found']);signals.add('ROOT_ABSENT_FROM_VERIFIED_INDICES')
        elif not p['exact_available']:codes.add(CODES['exact_version']);signals.add('ROOT_EXACT_VERSION_ABSENT')
        if p['installed_version'] and version_compare(p['installed_version'],p['expected_version'])>0:
            codes.add(CODES['downgrade']);signals.add('INSTALLED_ROOT_NEWER_THAN_REQUESTED')
    for name in roots:
        if re.search(r"E: Unable to locate package "+re.escape(name)+r"(?:\s|$)",raw) and any(
            p['package']==name and p['exact_available'] for p in evidence):
            codes.add(CODES['source']);signals.add('APT_INDEX_VISIBILITY_CONTRADICTION')
        if re.search(r"E: Version '"+re.escape(roots[name])+r"' for '"+re.escape(name)+r"' was not found",raw):
            if any(p['package']==name and p['exact_available'] for p in evidence):
                codes.add(CODES['source']);signals.add('APT_VERSION_VISIBILITY_CONTRADICTION')
            else:codes.add(CODES['exact_version']);signals.add('APT_EXACT_VERSION_NOT_FOUND')
    # Match only known package names from verified indices or actual installed state.
    known=set(installed)|set(roots)
    for suite in suites:known.update(k[0] for k in indices.get(suite,{}))
    dependencies=set(re.findall(r'\b(?:PreDepends|Depends): ('+NAME+r')(?=\s|$)',raw)) & known
    if dependencies:codes.add(CODES['dependency']);signals.add('APT_DEPENDENCY_MESSAGE')
    if broken:codes.add(CODES['broken']);signals.add('HOST_INVENTORY_BROKEN_STATE')
    held_known=sorted(set(held)&known)
    if held_known and any(re.search(r'\bheld\b',line,re.I) and any(
        re.search(r'(?<![a-z0-9+.-])'+re.escape(n)+r'(?![a-z0-9+.-])',line) for n in held_known)
        for line in raw.splitlines()):
        codes.add(CODES['held']);signals.add('HELD_PACKAGE_AND_SOLVER_CONFLICT_MESSAGE')
    if 'DOWNGRADED' in raw or 'downgrades' in raw.lower():
        codes.add(CODES['downgrade']);signals.add('APT_DOWNGRADE_MESSAGE')
    if return_code==0 and not codes:
        return {'status':'SOLVER_ACCEPTED_NOT_TRANSACTION_PROOF','return_code':0,'failure_codes':[],
                'classification_basis':[],'root_packages':evidence,'dependency_packages':[],
                'held_packages':[],'broken_packages':[],'installed_package_coverage':coverage}
    if not codes:codes.add(CODES['unknown']);signals.add('NO_SUPPORTED_FIXED_PATTERN')
    return {'status':'DIAGNOSTIC_BLOCKED','return_code':return_code,'failure_codes':sorted(codes),
        'classification_basis':sorted(signals),'root_packages':evidence,
        'dependency_packages':sorted(dependencies)[:100],'held_packages':held_known[:100],
        'broken_packages':sorted(set(broken)&known)[:100],'installed_package_coverage':coverage}


def compare_reports(reports):
    need(set(reports)==set(CASES),'RUNTIME_APT_SOURCE_INDEX_MISMATCH')
    baseline=reports['release_only'];changes=[]
    before={p['package']:p for p in baseline['root_packages']}
    for case in CASES:
        if case=='release_only':continue
        for p in reports[case]['root_packages']:
            old=before[p['package']]
            if (p['exact_available'],p['candidate_version'])!=(old['exact_available'],old['candidate_version']):
                changes.append({'case':case,'package':p['package'],'release_exact_available':old['exact_available'],
                    'case_exact_available':p['exact_available'],'release_candidate':old['candidate_version'],
                    'case_candidate':p['candidate_version']})
    return {'kind':'POCKET_COMPARISON_NOT_TRANSACTION_PROOF','root_candidate_differences':changes,
        'release_only_failure_codes':baseline['failure_codes'],
        'case_failure_codes':{case:reports[case]['failure_codes'] for case in CASES},
        'release_state_conflict_proven':False,
        'interpretation':'Diagnostic comparison only; different candidates do not establish 004 root cause or authorize install'}
