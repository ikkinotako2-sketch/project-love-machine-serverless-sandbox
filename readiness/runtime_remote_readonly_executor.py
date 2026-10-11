"""One-shot four-GET executor. No IO on import; source/metadata never persisted."""
import hashlib,json,re
from pathlib import Path
IDENTITY='provider-neutral-runtime-remote-readonly-inspection-20261011-r1'
PARENT='5dc0c5f3bb0dfc866ed59baecc09296629b8580c'
REPO='ikkinotako2-sketch/project-love-machine-serverless-sandbox'
BRANCH='refs/heads/plm-offline-readiness-v1-20261002'
ACCOUNT='6c8ccd6aface937ab5dabef61cb64534'
WORKER='plm-serverless-sandbox-control'
DB='18050cf6-934e-4f3a-a1cd-5041bac1c35e'
BUNDLE='8a6615fd020ca6590ba8f5e2c73a3844473d9e6ecd3babb19ea836d604d4a8a9'
SOURCE='134c97c36a0a20cc43b35e3dce1a1243a5d9008673ece5fb29f7cb8c3a52f3ea'
PREFIX='/accounts/'+ACCOUNT+'/workers/scripts/'+WORKER
ENDPOINTS=(PREFIX+'/content/v2',PREFIX+'/settings',PREFIX+'/schedules','/accounts/'+ACCOUNT+'/queues')
HELPER='readiness/runtime_remote_readonly_executor.py'
CONTRACT='readiness/runtime_remote_readonly_contract.py'
WORKFLOW='.github/workflows/plm-runtime-remote-readonly-once.yml'
PLAN='readiness/runtime-remote-readonly-executor-plan.json'
SCHEMA='readiness/runtime-remote-readonly-executor-marker.schema.json'
TARGET='readiness/runtime-target-pinned-manifest.json'
MARKER='audit-evidence/consumed/'+IDENTITY+'.json'
MESSAGE='PLM runtime remote readonly once '+IDENTITY
MAX=262144
ERROR_MAX=32768
TIMEOUT=15
JS={'application/javascript','text/javascript','application/javascript+module','text/javascript+module'}
class Stop(Exception):pass
def need(x,code):
 if not x:raise Stop(code)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def json_exact(raw):
 def pairs(items):
  d={}
  for k,v in items:need(k not in d,'DUPLICATE_JSON_STOP');d[k]=v
  return d
 try:return json.loads(raw.decode('utf-8'),object_pairs_hook=pairs,parse_constant=lambda _:(_ for _ in ()).throw(Stop('JSON_NUMBER_STOP')))
 except Stop:raise
 except Exception:raise Stop('RESPONSE_SHAPE_STOP') from None
def envelope(raw):
 d=json_exact(raw);need(type(d) is dict and d.get('success') is True,'RESPONSE_SHAPE_STOP');return d

