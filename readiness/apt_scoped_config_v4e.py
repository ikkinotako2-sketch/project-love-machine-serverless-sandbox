"""Filter keys before interpreting values. Pure; no raw/default values in evidence."""
import json
import re
from one_shot_executor import Stop
from apt_config_fields_v4d import FIELDS
CODE='RUNTIME_APT_CONFIG_FAILED'
SCOPES=('ARCHITECTURES','ROOT_DIR','DPKG_HOOKS','APT_UPDATE_HOOKS','BINARY_OVERRIDES','CONFIG_INSPECTION')
REASONS=('REQUIRED_SCOPE_MISSING','REQUIRED_SCOPE_VALUE_MISMATCH','ARCH_LIST_UNSUPPORTED',
 'FORBIDDEN_HOOK_PRESENT','HOST_SOURCE_LEAK','BINARY_OVERRIDE_CONFLICT',
 'RELEVANT_SCOPE_SYNTAX_UNSUPPORTED','DUMP_QUERY_FAILED')
KINDS=('FILTERED_DUMP','ANONYMOUS_LIST','EMPTY_OR_ABSENT','FIXED_KEY_EMPTY','FIXED_KEY_ABSENT','BINARY_SCOPE','KEY_QUERY')
KEY=r'[A-Za-z0-9_:./+\-]+'
ARCH='apt::architectures'
HOOKS={'dpkg::pre-invoke':'DPKG_HOOKS','dpkg::post-invoke':'DPKG_HOOKS',
 'dpkg::pre-install-pkgs':'DPKG_HOOKS','apt::update::pre-invoke':'APT_UPDATE_HOOKS',
 'apt::update::post-invoke':'APT_UPDATE_HOOKS','apt::update::post-invoke-success':'APT_UPDATE_HOOKS'}
BINARY=('binary::apt-get','binary::apt-cache','binary::apt-config')
SCALARS={key.lower() for fid,key in FIELDS}
PARENTS={'dir','dir::state','dir::etc','dir::cache','dir::bin','apt','apt::get','acquire','dpkg','apt::update'}

class ScopeStop(Stop):
    def __init__(self,scope,kind,reason):
        self.scope=scope if scope in SCOPES else 'CONFIG_INSPECTION'
        self.kind=kind if kind in KINDS else 'FILTERED_DUMP'
        self.reason=reason if reason in REASONS else 'RELEVANT_SCOPE_SYNTAX_UNSUPPORTED'
        super().__init__(CODE)
    def evidence(self):return {'scope_id':self.scope,'syntax_kind':self.kind,'matched':False,'fixed_reason':self.reason}


def check(ok,scope,reason,kind='FILTERED_DUMP'):
    if not ok:raise ScopeStop(scope,kind,reason)


def hook_scope(key):
    for prefix,scope in sorted(HOOKS.items(),key=lambda x:-len(x[0])):
        if key==prefix or key.startswith(prefix+'::'):return scope
    return None


def relevant(key):
    if key==ARCH or key.startswith(ARCH+'::'):return 'ARCHITECTURES',None
    if key=='rootdir' or key.startswith('rootdir::'):return 'ROOT_DIR',None
    hook=hook_scope(key)
    if hook:return hook,None
    for prefix in BINARY:
        if key==prefix:return 'BINARY_OVERRIDES',''
        if key.startswith(prefix+'::'):
            nested=key[len(prefix)+2:]
            if nested in PARENTS or nested in SCALARS or any(nested.startswith(k+'::') for k in SCALARS) or nested=='rootdir' or nested.startswith('rootdir::') or nested==ARCH or nested.startswith(ARCH+'::') or hook_scope(nested):
                return 'BINARY_OVERRIDES',nested
    return None,None


def strict_row(line,scope):
    m=re.fullmatch(r'\s*('+KEY+r')\s+("(?:[^"\\]|\\.)*");\s*',line)
    check(m is not None,scope,'RELEVANT_SCOPE_SYNTAX_UNSUPPORTED')
    try:value=json.loads(m[2])
    except Exception:raise ScopeStop(scope,'FILTERED_DUMP','RELEVANT_SCOPE_SYNTAX_UNSUPPORTED') from None
    check(isinstance(value,str),scope,'RELEVANT_SCOPE_SYNTAX_UNSUPPORTED')
    return m[1].lower(),value


