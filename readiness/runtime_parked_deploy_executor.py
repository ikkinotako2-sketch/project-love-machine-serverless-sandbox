"""One parked replacement; import-time behavior is strictly offline."""
import hashlib,json,math,re
from pathlib import Path
from readiness.runtime_remote_readonly_executor import Stop,need,sha,json_exact,envelope,source_metadata,MAX,ERROR_MAX,TIMEOUT
from readiness.runtime_visibility_completion_r4_executor import subdomain,domains,zones
IDENTITY='provider-neutral-runtime-parked-deploy-20261011-r1'
PARENT='b6c1061e55c3cc03be1561ba482e5dc1b306bfb2'
REPO='ikkinotako2-sketch/project-love-machine-serverless-sandbox'
BRANCH='refs/heads/plm-offline-readiness-v1-20261002'
ACCOUNT='6c8ccd6aface937ab5dabef61cb64534'
WORKER='plm-serverless-sandbox-control'
OLD='6c5d726f96d56dac792ff739f87227926197891f1149b1dedeeac38e67128451'
NEW='8a6615fd020ca6590ba8f5e2c73a3844473d9e6ecd3babb19ea836d604d4a8a9'
BUNDLE='serverless/youtube-connection/runtime-bundle.mjs'
CONFIG='serverless/youtube-connection/wrangler.runtime.stopped.json'
WORKFLOW='.github/workflows/plm-runtime-parked-deploy-once.yml'
HELPER='readiness/runtime_parked_deploy_executor.py'
PLAN='readiness/runtime-parked-deploy-plan.json'
SCHEMA='readiness/runtime-parked-deploy-marker.schema.json'
POSTPLAN='readiness/runtime-parked-postdeploy-readonly-plan.json'
AUDIT='readiness/runtime-parked-deploy-audit.json'
TARGET='readiness/runtime-target-pinned-manifest.json'
R4='audit-evidence/consumed/provider-neutral-runtime-visibility-completion-20261011-r4.json'
DEPENDENCY='readiness/runtime_remote_readonly_executor.py'
EXPOSURE='readiness/runtime_visibility_completion_r4_executor.py'
MARKER='audit-evidence/consumed/'+IDENTITY+'.json'
MESSAGE='PLM runtime parked deploy once '+IDENTITY
PREFIX='/accounts/'+ACCOUNT+'/workers/scripts/'+WORKER
GETS=(PREFIX+'/content/v2',PREFIX+'/subdomain','/accounts/'+ACCOUNT+'/workers/domains?service='+WORKER,'/zones?account.id='+ACCOUNT+'&per_page=50&page=1')
PUT=PREFIX
FLAGS={k:'true' for k in ('TEST_ONLY','DRY_RUN','NO_PUBLISH','EMERGENCY_STOP')}
EXPECTED_CONFIG={'name':WORKER,'main':'runtime-bundle.mjs','compatibility_date':'2026-10-06','d1_databases':[{'binding':'DB','database_id':'18050cf6-934e-4f3a-a1cd-5041bac1c35e','database_name':'plm-serverless-sandbox-state'}],'workers_dev':False,'preview_urls':False,'routes':[],'triggers':{'crons':[]},'vars':FLAGS}
IMMUTABLE={BUNDLE:NEW,CONFIG:'461f93e9d8468fd26f93895f7cbac002d5b49d35ff3eabe0a865e422226652eb',R4:'f6de5d6bceb8789ef3941d7524ae4e74f3e61c3299f693531eb7a0a8181c851f',TARGET:'8315eac39526ed97126c3b5f85df9e150afc63186c224a3820fb03103bf11828',DEPENDENCY:'4e5c746374757d77baf053c46c7516f65298f3cedbd8d37f6dea09242e619ee6',EXPOSURE:'7c7f963852edeea87aac66d23da7779708bef21ede4272517fa32de7bf2331af'}
PIN_FILES={'workflow_sha256':WORKFLOW,'executor_sha256':HELPER,'plan_sha256':PLAN,'schema_sha256':SCHEMA,'bundle_sha256':BUNDLE,'stopped_config_sha256':CONFIG,'visibility_r4_marker_sha256':R4,'target_manifest_sha256':TARGET,'parser_dependency_sha256':DEPENDENCY,'exposure_parser_sha256':EXPOSURE,'postdeploy_plan_sha256':POSTPLAN,'audit_sha256':AUDIT}
PREPARATION_FILES={WORKFLOW,HELPER,PLAN,SCHEMA,POSTPLAN,AUDIT,'readiness/test_runtime_parked_deploy.py','serverless/test-runtime-parked-deploy.mjs','.github/workflows/plm-runtime-integration-offline.yml','readiness/test_runtime_visibility_completion_r4.py'}
PARKED_DEFAULT=b"export default {async fetch(){return new Response('PARKED_RUNTIME_COMPOSITION',{status:503});},async scheduled(){throw new Error('CRON_DISABLED');},async queue(){throw new Error('QUEUE_CONSUMER_DISABLED');}};"
DISABLED_LIVE=b"export function createLiveComposition(){throw new Error('PREPARATION_ONLY_REMOTE_ACTIVATION_DISABLED');}"
def validate_candidate(bundle,config):
 need(type(bundle) is bytes and sha(bundle)==NEW,'BUNDLE_HASH_STOP')
 need(bundle.rstrip().endswith(PARKED_DEFAULT) and bundle.count(b'export default ')==1 and bundle.count(DISABLED_LIVE)==1,'PARKED_BUNDLE_STOP')
 need(type(config) is bytes and sha(config)==IMMUTABLE[CONFIG],'CONFIG_HASH_STOP')
 need(json_exact(config)==EXPECTED_CONFIG,'STOPPED_CONFIG_STOP')

