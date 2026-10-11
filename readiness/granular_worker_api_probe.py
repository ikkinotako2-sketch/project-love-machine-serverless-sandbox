"""Independent two-GET credential proof. No IO or credential lookup on import."""
import json,re
from pathlib import Path
from datetime import datetime,timezone
try:
 from readiness.runtime_remote_readonly_executor import Stop,need,sha,json_exact,envelope,MAX,ERROR_MAX,TIMEOUT
except ModuleNotFoundError:
 from runtime_remote_readonly_executor import Stop,need,sha,json_exact,envelope,MAX,ERROR_MAX,TIMEOUT
IDENTITY='provider-neutral-granular-worker-api-probe-20261011-r1'
PARENT='42b53532ea1b31d1836ec7af58003b334ef9e24d'
R3_MARKER='audit-evidence/consumed/provider-neutral-runtime-parked-deploy-token-verify-20261011-r3.json'
R3_HASH='7aee4bc42b39f96c698cc285de349dc07c3893329719d19e23be13140ba143c3'
R2_MARKER='audit-evidence/consumed/provider-neutral-runtime-parked-deploy-token-verify-20261011-r2.json'
R2_HASH='b51954cc2f6aae162849db7c4041837c9a064e24c1c25ae8f273852bc5d9a08a'
DEPLOY_PREPARED='acf9822aeedc4418c8f47bed760c18fd18db2be3'
R1_MARKER='audit-evidence/consumed/provider-neutral-runtime-parked-deploy-token-verify-20261011-r1.json'
R1_HASH='44275c75b3c0b1f4ac13cf4d6e73ec591ffec6f5760f9900a8d56d8cccca8e2d'
REPO='ikkinotako2-sketch/project-love-machine-serverless-sandbox'
BRANCH='refs/heads/plm-offline-readiness-v1-20261002'
ACCOUNT='6c8ccd6aface937ab5dabef61cb64534'
WORKER='plm-serverless-sandbox-control'
SECRET='PLM_CF_WORKER_DEPLOY_TOKEN'
OLD='6c5d726f96d56dac792ff739f87227926197891f1149b1dedeeac38e67128451'
NEW='8a6615fd020ca6590ba8f5e2c73a3844473d9e6ecd3babb19ea836d604d4a8a9'
GETS=('/accounts/'+ACCOUNT+'/tokens/verify','/accounts/'+ACCOUNT+'/workers/workers/'+WORKER)
WORKFLOW='.github/workflows/plm-granular-worker-api-probe-once.yml'
HELPER='readiness/granular_worker_api_probe.py'
PLAN='readiness/granular-worker-api-probe-plan.json'
SCHEMA='readiness/granular-worker-api-probe-marker.schema.json'
DEPLOY_PLAN='readiness/runtime-parked-deploy-plan.json'
DEPLOY_EXECUTOR='readiness/runtime_parked_deploy_executor.py'
PARSER='readiness/runtime_remote_readonly_executor.py'
BOOTSTRAP='serverless/bootstrap-placeholder.mjs'
BUNDLE='serverless/youtube-connection/runtime-bundle.mjs'
DEPLOY_MARKER='audit-evidence/consumed/provider-neutral-runtime-parked-deploy-20261011-r1.json'
MARKER='audit-evidence/consumed/'+IDENTITY+'.json'
MESSAGE='PLM granular worker api probe once '+IDENTITY
FLAGS={k:'true' for k in ('TEST_ONLY','DRY_RUN','NO_PUBLISH','EMERGENCY_STOP')}
IMMUTABLE={R3_MARKER:R3_HASH,R2_MARKER:R2_HASH,R1_MARKER:R1_HASH,DEPLOY_PLAN:'b96edafbbc0df5121eda655bd1fa12af6dc086f9b2077982410c97f740851985',DEPLOY_EXECUTOR:'56163be0825d3cc240e85eef8a757ee2a50a2ea92380979aa3fae81a8a9f795d',PARSER:'4e5c746374757d77baf053c46c7516f65298f3cedbd8d37f6dea09242e619ee6',BOOTSTRAP:OLD,BUNDLE:NEW}
PINS={'r3_consumed_marker_sha256':R3_MARKER,'r2_consumed_marker_sha256':R2_MARKER,'r1_consumed_marker_sha256':R1_MARKER,'workflow_sha256':WORKFLOW,'executor_sha256':HELPER,'plan_sha256':PLAN,'schema_sha256':SCHEMA,'parked_deploy_plan_sha256':DEPLOY_PLAN,'parked_deploy_executor_sha256':DEPLOY_EXECUTOR,'parser_dependency_sha256':PARSER,'expected_old_source_sha256':BOOTSTRAP,'expected_new_bundle_sha256':BUNDLE}
ZERO_KEYS=('writes','D1_requests','deploys','Worker_invocations','dispatches','YouTube_calls','route_writes','domain_writes','subdomain_writes','retry','rerun','resume','resend','redirect','fallback','raw_retention')
# Exact diff authority is the hash-pinned plan; this is category defense only.
def preparation_files(plan,actual):
 paths=plan.get('preparation_files')
 need(type(paths) is list and type(actual) is list and all(type(p) is str for p in paths+actual),'PREPARATION_HISTORY_STOP')
 need(len(paths)==len(set(paths)) and len(actual)==len(set(actual)),'PREPARATION_HISTORY_STOP')
 allowed={WORKFLOW,HELPER,PLAN,SCHEMA,'readiness/test_granular_worker_api_probe.py','.github/workflows/plm-runtime-integration-offline.yml','readiness/test_runtime_parked_deploy_token_verify.py','readiness/test_runtime_parked_deploy_token_verify_r2.py','readiness/test_runtime_parked_deploy_token_verify_r3.py'}
 required={WORKFLOW,HELPER,PLAN,SCHEMA,'readiness/test_granular_worker_api_probe.py'}
 need(all(p in allowed and not p.startswith('/') and '..' not in p.split('/') for p in paths) and required.issubset(paths),'PREPARATION_HISTORY_STOP')
 need(sorted(paths)==sorted(actual),'PREPARATION_HISTORY_STOP')

