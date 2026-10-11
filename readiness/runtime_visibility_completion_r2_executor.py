"""Single-use exposure inspection. All import-time behavior is offline."""
import hashlib,json,re
from pathlib import Path
try:
 from readiness.runtime_remote_readonly_executor import Stop,need,sha,json_exact,envelope,source_metadata,MAX,ERROR_MAX,TIMEOUT
except ModuleNotFoundError:
 from runtime_remote_readonly_executor import Stop,need,sha,json_exact,envelope,source_metadata,MAX,ERROR_MAX,TIMEOUT
IDENTITY='provider-neutral-runtime-visibility-completion-20261011-r2'
PARENT='224e15e9fd598337da1ecedf7bc7c2e04dd99dda'
EVIDENCE_COMMIT='8535d651e21623e521ed4024bf3abc4031b7474b'
R1_MARKER='audit-evidence/consumed/provider-neutral-runtime-visibility-completion-20261011-r1.json'
R1_MARKER_SHA='d07a86dd1f6cd9b46396cbb7c726016333ae07986183cd5cd825bb2e15f7a9cb'
REPO='ikkinotako2-sketch/project-love-machine-serverless-sandbox'
BRANCH='refs/heads/plm-offline-readiness-v1-20261002'
ACCOUNT='6c8ccd6aface937ab5dabef61cb64534'
WORKER='plm-serverless-sandbox-control'
REMOTE_SHA='6c5d726f96d56dac792ff739f87227926197891f1149b1dedeeac38e67128451'
PREFIX='/accounts/'+ACCOUNT+'/workers/scripts/'+WORKER
ENDPOINTS=(PREFIX+'/subdomain','/accounts/'+ACCOUNT+'/workers/domains','/zones?account.id='+ACCOUNT+'&per_page=50&page=1',PREFIX+'/content/v2')
HELPER='readiness/runtime_visibility_completion_r2_executor.py'
WORKFLOW='.github/workflows/plm-runtime-visibility-completion-r2-once.yml'
PLAN='readiness/runtime-visibility-completion-r2-plan.json'
SCHEMA='readiness/runtime-visibility-completion-r2-marker.schema.json'
CENSUS='readiness/runtime-visibility-source-census.json'
PRIOR='readiness/runtime-visibility-prior-evidence.json'
BOOTSTRAP='serverless/bootstrap-placeholder.mjs'
DEPENDENCY='readiness/runtime_remote_readonly_executor.py'
TARGET='readiness/runtime-target-pinned-manifest.json'
MARKER='audit-evidence/consumed/'+IDENTITY+'.json'
MESSAGE='PLM runtime visibility readonly once '+IDENTITY
PIN_FILES={'workflow_sha256':WORKFLOW,'helper_sha256':HELPER,'plan_sha256':PLAN,'schema_sha256':SCHEMA,'census_sha256':CENSUS,'prior_evidence_sha256':PRIOR,'parser_dependency_sha256':DEPENDENCY,'target_manifest_sha256':TARGET,'known_source_sha256':BOOTSTRAP,'r1_consumed_marker_sha256':R1_MARKER}
# Fixed finite grammar; no eval, import, property lookup or arbitrary expressions.
LITERAL_PARKED=re.compile(rb'\s*export\s+default\s*\{\s*fetch\s*\(\s*\)\s*\{\s*return\s+new\s+Response\s*\(\s*"PARKED"\s*,\s*\{\s*status\s*:\s*503\s*\}\s*\)\s*;\s*\}\s*\}\s*;\s*')
def strict_parked(raw,known_bytes=None):
 if type(raw) is not bytes or len(raw)>65536:return False
 if known_bytes is not None and raw==known_bytes and sha(raw)==REMOTE_SHA:return True
 return LITERAL_PARKED.fullmatch(raw) is not None

def census_proof(census,known_bytes,prior):
 return (type(census) is dict and census.get('exact_match') is True and census.get('remote_sha256')==REMOTE_SHA and census.get('matched_path')==BOOTSTRAP and census.get('matched_commit')==EVIDENCE_COMMIT and census.get('known_old_parked_source') is True and sha(known_bytes)==REMOTE_SHA and strict_parked(known_bytes,known_bytes) and prior.get('source_module_sha256')==REMOTE_SHA and prior.get('source_representation_proven') is True)

