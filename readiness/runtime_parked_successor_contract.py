"""Parked successor contract; import-time operations are offline only."""
import json,re
from pathlib import Path
from datetime import datetime,timezone
try:
 from readiness import runtime_parked_deploy_executor as old
 from readiness import runtime_parked_deploy_token_verify_r4 as token
 from readiness.runtime_remote_readonly_executor import Stop,need,sha,json_exact,envelope,source_metadata,schedules_metadata,queues_metadata,MAX,ERROR_MAX,TIMEOUT
 from readiness.runtime_visibility_completion_r4_executor import subdomain,domains,zones
except ModuleNotFoundError:
 import runtime_parked_deploy_executor as old
 import runtime_parked_deploy_token_verify_r4 as token
 from runtime_remote_readonly_executor import Stop,need,sha,json_exact,envelope,source_metadata,schedules_metadata,queues_metadata,MAX,ERROR_MAX,TIMEOUT
 from runtime_visibility_completion_r4_executor import subdomain,domains,zones
PARENT='acf688aa1e9ef08457049baea5fe1aa5fb4da4c1'
REPO=old.REPO;BRANCH=old.BRANCH;ACCOUNT=old.ACCOUNT;WORKER=old.WORKER;FLAGS=old.FLAGS
OLD=old.OLD;NEW=old.NEW;BUNDLE=old.BUNDLE;CONFIG=old.CONFIG;TARGET=old.TARGET
DEPLOY_ID='provider-neutral-runtime-parked-deploy-20261012-r2'
POST_ID='provider-neutral-runtime-parked-postdeploy-readonly-20261012-r1'
OLD_MARKER=old.MARKER
R4_MARKER='audit-evidence/consumed/provider-neutral-runtime-parked-deploy-token-verify-20261012-r4.json'
R4_RUN=38189160131
COMMON='readiness/runtime_parked_successor_contract.py'
AUDIT_GETS=(old.PREFIX+'/content/v2',old.PREFIX+'/settings',old.PREFIX+'/schedules','/accounts/'+ACCOUNT+'/queues',old.PREFIX+'/subdomain','/accounts/'+ACCOUNT+'/workers/domains?service='+WORKER,'/zones?account.id='+ACCOUNT+'&per_page=50&page=1')
VERIFY='/accounts/'+ACCOUNT+'/tokens/verify'
ACK='PARKED_DEPLOY_ACK_STOP_BEFORE_POSTCHECK'
POST_SUCCESS='PARKED_POSTDEPLOY_READONLY_SUCCESS_STOP'
_CAPABILITY=object()
ZERO=('D1_requests','invocations','dispatches','YouTube_calls','production_writes','route_writes','domain_writes','subdomain_writes','cron_writes','queue_writes','query_mutations','retry','rerun','resume','resend','rollback','redirect','fallback','raw_retention','secret_exposure')

def filelist(value):
 need(type(value) is list and value and all(type(p) is str for p in value) and value==sorted(value) and len(value)==len(set(value)),'PREPARATION_HISTORY_STOP')
 need(all(type(p) is str and p and not p.startswith('/') and '\\' not in p and all(x not in ('','..','.') for x in p.split('/')) and not p.startswith('audit-evidence/consumed/') for p in value),'PREPARATION_HISTORY_STOP')
 return value