def source_metadata(raw,meta,known_old):
 """Strict memory-only single JS or multipart selector; extra modules forbid equality."""
 result={'source_response_sha256':sha(raw),'source_response_bytes':len(raw),'source_representation_proven':False,'candidate_equal':'UNVERIFIED_SOURCE_REPRESENTATION','known_old_parked_source':False,'parked_proven':False}
 try:
  ctype=meta.get('content_type','');mime=ctype.split(';')[0].strip().lower();selector=meta.get('entrypoint');modules={};selected=None
  def name(s):need(type(s) is str and re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]{0,95}',s) and '..' not in s,'SOURCE_PARSE_UNVERIFIED');return s
  def module(n,typ,b):
   need(n not in modules and len(modules)<8 and len(b)<=65536 and typ in JS,'SOURCE_PARSE_UNVERIFIED');b.decode('utf-8',errors='strict');modules[n]=b
  if selector is not None:name(selector)
  if mime in JS:module(selector or 'raw-body.js',mime,raw);selected=selector or 'raw-body.js'
  elif mime=='multipart/form-data':
   m=re.fullmatch(r'multipart/form-data\s*;\s*boundary=(?:"([A-Za-z0-9\x27()+_,./:=?-]{1,70})"|([A-Za-z0-9\x27()+_,./:=?-]{1,70}))\s*',ctype,re.I);need(m,'SOURCE_PARSE_UNVERIFIED')
   marker=b'--'+(m[1] or m[2]).encode('ascii');need(raw.startswith(marker+b'\r\n') and raw.endswith(marker+b'--\r\n') or raw.startswith(marker+b'\r\n') and raw.endswith(marker+b'--'),'SOURCE_PARSE_UNVERIFIED')
   parts=raw[len(marker)+2:].split(b'\r\n'+marker);need(parts[-1] in (b'--',b'--\r\n'),'SOURCE_PARSE_UNVERIFIED');seen=set();metadata=None
   for index,part in enumerate(parts[:-1]):
    if index:need(part.startswith(b'\r\n'),'SOURCE_PARSE_UNVERIFIED');part=part[2:]
    head,sep,body=part.partition(b'\r\n\r\n');need(sep and len(head)<=2048,'SOURCE_PARSE_UNVERIFIED');headers={}
    for line in head.decode('ascii').split('\r\n'):
     key,colon,val=line.partition(':');need(colon and re.fullmatch('[A-Za-z-]+',key) and key.lower() not in headers,'SOURCE_PARSE_UNVERIFIED');headers[key.lower()]=val.strip()
    need('content-transfer-encoding' not in headers,'SOURCE_PARSE_UNVERIFIED')
    cd=re.fullmatch(r'form-data;\s*name="([^"\r\n]*)"(?:;\s*filename="([^"\r\n]*)")?',headers.get('content-disposition',''),re.I);need(cd,'SOURCE_PARSE_UNVERIFIED');n=name(cd[1]);need(n not in seen and (cd[2] is None or name(cd[2])==n),'SOURCE_PARSE_UNVERIFIED');seen.add(n)
    typ=headers.get('content-type','text/plain').split(';')[0].strip().lower()
    if n=='metadata':need(len(body)<=8192 and typ in ('application/json','text/plain'),'SOURCE_PARSE_UNVERIFIED');metadata=json_exact(body);need(type(metadata) is dict,'SOURCE_PARSE_UNVERIFIED')
    else:module(n,typ,body)
   if metadata is not None:
    fields=[k for k in ('main_module','body_part') if k in metadata];need(len(fields)==1,'SOURCE_PARSE_UNVERIFIED');selected=name(metadata[fields[0]]);need(selector is None or selector==selected,'SOURCE_PARSE_UNVERIFIED')
   else:need(selector is not None,'SOURCE_PARSE_UNVERIFIED');selected=selector
  else:raise Stop('SOURCE_PARSE_UNVERIFIED')
  need(len(modules)==1 and selected in modules,'SOURCE_PARSE_UNVERIFIED');digest=sha(modules[selected]);result.update(source_representation_proven=True,source_module_sha256=digest,candidate_equal='YES' if digest==BUNDLE else 'NO',known_old_parked_source=digest in known_old,parked_proven=digest==BUNDLE or digest in known_old)
 except Exception:pass
 return result