def complete_list(raw,code,strict_one=False):
 d=envelope(raw);rows=d.get('result');i=d.get('result_info')
 need(type(rows) is list and len(rows)<=1000 and type(i) is dict,code)
 need(all(type(i.get(k)) is int for k in ('count','total_count','page','per_page','total_pages')),code)
 need(i['page']==1 and i['count']==i['total_count']==len(rows) and i['per_page']>=len(rows) and i['per_page']>0 and i['total_pages'] in ((1,) if strict_one else (0,1)) and (i['total_pages']!=0 or len(rows)==0),code)
 return rows

def subdomain(raw):
 r=envelope(raw).get('result');need(type(r) is dict and type(r.get('enabled')) is bool and type(r.get('previews_enabled')) is bool,'SUBDOMAIN_SHAPE_STOP')
 need(not r['enabled'] and not r['previews_enabled'],'STOP_UNEXPECTED_ACTIVE_RUNTIME')
 return {'workers_dev_enabled':False,'previews_enabled':False,'workers_dev_complete':True}

def domains(raw):
 rows=complete_list(raw,'BLOCKED_CUSTOM_DOMAIN_PAGINATION');seen=set();target_count=0;zones=set()
 for r in rows:
  need(type(r) is dict and type(r.get('id')) is str and r['id'] not in seen and type(r.get('service')) is str and type(r.get('enabled')) is bool and type(r.get('previews_enabled')) is bool,'DOMAIN_SHAPE_STOP');seen.add(r['id'])
  if r['service']==WORKER:
   target_count+=1
   need(not r['enabled'] and not r['previews_enabled'],'STOP_UNEXPECTED_ACTIVE_RUNTIME')
   if 'zone_id' in r:need(type(r['zone_id']) is str and re.fullmatch('[a-f0-9]{32}',r['zone_id']),'DOMAIN_SHAPE_STOP');zones.add(r['zone_id'])
 # PASS requires no target domains, including disabled records; no invented current exposure.
 need(target_count==0,'BLOCKED_TARGET_DOMAIN_PRESENT')
 return {'custom_domains_complete':True,'custom_domain_count':0,'custom_domain_zone_ids':sorted(zones)}

def zones(raw):
 rows=complete_list(raw,'BLOCKED_ZONE_PAGINATION',True);ids=set()
 for r in rows:
  need(type(r) is dict and type(r.get('id')) is str and re.fullmatch('[a-f0-9]{32}',r['id']) and r['id'] not in ids and type(r.get('account')) is dict and r['account'].get('id')==ACCOUNT,'ZONE_SHAPE_STOP');ids.add(r['id'])
 return {'zones_complete':True,'zone_count':len(ids),'zone_ids':sorted(ids),'classic_routes_complete':not ids,'classic_route_count':0 if not ids else None}

class RequestGate:
 def __init__(self,transport):self.transport=transport;self.count=0;self.statuses=[];self.stopped=False
 def get(self,method,path):
  need(not self.stopped and method=='GET' and self.count<4 and path==ENDPOINTS[self.count],'REQUEST_GATE_STOP');self.count+=1
  try:
   status,raw,meta=self.transport(method,path);need(type(status) is int and 100<=status<=599,'HTTP_SHAPE_STOP');self.statuses.append(status)
   if status!=200:
    if status==403:raise Stop('UNVERIFIED_ZONE_PERMISSION' if self.count==3 else 'UNVERIFIED_PERMISSION_LIMIT')
    if 300<=status<400:raise Stop('REDIRECT_STOP')
    raise Stop('HTTP_'+str(status)+'_STOP')
   need(type(raw) is bytes and 0<len(raw)<=MAX and type(meta) is dict,'RESPONSE_BOUND_STOP');return raw,meta
  except Stop:self.stopped=True;raise
  except Exception:self.stopped=True;raise Stop('TRANSPORT_UNKNOWN_NO_RETRY') from None

