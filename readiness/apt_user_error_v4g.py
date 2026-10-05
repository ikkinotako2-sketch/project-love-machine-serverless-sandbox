"""APT 2.8.3 source-derived user-facing boundary. No stable grammar claim.

No commands, fetching, logging or raw retention. Unknown E: is never ignored.
Debug grammar remains the frozen 004F implementation; only user errors change.
"""
import re
import apt_resolver_debug_v4f as base
context=base.context
DebugStop=base.DebugStop
P,V,REL,OP=base.P,base.V,base.REL,base.OP
FAMILIES=('DEPENDENCY_NOT_INSTALLABLE','DEPENDENCY_VERSION_NOT_AVAILABLE',
 'DEPENDENCY_VERSION_TO_BE_INSTALLED','DEPENDENCY_NOT_GOING_TO_BE_INSTALLED',
 'CONFLICTS_WITH_INSTALLED_OR_CANDIDATE','BROKEN_PACKAGE_SUMMARY','HELD_PACKAGE_SUMMARY',
 'GENERIC_APT_ERROR_BENIGN_WRAPPER','UNSUPPORTED_RELEVANT_USER_ERROR',
 'DEPENDENCY_VERSION_INSTALLED','DEPENDENCY_NOT_INSTALLED')
WRAPPERS=(
 'Some packages could not be installed. This may mean that you have',
 'requested an impossible situation or if you are using the unstable',
 'distribution that some required packages have not yet been created',
 'or been moved out of Incoming.',
 'The following information may help to resolve the situation:',
 'The following packages have unmet dependencies:')
SUMMARIES={
 'E: Broken packages':('BROKEN_PACKAGE_SUMMARY','BROKEN_SUMMARY_NOT_ROOT_CAUSE'),
 'E: Unable to correct dependencies':('BROKEN_PACKAGE_SUMMARY','DEPENDENCY_SUMMARY_NOT_ROOT_CAUSE'),
 "E: Unmet dependencies. Try 'apt --fix-broken install' with no packages (or specify a solution).":('BROKEN_PACKAGE_SUMMARY','BROKEN_SUMMARY_NOT_ROOT_CAUSE'),
 'E: Error, pkgProblemResolver::Resolve generated breaks, this may be caused by held packages.':('HELD_PACKAGE_SUMMARY','HELD_SUMMARY_NOT_ROOT_CAUSE'),
 'E: Unable to correct problems, you have held broken packages.':('HELD_PACKAGE_SUMMARY','HELD_SUMMARY_NOT_ROOT_CAUSE')}
# Prefix text is not a generic E: exception: only exact source-confirmed wrappers.
PROGRESS=('Reading package lists... Done','Building dependency tree... Done',
 'Building dependency tree...','Reading state information... Done',
 'Reading state information...','Reading package lists...')

