"""Pure, fail-closed resolver parser. No commands, network, package writes or logs."""
import hashlib
import json
import re
from one_shot_executor import Stop, need

NAME=r'[a-z0-9][a-z0-9+.-]*'
VERSION=r'[0-9][A-Za-z0-9.+:~_-]*'
REPO='https://archive.ubuntu.com/ubuntu'
CODES=('RUNTIME_APT_SOURCE_FAILED','RUNTIME_APT_SIGNATURE_FAILED','RUNTIME_APT_INDEX_FAILED',
 'RUNTIME_APT_SIMULATION_FAILED','RUNTIME_APT_REMOVE_PROPOSED','RUNTIME_APT_DOWNGRADE_PROPOSED',
 'RUNTIME_APT_UNEXPECTED_UPGRADE','RUNTIME_APT_VIRTUAL_UNRESOLVED',
 'RUNTIME_APT_ALTERNATIVE_AMBIGUOUS','RUNTIME_APT_TRANSACTION_INCOMPLETE',
 'RUNTIME_APT_TRANSACTION_SOURCE_MISMATCH')


def control_records(text):
    need(isinstance(text,str) and len(text)<=180_000_000,'RUNTIME_APT_INDEX_FAILED')
    result=[]
    for para in text.strip().split('\n\n'):
        record={};key=None
        for line in para.splitlines():
            if line.startswith((' ','\t')):
                need(key is not None,'RUNTIME_APT_INDEX_FAILED');record[key]+='\n'+line
            else:
                need(': ' in line or line.endswith(':'),'RUNTIME_APT_INDEX_FAILED')
                key,value=line.split(':',1)
                need(key not in record,'RUNTIME_APT_INDEX_FAILED');record[key]=value.lstrip()
        if record:result.append(record)
    return result


def version_compare(a,b):
    """Debian epoch/upstream/revision ordering; no dpkg subprocess."""
    def parts(v):
        need(isinstance(v,str) and re.fullmatch(VERSION,v),'RUNTIME_APT_TRANSACTION_INCOMPLETE')
        epoch,tail=v.split(':',1) if ':' in v else ('0',v)
        need(epoch.isdigit(),'RUNTIME_APT_TRANSACTION_INCOMPLETE')
        upstream,rev=tail.rsplit('-',1) if '-' in tail else (tail,'0')
        return int(epoch),upstream,rev
    def order(c):
        if c=='~':return -1
        if not c:return 0
        if c.isalpha():return ord(c)
        return ord(c)+256
    def segment(x,y):
        i=j=0
        while i<len(x) or j<len(y):
            while (i<len(x) and not x[i].isdigit()) or (j<len(y) and not y[j].isdigit()):
                u=x[i] if i<len(x) and not x[i].isdigit() else ''
                v=y[j] if j<len(y) and not y[j].isdigit() else ''
                if order(u)!=order(v):return 1 if order(u)>order(v) else -1
                i+=bool(u);j+=bool(v)
            u=re.match(r'\d*',x[i:])[0];v=re.match(r'\d*',y[j:])[0]
            i+=len(u);j+=len(v);u=u.lstrip('0');v=v.lstrip('0')
            if len(u)!=len(v):return 1 if len(u)>len(v) else -1
            if u!=v:return 1 if u>v else -1
        return 0
    ea,ua,ra=parts(a);eb,ub,rb=parts(b)
    return (1 if ea>eb else -1) if ea!=eb else segment(ua,ub) or segment(ra,rb)


def inventory(text):
    records={}
    for p in control_records(text):
        status=p.get('Status','')
        if status in ('deinstall ok config-files','purge ok not-installed'):continue
        need(status=='install ok installed','RUNTIME_APT_TRANSACTION_INCOMPLETE')
        n=p.get('Package','');v=p.get('Version','');arch=p.get('Architecture','')
        need(re.fullmatch(NAME,n) and re.fullmatch(VERSION,v) and arch in ('amd64','all')
             and n not in records,'RUNTIME_APT_TRANSACTION_INCOMPLETE')
        records[n]=p
    need(records,'RUNTIME_APT_TRANSACTION_INCOMPLETE')
    return records


def index_records(text,component):
    need(component in ('main','universe'),'RUNTIME_APT_SOURCE_FAILED')
    result={}
    for p in control_records(text):
        n=p.get('Package','');v=p.get('Version','');arch=p.get('Architecture','')
        need(re.fullmatch(NAME,n) and re.fullmatch(VERSION,v) and arch in ('amd64','all'),
             'RUNTIME_APT_INDEX_FAILED')
        fn=p.get('Filename','');sha=p.get('SHA256','')
        need(fn.startswith('pool/'+component+'/') and fn.endswith('.deb') and '..' not in fn and
             re.fullmatch('[0-9a-f]{64}',sha),'RUNTIME_APT_INDEX_FAILED')
        key=(n,v,arch);need(key not in result,'RUNTIME_APT_TRANSACTION_INCOMPLETE')
        result[key]={**p,'repository':REPO,'suite':'noble','pocket':'release','component':component}
    return result


