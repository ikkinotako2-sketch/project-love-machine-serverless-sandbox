"""Bounded APT 2.8.3 implementation-derived classifier, not a stable APT grammar.

Never echo input. Signed index + private status supply all public token authority.
Only source-confirmed, exact benign families may be ignored. Unknown syntax stops.
"""
import re
from functools import cmp_to_key
import apt_transaction_v4 as t
from one_shot_executor import Stop
CODE='RUNTIME_APT_RESOLVER_DIAGNOSTIC_FAILED'
FAMILIES=('RESOLVER_START','RESOLVER_END','INVESTIGATING','CONSIDERING',
 'BROKEN_DEPENDENCY','PACKAGE_SELECTION','PACKAGE_REJECTION','DEPENDENCY_SUMMARY',
 'USER_FACING_DEPENDENCY_ERROR','BENIGN_DIAGNOSTIC','UNSUPPORTED_RELEVANT_SYNTAX')
P=t.NAME+r'(?::(?:amd64|all))?'
V=r'(?:[0-9]+:)?[0-9][A-Za-z0-9.+~\-]*'
REL=r'Depends|PreDepends|Pre-Depends|Conflicts|Breaks'
OP=r'>=|<=|=|<<|>>'
# PrettyPkg selected/installed/action flags from apt-pkg/prettyprinters.cc 2.8.3.
PRETTY=r'(?:'+P+r') < [^\n]{1,250}? >'

class DebugStop(Stop):
    def __init__(self,reason,family='UNSUPPORTED_RELEVANT_SYNTAX',count=0):
        super().__init__(CODE)
        self.public={'syntax_family':family,'relevance':'DEPENDENCY_DECISION_OR_UNKNOWN',
          'known_package_tokens_count':min(count,100),'fixed_reason':reason}
    def evidence(self):return dict(self.public)


def context(indices,installed):
    versions={};constraints=set();alternatives={}
    for records in indices.values():
        for (name,version,arch),p in records.items():
            versions.setdefault(name,set()).add(version)
            for field,kind in (('Depends','Depends'),('Pre-Depends','PreDepends'),('Conflicts','Conflicts'),('Breaks','Breaks')):
                try:groups=t.dependency_groups(p.get(field,''))
                except Stop:continue # Unsupported signed metadata cannot authorize public conflicts.
                for group in groups:
                    for dep,op,required in group:
                        key=(name,kind,dep,op,required)
                        constraints.add(key)
                        alternatives.setdefault(key,set()).add(len(group)>1)
    for name,p in installed.items():versions.setdefault(name,set()).add(p['Version'])
    candidates={name:max(vs,key=cmp_to_key(t.version_compare)) for name,vs in versions.items()}
    return {'known':set(versions),'versions':versions,'installed':installed,'candidates':candidates,
            'constraints':constraints,'alternatives':alternatives}


def classify(line):
    s=line.strip()
    if s.startswith('Starting ') or s=='Entering ResolveByKeep':return 'RESOLVER_START'
    if s=='Done':return 'RESOLVER_END'
    if s=='Show Scores':return 'BENIGN_DIAGNOSTIC'
    if s.startswith('Investigating '):return 'INVESTIGATING'
    if s.startswith('Considering '):return 'CONSIDERING'
    if s.startswith('Broken '):return 'BROKEN_DEPENDENCY'
    if re.match(r'(?:Try to Re-Instate|Re-Instated|Re-Instated|Try Installing|Keeping [Pp]ackage|Or group keep|Fixing .* via keep|Upgrading )',s):return 'PACKAGE_SELECTION'
    if re.match(r'(?:Reinst Failed|Holding Back|Removing |Added |Or group remove|Fixing .* via remove)',s):return 'PACKAGE_REJECTION'
    if re.match(r'(?:Conflicts//Breaks|Dependencies are not satisfied|Policy breaks|Package )',s):return 'DEPENDENCY_SUMMARY'
    if s.startswith('E: ') or re.match(P+r'\s*:\s*(?:'+REL+r'):',s):return 'USER_FACING_DEPENDENCY_ERROR'
    return 'UNSUPPORTED_RELEVANT_SYNTAX'