class UserParser:
    def __init__(self,ctx):
        self.ctx=ctx;self.evidence=[];self.conflicts=[];self.counts={x:0 for x in FAMILIES}
        self.parent=None;self.kind=None;self.awaiting_alternative=False;self.line=''
    def fail(self,reason):
        count=sum(x.split(':')[0] in self.ctx['known'] for x in re.findall(r'(?<![\w.+-])'+P+r'(?![\w.+-])',self.line))
        raise DebugStop(reason,'UNSUPPORTED_RELEVANT_USER_ERROR',count)
    def pkg(self,value):
        if not re.fullmatch(P,value):self.fail('MALFORMED_PACKAGE')
        name=value.split(':')[0]
        if name not in self.ctx['known']:self.fail('UNKNOWN_PACKAGE_TOKEN')
        return name
    def ver(self,name,value,required=False):
        if not re.fullmatch(V,value):self.fail('MALFORMED_VERSION')
        allowed=self.ctx['versions'].get(name,set())
        if required:allowed=allowed|{x[4] for x in self.ctx['constraints'] if x[2]==name}
        if value not in allowed:self.fail('UNVERIFIED_VERSION')
        return value
    def add(self,family,reason,**fields):
        self.counts[family]+=1
        row={'syntax_family':family,'fixed_reason':reason,**fields};self.evidence.append(row)
        if len(self.evidence)>500:self.fail('EVIDENCE_BOUND_EXCEEDED')
        return row
    def line_parse(self,line):
        self.line=line;s=line.strip()
        if not s:return True
        if len(line)>2048:self.fail('LINE_BOUND_EXCEEDED')
        if s in WRAPPERS:
            if self.awaiting_alternative:self.fail('ALTERNATIVE_INCOMPLETE')
            self.parent=None;self.kind=None
            self.add('GENERIC_APT_ERROR_BENIGN_WRAPPER','SOURCE_CONFIRMED_WRAPPER_NOT_ROOT_CAUSE');return True
        if s in SUMMARIES:
            if self.awaiting_alternative:self.fail('ALTERNATIVE_INCOMPLETE')
            family,reason=SUMMARIES[s];self.add(family,reason);return True
        m=re.fullmatch(r'E: Internal Error, pkgProblemResolver::ResolveByKeep is looping on package ('+P+r')\.',s)
        if m:
            self.add('BROKEN_PACKAGE_SUMMARY','SOURCE_CONFIRMED_LOOP_SUMMARY_NOT_DEPENDENCY_CONFLICT',package=self.pkg(m[1]));return True
        m=re.fullmatch(r"E: Version '("+V+r")' for '("+P+r")' was not found",s)
        if m:
            name=self.pkg(m[2]);self.ver(name,m[1],required=True)
            self.add('DEPENDENCY_VERSION_NOT_AVAILABLE','SOURCE_CONFIRMED_VERSION_LOOKUP_ERROR_NOT_CONFLICT',package=name,required_version=m[1]);return True
        # A source header may have no dependency if no install version exists.
        m=re.fullmatch(r'('+P+r') :(?: (.*))?',s)
        if m:
            if self.awaiting_alternative:self.fail('ALTERNATIVE_INCOMPLETE')
            self.parent=self.pkg(m[1]);self.kind=None;body=m[2]
            if not body:
                self.add('BROKEN_PACKAGE_SUMMARY','PACKAGE_HEADER_ONLY_NOT_CONFLICT',package=self.parent);return True
        elif re.match(r'(?:'+REL+r'): ',s) or self.awaiting_alternative:
            if self.parent is None:self.fail('MISSING_PARENT_PACKAGE')
            if not line.startswith(' '):self.fail('CONTINUATION_LAYOUT_UNSUPPORTED')
            body=s
        else:return False
        if re.fullmatch(r'(?:'+REL+r'):',body):self.fail('MISSING_DEPENDENCY_TOKEN')
        m=re.fullmatch(r'('+REL+r'): (.*)',body)
        if m:
            if self.awaiting_alternative:self.fail('ALTERNATIVE_INCOMPLETE')
            self.kind=m[1].replace('Pre-Depends','PreDepends');body=m[2]
        elif not self.awaiting_alternative:self.fail('MISSING_RELATION_TOKEN')
        if self.kind is None:self.fail('MISSING_RELATION_TOKEN')
        alternative=body.endswith(' or')
        if alternative:body=body[:-3]
        m=re.fullmatch(r'('+P+r')(?: \(('+OP+r') ('+V+r')\))?(?: (.*))?',body)
        if not m:self.fail('UNSUPPORTED_DEPENDENCY_SYNTAX')
        token,op,required,tail=m.groups();dep=self.pkg(token)
        key=(self.parent,self.kind,dep,op,required)
        if key not in self.ctx['constraints']:self.fail('SIGNED_METADATA_MISMATCH')
        if required:self.ver(dep,required,required=True)
        member=True in self.ctx['alternatives'].get(key,set())
        if (alternative or self.awaiting_alternative) and not member:self.fail('SIGNED_ALTERNATIVE_MISMATCH')
        if tail and tail.startswith('('):self.fail('MALFORMED_VERSION')
        if tail=='but it is not installable':family='DEPENDENCY_NOT_INSTALLABLE';reason='SIGNED_RELATION_APT_NOT_INSTALLABLE_STATEMENT'
        elif tail=='but it is not going to be installed':family='DEPENDENCY_NOT_GOING_TO_BE_INSTALLED';reason='SIGNED_RELATION_APT_SELECTION_STATEMENT'
        elif tail=='but it is not installed':family='DEPENDENCY_NOT_INSTALLED';reason='SIGNED_RELATION_NOT_INSTALLED_STATEMENT'
        else:
            selected=re.fullmatch(r'but ('+V+r') is (to be installed|installed)',tail or '')
            if not selected:self.fail('UNSUPPORTED_DEPENDENCY_SUFFIX')
            observed=self.ver(dep,selected[1])
            if selected[2]=='installed' and self.ctx['installed'].get(dep,{}).get('Version')!=observed:self.fail('INSTALLED_VERSION_MISMATCH')
            family='DEPENDENCY_VERSION_TO_BE_INSTALLED' if selected[2]=='to be installed' else 'DEPENDENCY_VERSION_INSTALLED'
            reason='SIGNED_RELATION_VERIFIED_OBSERVED_VERSION'
        if self.kind in ('Conflicts','Breaks'):family='CONFLICTS_WITH_INSTALLED_OR_CANDIDATE'
        row=self.add(family,reason,package=self.parent,dependency_package=dep,relation_kind=self.kind,
         version_operator=op,required_version=required,
         installed_version=self.ctx['installed'].get(dep,{}).get('Version'),candidate_version=self.ctx['candidates'].get(dep))
        self.conflicts.append(row)
        if member:self.add('GENERIC_APT_ERROR_BENIGN_WRAPPER','SIGNED_ALTERNATIVE_MEMBER_NOT_PROVIDER_PROOF')
        self.awaiting_alternative=alternative
        if len(self.conflicts)>100:self.fail('CONFLICT_BOUND_EXCEEDED')
        return True
    def finish(self):
        if self.awaiting_alternative:self.fail('ALTERNATIVE_INCOMPLETE')