INST=re.compile(r'^Inst ('+NAME+r')(?::(amd64))?(?: \[('+VERSION+r')\])? \(('+VERSION+r') Ubuntu:24\.04/noble \[(amd64|all)\]\)$')
CONF=re.compile(r'^Conf ('+NAME+r')(?::amd64)? \(('+VERSION+r') Ubuntu:24\.04/noble \[(amd64|all)\]\)$')
TOTAL=re.compile(r'^(\d+) upgraded, (\d+) newly installed, (\d+) to remove and (\d+) not upgraded\.$')


def parse_simulation(raw,installed):
    """Discard known presentation text; require total and paired Inst/Conf records.

    Output format changes STOP. Nothing from unrecognized raw lines is reported.
    """
    need(isinstance(raw,str) and len(raw)<=2_000_000,'RUNTIME_APT_SIMULATION_FAILED')
    changed={};confirmed=set();total=None;section=False
    for line in raw.splitlines():
        if line.startswith(('Remv ','Purg ')):raise Stop('RUNTIME_APT_REMOVE_PROPOSED')
        m=INST.fullmatch(line)
        if m:
            n,qualified,previous,v,arch=m.groups();old=installed.get(n,{}).get('Version')
            need(n not in changed and previous==old and (qualified is None or arch=='amd64'),
                 'RUNTIME_APT_TRANSACTION_INCOMPLETE')
            action='Install' if old is None else ('Upgrade' if version_compare(v,old)>0 else
                    'Downgrade' if version_compare(v,old)<0 else 'Keep')
            need(action!='Keep','RUNTIME_APT_TRANSACTION_INCOMPLETE')
            changed[n]={'name':n,'version':v,'architecture':arch,'action':action,'previous_version':old}
            section=False;continue
        m=CONF.fullmatch(line)
        if m:
            n,v,arch=m.groups();need(n in changed and n not in confirmed and
                (v,arch)==(changed[n]['version'],changed[n]['architecture']),
                'RUNTIME_APT_TRANSACTION_INCOMPLETE');confirmed.add(n);section=False;continue
        m=TOTAL.fullmatch(line)
        if m:
            need(total is None,'RUNTIME_APT_TRANSACTION_INCOMPLETE');total=tuple(map(int,m.groups()));section=False;continue
        if line in ('Reading package lists...','Building dependency tree...','Reading state information...',''):
            section=False;continue
        if line in ('The following additional packages will be installed:',
                    'The following NEW packages will be installed:', 'The following packages will be upgraded:',
                    'The following packages will be DOWNGRADED:', 'The following packages will be REMOVED:'):
            section=True;continue
        if section and re.fullmatch(r'  '+NAME+r'(?:\s+'+NAME+r')*',line):continue
        # already-newest root messages have no origin, independently verified later.
        if re.fullmatch(NAME+r' is already the newest version \('+VERSION+r'\)\.',line):continue
        raise Stop('RUNTIME_APT_TRANSACTION_INCOMPLETE')
    need(total is not None and confirmed==set(changed),'RUNTIME_APT_TRANSACTION_INCOMPLETE')
    counts={k:sum(x['action']==k for x in changed.values()) for k in ('Install','Upgrade','Downgrade')}
    need(total[0]==counts['Upgrade'] and total[1]==counts['Install'] and total[2]==0 and
         counts['Downgrade']==0,'RUNTIME_APT_DOWNGRADE_PROPOSED' if counts['Downgrade'] else 'RUNTIME_APT_TRANSACTION_INCOMPLETE')
    return changed


def dependency_groups(raw):
    if not raw:return []
    result=[]
    for group in raw.split(','):
        alternatives=[]
        for value in group.split('|'):
            m=re.fullmatch(r'\s*('+NAME+r')(?::(any|native))?(?:\s*\((>=|<=|=|<<|>>) ('+VERSION+r')\))?\s*',value)
            need(m is not None,'RUNTIME_APT_ALTERNATIVE_AMBIGUOUS')
            n,qual,op,v=m.groups();need(qual is None or qual=='native','RUNTIME_APT_ALTERNATIVE_AMBIGUOUS')
            alternatives.append((n,op,v))
        result.append(alternatives)
    return result


def satisfies(actual,op,expected):
    if op is None:return True
    c=version_compare(actual,expected)
    return {'=':c==0,'>=':c>=0,'<=':c<=0,'<<':c<0,'>>':c>0}[op]