def timestamp(value):
 need(type(value) is str and len(value)<=64 and re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})',value),'TOKEN_TIMESTAMP_STOP')
 try:t=datetime.fromisoformat(value.replace('Z','+00:00'));need(t.tzinfo is not None and t.utcoffset() is not None,'TOKEN_TIMESTAMP_STOP');return t
 except Stop:raise
 except Exception:raise Stop('TOKEN_TIMESTAMP_STOP') from None

def verify(raw,now):
 need(type(raw) is bytes and len(raw)<=MAX,'RESPONSE_BOUND_STOP')
 r=envelope(raw).get('result');need(type(r) is dict and r.get('status')=='active','TOKEN_NOT_ACTIVE_STOP')
 out={'token_status':'active'}
 if 'expires_on' in r:need(timestamp(r['expires_on'])>now,'TOKEN_EXPIRED_STOP');out['expires_on']=r['expires_on']
 if 'not_before' in r:need(timestamp(r['not_before'])<=now,'TOKEN_NOT_YET_VALID_STOP');out['not_before']=r['not_before']
 # ID, policy, creator and arbitrary remote fields deliberately never accessed.
 return out

def numeric_errors(raw):
 try:
  d=json_exact(raw);rows=d.get('errors',[]);return [e['code'] for e in rows[:8] if type(e) is dict and type(e.get('code')) is int] if type(rows) is list else []
 except Exception:return []

