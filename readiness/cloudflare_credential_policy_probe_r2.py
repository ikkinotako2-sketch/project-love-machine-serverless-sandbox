"""Two-GET credential metadata probe. Import has no IO; never prints raw data."""
import hashlib
import json
import re
from pathlib import Path

IDENTITY = 'youtube-cloudflare-credential-policy-readonly-20261006-r2'
ACCOUNT = '6c8ccd6aface937ab5dabef61cb64534'
PARENT = 'a998f9e5bff137dfe2e3843ff081b862fd24e484'
SECRET_NAME = 'PLM_CF_WORKER_API_TOKEN'
PLAN = 'readiness/cloudflare-credential-policy-readonly-r2-plan.json'
WORKFLOW = '.github/workflows/plm-cloudflare-credential-policy-readonly-r2-once.yml'
MARKER = 'audit-evidence/consumed/'+IDENTITY+'.json'
SCHEMA = 'readiness/cloudflare-credential-policy-r2-marker.schema.json'
HEX = re.compile(r'[a-f0-9]{32}')
SHA = re.compile(r'[a-f0-9]{64}')
GROUPS = {'Workers Scripts Read','Workers Scripts Write','Workers Routes Read',
          'Workers Routes Write','Queues Read','Queues Write','Content Read-Only',
          'API Tokens Read','Account API Tokens Read','Individual Workers Editor'}

class Stop(Exception): pass

def need(ok, code):
    if not ok: raise Stop(code)

def digest(raw): return hashlib.sha256(raw).hexdigest()

def decode(raw):
    need(type(raw) is bytes and len(raw)<=262144,'RESPONSE_LIMIT_STOP')
    def pairs(items):
        out={}
        for key,value in items:
            need(key not in out,'DUPLICATE_JSON_STOP');out[key]=value
        return out
    try: return json.loads(raw.decode('utf-8'),object_pairs_hook=pairs)
    except Stop: raise
    except Exception: raise Stop('RESPONSE_SHAPE_STOP') from None

def resources(raw):
    # Unknown granular selectors are hashed, never promoted to account permission.
    need(type(raw) is dict and len(raw)<=64,'RESOURCE_SHAPE_STOP')
    safe={};complete=True
    for key,value in raw.items():
        if type(key) is str and re.fullmatch(r'com\.cloudflare\.api\.(?:account(?:\.zone)?|user)\.(?:[a-f0-9]{32}|\*)',key) and value=='*':
            safe[key]='*'
        else:
            complete=False
    return safe,complete

def sanitize_details(raw, token_id):
    need(raw.get('id')==token_id,'TOKEN_ID_BINDING_STOP')
    need(raw.get('status') in ('active','disabled','expired'),'TOKEN_STATUS_STOP')
    policies=raw.get('policies');need(type(policies) is list and len(policies)<=64,'POLICY_SHAPE_STOP')
    out={'id':token_id,'status':raw['status'],'expiry_present':raw.get('expires_on') is not None,'policies':[]}
    for policy in policies:
        need(type(policy) is dict and policy.get('effect') in ('allow','deny'),'POLICY_SHAPE_STOP')
        groups=policy.get('permission_groups');need(type(groups) is list and len(groups)<=128,'GROUP_SHAPE_STOP')
        safe_groups=[]
        for group in groups:
            need(type(group) is dict and type(group.get('id')) is str and HEX.fullmatch(group['id']) and type(group.get('name')) is str,'GROUP_SHAPE_STOP')
            name=group['name'];need(len(name.encode())<=256,'GROUP_SHAPE_STOP')
            safe_groups.append({'id':group['id'],**({'name':name} if name in GROUPS else {'unmapped_name_sha256':digest(name.encode())})})
        scope,complete=resources(policy.get('resources'))
        out['policies'].append({'effect':policy['effect'],'permission_groups':safe_groups,'resources':scope,'resource_scope_complete':complete})
    return out