def validate_gate(spec,env,event,facts,marker,files):
 need(all(env.get(k)=='true' for k in FLAGS),'SAFE_FLAGS_STOP')
 need(env.get('GITHUB_REPOSITORY')==REPO and env.get('GITHUB_REF')==BRANCH and env.get('GITHUB_EVENT_NAME')=='push' and env.get('GITHUB_RUN_ATTEMPT')=='1','EXECUTION_CONTEXT_STOP')
 before=event.get('before');after=event.get('after');head=event.get('head_commit',{})
 need(type(before) is str and re.fullmatch('[a-f0-9]{40}',before) and after==env.get('GITHUB_SHA') and head.get('id')==after and head.get('message')==spec['message'] and len(event.get('commits',[]))==1,'PUSH_BINDING_STOP')
 required=set(spec['pins'])|{'identity','state','prepared_commit_sha'}
 if spec['post']:required|={'prerequisite_commit_sha','prerequisite_run_id'}
 else:required|={'operational_exclusion_attested'}
 need(type(marker) is dict and set(marker)==required and marker['identity']==spec['identity'] and marker['state']=='CONSUMED_BEFORE_REMOTE' and re.fullmatch('[a-f0-9]{40}',marker['prepared_commit_sha']),'MARKER_BINDING_STOP')
 for k,p in spec['pins'].items():need(sha(files[p])==marker[k],'SOURCE_HASH_DRIFT_STOP')
 for p,h in spec['immutable'].items():need(sha(files[p])==h,'IMMUTABLE_DEPENDENCY_STOP')
 plan=json_exact(files[spec['plan']]);expected=filelist(plan.get('preparation_files'))
 need(facts.get('full_history') is True and facts.get('root')==PARENT and facts.get('count')==1 and facts.get('preparation_files')==expected,'PREPARATION_HISTORY_STOP')
 need(facts.get('head')==after and facts.get('parent')==before and facts.get('files')==[spec['marker']] and facts.get('message')==spec['message'] and facts.get('marker_preexisted') is False,'MARKER_ONLY_STOP')
 need(all(facts.get('old_deploy_absent',{}).get(k) is True for k in ('root','prepared','head','worktree')),'OLD_DEPLOY_CONSUMED_STOP')
 need(facts.get('historical_hashes')=={p:{k:h for k in ('root','prepared','head')} for p,h in spec['historical'].items()},'CONSUMED_HISTORY_DRIFT_STOP')
 need(facts.get('immutable_root_hashes')==spec['immutable'],'ROOT_DEPENDENCY_DRIFT_STOP')
 if spec['post']:
  need(marker['prerequisite_commit_sha']==before and type(marker['prerequisite_run_id']) is int and marker['prerequisite_run_id']>0 and facts.get('deploy_marker_chain') is True,'PREREQUISITE_CHAIN_STOP')
 else:
  need(marker['prepared_commit_sha']==before,'PREPARED_COMMIT_STOP')
  need(marker.get('operational_exclusion_attested') is True,'OPERATIONAL_EXCLUSION_REQUIRED_STOP')
 need(plan['identity']==spec['identity'] and plan['exact_preparation_parent']==PARENT and plan['preparation_commit_count']==1 and plan['requests']==[{'method':'GET','path':p} for p in AUDIT_GETS],'PLAN_CONTRACT_STOP')
 need(plan['maximum_audit_GETs']==7 and plan['maximum_script_writes']==(0 if spec['post'] else 1) and plan['maximum_token_verify_GETs']==(0 if spec['post'] else 1) and plan['maximum_Cloudflare_HTTP']==(7 if spec['post'] else 9),'PLAN_BUDGET_STOP')
 need(plan['timeout_seconds']==TIMEOUT and plan['response_bytes_max_each']==MAX and plan['error_body_bytes_max']==ERROR_MAX and plan['runtime_activation_approved'] is False and plan['execution_approved'] is False,'PLAN_SAFETY_STOP')
 for k in ZERO:need(type(plan.get(k)) is int and plan[k]==0,'PLAN_SAFETY_STOP')
 for k in spec['pins']:
  if k!='plan_sha256':need(plan[k]==marker[k],'PLAN_PIN_STOP')
 old.validate_candidate(files[BUNDLE],files[CONFIG]);t=json_exact(files[TARGET])
 need(t['target_status']=='PINNED_READONLY_NOT_EXECUTION_APPROVED' and t['execution_approved'] is False and t['launchable'] is False and t['mutable_branch_fallback'] is False,'TARGET_ACTIVATION_STOP')
 return plan