def inspect(transport,census,known_bytes,prior):
 g=RequestGate(transport);proven=census_proof(census,known_bytes,prior)
 out={'identity':IDENTITY,'classification':'BLOCKED_REMOTE_VISIBILITY','reason_codes':[],'pass':False,'source_identity_proven':proven,'source_sha256':REMOTE_SHA if proven else None,'source_proof_basis':'PRIOR_RUN_EXACT_REPO_IDENTITY' if proven else 'UNVERIFIED','source_freshly_revalidated':False,'known_old_parked_source':proven,'parked_proven':proven,'candidate_equal':'NO','classic_routes_complete':False,'classic_route_count':None,'cron_count':prior.get('cron_count'),'consumer_count':prior.get('consumer_count'),'binding_exact':prior.get('binding_exact'),'inherited_evidence_run':38128155103,'inherited_metadata_is_fresh':False,'writes':0,'D1_requests':0,'deploys':0,'dispatches':0,'uploads':0,'YouTube_calls':0,'retry':0,'resume':0,'redirect':0,'fallback':0,'raw_retention':0,'secret_exposure':0,'secret_values_accessed':False,'execution_approved':False,'launchable':False,'next_one_action':'REPORT_ONLY_STOP_NO_DEPLOY'}
 try:
  raw,_=g.get('GET',ENDPOINTS[0]);out.update(subdomain(raw));del raw
  raw,_=g.get('GET',ENDPOINTS[1]);out.update(domains(raw));del raw
  raw,_=g.get('GET',ENDPOINTS[2]);out.update(zones(raw));del raw
  need(out['zone_count']==0,'ROUTE_INSPECTION_REQUIRED')
  if not proven:
   raw,meta=g.get('GET',ENDPOINTS[3]);sm=source_metadata(raw,meta,set());out.update(source_sha256=sm.get('source_module_sha256'),source_freshly_revalidated=True,source_identity_proven=False,source_proof_basis='STRICT_STATIC_MEMORY_ONLY')
   # Only exact single raw JS representation is accepted by finite grammar.
   mime=meta.get('content_type','').split(';')[0].strip().lower()
   out['parked_proven']=sm.get('source_representation_proven') is True and mime in ('text/javascript','application/javascript','application/javascript+module','text/javascript+module') and strict_parked(raw)
   del raw
  need(out['parked_proven'],'BLOCKED_UNKNOWN_REMOTE_SOURCE')
  need(prior.get('worker_exists') is True and prior.get('binding_exact') is True and prior.get('cron_complete') is True and prior.get('cron_count')==0 and prior.get('consumers_complete') is True and prior.get('consumer_count')==0,'BLOCKED_PRIOR_EVIDENCE')
  out.update({'classification':'REMOTE_INACTIVE_SOURCE_PINNED','pass':True})
 except Stop as e:
  out['reason_codes']=[str(e)]
  if str(e) in ('STOP_UNEXPECTED_ACTIVE_RUNTIME','BLOCKED_UNKNOWN_REMOTE_SOURCE'):out['classification']=str(e)
 except Exception:out['reason_codes']=['RESPONSE_SHAPE_STOP']
 out.update(requests_attempted=g.count,request_order=list(ENDPOINTS[:g.count]),http_statuses=g.statuses)
 return out