def canonical_bytes(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()


def transaction(raw,installed,index,roots,inventory_sha,index_sha):
    changes=parse_simulation(raw,installed)
    final={n:(p['Version'],p['Architecture']) for n,p in installed.items()}
    final.update({n:(p['version'],p['architecture']) for n,p in changes.items()})
    for n,v in roots.items():
        need(final.get(n) is not None and final[n][0]==v,'RUNTIME_APT_TRANSACTION_INCOMPLETE')
    selected={};edges=[];todo=list(roots)+list(changes)
    while todo:
        n=todo.pop()
        if n in selected:continue
        need(n in final,'RUNTIME_APT_VIRTUAL_UNRESOLVED');v,arch=final[n]
        p=index.get((n,v,arch));need(p is not None,'RUNTIME_APT_TRANSACTION_SOURCE_MISMATCH')
        need(p.get('repository')==REPO and p.get('suite')=='noble' and p.get('pocket')=='release'
             and p.get('component') in ('main','universe'),'RUNTIME_APT_TRANSACTION_SOURCE_MISMATCH')
        selected[n]={'name':n,'version':v,'architecture':arch,'action':changes.get(n,{}).get('action','Keep'),
            'previous_version':installed.get(n,{}).get('Version'),'repository':REPO,'suite':'noble',
            'pocket':'release','component':p['component'],'filename':p['Filename'],'sha256':p['SHA256']}
        need(len(selected)<=1000,'RUNTIME_APT_TRANSACTION_INCOMPLETE')
        for field in ('Pre-Depends','Depends'):
            for group in dependency_groups(p.get(field,'')):
                candidates={};virtual=False
                for dep,op,expected in group:
                    if dep in final and satisfies(final[dep][0],op,expected):
                        candidates[dep]=(dep,op,expected,False)
                    else:virtual=True
                    for name,(pv,pa) in final.items():
                        meta=index.get((name,pv,pa))
                        if not meta:continue
                        for providers in dependency_groups(meta.get('Provides','')):
                            for provided,pop,pversion in providers:
                                if provided==dep and (op is None or (pversion is not None and satisfies(pversion,op,expected))):
                                    candidates[name]=(dep,op,expected,True)
                need(candidates,'RUNTIME_APT_VIRTUAL_UNRESOLVED' if virtual else 'RUNTIME_APT_TRANSACTION_INCOMPLETE')
                need(len(candidates)==1,'RUNTIME_APT_ALTERNATIVE_AMBIGUOUS')
                provider,(dep,op,expected,is_virtual)=next(iter(candidates.items()));todo.append(provider)
                edges.append({'package':n,'field':field,'alternatives':[list(a) for a in group],
                    'selected_provider':provider,'selected_version':final[provider][0],'virtual':is_virtual})
    need(len(edges)<=20000,'RUNTIME_APT_TRANSACTION_INCOMPLETE')
    packages=[selected[n] for n in sorted(selected)]
    for p in packages:
        need(p['architecture'] in ('amd64','all') and re.fullmatch(VERSION,p['version']) and
             re.fullmatch('[0-9a-f]{64}',p['sha256']),'RUNTIME_APT_TRANSACTION_INCOMPLETE')
    counts={a.lower()+'_count':sum(p['action']==a for p in packages) for a in ('Install','Upgrade','Downgrade','Keep')}
    counts['remove_count']=0
    need(all(re.fullmatch('[0-9a-f]{64}',x) for x in (inventory_sha,index_sha)),'RUNTIME_APT_TRANSACTION_INCOMPLETE')
    canonical={'schema':'plm-apt-transaction-v4','inventory_sha256':inventory_sha,'index_cohort_sha256':index_sha,
        'root_constraints':roots,'packages':packages,'dependency_selections':sorted(edges,key=lambda x:canonical_bytes(x)),
        'counts':counts}
    fingerprint=hashlib.sha256(canonical_bytes(canonical)).hexdigest()
    status='BLOCKED' if counts['upgrade_count'] else 'PASS'
    return {'status':status,'failure_code':'RUNTIME_APT_UNEXPECTED_UPGRADE' if status=='BLOCKED' else None,
        'transaction_fingerprint':fingerprint,'transaction':canonical,
        'upgrade_reasons':[{'name':p['name'],'previous_version':p['previous_version'],'selected_version':p['version'],
            'reason':'Resolver requires version change; separate review mandatory','repository':p['repository'],
            'pocket':p['pocket']} for p in packages if p['action']=='Upgrade']}


def verify_handoff(report,expected_fingerprint,inventory_sha,index_sha):
    """Pure 005 boundary check; authentic run retrieval still independently mandatory."""
    need(report.get('status')=='PASS' and report.get('failure_code') is None,
         'RUNTIME_APT_TRANSACTION_INCOMPLETE')
    value=report.get('transaction');fingerprint=hashlib.sha256(canonical_bytes(value)).hexdigest()
    need(fingerprint==report.get('transaction_fingerprint')==expected_fingerprint and
         value.get('inventory_sha256')==inventory_sha and value.get('index_cohort_sha256')==index_sha,
         'RUNTIME_APT_TRANSACTION_INCOMPLETE')
    need(value.get('counts',{}).get('upgrade_count')==value['counts'].get('remove_count')==
         value['counts'].get('downgrade_count')==0,'RUNTIME_APT_TRANSACTION_INCOMPLETE')
    return True
