"""Bounded one-shot read-only inspection. No IO on import; raw bytes never retained."""
import hashlib
import json
import re
from pathlib import Path

IDENTITY='youtube-worker-current-readonly-inspect-20261006-r1'
PARENT='bb13c44361b927a67245a846bc38db00c578733f'
ACCOUNT='6c8ccd6aface937ab5dabef61cb64534'
WORKER='plm-serverless-sandbox-control'
SECRET_NAME='PLM_CF_WORKER_API_TOKEN'
HELPER='readiness/youtube_worker_current_inspection.py'
WORKFLOW='.github/workflows/plm-youtube-worker-current-readonly-once.yml'
PLAN='readiness/youtube-worker-current-readonly-inspection-plan.json'
SCHEMA='readiness/youtube-worker-current-readonly-marker.schema.json'
MARKER='audit-evidence/consumed/'+IDENTITY+'.json'
ENDPOINTS=('/accounts/'+ACCOUNT+'/workers/scripts/'+WORKER+'/content/v2',
           '/accounts/'+ACCOUNT+'/workers/scripts/'+WORKER+'/schedules',
           '/accounts/'+ACCOUNT+'/queues')
MAX_BYTES=262144
OBSERVED_GROUP_ID='3517fad527464d8bbba2c2a9a6eefaa9'
KNOWN_PERMISSION='Workers Content Read-Only'
OBSERVED_NAME_HASH='5f5fa61c1fabd098b28886c17a312aea38d9fdb3a86dfad019700b474a6764dd'

class Stop(Exception):pass

def need(ok,code):
    if not ok:raise Stop(code)

def digest(raw):return hashlib.sha256(raw).hexdigest()

def map_worker_permission(group):
    """Exact observed ID and exact name/hash only; arbitrary new roles never pass."""
    if type(group) is not dict or group.get('id')!=OBSERVED_GROUP_ID:return None
    if group.get('name')==KNOWN_PERMISSION and digest(KNOWN_PERMISSION.encode())==OBSERVED_NAME_HASH:return KNOWN_PERMISSION
    if 'name' not in group and group.get('unmapped_name_sha256')==OBSERVED_NAME_HASH:return KNOWN_PERMISSION
    return None

def policy_candidate(details):
    out={'worker_source':'UNVERIFIED','worker_schedules':'UNVERIFIED','endpoint_success':'UNVERIFIED',
         'worker_only_resource_restriction':'UNVERIFIED'}
    if details.get('status')!='active':return out
    policies=details.get('policies',[])
    if type(policies) is not list or any(type(p) is not dict or p.get('effect')!='allow' or p.get('resource_scope_complete') is not True for p in policies):return out
    for p in policies:
        if p.get('resources')=={'com.cloudflare.api.account.'+ACCOUNT:'*'} and any(map_worker_permission(g) for g in p.get('permission_groups',[])):
            out['worker_source']=out['worker_schedules']='READ_CANDIDATE'
    return out

def decode(raw):
    need(type(raw) is bytes and len(raw)<=MAX_BYTES,'RESPONSE_LIMIT_STOP')
    def pairs(items):
        out={}
        for k,v in items:
            need(k not in out,'DUPLICATE_JSON_STOP');out[k]=v
        return out
    try:data=json.loads(raw.decode('utf-8'),object_pairs_hook=pairs)
    except Stop:raise
    except Exception:raise Stop('RESPONSE_SHAPE_STOP') from None
    need(type(data) is dict and data.get('success') is True,'PROVIDER_RESPONSE_STOP')
    return data

def source_evidence(body,metadata):
    need(type(body) is bytes and 0<len(body)<=MAX_BYTES,'RESPONSE_LIMIT_STOP')
    mime=metadata.get('content_type','').split(';',1)[0].strip().lower()
    need(mime in ('application/javascript','text/javascript','text/plain','application/octet-stream','multipart/form-data'),'SOURCE_CONTENT_TYPE_STOP')
    return {'http_status':200,'response_bytes':len(body),'sha256':digest(body),'content_type':mime,
            'hash_scope':'EXACT_CONTENT_V2_RESPONSE_BYTES_NOT_ASSUMED_SANDBOX_BUNDLE',
            'worker_exists':True,'source_read_capability':'CONFIRMED','raw_retention':0}

def schedules_evidence(body):
    data=decode(body);need('result_info' not in data,'UNEXPECTED_PAGINATION_STOP')
    result=data.get('result');need(type(result) is dict,'SCHEDULES_SHAPE_STOP')
    schedules=result.get('schedules');need(type(schedules) is list and len(schedules)<=64,'SCHEDULES_SHAPE_STOP')
    crons=[]
    for item in schedules:
        need(type(item) is dict and type(item.get('cron')) is str,'SCHEDULES_SHAPE_STOP')
        cron=item['cron']
        need(len(cron)<=128 and len(cron.split())==5 and re.fullmatch(r'[0-9A-Z*/?,#L\- ]+',cron),'SCHEDULES_SHAPE_STOP')
        crons.append(cron)
    need(len(crons)==len(set(crons)),'SCHEDULES_SHAPE_STOP')
    return {'http_status':200,'cron_count':len(crons),'crons':crons,'schedules_read_capability':'CONFIRMED','raw_retention':0}