def settings_metadata(raw):
 d=envelope(raw);r=d.get('result');need(type(r) is dict and type(r.get('bindings')) is list and len(r['bindings'])<=128,'SETTINGS_SHAPE_STOP')
 out={'settings_visible':True,'binding_exact':False,'binding_name':None,'database_id_match':False,'secret_binding_names_present':[],'secret_values_accessed':False,'key_readiness':'UNVERIFIED_PERMISSION_LIMIT','workers_dev_exposure':'UNVERIFIED','routes_complete':False,'route_status':'UNVERIFIED_ZONE_ID_OR_PERMISSION'}
 seen=set()
 for b in r['bindings']:
  need(type(b) is dict and type(b.get('name')) is str and b['name'] not in seen,'SETTINGS_SHAPE_STOP');seen.add(b['name'])
  if b.get('type')=='d1' and b['name']=='DB':
   out['binding_name']='DB';out['database_id_match']=b.get('id')==DB;out['binding_exact']=out['database_id_match'] and ('database_name' not in b or b.get('database_name')=='plm-serverless-sandbox-state')
  if b.get('type')=='secret_text' and b['name'] in ('PLM_YOUTUBE_CHECKPOINT_KEY','PLM_YOUTUBE_RESULT_CALLBACK_KEY','PLM_GITHUB_DISPATCH_TOKEN'):out['secret_binding_names_present'].append(b['name'])
 out['secret_binding_names_present'].sort()
 if out['secret_binding_names_present']:out['key_readiness']='NAME_PRESENT_VALUE_UNVERIFIED'
 for key in ('workers_dev','preview_urls'):
  if r.get(key) is True:out.update(active=True,workers_dev_exposure='ACTIVE')
 # No settings field can establish completeness of unknown zone routes.
 return out

def schedules_metadata(raw):
 d=envelope(raw);need('result_info' not in d,'BLOCKED_REMOTE_VISIBILITY');r=d.get('result');need(type(r) is dict and type(r.get('schedules')) is list and len(r['schedules'])<=64,'SCHEDULES_SHAPE_STOP')
 for s in r['schedules']:need(type(s) is dict and type(s.get('cron')) is str and len(s['cron'])<=128 and len(s['cron'].split())==5 and re.fullmatch(r'[0-9A-Z*/?,#L\- ]+',s['cron']),'SCHEDULES_SHAPE_STOP')
 return {'schedules_visible':True,'cron_complete':True,'cron_count':len(r['schedules']),'active':bool(r['schedules'])}

def queues_metadata(raw):
 d=envelope(raw);rows=d.get('result');i=d.get('result_info');need(type(rows) is list and len(rows)<=1000 and type(i) is dict,'UNVERIFIED_INCOMPLETE_PAGINATION')
 need(all(type(i.get(k)) is int for k in ('count','total_count','page','per_page','total_pages')) and i['page']==1 and i['count']==i['total_count']==len(rows) and i['per_page']>0 and i['per_page']>=len(rows) and i['total_pages'] in (0,1) and (i['total_pages']!=0 or not rows),'UNVERIFIED_INCOMPLETE_PAGINATION')
 out={'queues_visible':True,'queue_count':len(rows),'consumers_complete':not rows,'consumer_count':0 if not rows else None}
 # Embedded positive association may prove active; absence never inferred for nonempty inventory.
 for q in rows:
  need(type(q) is dict,'QUEUES_SHAPE_STOP')
  if type(q.get('consumers')) is list:
   for c in q['consumers']:
    if type(c) is dict and c.get('type')=='worker' and c.get('script_name')==WORKER:out['active']=True
 return out

def classify(out):
 if out.get('active') is True:return 'STOP_UNEXPECTED_ACTIVE_RUNTIME'
 required=('worker_exists','source_representation_proven','routes_complete','cron_complete','consumers_complete','binding_exact','parked_proven')
 if not all(out.get(k) is True for k in required):return 'BLOCKED_REMOTE_VISIBILITY'
 if out.get('cron_count')!=0 or out.get('consumer_count')!=0 or out.get('route_count')!=0:return 'STOP_UNEXPECTED_ACTIVE_RUNTIME'
 if out.get('candidate_equal')=='YES':return 'REMOTE_EXACT_PARKED'
 if out.get('candidate_equal')=='NO' and out.get('known_old_parked_source') is True:return 'REMOTE_PARKED_OLD_SOURCE_DEPLOY_PREPARATION_REQUIRED'
 return 'BLOCKED_REMOTE_VISIBILITY'