def validate_gate(env,event,facts,marker,files):
 need(all(env.get(k)=='true' for k in FLAGS),'SAFE_FLAGS_STOP')
 need(env.get('GITHUB_REPOSITORY')==REPO and env.get('GITHUB_REF')==BRANCH and env.get('GITHUB_EVENT_NAME')=='push' and env.get('GITHUB_RUN_ATTEMPT')=='1','EXECUTION_CONTEXT_STOP')
 before=event.get('before');after=event.get('after');head=event.get('head_commit',{})
 need(type(before) is str and re.fullmatch('[a-f0-9]{40}',before) and after==env.get('GITHUB_SHA') and head.get('id')==after and head.get('message')==MESSAGE and len(event.get('commits',[]))==1,'PUSH_BINDING_STOP')
 need(facts.get('full_history') is True and facts.get('root')==PARENT and type(facts.get('count')) is int and facts['count']==1,'PREPARATION_HISTORY_STOP')
 plan=json_exact(files[PLAN]);need(sha(files[PLAN])==marker.get('plan_sha256'),'SOURCE_HASH_DRIFT_STOP');preparation_files(plan,facts.get('preparation_files'))
 need(facts.get('head')==after and facts.get('parent')==before and facts.get('files')==[MARKER] and facts.get('message')==MESSAGE and facts.get('marker_preexisted') is False,'MARKER_ONLY_STOP')
 need(facts.get('deploy_marker_absent_root') is True and facts.get('deploy_marker_absent_prepared') is True and facts.get('deploy_marker_absent_head') is True and facts.get('deploy_marker_absent_worktree') is True,'DEPLOY_CONSUMED_STOP')
 need(facts.get('deploy_root_hashes')=={p:IMMUTABLE[p] for p in (DEPLOY_PLAN,DEPLOY_EXECUTOR)},'DEPLOY_PREPARATION_DEPENDENCY_STOP')
 need(facts.get('r3_marker_hashes')=={k:R3_HASH for k in ('root','prepared','head')},'R3_HISTORY_STOP')
 need(facts.get('r2_marker_hashes')=={k:R2_HASH for k in ('root','prepared','head')},'R2_HISTORY_STOP')
 need(facts.get('deploy_ancestor')==DEPLOY_PREPARED and facts.get('r1_marker_hashes')=={k:R1_HASH for k in ('root','prepared','head')},'R1_OR_DEPLOY_HISTORY_STOP')
 need(type(marker) is dict and set(marker)==set(PINS)|{'identity','state','prepared_commit_sha'} and marker['identity']==IDENTITY and marker['state']=='CONSUMED_BEFORE_REMOTE' and marker['prepared_commit_sha']==before,'MARKER_BINDING_STOP')
 for k,p in PINS.items():need(sha(files[p])==marker[k],'SOURCE_HASH_DRIFT_STOP')
 for p,h in IMMUTABLE.items():need(sha(files[p])==h,'IMMUTABLE_DEPENDENCY_STOP')
 plan=json_exact(files[PLAN]);need(plan['identity']==IDENTITY and plan['exact_preparation_parent']==PARENT and plan['parked_deploy_prepared_commit']==DEPLOY_PREPARED and plan['allowed_requests']==[{'method':'GET','path':p} for p in GETS] and plan['maximum_GETs']==2,'PLAN_CONTRACT_STOP')
 for k in ZERO_KEYS:need(type(plan.get(k)) is int and plan[k]==0,'PLAN_BUDGET_STOP')
 need(plan['scope_attestation']=='OWNER_ATTESTED_SPECIFIED_WORKER_EDITOR' and plan['scope_api_verified'] is False and plan['write_capability_remote_tested'] is False and plan['deploy_authorized'] is False and plan['timeout_seconds']==TIMEOUT and plan['response_bytes_max_each']==MAX and plan['error_body_bytes_max']==ERROR_MAX,'PLAN_SAFETY_STOP')
 for k in PINS:
  if k!='plan_sha256':need(plan[k]==marker[k],'PLAN_PIN_STOP')

_CAPABILITY=object()
class RequestBudget:
 def __init__(self):self.count=0;self.active=False
 def admit(self,method,path):
  need(method=='GET' and self.count<2 and path==GETS[self.count] and (self.count==0 or self.active),'REQUEST_GATE_STOP');self.count+=1
 def verified(self,capability):need(capability is _CAPABILITY and self.count==1,'ACTIVE_PROOF_REQUIRED');self.active=True

