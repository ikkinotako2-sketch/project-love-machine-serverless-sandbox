"""Pure fixed-field inspection; no exec/eval, subprocess, paths in public evidence."""
import json
import re
from pathlib import Path
from one_shot_executor import Stop

FIELDS=(
 ('STATE_STATUS','Dir::State::status'),('STATE_LISTS','Dir::State::lists'),
 ('SOURCE_LIST','Dir::Etc::sourcelist'),('SOURCE_PARTS','Dir::Etc::sourceparts'),
 ('CONFIG_MAIN','Dir::Etc::main'),('CONFIG_PARTS','Dir::Etc::parts'),
 ('PREFERENCES','Dir::Etc::preferences'),('PREFERENCE_PARTS','Dir::Etc::preferencesparts'),
 ('TRUSTED_KEYRING','Dir::Etc::trusted'),('TRUSTED_PARTS','Dir::Etc::trustedparts'),
 ('CACHE_DIR','Dir::Cache'),('PACKAGE_CACHE','Dir::Cache::pkgcache'),('SOURCE_CACHE','Dir::Cache::srcpkgcache'),
 ('DPKG_BINARY','Dir::Bin::dpkg'),('ARCHITECTURE','APT::Architecture'),
 ('INSTALL_RECOMMENDS','APT::Install-Recommends'),('INSTALL_SUGGESTS','APT::Install-Suggests'),
 ('DOWNLOAD','APT::Get::Download'),('SIMULATE','APT::Get::Simulate'),('RETRIES','Acquire::Retries'),
 ('INSECURE_REPOSITORIES','Acquire::AllowInsecureRepositories'),('UNAUTHENTICATED','APT::Get::AllowUnauthenticated'))
EXTRA=('ARCHITECTURES','DPKG_HOOKS','ROOT_DIR','BINARY_OVERRIDES','CONFIG_INSPECTION')
IDS=tuple(x[0] for x in FIELDS)+EXTRA
REASONS=('FIELD_MISSING','FIELD_VALUE_MISMATCH','SCALAR_DUPLICATE','LIST_FORMAT_UNSUPPORTED',
 'FORBIDDEN_HOOK_PRESENT','HOST_SOURCE_LEAK','MALFORMED_CONFIG_OUTPUT','QUERY_FAILED')
CODE='RUNTIME_APT_CONFIG_FAILED'

class ConfigStop(Stop):
    def __init__(self,field_id,reason):
        # Invalid caller input cannot become report text.
        self.field_id=field_id if field_id in IDS else 'CONFIG_INSPECTION'
        self.reason=reason if reason in REASONS else 'MALFORMED_CONFIG_OUTPUT'
        super().__init__(CODE)
    def evidence(self):return {'field_id':self.field_id,'reason':self.reason,'matched':False}


def check(ok,field_id,reason):
    if not ok:raise ConfigStop(field_id,reason)


def expected_scalars(directory,keyring):
    from apt_startup_v4c import config_expected
    expected=config_expected(directory,keyring)
    return {field_id:expected[key.lower()] for field_id,key in FIELDS}


def scalar_query(field_id,raw,expected,return_code=0):
    check(field_id in dict(FIELDS),field_id,'MALFORMED_CONFIG_OUTPUT')
    check(return_code==0,field_id,'QUERY_FAILED')
    check(isinstance(raw,str) and len(raw.encode())<=65536,field_id,'MALFORMED_CONFIG_OUTPUT')
    lines=raw.splitlines()
    check(bool(lines),field_id,'FIELD_MISSING')
    check(len(lines)==1,field_id,'SCALAR_DUPLICATE')
    # Shell assignment is treated as inert data. No eval, shell or substitutions.
    m=re.fullmatch(r"PLM_VALUE='([^'\n\r]*)'",lines[0])
    check(m is not None,field_id,'MALFORMED_CONFIG_OUTPUT')
    observed=m[1]
    reason='HOST_SOURCE_LEAK' if field_id in ('SOURCE_LIST','SOURCE_PARTS','CONFIG_MAIN','CONFIG_PARTS','PREFERENCES','PREFERENCE_PARTS','TRUSTED_KEYRING','TRUSTED_PARTS') and observed.startswith('/etc/apt') else 'FIELD_VALUE_MISMATCH'
    check(observed==expected,field_id,reason)
    return {'field_id':field_id,'matched':True}


def inspection(raw,return_code=0):
    """Supplementary list/hook/leakage inspection; scalars come only from shell queries.
    Flattened dump represents tree scopes with empty parent records and anonymous ::
    list entries. Unknown valid defaults are ignored, not echoed or used as authority.
    """
    check(return_code==0,'CONFIG_INSPECTION','QUERY_FAILED')
    check(isinstance(raw,str) and len(raw.encode())<=2_000_000,'CONFIG_INSPECTION','MALFORMED_CONFIG_OUTPUT')
    scalar_ids={key.lower():fid for fid,key in FIELDS};seen=set();architectures=[];parent_seen=False
    for line in raw.splitlines():
        if not line:continue
        m=re.fullmatch(r'([A-Za-z0-9_:./+\-]+) ("(?:[^"\\]|\\.)*");',line)
        check(m is not None,'CONFIG_INSPECTION','MALFORMED_CONFIG_OUTPUT')
        key=m[1].lower()
        try:value=json.loads(m[2])
        except Exception:raise ConfigStop('CONFIG_INSPECTION','MALFORMED_CONFIG_OUTPUT') from None
        check(isinstance(value,str),'CONFIG_INSPECTION','MALFORMED_CONFIG_OUTPUT')
        if any(token.startswith(('pre-invoke','post-invoke','pre-install-pkgs')) for token in key.split('::')):
            check(value=='','DPKG_HOOKS','FORBIDDEN_HOOK_PRESENT')
        if key=='rootdir':check(value=='','ROOT_DIR','HOST_SOURCE_LEAK')
        if key.startswith(('binary::apt-get::','binary::apt-cache::','binary::apt-config::')):
            nested=key.split('::',2)[2]
            if nested in scalar_ids or nested.startswith('apt::architectures') or nested=='rootdir':
                check(value=='','BINARY_OVERRIDES','HOST_SOURCE_LEAK' if nested.startswith('dir::') or nested=='rootdir' else 'FIELD_VALUE_MISMATCH')
        if key in scalar_ids:
            check(key not in seen,scalar_ids[key],'SCALAR_DUPLICATE');seen.add(key)
        if key=='apt::architectures':
            parent_seen=True;check(value=='','ARCHITECTURES','LIST_FORMAT_UNSUPPORTED')
        elif key=='apt::architectures::':architectures.append(value)
        elif key.startswith('apt::architectures::'):
            raise ConfigStop('ARCHITECTURES','LIST_FORMAT_UNSUPPORTED')
    check(architectures,'ARCHITECTURES','FIELD_MISSING')
    check(all(value=='amd64' for value in architectures),'ARCHITECTURES','FIELD_VALUE_MISMATCH')
    # Duplicate anonymous entries are valid list syntax, never scalar duplicates.
    return [{'field_id':'ARCHITECTURES','matched':True}, {'field_id':'DPKG_HOOKS','matched':True},
            {'field_id':'ROOT_DIR','matched':True},{'field_id':'BINARY_OVERRIDES','matched':True}]