class FourGet:
 def __init__(self,transport):self.transport=transport;self.count=0;self.statuses=[];self.stopped=False
 def get(self,method,path):
  need(not self.stopped and method=='GET' and self.count<4 and path==ENDPOINTS[self.count],'REQUEST_GATE_STOP');self.count+=1
  try:
   status,raw,meta=self.transport(method,path);need(type(status) is int and 100<=status<=599,'HTTP_SHAPE_STOP');self.statuses.append(status)
   if status!=200:
    self.stopped=True
    if status==403:raise Stop('UNVERIFIED_PERMISSION_LIMIT')
    if status==404:raise Stop('WORKER_ABSENT_STOP' if self.count==1 else 'HTTP_404_STOP')
    if 300<=status<=399:raise Stop('REDIRECT_STOP')
    raise Stop('HTTP_'+str(status)+'_STOP')
   need(type(raw) is bytes and 0<len(raw)<=MAX and type(meta) is dict,'RESPONSE_BOUND_STOP');return raw,meta
  except Stop:self.stopped=True;raise
  except Exception:self.stopped=True;raise Stop('TRANSPORT_UNKNOWN_NO_RETRY') from None

def inspect(transport,known_old):
 g=FourGet(transport);out={'identity':IDENTITY,'pass':False,'read_complete':False,'reason_codes':[],'worker_exists':None,'source_representation_proven':False,'candidate_equal':'UNVERIFIED_SOURCE_REPRESENTATION','known_old_parked_source':False,'settings_visible':False,'binding_exact':False,'binding_name':None,'database_id_match':False,'secret_binding_names_present':[],'secret_values_accessed':False,'schedules_visible':False,'cron_complete':False,'cron_count':None,'queues_visible':False,'queue_count':None,'consumers_complete':False,'consumer_count':None,'routes_complete':False,'route_count':None,'route_status':'UNVERIFIED_ZONE_ID_OR_PERMISSION','candidate_bundle_sha256':BUNDLE,'candidate_runtime_source_sha256':SOURCE,'writes':0,'deploys':0,'dispatches':0,'uploads':0,'D1_requests':0,'YouTube_calls':0,'retry':0,'resume':0,'redirect':0,'raw_retention':0,'secret_exposure':0,'quota':'UNVERIFIED_PERMISSION_LIMIT'}
 try:
  raw,m=g.get('GET',ENDPOINTS[0]);out['worker_exists']=True;out.update(source_metadata(raw,m,known_old));del raw
  raw,_=g.get('GET',ENDPOINTS[1]);out.update(settings_metadata(raw));del raw
  need(out.get('active') is not True,'STOP_UNEXPECTED_ACTIVE_RUNTIME')
  raw,_=g.get('GET',ENDPOINTS[2]);out.update(schedules_metadata(raw));del raw
  need(out.get('active') is not True,'STOP_UNEXPECTED_ACTIVE_RUNTIME')
  raw,_=g.get('GET',ENDPOINTS[3]);out.update(queues_metadata(raw));del raw
  out['read_complete']=True
 except Stop as e:
  out['reason_codes'].append(str(e))
  if str(e)=='WORKER_ABSENT_STOP':out['worker_exists']=False
  if str(e)=='STOP_UNEXPECTED_ACTIVE_RUNTIME':out['active']=True
 except Exception:out['reason_codes'].append('UNVERIFIED_RESPONSE_STOP')
 out['classification']=classify(out)
 if out['classification']=='BLOCKED_REMOTE_VISIBILITY' and not out['reason_codes']:out['reason_codes']=['UNVERIFIED_ZONE_ID_OR_PERMISSION']
 out['pass']=out['classification'] in ('REMOTE_EXACT_PARKED','REMOTE_PARKED_OLD_SOURCE_DEPLOY_PREPARATION_REQUIRED')
 out.update(requests_attempted=g.count,request_order=list(ENDPOINTS[:g.count]),http_statuses=g.statuses,next_one_action='REPORT_ONLY_STOP_NO_DEPLOY')
 return out