def validate_gate(env,event,facts,marker,plan,files):
 need(all(env.get(k)=='true' for k in ('TEST_ONLY','DRY_RUN','NO_PUBLISH','EMERGENCY_STOP')),'SAFE_FLAGS_STOP')
 need(env.get('GITHUB_REPOSITORY')==REPO and env.get('GITHUB_REF')==BRANCH and env.get('GITHUB_EVENT_NAME')=='push' and env.get('GITHUB_RUN_ATTEMPT')=='1','EXECUTION_CONTEXT_STOP')
 before=event.get('before');after=event.get('after');head=event.get('head_commit',{})
 need(type(before) is str and re.fullmatch('[a-f0-9]{40}',before) and after==env.get('GITHUB_SHA') and head.get('id')==after and head.get('message')==MESSAGE and len(event.get('commits',[]))==1,'PUSH_BINDING_STOP')
 need({k:facts.get(k) for k in ('head','parent','files','marker_preexisted','message')}=={'head':after,'parent':before,'files':[MARKER],'marker_preexisted':False,'message':MESSAGE},'MARKER_ONLY_CHAIN_STOP')
 need(facts.get('preparation_root_ancestor') is True and type(facts.get('preparation_commit_count')) is int and 1<=facts['preparation_commit_count']<=3,'PREPARATION_CHAIN_STOP')
 core={HELPER,WORKFLOW,PLAN,SCHEMA,'readiness/test_runtime_visibility_completion_r2.py','.github/workflows/plm-runtime-integration-offline.yml'}
 allowed=core|{'readiness/test_runtime_visibility_completion.py'}
 changed=facts.get('preparation_files');need(type(changed) is list and len(changed)==len(set(changed)) and core<=set(changed)<=allowed,'PREPARATION_DIFF_STOP')
 need(type(marker) is dict and set(marker)==set(PIN_FILES)|{'identity','state','prepared_commit_sha'} and marker['identity']==IDENTITY and marker['state']=='CONSUMED_BEFORE_REMOTE' and marker['prepared_commit_sha']==before,'MARKER_BINDING_STOP')
 for k,p in PIN_FILES.items():need(sha(files[p])==marker[k],'SOURCE_HASH_DRIFT_STOP')
 need(plan.get('identity')==IDENTITY and plan.get('exact_preparation_parent')==PARENT and plan.get('allowed_requests')==[{'method':'GET','path':p} for p in ENDPOINTS] and plan.get('maximum_remote_reads')==4 and plan.get('timeout_seconds')==TIMEOUT and plan.get('response_bytes_max_each')==MAX and plan.get('error_body_bytes_max')==ERROR_MAX,'PLAN_BINDING_STOP')
 for k in ('maximum_writes','maximum_D1_requests','maximum_deploys','maximum_dispatches','maximum_uploads','maximum_YouTube_calls','retry','resume','redirect','fallback','pagination_fallback','raw_retention'):need(type(plan.get(k)) is int and plan[k]==0,'PLAN_LIMITS_STOP')
 for k in PIN_FILES:
  if k!='plan_sha256':need(plan.get(k)==marker[k],'PLAN_PIN_STOP')
 need(facts.get('full_history') is True and facts.get('r1_marker_in_parent_sha256')==R1_MARKER_SHA and sha(files[R1_MARKER])==R1_MARKER_SHA,'FULL_HISTORY_OR_R1_MARKER_STOP')
 need(plan.get('checkout_fetch_depth')==0 and plan.get('r1_historical_failure_run')==38130789006 and plan.get('r1_is_success_prerequisite') is False,'CHECKOUT_OR_PREREQUISITE_STOP')
 need(plan.get('execution_approved') is False and plan.get('launchable') is False,'ACTIVATION_STOP')
 census=json_exact(files[CENSUS]);prior=json_exact(files[PRIOR])
 need(prior.get('identity')=='provider-neutral-runtime-remote-readonly-inspection-20261011-r1' and prior.get('run_id')==38128155103 and prior.get('commit')==EVIDENCE_COMMIT and prior.get('attempt')==1 and prior.get('conclusion')=='success','PRIOR_BINDING_STOP')
 need(census_proof(census,files[BOOTSTRAP],prior),'CENSUS_BINDING_STOP')
 target=json_exact(files[TARGET]);need(target.get('target_status')=='PINNED_READONLY_NOT_EXECUTION_APPROVED' and target.get('execution_approved') is False and target.get('launchable') is False and target.get('mutable_branch_fallback') is False,'TARGET_BINDING_STOP')