class AuthorizedTransport:
 def __init__(self,token,capability=None):
  need(capability is _CAPABILITY,'ONE_SHOT_GATE_REQUIRED');need(type(token) is str and token and not any(c in token for c in '\r\n'),'DEPLOY_TOKEN_MISSING_STOP');self.token=token;self.budget=RequestBudget()
 def verified(self,c):self.budget.verified(c)
 def __call__(self,method,path):
  import http.client,time
  self.budget.admit(method,path);started=time.monotonic();c=http.client.HTTPSConnection('api.cloudflare.com',timeout=TIMEOUT)
  try:
   c.connect();left=TIMEOUT-(time.monotonic()-started);need(left>0,'TRANSPORT_UNKNOWN_STOP');c.sock.settimeout(left)
   c.request('GET','/client/v4'+path,headers={'Authorization':'Bearer '+self.token,'Accept':'*/*'})
   left=TIMEOUT-(time.monotonic()-started);need(left>0,'TRANSPORT_UNKNOWN_STOP');c.sock.settimeout(left)
   r=c.getresponse();status=r.status;limit=MAX if status==200 else ERROR_MAX;parts=[];n=0
   while n<=limit:
    left=TIMEOUT-(time.monotonic()-started);need(left>0,'TRANSPORT_UNKNOWN_STOP')
    sock=c.sock if c.sock is not None else getattr(getattr(getattr(r,'fp',None),'raw',None),'_sock',None)
    if sock is not None:sock.settimeout(left)
    chunk=r.read1(min(8192,limit+1-n))
    if not chunk:break
    parts.append(chunk);n+=len(chunk)
   raw=b''.join(parts);need(len(raw)<=limit,'RESPONSE_BOUND_STOP')
   return status,raw,{'content_type':r.getheader('Content-Type') or '', 'entrypoint':r.getheader('cf-entrypoint')}
  finally:c.close()

def worker_metadata(raw):
 r=envelope(raw).get('result');need(type(r) is dict,'WORKER_RESPONSE_SHAPE_STOP')
 need(r.get('name')==WORKER,'WORKER_NAME_MISMATCH_STOP')
 wid=r.get('id');need(type(wid) is str and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,127}',wid),'WORKER_IDENTIFIER_STOP')
 out={'worker_name_exact':True,'worker_id':wid}
 for field in ('created_on','updated_on'):
  if field in r:
   try:timestamp(r[field])
   except Stop:raise Stop('WORKER_TIMESTAMP_STOP') from None
   out[field]=r[field]
 if 'subdomain' in r:
  sub=r['subdomain'];need(type(sub) is dict,'WORKER_METADATA_SHAPE_STOP')
  for field in ('enabled','previews_enabled'):
   if field in sub:need(type(sub[field]) is bool,'WORKER_METADATA_SHAPE_STOP');out['subdomain_'+field]=sub[field]
 if 'references' in r:
  refs=r['references'];need(type(refs) is dict,'WORKER_METADATA_SHAPE_STOP');counts={}
  for field in ('dispatch_namespace_outbounds','domains','durable_objects','queues','workers'):
   if field in refs:need(type(refs[field]) is list,'WORKER_METADATA_SHAPE_STOP');counts[field]=len(refs[field])
  out['reference_counts']=counts
 # Hostnames, URLs, resource details, IDs of other Workers and arbitrary text never emitted.
 return out

def result_base():
 out={k:0 for k in ZERO_KEYS};out.update(identity=IDENTITY,classification='GRANULAR_WORKER_API_TOKEN_VERIFY_BLOCKED',reason_codes=[],requests_attempted=0,request_order=[],HTTP_statuses=[],cloudflare_error_codes=[],credential_active=False,granular_target_read=False,worker_name_exact=False,legacy_scripts_content_access=False,legacy_scripts_content_access_fresh=False,scope_attestation='OWNER_ATTESTED_SPECIFIED_WORKER_EDITOR',scope_api_verified=False,write_capability_remote_tested=False,deploy_authorized=False,deploy_identity_consumed=False,secret_exposure=0)
 return out