PIN_FILES={'plan_sha256':PLAN,'target_manifest_sha256':TARGET,'workflow_sha256':WORKFLOW,'helper_sha256':HELPER,'offline_contract_sha256':CONTRACT}
def validate_gate(env,event,gitfacts,marker,plan,files):
 need(all(env.get(k)=='true' for k in ('TEST_ONLY','DRY_RUN','NO_PUBLISH','EMERGENCY_STOP')),'SAFE_FLAGS_STOP')
 need(env.get('GITHUB_REPOSITORY')==REPO and env.get('GITHUB_REF')==BRANCH and env.get('GITHUB_EVENT_NAME')=='push' and env.get('GITHUB_RUN_ATTEMPT')=='1','EXECUTION_CONTEXT_STOP')
 before=event.get('before');after=event.get('after');head=event.get('head_commit',{})
 need(type(before) is str and re.fullmatch('[a-f0-9]{40}',before) and after==env.get('GITHUB_SHA') and head.get('id')==after and head.get('message')==MESSAGE and len(event.get('commits',[]))==1,'PUSH_BINDING_STOP')
 need(gitfacts=={'head':after,'parent':before,'prepared_parent':PARENT,'files':[MARKER],'marker_preexisted':False,'message':MESSAGE},'MARKER_ONLY_CHAIN_STOP')
 expected=set(PIN_FILES)|{'identity','state','prepared_commit_sha','candidate_bundle_sha256','candidate_runtime_source_sha256'}
 need(type(marker) is dict and set(marker)==expected and marker['identity']==IDENTITY and marker['state']=='CONSUMED_BEFORE_REMOTE' and marker['prepared_commit_sha']==before and marker['candidate_bundle_sha256']==BUNDLE and marker['candidate_runtime_source_sha256']==SOURCE,'MARKER_BINDING_STOP')
 for key,path in PIN_FILES.items():need(sha(files[path])==marker[key],'SOURCE_HASH_DRIFT_STOP')
 need(plan['identity']==IDENTITY and plan['exact_preparation_parent']==PARENT and plan['allowed_requests']==[{'method':'GET','path':p} for p in ENDPOINTS] and plan['maximum_remote_reads']==4 and plan['response_bytes_max_each']==MAX and plan['error_body_bytes_max']==ERROR_MAX and plan['timeout_seconds']==TIMEOUT,'PLAN_BINDING_STOP')
 for k in ('maximum_writes','maximum_D1_requests','maximum_deploys','maximum_dispatches','maximum_uploads','maximum_YouTube_calls','retry','resume','redirect','fallback','pagination_fallback','raw_retention'):need(type(plan.get(k)) is int and plan[k]==0,'PLAN_LIMITS_STOP')
 for key in PIN_FILES:
  if key!='plan_sha256':need(plan[key]==marker[key],'PLAN_PIN_STOP')
 need(sha(files[SCHEMA])==plan['schema_sha256'] and sha(files['serverless/youtube-connection/runtime-bundle.mjs'])==BUNDLE and sha(files['serverless/youtube-connection/runtime.mjs'])==SOURCE,'CANDIDATE_OR_SCHEMA_DRIFT_STOP')
 target=json_exact(files[TARGET]);need(target['required_commit_sha']=='1ea540cd373dab6c4ff789619b357fb72828a75e' and target['target_status']=='PINNED_READONLY_NOT_EXECUTION_APPROVED' and target['execution_approved'] is False and target['launchable'] is False and target['mutable_branch_fallback'] is False,'TARGET_BINDING_STOP')
 for p,h in plan['known_old_parked_source_files'].items():need(sha(files[p])==h,'KNOWN_OLD_SOURCE_DRIFT_STOP')