def queues_evidence(body):
    data=decode(body);rows=data.get('result');need(type(rows) is list and len(rows)<=1000,'QUEUES_SHAPE_STOP')
    info=data.get('result_info')
    need(type(info) is dict,'UNVERIFIED_INCOMPLETE_PAGINATION')
    need(all(type(info.get(k)) is int for k in ('count','page','per_page','total_count','total_pages')),'UNVERIFIED_INCOMPLETE_PAGINATION')
    need(info['page']==1 and info['count']==info['total_count']==len(rows) and info['per_page']>=len(rows) and info['per_page']>0 and info['total_pages'] in (0,1) and (info['total_pages']!=0 or not rows),'UNVERIFIED_INCOMPLETE_PAGINATION')
    queues=[];all_consumers_complete=True;ids=[];target_count=0
    for q in rows:
        need(type(q) is dict and type(q.get('queue_id')) is str and re.fullmatch(r'[a-f0-9]{32}',q['queue_id']),'QUEUES_SHAPE_STOP')
        ids.append(q['queue_id']);out={'queue_id':q['queue_id']}
        # Queue name is metadata, represented only by hash to avoid retaining arbitrary values.
        if type(q.get('queue_name')) is str:out['queue_name_sha256']=digest(q['queue_name'].encode())
        consumers=q.get('consumers');total=q.get('consumers_total_count')
        complete=type(consumers) is list and type(total) is int and 0<=total<=1000 and total==len(consumers)
        safe=[]
        if type(consumers) is list:
            need(len(consumers)<=1000,'QUEUES_SHAPE_STOP')
            for c in consumers:
                need(type(c) is dict,'QUEUES_SHAPE_STOP')
                kind=c.get('type');entry={'type':kind if kind in ('worker','http_pull') else 'UNVERIFIED'}
                if type(c.get('consumer_id')) is str and re.fullmatch(r'[a-f0-9]{32}',c['consumer_id']):entry['consumer_id']=c['consumer_id']
                else:complete=False
                if kind=='worker' and type(c.get('script_name')) is str:
                    entry['target_worker']=c['script_name']==WORKER
                    if entry['target_worker']:target_count+=1
                elif kind!='http_pull':complete=False
                safe.append(entry)
        else:complete=False
        out['consumers']=safe;out['consumer_inventory']='COMPLETE' if complete else 'UNVERIFIED'
        if type(total) is int and 0<=total<=1000:out['consumers_total_count']=total
        all_consumers_complete=all_consumers_complete and complete;queues.append(out)
    need(len(ids)==len(set(ids)),'QUEUES_SHAPE_STOP')
    return {'http_status':200,'queue_count':len(queues),'inventory':'COMPLETE','queues':queues,
            'target_worker_consumer_count_observed':target_count,
            'consumer_association':'CONFIRMED_PRESENT' if target_count else ('CONFIRMED_ABSENT' if all_consumers_complete else 'UNVERIFIED'),
            'raw_retention':0}

class ThreeGet:
    def __init__(self,transport):self.transport=transport;self.count=0;self.stopped=False
    def get(self,method,path):
        need(not self.stopped and method=='GET' and self.count<3 and path==ENDPOINTS[self.count],'REQUEST_GATE_STOP')
        self.count+=1
        try:
            status,body,metadata=self.transport(method,path)
            need(type(status) is int,'RESPONSE_SHAPE_STOP')
            need(status==200,'HTTP_'+str(status)+'_STOP' if status in (403,404,301,302,307,308) else 'HTTP_STATUS_STOP')
            need(type(body) is bytes and len(body)<=MAX_BYTES and type(metadata) is dict,'RESPONSE_LIMIT_STOP')
            return body,metadata
        except Stop:self.stopped=True;raise
        except Exception:self.stopped=True;raise Stop('TRANSPORT_UNKNOWN_NO_RETRY') from None

def inspect(transport):
    gate=ThreeGet(transport)
    out={'identity':IDENTITY,'maximum_requests':3,'maximum_writes':0,'retry':0,'resume':0,'redirect':0,'pagination_fallback':0,'raw_retention':0,
         'routes':'UNVERIFIED_ZONE_ID_OR_PERMISSION','d1':'SEPARATE_EXISTING_EVIDENCE_NOT_EVALUATED'}
    try:
        body,meta=gate.get('GET',ENDPOINTS[0]);out['source']=source_evidence(body,meta);del body
        body,_=gate.get('GET',ENDPOINTS[1]);out['schedules']=schedules_evidence(body);del body
        body,_=gate.get('GET',ENDPOINTS[2]);out['queues']=queues_evidence(body);del body
        out['result']='WORKER_CURRENT_READONLY_INSPECTION_SUCCESS_STOP'
    except Stop as e:gate.stopped=True;out['result']=str(e)
    except Exception:gate.stopped=True;out['result']='UNVERIFIED_RESPONSE_STOP'
    out['cloudflare_requests']=gate.count
    return out