def collect_facts(spec,before,marker,git,exists):
 need(git('rev-parse','--is-shallow-repository')=='false','SHALLOW_REPOSITORY_STOP')
 prepared=marker['prepared_commit_sha'];root=git('merge-base',PARENT,prepared);need(root==PARENT,'PREPARATION_ROOT_STOP')
 count=git('rev-list','--count',PARENT+'..'+prepared);need(count.isdigit(),'GIT_HISTORY_STOP')
 f={'full_history':True,'root':root,'count':int(count),'preparation_files':git('diff','--name-only',PARENT,prepared).splitlines(),'head':git('rev-parse','HEAD'),'parent':git('rev-parse','HEAD^'),'files':git('diff','--name-only',before,'HEAD').splitlines(),'message':git('log','-1','--format=%B'),'marker_preexisted':exists(before+':'+spec['marker']),'old_deploy_absent':{k:not exists(s+':'+OLD_MARKER) for k,s in [('root',PARENT),('prepared',prepared),('head','HEAD')]}}
 f['old_deploy_absent']['worktree']=not Path(OLD_MARKER).exists()
 f['historical_hashes']={p:{k:sha(git('show',s+':'+p).encode()) for k,s in [('root',PARENT),('prepared',prepared),('head','HEAD')]} for p in spec['historical']}
 f['immutable_root_hashes']={p:sha(git('show',PARENT+':'+p).encode()) for p in spec['immutable']}
 if spec['post']:
  dp=spec['deploy_marker'];dm=json_exact(git('show',before+':'+dp).encode())
  expected={k:sha(Path(p).read_bytes()) for k,p in spec['deploy_pins'].items()};expected.update(identity=DEPLOY_ID,state='CONSUMED_BEFORE_REMOTE',prepared_commit_sha=prepared,operational_exclusion_attested=True)
  f['deploy_marker_chain']=git('rev-parse',before+'^')==prepared and git('diff','--name-only',prepared,before).splitlines()==[dp] and git('log','-1','--format=%B',before)=='PLM runtime parked deploy once '+DEPLOY_ID and dm==expected and not exists(prepared+':'+dp)
 return f