def parse_debug(stderr,ctx,stdout='',return_code=None):
    if not isinstance(stderr,str) or not isinstance(stdout,str) or len(stderr.encode())>65536 or len(stdout.encode())>2000000:
        raise DebugStop('OUTPUT_BOUND_EXCEEDED','UNSUPPORTED_RELEVANT_USER_ERROR')
    user=UserParser(ctx);debug=[]
    # Classify/filter before parsing: unrelated resolver lines stay with frozen 004F.
    for line in stderr.splitlines():
        if not line.strip():continue
        if user.line_parse(line):continue
        if base.classify(line)=='USER_FACING_DEPENDENCY_ERROR' or line.lstrip().startswith(('E:','W:','N:','D:')):user.fail('UNSUPPORTED_RELEVANT_USER_ERROR')
        debug.append(line)
    user.finish()
    old=base.parse_debug('\n'.join(debug),ctx)
    # CLI ShowBroken uses c1out. Outside its user-error section only exact known
    # startup progress is skipped. rc0 transaction stdout stays untrusted/non-proof.
    entered=False
    for line in stdout.splitlines():
        if not line.strip():continue
        s=line.strip()
        relevant=s in WRAPPERS or s in SUMMARIES or s.startswith('E:') or re.match(P+r' :',s)
        if relevant:entered=True
        if entered:
            if not user.line_parse(line):user.fail('UNSUPPORTED_RELEVANT_USER_ERROR')
        elif return_code==100 and s not in PROGRESS:
            user.line=line;user.fail('UNSUPPORTED_USER_OUTPUT_PREAMBLE')
        elif re.search(r'(?:'+REL+r'):',s):
            user.line=line;user.fail('MISSING_PARENT_PACKAGE')
    user.finish()
    evidence=old['evidence']+user.evidence;conflicts=old['conflicts']+user.conflicts
    if len(evidence)>500 or len(conflicts)>100:raise DebugStop('EVIDENCE_BOUND_EXCEEDED','UNSUPPORTED_RELEVANT_USER_ERROR')
    return {'parsed':True,'syntax_family_counts':old['syntax_family_counts'],
      'user_error_family_counts':user.counts,'evidence':evidence,'conflicts':conflicts,
      'proof':False,'install_authorized':False}