_CAPABILITY=object()
class AuthorizedTransport:
 def __init__(self,token,capability=None):
  need(capability is _CAPABILITY,'ONE_SHOT_GATE_REQUIRED');self.token=token;self.count=0
 def __call__(self,method,path):
  import http.client,time
  need(method=='GET' and self.count<4 and path==ENDPOINTS[self.count],'REQUEST_GATE_STOP');self.count+=1;started=time.monotonic();c=http.client.HTTPSConnection('api.cloudflare.com',timeout=TIMEOUT)
  try:
   c.request('GET','/client/v4'+path,headers={'Authorization':'Bearer '+self.token,'Accept':'*/*'});r=c.getresponse();status=r.status
   def read(limit):
    parts=[];n=0
    while n<=limit:
     remaining=TIMEOUT-(time.monotonic()-started);need(remaining>0,'TRANSPORT_UNKNOWN_NO_RETRY')
     sock=c.sock if c.sock is not None else getattr(getattr(getattr(r,'fp',None),'raw',None),'_sock',None)
     if sock is not None:sock.settimeout(remaining)
     chunk=r.read1(min(8192,limit+1-n))
     if not chunk:break
     parts.append(chunk);n+=len(chunk)
    return b''.join(parts)
   if status!=200:
    b=read(ERROR_MAX);del b;return status,b'',{}
   n=r.getheader('Content-Length');need(n is None or n.isdigit() and int(n)<=MAX,'RESPONSE_BOUND_STOP');raw=read(MAX);need(len(raw)<=MAX,'RESPONSE_BOUND_STOP');return status,raw,{'content_type':r.getheader('Content-Type') or '', 'entrypoint':r.getheader('cf-entrypoint')}
  finally:c.close()

def collect_git_facts(before,git,exists):
 # Reject shallow state before attempting ancestry/count/diff. No GitHub history API scan.
 need(git('rev-parse','--is-shallow-repository')=='false','SHALLOW_REPOSITORY_STOP')
 root=git('merge-base',PARENT,before);need(root==PARENT,'PREPARATION_ROOT_STOP')
 count=git('rev-list','--count',PARENT+'..'+before);need(count.isdigit(),'GIT_HISTORY_SHAPE_STOP')
 r1_at_parent=git('show',PARENT+':'+R1_MARKER)
 # git show returns exact file bytes through text decoding; do not strip trailing newline.
 need(sha(r1_at_parent.encode())==R1_MARKER_SHA,'R1_CONSUMED_MARKER_DRIFT_STOP')
 return {'head':git('rev-parse','HEAD'),'parent':git('rev-parse','HEAD^'),'preparation_root_ancestor':True,'preparation_commit_count':int(count),'preparation_files':git('diff','--name-only',PARENT,before).splitlines(),'files':git('diff','--name-only',before,'HEAD').splitlines(),'marker_preexisted':exists(before+':'+MARKER),'message':git('log','-1','--format=%B'),'full_history':True,'r1_marker_in_parent_sha256':sha(r1_at_parent.encode())}

def load_gate():
 import os,subprocess
 event=json_exact(Path(os.environ['GITHUB_EVENT_PATH']).read_bytes());before=event['before'];need(type(before) is str and re.fullmatch('[a-f0-9]{40}',before),'PREPARED_COMMIT_STOP')
 def git(*a):
  try:
   r=subprocess.run(['git',*a],text=True,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,check=False)
   need(r.returncode==0,'GIT_HISTORY_COMMAND_STOP')
   return r.stdout if a[0]=='show' else r.stdout.strip()
  except Stop:raise
  except Exception:raise Stop('GIT_HISTORY_COMMAND_STOP') from None
 def exists(spec):return subprocess.run(['git','cat-file','-e',spec],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0
 facts=collect_git_facts(before,git,exists)
 files={p:Path(p).read_bytes() for p in PIN_FILES.values()};plan=json_exact(files[PLAN]);validate_gate(dict(os.environ),event,facts,json_exact(Path(MARKER).read_bytes()),plan,files);return files

def main():
 import os
 out={'identity':IDENTITY,'classification':'BLOCKED_REMOTE_VISIBILITY','reason_codes':[],'requests_attempted':0,'writes':0,'D1_requests':0,'deploys':0,'dispatches':0,'uploads':0,'YouTube_calls':0,'retry':0,'resume':0,'redirect':0,'raw_retention':0,'secret_exposure':0}
 try:
  files=load_gate();token=os.environ.get('PLM_CF_WORKER_API_TOKEN');need(type(token) is str and token and not any(c in token for c in '\r\n'),'CREDENTIAL_MISSING_STOP')
  out=inspect(AuthorizedTransport(token,_CAPABILITY),json_exact(files[CENSUS]),files[BOOTSTRAP],json_exact(files[PRIOR]))
 except Stop as e:out['reason_codes']=[str(e)]
 except Exception:out['reason_codes']=['LOCAL_GATE_STOP']
 print(json.dumps(out,sort_keys=True))
if __name__=='__main__':main()