def load_gate(spec):
 import os,subprocess
 event=json_exact(Path(os.environ['GITHUB_EVENT_PATH']).read_bytes());marker=json_exact(Path(spec['marker']).read_bytes());before=event['before']
 need(type(before) is str and re.fullmatch('[a-f0-9]{40}',before),'PREPARED_COMMIT_STOP')
 def git(*a):
  r=subprocess.run(['git',*a],text=True,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,check=False);need(r.returncode==0,'GIT_HISTORY_COMMAND_STOP');return r.stdout if a[0]=='show' else r.stdout.strip()
 def exists(s):return subprocess.run(['git','cat-file','-e',s],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0
 files={p:Path(p).read_bytes() for p in spec['pins'].values()};facts=collect_facts(spec,before,marker,git,exists)
 validate_gate(spec,dict(os.environ),event,facts,marker,files);return files,marker

def settings(raw,post):
 r=envelope(raw).get('result');need(type(r) is dict and type(r.get('bindings')) is list and len(r['bindings'])<=128,'SETTINGS_SHAPE_STOP')
 seen=set();flags={};db=False
 for b in r['bindings']:
  need(type(b) is dict and type(b.get('name')) is str and b['name'] not in seen,'SETTINGS_SHAPE_STOP');n=b['name'];seen.add(n)
  if n=='DB':need(b.get('type')=='d1' and b.get('id')=='18050cf6-934e-4f3a-a1cd-5041bac1c35e','DB_BINDING_DRIFT_STOP');db=True
  elif n in FLAGS:need(b.get('type')=='plain_text' and b.get('text')=='true','SAFE_FLAG_DRIFT_STOP');flags[n]='true'
  else:raise Stop('UNEXPECTED_BINDING_STOP')
 need(db,'DB_BINDING_DRIFT_STOP')
 if post:need(flags==FLAGS and seen==set(FLAGS)|{'DB'},'PARKED_BINDINGS_STOP')
 need(r.get('workers_dev') is not True and r.get('preview_urls') is not True,'STOP_UNEXPECTED_ACTIVE_RUNTIME')
 return {'binding_exact':True,'safe_flags_exact':flags==FLAGS,'secret_values_accessed':False}

def audit_response(index,raw,meta,post):
 if index==0:
  p=source_metadata(raw,meta,{OLD});expected=NEW if post else OLD
  need(p.get('source_representation_proven') is True,'SOURCE_REPRESENTATION_UNVERIFIED_STOP')
  need(p.get('source_module_sha256')==expected,'SOURCE_DRIFT_STOP_NO_DEPLOY')
  return {'source_exact':True,'source_sha256':expected,'parked_proven':True}
 if index==1:return settings(raw,post)
 if index==2:
  p=schedules_metadata(raw);need(p['cron_complete'] is True and p['cron_count']==0,'STOP_UNEXPECTED_ACTIVE_RUNTIME');return {'cron_complete':True,'cron_count':0}
 if index==3:
  p=queues_metadata(raw);need(p['consumers_complete'] is True and p['consumer_count']==0,'CONSUMERS_UNVERIFIED_STOP');return {'consumers_complete':True,'consumer_count':0}
 if index==4:return subdomain(raw)
 if index==5:
  p=domains(raw);return {'custom_domains_complete':p['custom_domains_complete'],'custom_domain_count':p['custom_domain_count']}
 p=zones(raw);need(p['zones_complete'] is True and p['zone_count']==0,'ROUTE_INSPECTION_REQUIRED');return {'zones_complete':True,'zone_count':0,'classic_routes_complete':True,'classic_route_count':0}

class Budget:
 def __init__(self,post):self.post=post;self.index=0;self.ready=False;self.write=0
 def admit(self,method,path):
  paths=AUDIT_GETS if self.post else (VERIFY,)+AUDIT_GETS
  if method=='GET':need(not self.write and self.index<len(paths) and path==paths[self.index],'REQUEST_GATE_STOP');self.index+=1
  else:need(not self.post and method=='PUT' and path==old.PUT and self.index==8 and self.ready and not self.write,'WRITE_GATE_STOP');self.write=1
 def permit(self,cap):need(cap is _CAPABILITY and not self.post and self.index==8 and not self.write,'WRITE_GATE_STOP');self.ready=True

class Transport:
 def __init__(self,read_token,deploy_token=None,post=False,capability=None):
  need(capability is _CAPABILITY,'ONE_SHOT_GATE_REQUIRED')
  need(type(read_token) is str and read_token and not any(c in read_token for c in '\r\n'),'READ_CREDENTIAL_MISSING_STOP')
  if not post:
   need(type(deploy_token) is str and deploy_token and not any(c in deploy_token for c in '\r\n'),'DEPLOY_CREDENTIAL_MISSING_STOP');need(read_token!=deploy_token,'CREDENTIAL_ROLES_NOT_DISTINCT_STOP')
  else:need(deploy_token is None,'POSTCHECK_WRITE_CREDENTIAL_FORBIDDEN')
  self.read_token=read_token;self.deploy_token=deploy_token;self.budget=Budget(post)
 def permit(self,c):self.budget.permit(c)
 def __call__(self,method,path,body=None,content_type=None):
  import http.client,time
  self.budget.admit(method,path);need(method!='PUT' or type(body) is bytes and type(content_type) is str,'UPLOAD_BODY_STOP')
  selected=self.deploy_token if method=='PUT' or path==VERIFY else self.read_token
  started=time.monotonic();c=http.client.HTTPSConnection('api.cloudflare.com',timeout=TIMEOUT)
  try:
   headers={'Authorization':'Bearer '+selected,'Accept':'*/*'}
   if method=='PUT':headers['Content-Type']=content_type
   c.connect();remaining=TIMEOUT-(time.monotonic()-started);need(remaining>0,'TRANSPORT_UNKNOWN_NO_RETRY');c.sock.settimeout(remaining)
   c.request(method,'/client/v4'+path,body=body,headers=headers)
   remaining=TIMEOUT-(time.monotonic()-started);need(remaining>0,'TRANSPORT_UNKNOWN_NO_RETRY');c.sock.settimeout(remaining)
   r=c.getresponse();status=r.status;limit=MAX if status==200 else ERROR_MAX;parts=[];n=0
   while n<=limit:
    remaining=TIMEOUT-(time.monotonic()-started);need(remaining>0,'TRANSPORT_UNKNOWN_NO_RETRY');sock=c.sock or getattr(getattr(getattr(r,'fp',None),'raw',None),'_sock',None)
    if sock:sock.settimeout(remaining)
    chunk=r.read1(min(8192,limit+1-n))
    if not chunk:break
    parts.append(chunk);n+=len(chunk)
   raw=b''.join(parts);need(len(raw)<=limit,'RESPONSE_BOUND_STOP')
   return status,raw,{'content_type':r.getheader('Content-Type') or '', 'entrypoint':r.getheader('cf-entrypoint')}
  finally:c.close()

def output(identity,post):
 return {'identity':identity,'classification':'POSTCHECK_STOP' if post else 'FRESH_PRE_GATE_STOP','reason_codes':[],'requests_attempted':0,'audit_GETs':0,'token_verify_GETs':0,'script_writes_attempted':0,'request_order':[],'HTTP_statuses':[],'cloudflare_error_codes':[],'postcheck_required':not post,'runtime_activation_approved':False,**{k:0 for k in ZERO}}

def execute(spec,t,files,now=None):
 out=output(spec['identity'],spec['post']);injected_now=now;now=now or datetime.now(timezone.utc)
 try:
  old.validate_candidate(files[BUNDLE],files[CONFIG])
  if not spec['post']:
   out['requests_attempted']+=1;out['token_verify_GETs']=1;out['request_order'].append('GET '+VERIFY)
   status,raw,_=t('GET',VERIFY);out['HTTP_statuses'].append(status)
   if status!=200:out['cloudflare_error_codes']=old.numeric_errors(raw);raise Stop('TOKEN_HTTP_'+str(status)+'_STOP')
   need(type(raw) is bytes and len(raw)<=MAX,'RESPONSE_BOUND_STOP');p=token.verify(raw,now)
   need('expires_on' in p,'FINITE_EXPIRY_REQUIRED_STOP');out.update(p);out['credential_active']=True;del raw
  for index,path in enumerate(AUDIT_GETS):
   out['requests_attempted']+=1;out['audit_GETs']+=1;out['request_order'].append('GET '+path)
   status,raw,meta=t('GET',path);out['HTTP_statuses'].append(status)
   if status!=200:out['cloudflare_error_codes']=old.numeric_errors(raw);raise Stop('AUDIT_HTTP_'+str(status)+'_STOP')
   need(type(raw) is bytes and len(raw)<=MAX,'RESPONSE_BOUND_STOP');out.update(audit_response(index,raw,meta,spec['post']));del raw
  if spec['post']:out['classification']=POST_SUCCESS;out['read_complete']=True;return out
  need(token.timestamp(out['expires_on'])>datetime.now(timezone.utc) if injected_now is None else token.timestamp(out['expires_on'])>now,'TOKEN_EXPIRED_STOP')
  body,typ=old.multipart(files[BUNDLE],files[CONFIG]);t.permit(_CAPABILITY);out['fresh_pre_gate']='PASS';out['script_writes_attempted']=1;out['requests_attempted']+=1;out['request_order'].append('PUT '+old.PUT)
  status,raw,_=t('PUT',old.PUT,body,typ);out['HTTP_statuses'].append(status);out['cloudflare_error_codes']=old.numeric_errors(raw)
  need(status==200 and type(raw) is bytes and len(raw)<=MAX,'DEPLOY_UNKNOWN_STOP_NO_RETRY');d=envelope(raw);r=d.get('result')
  need(type(r) is dict and r.get('id')==WORKER and d.get('errors')==[],'DEPLOY_UNKNOWN_STOP_NO_RETRY');del raw
  out.update(classification=ACK,acknowledged=True)
 except Stop as e:
  out['reason_codes']=['DEPLOY_UNKNOWN_STOP_NO_RETRY' if out['script_writes_attempted'] else str(e)]
  if out['script_writes_attempted']:out['classification']='DEPLOY_UNKNOWN_STOP_NO_RETRY'
 except Exception:
  out['reason_codes']=['DEPLOY_UNKNOWN_STOP_NO_RETRY' if out['script_writes_attempted'] else 'TRANSPORT_UNKNOWN_NO_RETRY']
  if out['script_writes_attempted']:out['classification']='DEPLOY_UNKNOWN_STOP_NO_RETRY'
 return out

def check_prerequisite(marker,run,jobs,workflow):
 need(type(run) is dict and run.get('id')==marker['prerequisite_run_id'] and run.get('run_attempt')==1 and run.get('status')=='completed' and run.get('conclusion')=='success' and run.get('event')=='push' and run.get('head_sha')==marker['prerequisite_commit_sha'] and run.get('head_branch')==BRANCH.split('/')[-1] and run.get('path')==workflow and type(run.get('repository')) is dict and run['repository'].get('full_name')==REPO,'PREREQUISITE_RUN_STOP')
 need(type(jobs) is dict and type(jobs.get('jobs')) is list and jobs.get('total_count')==len(jobs['jobs'])==1,'PREREQUISITE_JOBS_STOP')
 j=jobs['jobs'][0];need(j.get('run_id')==marker['prerequisite_run_id'] and j.get('name')=='deploy' and j.get('status')=='completed' and j.get('conclusion')=='success' and type(j.get('steps')) is list,'PREREQUISITE_JOBS_STOP')
 ack=[s for s in j['steps'] if type(s) is dict and s.get('name')==ACK]
 need(len(ack)==1 and ack[0].get('status')=='completed' and ack[0].get('conclusion')=='success','PREREQUISITE_ACK_STOP')
 return True

def github_prerequisite(spec,marker,github_token):
 import http.client,time
 need(type(github_token) is str and github_token and not any(c in github_token for c in '\r\n'),'GITHUB_CREDENTIAL_MISSING_STOP')
 base='/repos/'+REPO+'/actions/runs/'+str(marker['prerequisite_run_id'])
 values=[]
 for path in (base,base+'/jobs?per_page=10'):
  started=time.monotonic();c=http.client.HTTPSConnection('api.github.com',timeout=TIMEOUT)
  try:
   c.connect();remaining=TIMEOUT-(time.monotonic()-started);need(remaining>0,'PREREQUISITE_TIMEOUT_STOP');c.sock.settimeout(remaining)
   c.request('GET',path,headers={'Authorization':'Bearer '+github_token,'Accept':'application/vnd.github+json','User-Agent':'PLM-bounded-postdeploy-prerequisite'})
   remaining=TIMEOUT-(time.monotonic()-started);need(remaining>0,'PREREQUISITE_TIMEOUT_STOP');c.sock.settimeout(remaining)
   r=c.getresponse();need(r.status==200,'PREREQUISITE_HTTP_STOP');parts=[];n=0
   while n<=MAX:
    remaining=TIMEOUT-(time.monotonic()-started);need(remaining>0,'PREREQUISITE_TIMEOUT_STOP');sock=c.sock or getattr(getattr(getattr(r,'fp',None),'raw',None),'_sock',None)
    if sock:sock.settimeout(remaining)
    chunk=r.read1(min(8192,MAX+1-n))
    if not chunk:break
    parts.append(chunk);n+=len(chunk)
   raw=b''.join(parts);need(len(raw)<=MAX,'PREREQUISITE_RESPONSE_BOUND_STOP');values.append(json_exact(raw));del raw
  finally:c.close()
 return check_prerequisite(marker,*values,spec['deploy_workflow'])