def upload_metadata():
 return {'main_module':'runtime-bundle.mjs','compatibility_date':'2026-10-06','bindings':[{'type':'d1','name':'DB','id':EXPECTED_CONFIG['d1_databases'][0]['database_id']}]+[{'type':'plain_text','name':k,'text':v} for k,v in FLAGS.items()],'keep_bindings':[]}

def multipart(bundle,config):
 validate_candidate(bundle,config);boundary=b'plm-parked-runtime-20261011-r1'
 meta=json.dumps(upload_metadata(),sort_keys=True,separators=(',',':')).encode()
 need(boundary not in bundle and boundary not in meta,'MULTIPART_BOUNDARY_STOP')
 body=b'--'+boundary+b'\r\nContent-Disposition: form-data; name="metadata"\r\nContent-Type: application/json\r\n\r\n'+meta+b'\r\n--'+boundary+b'\r\nContent-Disposition: form-data; name="runtime-bundle.mjs"; filename="runtime-bundle.mjs"\r\nContent-Type: application/javascript+module\r\n\r\n'+bundle+b'\r\n--'+boundary+b'--\r\n'
 return body,'multipart/form-data; boundary='+boundary.decode()

def validate_gate(env,event,facts,marker,files):
 need(all(env.get(k)=='true' for k in FLAGS),'SAFE_FLAGS_STOP')
 need(env.get('GITHUB_REPOSITORY')==REPO and env.get('GITHUB_REF')==BRANCH and env.get('GITHUB_EVENT_NAME')=='push' and env.get('GITHUB_RUN_ATTEMPT')=='1','EXECUTION_CONTEXT_STOP')
 before=event.get('before');after=event.get('after');head=event.get('head_commit',{})
 need(type(before) is str and re.fullmatch('[a-f0-9]{40}',before) and after==env.get('GITHUB_SHA') and head.get('id')==after and head.get('message')==MESSAGE and len(event.get('commits',[]))==1,'PUSH_BINDING_STOP')
 need(facts.get('full_history') is True and facts.get('root')==PARENT and type(facts.get('count')) is int and 1<=facts['count']<=3 and set(facts.get('preparation_files',[]))==PREPARATION_FILES,'PREPARATION_HISTORY_STOP')
 need(facts.get('head')==after and facts.get('parent')==before and facts.get('files')==[MARKER] and facts.get('message')==MESSAGE and facts.get('marker_preexisted') is False,'MARKER_ONLY_STOP')
 need(facts.get('r4_parent_hash')==IMMUTABLE[R4],'CONSUMED_MARKER_DRIFT_STOP')
 need(type(marker) is dict and set(marker)==set(PIN_FILES)|{'identity','state','prepared_commit_sha','old_remote_source_sha256','expected_new_bundle_sha256'},'MARKER_SHAPE_STOP')
 need(marker['identity']==IDENTITY and marker['state']=='CONSUMED_BEFORE_REMOTE' and marker['prepared_commit_sha']==before and marker['old_remote_source_sha256']==OLD and marker['expected_new_bundle_sha256']==NEW,'MARKER_BINDING_STOP')
 for k,p in PIN_FILES.items():need(sha(files[p])==marker[k],'SOURCE_HASH_DRIFT_STOP')
 for p,h in IMMUTABLE.items():need(sha(files[p])==h,'IMMUTABLE_DRIFT_STOP')
 validate_candidate(files[BUNDLE],files[CONFIG]);plan=json_exact(files[PLAN])
 need(plan['identity']==IDENTITY and plan['exact_preparation_parent']==PARENT and plan['allowed_prewrite_requests']==[{'method':'GET','path':p} for p in GETS] and plan['write']=={'method':'PUT','path':PUT,'metadata':upload_metadata()},'PLAN_CONTRACT_STOP')
 need(plan['maximum_prewrite_GET']==4 and plan['maximum_script_writes']==1 and plan['maximum_total_HTTP']==5 and plan['timeout_seconds']==TIMEOUT and plan['response_bytes_max_each']==MAX and plan['error_body_bytes_max']==ERROR_MAX,'PLAN_BUDGET_STOP')
 for k in ('D1_requests','invocations','route_writes','domain_writes','subdomain_writes','cron_writes','queue_writes','dispatches','uploads_to_YouTube','production_writes','retry','rerun','resume','resend','fallback','redirect','rollback','raw_retention'):need(type(plan.get(k)) is int and plan[k]==0,'PLAN_SAFETY_STOP')
 for k,p in PIN_FILES.items():
  if k!='plan_sha256':need(plan[k]==marker[k],'PLAN_PIN_STOP')
 target=json_exact(files[TARGET]);need(target.get('target_status')=='PINNED_READONLY_NOT_EXECUTION_APPROVED' and target.get('execution_approved') is False and target.get('launchable') is False and target.get('mutable_branch_fallback') is False,'TARGET_ACTIVATION_STOP')
 need(plan['runtime_activation_approved'] is False and plan['deploy_credential_verified'] is False,'ACTIVATION_STOP')

