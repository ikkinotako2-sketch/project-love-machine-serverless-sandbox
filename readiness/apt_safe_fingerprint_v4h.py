"""Lossy fixed-enum structural diagnostic; no raw text, hashes or I/O.

This changes observation only. Unknown user errors still stop. A fingerprint is
not a source template identification, a dependency conflict, or transaction proof.
"""
import re
import apt_user_error_v4g as g
base=g.base
context=base.context
REASONS=('OUTPUT_BOUND_EXCEEDED','LINE_BOUND_EXCEEDED','MALFORMED_PACKAGE',
 'UNKNOWN_PACKAGE_TOKEN','MALFORMED_VERSION','UNVERIFIED_VERSION',
 'PRETTY_PACKAGE_SYNTAX_UNSUPPORTED','INSTALLED_VERSION_MISMATCH',
 'EVIDENCE_BOUND_EXCEEDED','CONFLICT_BOUND_EXCEEDED','SIGNED_METADATA_MISMATCH',
 'ALTERNATIVE_INCOMPLETE','MISSING_PARENT_PACKAGE','CONTINUATION_LAYOUT_UNSUPPORTED',
 'MISSING_DEPENDENCY_TOKEN','MISSING_RELATION_TOKEN','UNSUPPORTED_DEPENDENCY_SYNTAX',
 'SIGNED_ALTERNATIVE_MISMATCH','UNSUPPORTED_DEPENDENCY_SUFFIX',
 'UNSUPPORTED_RELEVANT_USER_ERROR','UNSUPPORTED_USER_OUTPUT_PREAMBLE',
 'UNSUPPORTED_RELEVANT_SYNTAX')
ENUMS={
 'stream':('STDOUT','STDERR'),
 'section':('PREAMBLE','SHOW_BROKEN','CONTINUATION','GLOBAL_ERROR','RESOLVER_DEBUG','UNKNOWN'),
 'prefix_class':('E_PREFIX','W_PREFIX','N_PREFIX','D_PREFIX','PACKAGE_HEADER','RELATION_CONTINUATION','OTHER'),
 'relation_token':('NONE','DEPENDS','PREDEPENDS','CONFLICTS','BREAKS'),
 'version_operator':('NONE','EQ','GE','LE','LT','GT'),
 'indent_bucket':('NONE','SMALL','LARGE'),
 'suffix_family':('SOURCE_CONFIRMED_NOT_INSTALLABLE','SOURCE_CONFIRMED_NOT_GOING_TO_BE_INSTALLED',
  'SOURCE_CONFIRMED_NOT_INSTALLED','SOURCE_CONFIRMED_VERSION_TO_BE_INSTALLED',
  'SOURCE_CONFIRMED_VERSION_INSTALLED','SOURCE_CONFIRMED_SUMMARY',
  'SOURCE_CONFIRMED_PACKAGE_HEADER','SOURCE_CONFIRMED_WRAPPER','SOURCE_CONFIRMED_VERSION_LOOKUP','UNKNOWN'),
 'fixed_reason':REASONS,
 'syntax_family':tuple(base.FAMILIES)+('UNSUPPORTED_RELEVANT_USER_ERROR',),
 'relevance':('DEPENDENCY_DECISION_OR_UNKNOWN',)}
BOOLS=('has_parent_package','has_dependency_package','has_version_token')


def fingerprint(line,ctx,stream,section='UNKNOWN',parent=None,reason='UNSUPPORTED_RELEVANT_USER_ERROR',family='UNSUPPORTED_RELEVANT_USER_ERROR'):
    # No input substring is returned. Unknown reason/family is replaced by a fixed enum.
    line=line if isinstance(line,str) else ''
    s=line.strip();prefix='OTHER';header=re.match(r'^('+g.P+r')\s*:(?:\s|$)',s)
    relation=re.match(r'^(?:'+g.REL+r'):',s)
    for label in ('E','W','N','D'):
        if s.startswith(label+':'):
            prefix=label+'_PREFIX';section='GLOBAL_ERROR';break
    else:
        if header:prefix='PACKAGE_HEADER';section='SHOW_BROKEN'
        elif relation:prefix='RELATION_CONTINUATION';section='CONTINUATION'
        elif line[:1].isspace() and section=='GLOBAL_ERROR':section='CONTINUATION'
    body=s[header.end():] if header else s
    rel=re.match(r'^('+g.REL+r'):\s*(.*)',body)
    token='NONE';dep=None;required=None;operator='NONE'
    if rel:
        token={'Depends':'DEPENDS','PreDepends':'PREDEPENDS','Pre-Depends':'PREDEPENDS','Conflicts':'CONFLICTS','Breaks':'BREAKS'}[rel[1]]
        dep=re.match(r'^('+g.P+r')(?:\s+\(('+g.OP+r')\s+('+g.V+r')\))?',rel[2])
        if dep:
            required=dep[3]
            if dep[2]:operator={'=':'EQ','>=':'GE','<=':'LE','<<':'LT','>>':'GT'}[dep[2]]
    count=min(100,sum(x.split(':')[0] in ctx['known'] for x in re.findall(r'(?<![\w.+-])'+g.P+r'(?![\w.+-])',line)))
    suffix='UNKNOWN'
    for tail,enum in (
      ('but it is not installable','SOURCE_CONFIRMED_NOT_INSTALLABLE'),
      ('but it is not going to be installed','SOURCE_CONFIRMED_NOT_GOING_TO_BE_INSTALLED'),
      ('but it is not installed','SOURCE_CONFIRMED_NOT_INSTALLED')):
        if rel and s.endswith(tail):suffix=enum;break
    if rel and re.search(r' but '+g.V+r' is to be installed$',s):suffix='SOURCE_CONFIRMED_VERSION_TO_BE_INSTALLED'
    elif rel and re.search(r' but '+g.V+r' is installed$',s):suffix='SOURCE_CONFIRMED_VERSION_INSTALLED'
    elif s in g.SUMMARIES or re.fullmatch(r'E: Internal Error, pkgProblemResolver::ResolveByKeep is looping on package '+g.P+r'\.',s):suffix='SOURCE_CONFIRMED_SUMMARY'
    elif header and not body:suffix='SOURCE_CONFIRMED_PACKAGE_HEADER'
    elif s in g.WRAPPERS:suffix='SOURCE_CONFIRMED_WRAPPER'
    elif re.fullmatch(r"E: Version '"+g.V+r"' for '"+g.P+r"' was not found",s):suffix='SOURCE_CONFIRMED_VERSION_LOOKUP'
    indent=len(line)-len(line.lstrip(' \t'))
    parent_name=header[1].split(':')[0] if header else parent
    return dict(stream=stream if stream in ENUMS['stream'] else 'STDERR',
      section=section if section in ENUMS['section'] else 'UNKNOWN',prefix_class=prefix,
      known_package_tokens_count=count,relation_token=token,version_operator=operator,
      has_parent_package=parent_name in ctx['known'],
      has_dependency_package=bool(dep and dep[1].split(':')[0] in ctx['known']),
      has_version_token=bool(required or re.search(r'(?:\(|but |Version \x27)'+g.V+r'(?:\)| is |\x27)',s)),
      indent_bucket='NONE' if indent==0 else 'SMALL' if indent<8 else 'LARGE',
      suffix_family=suffix,fixed_reason=reason if reason in REASONS else 'UNSUPPORTED_RELEVANT_USER_ERROR',
      syntax_family=family if family in ENUMS['syntax_family'] else 'UNSUPPORTED_RELEVANT_USER_ERROR',
      relevance='DEPENDENCY_DECISION_OR_UNKNOWN')