def evaluate(details):
    out=dict.fromkeys(('worker_source','worker_schedules','queues'),'UNVERIFIED_PERMISSION_OR_SCOPE')
    out['routes']='UNVERIFIED_ZONE_ID_OR_PERMISSION'
    out['d1']='SEPARATE_EXISTING_EVIDENCE_NOT_EVALUATED'
    if details['status']!='active' or any(p['effect']=='deny' or not p['resource_scope_complete'] for p in details['policies']): return out
    allowed=set()
    for p in details['policies']:
        if p['resources'].get('com.cloudflare.api.account.'+ACCOUNT)=='*' or p['resources'].get('com.cloudflare.api.account.*')=='*':
            allowed.update(g.get('name') for g in p['permission_groups'])
    if allowed & {'Workers Scripts Read','Workers Scripts Write'}:
        out['worker_source']=out['worker_schedules']='POLICY_READ_CAPABILITY_CONFIRMED'
    if allowed & {'Queues Read','Queues Write','Workers Scripts Read','Workers Scripts Write'}:
        out['queues']='POLICY_READ_CAPABILITY_CONFIRMED'
    return out

class TwoGet:
    def __init__(self, token_type, transport):
        need(token_type=='ACCOUNT_OWNED','TOKEN_TYPE_UNVERIFIED')
        self.root='/accounts/'+ACCOUNT+'/tokens'
        self.transport=transport;self.count=0;self.bound_id=None
    def get(self, method, path):
        expected=self.root+'/verify' if self.count==0 else self.root+'/'+str(self.bound_id)
        need(method=='GET' and path==expected and self.count<2 and (self.count==0 or self.bound_id is not None),'REQUEST_GATE_STOP')
        self.count+=1  # consumed BEFORE the transport; exceptions are never retried
        try: status,body=self.transport(method,path)
        except Exception: raise Stop('TRANSPORT_UNKNOWN_NO_RETRY') from None
        if status==403: raise Stop('TOKEN_POLICY_METADATA_NOT_READABLE_WITH_CURRENT_CREDENTIAL' if self.count==2 else 'VERIFY_FORBIDDEN_STOP')
        if status==404: raise Stop('TOKEN_ENDPOINT_404_NO_FALLBACK')
        need(status==200,'HTTP_STATUS_STOP')
        data=decode(body);need(type(data) is dict and data.get('success') is True and type(data.get('result')) is dict,'PROVIDER_RESPONSE_STOP')
        need('result_info' not in data,'UNEXPECTED_PAGINATION_STOP')
        result=data['result']
        if self.count==1:
            need(type(result.get('id')) is str and HEX.fullmatch(result['id']),'TOKEN_ID_STOP')
            need(result.get('status')=='active','TOKEN_NOT_ACTIVE_STOP')
            self.bound_id=result['id']
        return result

def probe(token_type, transport):
    gate=None
    out={'identity':IDENTITY,'token_type':token_type,'cloudflare_requests':0,'maximum_requests':2,'maximum_writes':0,'retry':0,'resume':0,'redirect':0,'raw_retention':0,'worker_inspection_permitted':False}
    try:
        gate=TwoGet(token_type,transport)
        verify=gate.get('GET',gate.root+'/verify')
        out['verify']={'id':gate.bound_id,'status':'active','expiry_present':verify.get('expires_on') is not None}
        details=gate.get('GET',gate.root+'/'+gate.bound_id)
        out['details']=sanitize_details(details,gate.bound_id)
        need(out['details']['status']=='active','TOKEN_NOT_ACTIVE_STOP')
        out['readiness']=evaluate(out['details']);out['result']='TOKEN_POLICY_METADATA_READ_SUCCESS_STOP_BEFORE_WORKER_INSPECTION'
    except Stop as e: out['result']=str(e)
    except Exception: out['result']='UNVERIFIED_RESPONSE_STOP'
    out['cloudflare_requests']=gate.count if gate else 0
    return out