_CAPABILITY=object()
class RequestBudget:
 def __init__(self):self.reads=0;self.writes=0;self.ready=False
 def admit(self,method,path):
  if method=='GET':
   need(self.writes==0 and self.reads<4 and path==GETS[self.reads],'REQUEST_GATE_STOP');self.reads+=1
  else:
   need(method=='PUT' and path==PUT and self.reads==4 and self.ready and self.writes==0,'WRITE_GATE_STOP');self.writes+=1
 def preflight_complete(self,capability):need(capability is _CAPABILITY and self.reads==4 and self.writes==0,'WRITE_GATE_STOP');self.ready=True

class AuthorizedTransport:
 def __init__(self,read_token,deploy_token,capability=None):
  need(capability is _CAPABILITY,'ONE_SHOT_GATE_REQUIRED')
  need(all(type(t) is str and t and not any(c in t for c in '\r\n') for t in (read_token,deploy_token)),'CREDENTIAL_MISSING_STOP')
  need(read_token!=deploy_token,'CREDENTIAL_ROLES_NOT_DISTINCT_STOP');self.read_token=read_token;self.deploy_token=deploy_token;self.budget=RequestBudget()
 def preflight_complete(self,capability):self.budget.preflight_complete(capability)
 def __call__(self,method,path,body=None,content_type=None):
  import http.client,time
  self.budget.admit(method,path)
  need(method!='PUT' or type(body) is bytes and type(content_type) is str,'UPLOAD_BODY_STOP')
  started=time.monotonic();c=http.client.HTTPSConnection('api.cloudflare.com',timeout=TIMEOUT)
  try:
   headers={'Authorization':'Bearer '+(self.read_token if method=='GET' else self.deploy_token),'Accept':'application/json' if method=='PUT' else '*/*'}
   if method=='PUT':headers['Content-Type']=content_type
   c.connect()
   remaining=TIMEOUT-(time.monotonic()-started);need(remaining>0,'TRANSPORT_UNKNOWN_NO_RETRY');c.sock.settimeout(remaining)
   c.request(method,'/client/v4'+path,body=body,headers=headers)
   remaining=TIMEOUT-(time.monotonic()-started);need(remaining>0,'TRANSPORT_UNKNOWN_NO_RETRY');c.sock.settimeout(remaining)
   r=c.getresponse();status=r.status
   limit=MAX if status==200 else ERROR_MAX;parts=[];n=0
   while n<=limit:
    remaining=TIMEOUT-(time.monotonic()-started);need(remaining>0,'TRANSPORT_UNKNOWN_NO_RETRY')
    sock=c.sock if c.sock is not None else getattr(getattr(getattr(r,'fp',None),'raw',None),'_sock',None)
    if sock is not None:sock.settimeout(remaining)
    chunk=r.read1(min(8192,limit+1-n))
    if not chunk:break
    parts.append(chunk);n+=len(chunk)
   raw=b''.join(parts);need(len(raw)<=limit,'RESPONSE_BOUND_STOP')
   return status,raw,{'content_type':r.getheader('Content-Type') or '', 'entrypoint':r.getheader('cf-entrypoint')}
  finally:c.close()