def inspect(transport,now=None):
 out=result_base()
 try:
  now=now or datetime.now(timezone.utc)
  for index,path in enumerate(GETS):
   if index:out['classification']='GRANULAR_WORKER_API_TARGET_READ_BLOCKED'
   out['requests_attempted']+=1;out['request_order'].append('GET '+path)
   status,raw,meta=transport('GET',path);out['HTTP_statuses'].append(status)
   if status!=200:out['cloudflare_error_codes']=numeric_errors(raw);raise Stop('HTTP_'+str(status)+'_STOP')
   need(type(raw) is bytes and len(raw)<=MAX,'RESPONSE_BOUND_STOP')
   if index==0:
    out.update(verify(raw,now));out['credential_active']=True;transport.verified(_CAPABILITY)
   else:
    out.update(worker_metadata(raw));out['granular_target_read']=True;out['classification']='GRANULAR_WORKER_API_TARGET_READ_CONFIRMED'
   del raw
 except Stop as e:out['reason_codes']=[str(e)]
 except Exception:out['reason_codes']=['TRANSPORT_OR_SHAPE_UNKNOWN_STOP']
 return out

def collect_git_facts(before,git,exists):
 need(git('rev-parse','--is-shallow-repository')=='false','SHALLOW_REPOSITORY_STOP')
 root=git('merge-base',PARENT,before);need(root==PARENT,'PREPARATION_ROOT_STOP')
 count=git('rev-list','--count',PARENT+'..'+before);need(count.isdigit(),'GIT_HISTORY_STOP')
 return {'full_history':True,'root':root,'count':int(count),'preparation_files':git('diff','--name-only',PARENT,before).splitlines(),'head':git('rev-parse','HEAD'),'parent':git('rev-parse','HEAD^'),'files':git('diff','--name-only',before,'HEAD').splitlines(),'message':git('log','-1','--format=%B'),'marker_preexisted':exists(before+':'+MARKER),'deploy_marker_absent_root':not exists(PARENT+':'+DEPLOY_MARKER),'deploy_marker_absent_prepared':not exists(before+':'+DEPLOY_MARKER),'deploy_marker_absent_head':not exists('HEAD:'+DEPLOY_MARKER),'deploy_marker_absent_worktree':not Path(DEPLOY_MARKER).exists(),'deploy_ancestor':git('merge-base',DEPLOY_PREPARED,PARENT),'r3_marker_hashes':{k:sha(git('show',c+':'+R3_MARKER).encode()) for k,c in [('root',PARENT),('prepared',before),('head','HEAD')]},'r2_marker_hashes':{k:sha(git('show',c+':'+R2_MARKER).encode()) for k,c in [('root',PARENT),('prepared',before),('head','HEAD')]},'r1_marker_hashes':{k:sha(git('show',c+':'+R1_MARKER).encode()) for k,c in [('root',PARENT),('prepared',before),('head','HEAD')]},'deploy_root_hashes':{p:sha(git('show',DEPLOY_PREPARED+':'+p).encode()) for p in (DEPLOY_PLAN,DEPLOY_EXECUTOR)}}

def load_gate():
 import os,subprocess
 event=json_exact(Path(os.environ['GITHUB_EVENT_PATH']).read_bytes());before=event['before'];need(type(before) is str and re.fullmatch('[a-f0-9]{40}',before),'PREPARED_COMMIT_STOP')
 def git(*a):
  r=subprocess.run(['git',*a],text=True,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,check=False);need(r.returncode==0,'GIT_HISTORY_COMMAND_STOP');return r.stdout if a[0]=='show' else r.stdout.strip()
 def exists(spec):return subprocess.run(['git','cat-file','-e',spec],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0
 facts=collect_git_facts(before,git,exists);files={p:Path(p).read_bytes() for p in PINS.values()};validate_gate(dict(os.environ),event,facts,json_exact(Path(MARKER).read_bytes()),files);return files

def main():
 import os
 out=result_base()
 try:
  load_gate();t=AuthorizedTransport(os.environ.get(SECRET),_CAPABILITY);out=inspect(t)
 except Stop as e:out['reason_codes']=[str(e)]
 except Exception:out['reason_codes']=['LOCAL_GATE_STOP']
 print(json.dumps(out,sort_keys=True))
if __name__=='__main__':main()