def root_query(raw,return_code=0):
    check(return_code==0,'ROOT_DIR','DUMP_QUERY_FAILED','KEY_QUERY')
    check(isinstance(raw,str) and len(raw.encode())<=65536,'ROOT_DIR','RELEVANT_SCOPE_SYNTAX_UNSUPPORTED','KEY_QUERY')
    if raw=='':return {'scope_id':'ROOT_DIR','syntax_kind':'FIXED_KEY_ABSENT','matched':True,'fixed_reason':None}
    m=re.fullmatch(r"PLM_VALUE='([^'\n\r]*)'\n?",raw)
    check(m is not None,'ROOT_DIR','RELEVANT_SCOPE_SYNTAX_UNSUPPORTED','KEY_QUERY')
    check(m[1]=='','ROOT_DIR','HOST_SOURCE_LEAK' if m[1].startswith('/etc/apt') else 'REQUIRED_SCOPE_VALUE_MISMATCH','KEY_QUERY')
    return {'scope_id':'ROOT_DIR','syntax_kind':'FIXED_KEY_EMPTY','matched':True,'fixed_reason':None}


def inspect(raw,return_code=0):
    check(return_code==0,'CONFIG_INSPECTION','DUMP_QUERY_FAILED')
    check(isinstance(raw,str) and len(raw.encode())<=2_000_000,'CONFIG_INSPECTION','RELEVANT_SCOPE_SYNTAX_UNSUPPORTED')
    architectures=[]
    for line in raw.splitlines():
        # No value/delimiter parsing before relevance selection. Even unknown malformed
        # values are ignored. A relevant key followed by invalid punctuation still STOPs.
        key_match=re.match(r'\s*('+KEY+r')',line)
        if not key_match:continue
        scope,nested=relevant(key_match[1].lower())
        if scope is None:continue
        key,value=strict_row(line,scope)
        if scope=='ARCHITECTURES':
            if key==ARCH:check(value=='',scope,'ARCH_LIST_UNSUPPORTED')
            elif key==ARCH+'::':
                check(len(architectures)<1024,scope,'ARCH_LIST_UNSUPPORTED');architectures.append(value)
            else:raise ScopeStop(scope,'ANONYMOUS_LIST','ARCH_LIST_UNSUPPORTED')
        elif scope=='ROOT_DIR':
            check(key=='rootdir',scope,'RELEVANT_SCOPE_SYNTAX_UNSUPPORTED')
            check(value=='',scope,'HOST_SOURCE_LEAK' if value.startswith('/etc/apt') else 'REQUIRED_SCOPE_VALUE_MISMATCH')
        elif scope in ('DPKG_HOOKS','APT_UPDATE_HOOKS'):
            check(value=='',scope,'FORBIDDEN_HOOK_PRESENT')
        elif scope=='BINARY_OVERRIDES':
            if nested=='' or nested in PARENTS:
                check(value=='',scope,'BINARY_OVERRIDE_CONFLICT');continue
            if hook_scope(nested):check(value=='',scope,'FORBIDDEN_HOOK_PRESENT');continue
            # A leaf assignment, even empty, can shadow the verified scalar authority.
            reason='HOST_SOURCE_LEAK' if value.startswith('/etc/apt') and (nested.startswith('dir::') or nested=='rootdir') else 'BINARY_OVERRIDE_CONFLICT'
            raise ScopeStop(scope,'BINARY_SCOPE',reason)
    check(bool(architectures),'ARCHITECTURES','REQUIRED_SCOPE_MISSING','ANONYMOUS_LIST')
    check(all(v=='amd64' for v in architectures),'ARCHITECTURES','REQUIRED_SCOPE_VALUE_MISMATCH','ANONYMOUS_LIST')
    return [{'scope_id':scope,'syntax_kind':kind,'matched':True,'fixed_reason':None} for scope,kind in (
      ('ARCHITECTURES','ANONYMOUS_LIST'),('ROOT_DIR','EMPTY_OR_ABSENT'),('DPKG_HOOKS','EMPTY_OR_ABSENT'),
      ('APT_UPDATE_HOOKS','EMPTY_OR_ABSENT'),('BINARY_OVERRIDES','BINARY_SCOPE'))]