def numeric_errors(raw):
 try:
  d=json_exact(raw);rows=d.get('errors',[]);return [e['code'] for e in rows[:8] if type(e) is dict and type(e.get('code')) is int] if type(rows) is list else []
 except Exception:return []

def execute(transport,bundle,config):
 out={'identity':IDENTITY,'classification':'PREWRITE_STOP_NO_DEPLOY','reason_codes':[],'requests_attempted':0,'prewrite_GETs':0,'script_writes_attempted':0,'request_order':[],'HTTP_statuses':[],'cloudflare_error_codes':[],'D1_requests':0,'invocations':0,'dispatches':0,'YouTube_calls':0,'retry':0,'rerun':0,'resume':0,'resend':0,'rollback':0,'redirect':0,'fallback':0,'raw_retention':0,'secret_exposure':0,'runtime_activation_approved':False,'postcheck_required':True}
 try:
  validate_candidate(bundle,config)
  for index,path in enumerate(GETS):
   out['requests_attempted']+=1;out['prewrite_GETs']+=1;out['request_order'].append('GET '+path)
   status,raw,meta=transport('GET',path);out['HTTP_statuses'].append(status)
   if status!=200:out['cloudflare_error_codes']=numeric_errors(raw);raise Stop('PREFLIGHT_HTTP_'+str(status)+'_STOP_NO_DEPLOY')
   need(type(raw) is bytes and len(raw)<=MAX,'RESPONSE_BOUND_STOP')
   if index==0:
    proof=source_metadata(raw,meta,{OLD});need(proof.get('source_representation_proven') is True and proof.get('source_module_sha256')==OLD,'SOURCE_DRIFT_STOP_NO_DEPLOY');out['old_source_exact']=True
   else:
    try:
     if index==1:subdomain(raw)
     elif index==2:domains(raw)
     else:
      z=zones(raw);need(z['zones_complete'] is True and z['zone_count']==0,'EXPOSURE_DRIFT_STOP_NO_DEPLOY')
    except Stop:raise Stop('EXPOSURE_DRIFT_STOP_NO_DEPLOY') from None
   del raw
  body,typ=multipart(bundle,config);transport.preflight_complete(_CAPABILITY)
  out['prewrite_result']='PASS';out['script_writes_attempted']=1;out['requests_attempted']+=1;out['request_order'].append('PUT '+PUT)
  status,raw,_=transport('PUT',PUT,body,typ);out['HTTP_statuses'].append(status)
  out['cloudflare_error_codes']=numeric_errors(raw)
  need(status==200 and len(raw)<=MAX,'DEPLOY_UNKNOWN_STOP_NO_RETRY')
  d=envelope(raw);r=d.get('result');need(type(r) is dict and r.get('id')==WORKER and d.get('errors')==[],'DEPLOY_UNKNOWN_STOP_NO_RETRY')
  out['classification']='PARKED_DEPLOY_ACK_STOP_BEFORE_POSTCHECK';out['acknowledged']=True
 except Stop as e:
  code=str(e);out['reason_codes']=[code if out['script_writes_attempted']==0 else 'DEPLOY_UNKNOWN_STOP_NO_RETRY']
  if out['script_writes_attempted']:out['classification']='DEPLOY_UNKNOWN_STOP_NO_RETRY'
 except Exception:
  out['reason_codes']=['PREFLIGHT_TRANSPORT_UNKNOWN_NO_DEPLOY' if out['script_writes_attempted']==0 else 'DEPLOY_UNKNOWN_STOP_NO_RETRY']
  if out['script_writes_attempted']:out['classification']='DEPLOY_UNKNOWN_STOP_NO_RETRY'
 return out