def validate_marker(marker,plan,before,files):
    need(type(marker) is dict and set(marker)=={'identity','state','prepared_commit_sha','plan_sha256','workflow_sha256','helper_sha256'},'MARKER_SCHEMA_STOP')
    need(marker['identity']==IDENTITY and marker['state']=='CONSUMED_BEFORE_REMOTE' and marker['prepared_commit_sha']==before and type(before) is str and re.fullmatch(r'[a-f0-9]{40}',before),'MARKER_BINDING_STOP')
    need(plan.get('identity')==IDENTITY and plan.get('exact_parent_sha')==PARENT and plan.get('target_account')==ACCOUNT and plan.get('target_worker')==WORKER and plan.get('credential_secret_name')==SECRET_NAME and plan.get('token_type')=='ACCOUNT_OWNED','PLAN_BINDING_STOP')
    need(plan.get('endpoints')==list(ENDPOINTS) and plan.get('maximum_requests')==3 and plan.get('maximum_writes')==0 and plan.get('run_attempt')==1 and all(plan.get(k)==0 for k in ('retry','resume','redirect','raw_retention','pagination_fallback')) and plan.get('response_bytes_max_each')==MAX_BYTES and plan.get('no_retry') is True and plan.get('no_resume') is True,'PLAN_LIMITS_STOP')
    need(plan['marker']['path']==MARKER and plan['marker']['schema_path']==SCHEMA and digest(files[SCHEMA])==plan['marker']['schema_sha256'],'MARKER_SCHEMA_HASH_STOP')
    for key,path in [('plan_sha256',PLAN),('workflow_sha256',WORKFLOW),('helper_sha256',HELPER)]:
        need(type(marker[key]) is str and re.fullmatch(r'[a-f0-9]{64}',marker[key]) and digest(files[path])==marker[key],'MARKER_HASH_STOP')
    need(plan['helper_sha256']==marker['helper_sha256'] and plan['workflow_sha256']==marker['workflow_sha256'],'PLAN_HASH_STOP')

def live_transport(token):
    import http.client
    need(type(token) is str and bool(token) and not any(c in token for c in '\r\n'),'CREDENTIAL_MISSING_STOP')
    def get(method,path):
        need(method=='GET' and path in ENDPOINTS,'REQUEST_GATE_STOP')
        conn=http.client.HTTPSConnection('api.cloudflare.com',timeout=15)
        try:
            conn.request('GET','/client/v4'+path,headers={'Authorization':'Bearer '+token,'Accept':'*/*'})
            response=conn.getresponse()
            if response.status!=200:return response.status,b'',{}
            size=response.getheader('Content-Length')
            need(size is None or (size.isdigit() and int(size)<=MAX_BYTES),'RESPONSE_LIMIT_STOP')
            raw=response.read(MAX_BYTES+1);need(len(raw)<=MAX_BYTES,'RESPONSE_LIMIT_STOP')
            return response.status,raw,{'content_type':response.getheader('Content-Type') or ''}
        finally:conn.close()
    return get

def main():
    import os
    env=os.environ
    try:
        need(all(env.get(k)=='true' for k in ('TEST_ONLY','DRY_RUN','NO_PUBLISH','EMERGENCY_STOP')),'SAFE_FLAGS_STOP')
        need(env.get('GITHUB_RUN_ATTEMPT')=='1' and env.get('GITHUB_EVENT_NAME')=='push' and env.get('GITHUB_REPOSITORY')=='ikkinotako2-sketch/project-love-machine-serverless-sandbox' and env.get('GITHUB_REF')=='refs/heads/plm-offline-readiness-v1-20261002','EXECUTION_CONTEXT_STOP')
        files={p:Path(p).read_bytes() for p in (PLAN,WORKFLOW,HELPER,SCHEMA)}
        validate_marker(json.loads(Path(MARKER).read_bytes()),json.loads(files[PLAN]),env['PLM_APPROVED_BEFORE'],files)
        out=inspect(live_transport(env.get(SECRET_NAME)))
    except Stop as e:out={'identity':IDENTITY,'result':'PRE_REMOTE_GATE_STOP','gate_code':str(e),'cloudflare_requests':0,'maximum_writes':0,'raw_retention':0}
    except Exception:out={'identity':IDENTITY,'result':'PRE_REMOTE_GATE_STOP','gate_code':'UNVERIFIED_LOCAL_GATE_STOP','cloudflare_requests':0,'maximum_writes':0,'raw_retention':0}
    print(json.dumps(out,sort_keys=True))
    return 0

if __name__=='__main__':raise SystemExit(main())