_CAPABILITY=object()
class AuthorizedTransport:
 def __init__(self,token,capability=None):
  need(capability is _CAPABILITY,'ONE_SHOT_GATE_REQUIRED');self.token=token;self.count=0
 def __call__(self,method,path):
  import http.client,time
  started=time.monotonic()
  need(method=='GET' and self.count<4 and path==ENDPOINTS[self.count],'REQUEST_GATE_STOP');self.count+=1
  c=http.client.HTTPSConnection('api.cloudflare.com',timeout=TIMEOUT)
  try:
   c.request('GET','/client/v4'+path,headers={'Authorization':'Bearer '+self.token,'Accept':'*/*'});r=c.getresponse();status=r.status
   def bounded_read(limit):
    parts=[];total=0
    while total<=limit:
     remaining=TIMEOUT-(time.monotonic()-started);need(remaining>0,'TRANSPORT_UNKNOWN_NO_RETRY')
     sock=c.sock if getattr(c,'sock',None) is not None else getattr(getattr(getattr(r,'fp',None),'raw',None),'_sock',None)
     if sock is not None:sock.settimeout(remaining)
     chunk=r.read1(min(8192,limit+1-total))
     if not chunk:break
     parts.append(chunk);total+=len(chunk)
    return b''.join(parts)
   if status!=200:
    # Do not parse error strings or headers; bounded diagnostic body discarded.
    body=bounded_read(ERROR_MAX);del body
    return status,b'',{}
   n=r.getheader('Content-Length');need(n is None or (n.isdigit() and int(n)<=MAX),'RESPONSE_BOUND_STOP');raw=bounded_read(MAX);need(len(raw)<=MAX,'RESPONSE_BOUND_STOP');return status,raw,{'content_type':r.getheader('Content-Type') or '', 'entrypoint':r.getheader('cf-entrypoint')}
  finally:c.close()

def authorize_transport(env,event,facts,marker,plan,files):
 validate_gate(env,event,facts,marker,plan,files)
 token=env.get('PLM_CF_WORKER_API_TOKEN');need(type(token) is str and token and not any(c in token for c in '\r\n'),'CREDENTIAL_MISSING_STOP')
 return AuthorizedTransport(token,_CAPABILITY)

def main():
 import os,subprocess
 out={'identity':IDENTITY,'classification':'BLOCKED_REMOTE_VISIBILITY','reason_codes':[],'requests_attempted':0,'writes':0,'deploys':0,'dispatches':0,'uploads':0,'D1_requests':0,'YouTube_calls':0,'raw_retention':0,'secret_exposure':0,'retry':0,'resume':0,'redirect':0,'next_one_action':'REPORT_ONLY_STOP'}
 try:
  event=json_exact(Path(os.environ['GITHUB_EVENT_PATH']).read_bytes());before=event['before']
  need(type(before) is str and re.fullmatch('[a-f0-9]{40}',before),'PREPARED_COMMIT_STOP')
  def git(*a):return subprocess.check_output(['git',*a],text=True,stderr=subprocess.DEVNULL).strip()
  facts={'head':git('rev-parse','HEAD'),'parent':git('rev-parse','HEAD^'),'prepared_parent':git('rev-parse',before+'^'),'files':git('diff','--name-only',before,'HEAD').splitlines(),'marker_preexisted':subprocess.run(['git','cat-file','-e',before+':'+MARKER],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0,'message':git('log','-1','--format=%B')}
  plan=json_exact(Path(PLAN).read_bytes());paths=set(PIN_FILES.values())|{SCHEMA,'serverless/youtube-connection/runtime-bundle.mjs','serverless/youtube-connection/runtime.mjs'}|set(plan['known_old_parked_source_files']);files={p:Path(p).read_bytes() for p in paths}
  t=authorize_transport(dict(os.environ),event,facts,json_exact(Path(MARKER).read_bytes()),plan,files)
  out=inspect(t,set(plan['known_old_parked_source_files'].values()))
 except Stop as e:out['reason_codes']=[str(e)]
 except Exception:out['reason_codes']=['LOCAL_GATE_STOP']
 print(json.dumps(out,sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