def collect_git_facts(before,git,exists):
 need(git('rev-parse','--is-shallow-repository')=='false','SHALLOW_REPOSITORY_STOP')
 root=git('merge-base',PARENT,before);need(root==PARENT,'PREPARATION_ROOT_STOP')
 count=git('rev-list','--count',PARENT+'..'+before);need(count.isdigit(),'GIT_HISTORY_STOP')
 return {'full_history':True,'root':root,'count':int(count),'preparation_files':git('diff','--name-only',PARENT,before).splitlines(),'head':git('rev-parse','HEAD'),'parent':git('rev-parse','HEAD^'),'files':git('diff','--name-only',before,'HEAD').splitlines(),'message':git('log','-1','--format=%B'),'marker_preexisted':exists(before+':'+MARKER),'r4_parent_hash':sha(git('show',PARENT+':'+R4).encode())}

def load_gate():
 import os,subprocess
 event=json_exact(Path(os.environ['GITHUB_EVENT_PATH']).read_bytes());before=event['before'];need(type(before) is str and re.fullmatch('[a-f0-9]{40}',before),'PREPARED_COMMIT_STOP')
 def git(*a):
  r=subprocess.run(['git',*a],text=True,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,check=False);need(r.returncode==0,'GIT_HISTORY_COMMAND_STOP');return r.stdout if a[0]=='show' else r.stdout.strip()
 def exists(spec):return subprocess.run(['git','cat-file','-e',spec],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0
 facts=collect_git_facts(before,git,exists);files={p:Path(p).read_bytes() for p in PIN_FILES.values()}
 validate_gate(dict(os.environ),event,facts,json_exact(Path(MARKER).read_bytes()),files);return files

def main():
 import os
 out={'identity':IDENTITY,'classification':'LOCAL_GATE_STOP_NO_DEPLOY','requests_attempted':0,'script_writes_attempted':0,'D1_requests':0,'raw_retention':0,'secret_exposure':0,'reason_codes':[]}
 try:
  files=load_gate()
  # Token lookup is deliberately after gate; values never leave transport memory.
  t=AuthorizedTransport(os.environ.get('PLM_CF_WORKER_API_TOKEN'),os.environ.get('PLM_CF_WORKER_DEPLOY_TOKEN'),_CAPABILITY)
  out=execute(t,files[BUNDLE],files[CONFIG])
 except Stop as e:out['reason_codes']=[str(e)]
 except Exception:out['reason_codes']=['LOCAL_GATE_STOP_NO_DEPLOY']
 print(json.dumps(out,sort_keys=True))
if __name__=='__main__':main()