def parse_debug(raw,ctx):
    if not isinstance(raw,str) or len(raw.encode())>65536:raise DebugStop('OUTPUT_BOUND_EXCEEDED')
    evidence=[];counts={family:0 for family in FAMILIES};conflicts=[]
    known=ctx['known'];family='UNSUPPORTED_RELEVANT_SYNTAX';line=''
    def fail(reason):
        count=sum(token.split(':')[0] in known for token in re.findall(r'(?<![\w.+-])'+P+r'(?![\w.+-])',line))
        raise DebugStop(reason,family,count)
    def package(value):
        if not re.fullmatch(P,value):fail('MALFORMED_PACKAGE')
        name=value.split(':')[0]
        if name not in known:fail('UNKNOWN_PACKAGE_TOKEN')
        return name
    def version(name,value):
        if not re.fullmatch(V,value):fail('MALFORMED_VERSION')
        if value not in ctx['versions'].get(name,set()):fail('UNVERIFIED_VERSION')
        return value
    def pretty(value):
        m=re.fullmatch(r'('+P+r') < (none|'+V+r')(?: -> (none|'+V+r'))?(?: \| (none|'+V+r'))? @[uihrpX](?:HR|R|H)?[ncHUFWTiX] [prumg]*(?:N|U|D|I|P|R|H|K)?(?: N(?:Pb|b))?(?: I(?:Pb|b))? >',value)
        if not m:fail('PRETTY_PACKAGE_SYNTAX_UNSUPPORTED')
        name=package(m[1])
        for value in m.groups()[1:]:
            if value and value!='none':version(name,value)
        current=m[2]
        if current!='none' and ctx['installed'].get(name,{}).get('Version')!=current:fail('INSTALLED_VERSION_MISMATCH')
        if current=='none' and name in ctx['installed']:fail('INSTALLED_VERSION_MISMATCH')
        return name
    def event(reason,**fields):
        evidence.append({'syntax_family':family,'fixed_reason':reason,**fields})
        if len(evidence)>500:fail('EVIDENCE_BOUND_EXCEEDED')
    def dependency(parent,kind,dep,op,required):
        name=package(parent);target=package(dep);kind=kind.replace('Pre-Depends','PreDepends')
        key=(name,kind,target,op,required)
        if key not in ctx['constraints']:fail('SIGNED_METADATA_MISMATCH')
        # Required constraint need not be a downloadable version; authority is signed relationship itself.
        if required and not re.fullmatch(V,required):fail('MALFORMED_VERSION')
        record={'syntax_family':family,'fixed_reason':'SIGNED_RELATION_MATCH','package':name,
          'dependency_package':target,'relation_kind':kind,'version_operator':op,'required_version':required,
          'installed_version':ctx['installed'].get(target,{}).get('Version'),'candidate_version':ctx['candidates'].get(target)}
        conflicts.append(record);evidence.append(record)
        # Alternatives are acknowledged by fixed reason, never fabricated provider selection/proof.
        if True in ctx['alternatives'].get(key,set()):event('SIGNED_ALTERNATIVE_MEMBER_NOT_PROVIDER_PROOF',package=name,dependency_package=target)
        if len(conflicts)>100 or len(evidence)>500:fail('EVIDENCE_BOUND_EXCEEDED')
    for line in raw.splitlines():
        if not line.strip():continue
        family=classify(line)
        if len(line)>2048:fail('LINE_BOUND_EXCEEDED')
        s=line.strip();counts[family]+=1
        if re.fullmatch(r'Starting (?:2 )?pkgProblemResolver with broken count: [0-9]+',s) or s=='Entering ResolveByKeep':
            event('SOURCE_CONFIRMED_ENTRY');continue
        if s=='Done':event('SOURCE_CONFIRMED_END');continue
        if s=='Show Scores':event('SOURCE_CONFIRMED_SCORE_HEADER_NO_DECISION');continue
        # Exact user-facing summary reports failure, not proof of any particular held dependency.
        if s in ('E: Unable to correct problems, you have held broken packages.',
                 'E: Error, pkgProblemResolver::Resolve generated breaks, this may be caused by held packages.'):
            event('FIXED_FAILURE_SUMMARY_NOT_ROOT_CAUSE');continue
        m=re.fullmatch(r'Investigating \([0-9]+\) ('+PRETTY+r')',s)
        if m:event('SOURCE_CONFIRMED_INVESTIGATION',package=pretty(m[1]));continue
        m=re.fullmatch(r'Considering ('+P+r') -?[0-9]+ as a solution to ('+P+r') -?[0-9]+',s)
        if m:event('SOURCE_CONFIRMED_CONSIDERATION',package=package(m[1]),dependency_package=package(m[2]));continue
        m=re.fullmatch(r'Broken ('+P+r') ('+REL+r') on ('+PRETTY+r'|'+P+r')(?: \(('+OP+r') ('+V+r')\))?',s)
        if m:
            parent,kind,target,op,required=m.groups();target=pretty(target) if ' < ' in target else package(target)
            dependency(parent,kind,target,op,required);continue
        m=re.fullmatch(r'('+P+r') : ('+REL+r'): ('+P+r')(?: \(('+OP+r') ('+V+r')\))? but (?:it is not going to be installed|('+V+r') is to be installed|it is not installable)',s)
        if m:
            parent,kind,dep,op,required,observed=m.groups()
            if observed:version(package(dep),observed)
            dependency(parent,kind,dep,op,required);continue
        m=re.fullmatch(r'Try to Re-Instate \([0-9]+\) ('+P+r')',s)
        if m:event('SOURCE_CONFIRMED_SELECTION_ATTEMPT',package=package(m[1]));continue
        m=re.fullmatch(r'Re-Instated ('+P+r')(?: \([0-9]+ vs [0-9]+\))?',s)
        if m:event('SOURCE_CONFIRMED_SELECTION',package=package(m[1]));continue
        m=re.fullmatch(r'Reinst Failed (?:because of protected|because of|early because of) ('+P+r')',s)
        if m:event('SOURCE_CONFIRMED_REJECTION',package=package(m[1]));continue
        m=re.fullmatch(r'(?:Holding Back|Removing) ('+P+r') (?:rather than change|because I can\x27t find) ('+P+r')',s)
        if m:event('SOURCE_CONFIRMED_REJECTION',package=package(m[1]),dependency_package=package(m[2]));continue
        m=re.fullmatch(r'Try Installing ('+PRETTY+r') before changing ('+P+r')',s)
        if m:event('SOURCE_CONFIRMED_SELECTION_ATTEMPT',package=pretty(m[1]),dependency_package=package(m[2]));continue
        m=re.fullmatch(r'Upgrading ('+P+r') due to Breaks field in ('+P+r')',s)
        if m:
            target,parent=m.groups()
            if not any(x[0]==package(parent) and x[1]=='Breaks' and x[2]==package(target) for x in ctx['constraints']):fail('SIGNED_METADATA_MISMATCH')
            event('SOURCE_CONFIRMED_BREAKS_SELECTION',package=package(parent),dependency_package=package(target));continue
        m=re.fullmatch(r'Added ('+P+r') to the remove list',s)
        if m:event('SOURCE_CONFIRMED_REJECTION',package=package(m[1]));continue
        m=re.fullmatch(r'Or group (?:remove|keep) for ('+P+r')',s)
        if m:event('SOURCE_CONFIRMED_GROUP_DECISION',package=package(m[1]));continue
        m=re.fullmatch(r'Fixing ('+P+r') via (?:remove|keep) of ('+P+r')',s)
        if m:event('SOURCE_CONFIRMED_FIX_DECISION',package=package(m[1]),dependency_package=package(m[2]));continue
        m=re.fullmatch(r'Keeping [Pp]ackage ('+P+r')(?: due to ('+REL+r'))?',s)
        if m:event('SOURCE_CONFIRMED_KEEP',package=package(m[1]),**({'relation_kind':m[2]} if m[2] else {}));continue
        m=re.fullmatch(r'Package ('+P+r') ('+P+r') ('+REL+r') on ('+PRETTY+r')(?: \(('+OP+r') ('+V+r')\))?',s)
        if m:
            first,parent,kind,target,op,required=m.groups()
            if package(first)!=package(parent):fail('SIGNED_METADATA_MISMATCH')
            dependency(parent,kind,pretty(target),op,required);continue
        m=re.fullmatch(r'(?:Dependencies are not satisfied for|Policy breaks with upgrade of) ('+PRETTY+r')',s)
        if m:event('SOURCE_CONFIRMED_DEPENDENCY_SUMMARY',package=pretty(m[1]));continue
        m=re.fullmatch(r'Conflicts//Breaks against version ('+V+r') for ('+P+r') but that is not InstVer, ignoring',s)
        if m:
            name=package(m[2]);version(name,m[1]);event('SOURCE_CONFIRMED_UNSELECTED_NEGATIVE_VERSION',package=name);continue
        # No catch-all ignore. Even unknown lines without package tokens are unknown relevance.
        fail('UNSUPPORTED_RELEVANT_SYNTAX')
    return {'parsed':True,'syntax_family_counts':counts,'evidence':evidence,'conflicts':conflicts,
            'proof':False,'install_authorized':False}