class DebugStop(base.DebugStop):
    def __init__(self,public):
        super().__init__(public['fixed_reason'],public['syntax_family'],public['known_package_tokens_count'])
        self.public=dict(public)


class UserParser(g.UserParser):
    def __init__(self,ctx,stream):
        super().__init__(ctx);self.stream=stream
        self.section='PREAMBLE' if stream=='STDOUT' else 'RESOLVER_DEBUG'
    def fail(self,reason):
        raise DebugStop(fingerprint(self.line,self.ctx,self.stream,self.section,self.parent,reason)) from None
    def line_parse(self,line):
        self.line=line
        # Remember only lossy section state, never a source line or stream-crossing parent.
        shape=fingerprint(line,self.ctx,self.stream,self.section,self.parent)
        self.section=shape['section']
        if line.strip() in g.WRAPPERS:self.section='SHOW_BROKEN'
        return super().line_parse(line)


def parse_debug(stderr,ctx,stdout='',return_code=None):
    evidence=[];conflicts=[];counts=dict.fromkeys(base.FAMILIES,0);ucounts=dict.fromkeys(g.FAMILIES,0)
    for stream,raw,bound in (('STDERR',stderr,65536),('STDOUT',stdout,2000000)):
        if not isinstance(raw,str) or len(raw.encode())>bound:
            raise DebugStop(fingerprint('',ctx,stream,reason='OUTPUT_BOUND_EXCEEDED'))
        user=UserParser(ctx,stream);entered=False
        for line in raw.splitlines():
            if not line.strip():continue
            user.line=line;s=line.strip()
            if len(line)>2048:user.fail('LINE_BOUND_EXCEEDED')
            if stream=='STDERR':
                if user.line_parse(line):continue
                if base.classify(line)=='USER_FACING_DEPENDENCY_ERROR' or s.startswith(('E:','W:','N:','D:')):user.fail('UNSUPPORTED_RELEVANT_USER_ERROR')
                try:old=base.parse_debug(line,ctx)
                except base.DebugStop as error:
                    raise DebugStop(fingerprint(line,ctx,stream,user.section,user.parent,error.evidence()['fixed_reason'],error.evidence()['syntax_family'])) from None
                evidence.extend(old['evidence']);conflicts.extend(old['conflicts'])
                for key,value in old['syntax_family_counts'].items():counts[key]+=value
            else:
                relevant=s in g.WRAPPERS or s in g.SUMMARIES or s.startswith(('E:','W:','N:','D:')) or re.match(g.P+r' :',s)
                if relevant:entered=True
                if entered:
                    if not user.line_parse(line):user.fail('UNSUPPORTED_RELEVANT_USER_ERROR')
                elif return_code==100 and s not in g.PROGRESS:user.fail('UNSUPPORTED_USER_OUTPUT_PREAMBLE')
                elif re.search(r'(?:'+g.REL+r'):',s):user.fail('MISSING_PARENT_PACKAGE')
            if len(evidence)+len(user.evidence)>500 or len(conflicts)+len(user.conflicts)>100:user.fail('EVIDENCE_BOUND_EXCEEDED')
        user.finish()
        evidence.extend(user.evidence);conflicts.extend(user.conflicts)
        for key,value in user.counts.items():ucounts[key]+=value
        if len(evidence)>500 or len(conflicts)>100:user.fail('EVIDENCE_BOUND_EXCEEDED')
    return dict(parsed=True,syntax_family_counts=counts,user_error_family_counts=ucounts,
                evidence=evidence,conflicts=conflicts,proof=False,install_authorized=False)