def validate_marker(marker,plan,before,files):
    need(type(marker) is dict and set(marker)=={'identity','state','prepared_commit_sha','plan_sha256','workflow_sha256','helper_sha256'},'MARKER_SCHEMA_STOP')
    need(marker['identity']==IDENTITY and marker['state']=='CONSUMED_BEFORE_REMOTE' and marker['prepared_commit_sha']==before and re.fullmatch('[a-f0-9]{40}',before),'MARKER_BINDING_STOP')
    need(plan['identity']==IDENTITY and plan['exact_parent_sha']==PARENT and plan['token_type']=='ACCOUNT_OWNED' and plan['credential_secret_name']==SECRET_NAME,'PLAN_BINDING_STOP')
    need(plan.get('target_account')==ACCOUNT and plan.get('verify_endpoint')=='/accounts/'+ACCOUNT+'/tokens/verify' and plan.get('details_endpoint_template')=='/accounts/'+ACCOUNT+'/tokens/{exact_verify_result_id}','PLAN_ENDPOINT_STOP')
    need(plan.get('maximum_requests')==2 and plan.get('maximum_writes')==0 and all(plan.get(k)==0 for k in ('retry','resume','redirect','raw_retention')) and plan.get('no_retry') is True and plan.get('no_resume') is True and plan.get('pagination') is False,'PLAN_LIMITS_STOP')
    need(plan['marker']['schema_path']==SCHEMA and digest(files[SCHEMA])==plan['marker']['schema_sha256'],'MARKER_SCHEMA_HASH_STOP')
    for key,path in [('plan_sha256',PLAN),('workflow_sha256',WORKFLOW),('helper_sha256','readiness/cloudflare_credential_policy_probe_r2.py')]:
        need(type(marker[key]) is str and SHA.fullmatch(marker[key]) and digest(files[path])==marker[key],'MARKER_HASH_STOP')
    need(plan['workflow_sha256']==marker['workflow_sha256'] and plan['helper_sha256']==marker['helper_sha256'],'PLAN_HASH_STOP')

def live_transport(token):
    import http.client
    need(type(token) is str and bool(token) and not any(c in token for c in '\r\n'),'CREDENTIAL_MISSING_STOP')
    def get(method,path):
        conn=http.client.HTTPSConnection('api.cloudflare.com',timeout=15)
        try:
            conn.request(method,'/client/v4'+path,headers={'Authorization':'Bearer '+token,'Accept':'application/json'})
            response=conn.getresponse()
            # No redirects, retry, pagination or secondary network operation.
            if response.status!=200:return response.status,b''
            size=response.getheader('Content-Length')
            need(size is None or (size.isdigit() and int(size)<=262144),'RESPONSE_LIMIT_STOP')
            raw=response.read(262145);need(len(raw)<=262144,'RESPONSE_LIMIT_STOP')
            return response.status,raw
        finally: conn.close()
    return get

def main():
    import os
    env=os.environ
    try:
        need(all(env.get(k)=='true' for k in ('TEST_ONLY','DRY_RUN','NO_PUBLISH','EMERGENCY_STOP')),'SAFE_FLAGS_STOP')
        need(env.get('GITHUB_RUN_ATTEMPT')=='1' and env.get('GITHUB_EVENT_NAME')=='push' and env.get('GITHUB_REPOSITORY')=='ikkinotako2-sketch/project-love-machine-serverless-sandbox' and env.get('GITHUB_REF')=='refs/heads/plm-offline-readiness-v1-20261002','EXECUTION_CONTEXT_STOP')
        files={p:Path(p).read_bytes() for p in (PLAN,WORKFLOW,'readiness/cloudflare_credential_policy_probe_r2.py',SCHEMA)}
        plan=json.loads(files[PLAN]);marker=json.loads(Path(MARKER).read_bytes())
        validate_marker(marker,plan,env['PLM_APPROVED_BEFORE'],files)
        # Token is used only by the authorized future runner; never returned/logged.
        out=probe(plan['token_type'],live_transport(env.get(SECRET_NAME)))
    except Stop as e: out={'identity':IDENTITY,'result':'PRE_REMOTE_GATE_STOP','gate_code':str(e),'cloudflare_requests':0,'maximum_writes':0,'raw_retention':0}
    except Exception: out={'identity':IDENTITY,'result':'PRE_REMOTE_GATE_STOP','gate_code':'UNVERIFIED_LOCAL_GATE_STOP','cloudflare_requests':0,'maximum_writes':0,'raw_retention':0}
    print(json.dumps(out,sort_keys=True))
    # 403/404 are safe readiness results, not opportunities to rerun.
    return 0

if __name__=='__main__':raise SystemExit(main())
