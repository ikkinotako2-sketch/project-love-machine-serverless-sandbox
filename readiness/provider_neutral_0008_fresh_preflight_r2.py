"""0008 preparation: exact allowlisted readonly SQL; no migration executor."""
import hashlib,json,re,sqlite3
from pathlib import Path
from datetime import datetime,timezone
IDENTITY='provider-neutral-0008-fresh-readonly-preflight-20261007-r2'
PARENT='0a1d29b92044e0d315a23184e14f2596dd719fcc'
ACCOUNT='6c8ccd6aface937ab5dabef61cb64534'
DB='18050cf6-934e-4f3a-a1cd-5041bac1c35e'
NAME='plm-serverless-sandbox-state'
NAMESPACE='plm_rt_v2_'
HELPER='readiness/provider_neutral_0008_fresh_preflight_r2.py'
WORKFLOW='.github/workflows/plm-provider-neutral-0008-fresh-readonly-r2-once.yml'
PLAN='readiness/provider-neutral-0008-fresh-readonly-r2-plan.json'
SCHEMA='readiness/provider-neutral-0008-fresh-readonly-r2-marker.schema.json'
MARKER='audit-evidence/consumed/'+IDENTITY+'.json'
MESSAGE='PLM 0008 fresh readonly once '+IDENTITY
READ_SECRET='PLM_CF_D1_READ_TOKEN'
BACKEND_SECRET='PLM_CF_D1_ROUNDTRIP_BACKEND_TOKEN'
PINS={
 'serverless/migrations/0008_provider_neutral_roundtrip_backend.sql':'7734fe9ae6d950b5af444cc9a3f917b3da8d050c5e63083f51a79ea42d620bfe',
 'serverless/provider-neutral-backend-before.json':'02d8d6c9e0d131dfbfc4088af072ca704589f31e3753a59a80a10cd71b2e31b9',
 'serverless/provider-neutral-backend-after.json':'d0de3cd14ac3aa1afb55a358635c5a32a9c0f90528d1ca42f84ab4beb6fd54c3',
 'serverless/provider-neutral-backend-plan.json':'277fcf6ae8f465ae574e4c5f903b8c506689baf632a0e1e2d68ed2bd7dd5820a'}
ROOT='/accounts/'+ACCOUNT
VERIFY=ROOT+'/tokens/verify'
INVENTORY=ROOT+'/d1/database?page=1&per_page=100'
TARGET=ROOT+'/d1/database/'+DB
MAX_BYTES=262144
MAX_CALLS=16
REPO='ikkinotako2-sketch/project-love-machine-serverless-sandbox'
HISTORY='/repos/'+REPO+'/actions/runs?per_page=20&page='
class Stop(Exception):pass
def need(ok,code):
 if not ok:raise Stop(code)
def sha(b):return hashlib.sha256(b).hexdigest()
def canonical(x):return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False)
def load_candidate(root=Path('.')):
 files={p:(root/p).read_bytes() for p in PINS}
 need(all(sha(files[p])==h for p,h in PINS.items()),'RAW_SHA_STOP')
 before=json.loads(files['serverless/provider-neutral-backend-before.json']);after=json.loads(files['serverless/provider-neutral-backend-after.json'])
 need(after['preserved_before']==before,'BEFORE_BINDING_STOP')
 return before,after

def ident(s):
 need(type(s) is str and re.fullmatch(r'[a-zA-Z_][a-zA-Z_0-9]*',s),'IDENTIFIER_STOP');return '"'+s+'"'
def details_sql(table):
 t=ident(table)
 cols="(SELECT json_group_array(json_object('cid',cid,'name',name,'type',type,'notnull',\"notnull\",'dflt_value',dflt_value,'pk',pk)) FROM (SELECT * FROM pragma_table_info('"+table+"') ORDER BY cid))"
 indexes="(SELECT json_group_array(json_object('seq',seq,'name',name,'unique',\"unique\",'origin',origin,'partial',partial)) FROM (SELECT * FROM pragma_index_list('"+table+"') ORDER BY name))"
 return cols,indexes

def queries(before):
 # Pin schema equality by one exact count per expected schema row. Return only counts.
 schema=before['schema'];clauses=[];params=[]
 for i,row in enumerate(schema):
  values=["'"+row[k].replace("'","''")+"'" for k in ('type','name','tbl_name','sql')]
  clauses.append("SUM(CASE WHEN type IS "+values[0]+" AND name IS "+values[1]+" AND tbl_name IS "+values[2]+" AND sql COLLATE BINARY IS "+values[3]+" THEN 1 ELSE 0 END) AS s"+str(i))
 q="SELECT COUNT(*) AS total,"+','.join(clauses)+", SUM(CASE WHEN substr(name,1,10)='plm_rt_v2_' OR substr(tbl_name,1,10)='plm_rt_v2_' THEN 1 ELSE 0 END) AS candidate FROM sqlite_master WHERE substr(name,1,7) != 'sqlite_'"
 out=[{'kind':'schema','sql':q,'params':params,'expected':{'total':len(schema),'candidate':0,**{'s'+str(i):1 for i in range(len(schema))}}}]
 conn=sqlite3.connect(':memory:');conn.row_factory=sqlite3.Row
 for row in schema:
  if row['type']=='table':conn.execute(row['sql'])
 for table,rows in sorted(before['protected_rows'].items()):
  cols,indexes=details_sql(table);clauses=['COUNT(*) AS total'];params=[]
  need(len({canonical(r) for r in rows})==len(rows),'DUPLICATE_REFERENCE_STOP')
  for i,row in enumerate(rows):
   conditions=[]
   for key,value in sorted(row.items()):
    kind='null' if value is None else 'integer' if type(value) is int else 'real' if type(value) is float else 'text'
    need(value is None or type(value) in (str,int,float),'REFERENCE_TYPE_STOP')
    conditions.append('('+ident(key)+' COLLATE BINARY IS ? AND typeof('+ident(key)+') = ?)');params.extend((value,kind))
   clauses.append('SUM(CASE WHEN '+ ' AND '.join(conditions)+' THEN 1 ELSE 0 END) AS r'+str(i))
  # COALESCE is needed for empty tables; metadata selected by scalar subqueries.
  sql='SELECT '+','.join(clauses)+','+cols+' AS columns_json,'+indexes+' AS indexes_json FROM '+ident(table)
  expected={'total':len(rows),**{'r'+str(i):1 for i in range(len(rows))}}
  for col,expr in [('columns_json',cols),('indexes_json',indexes)]:expected[col]=json.loads(conn.execute('SELECT '+expr).fetchone()[0])
  out.append({'kind':'rows:'+table,'sql':sql,'params':params,'expected':expected})
 conn.close();need(len(out)==11,'QUERY_BUDGET_STOP');return out

def classifier(candidate,total=None):
 if type(candidate) is not int or candidate<0:return 'STILL_UNKNOWN'
 if candidate==0:return 'NOT_APPLIED'
 if candidate==16 and total==45:return 'FULL_APPLIED'
 return 'PARTIAL_APPLIED'

def compare_query(spec,rows):
 need(type(rows) is list and len(rows)==1 and type(rows[0]) is dict,'QUERY_SHAPE_STOP')
 row=dict(rows[0])
 if spec['kind']=='schema':need(classifier(row.get('candidate'),row.get('total'))=='NOT_APPLIED','CANDIDATE_ALREADY_PRESENT_NO_RESEND')
 for key in ('columns_json','indexes_json'):
  if key in row:
   try:row[key]=json.loads(row[key])
   except Exception:raise Stop('QUERY_SHAPE_STOP') from None
 need(canonical(row)==canonical(spec['expected']),'PROTECTED_SCHEMA_OR_ROWS_DRIFT_STOP')
 return True

def decode(raw):
 need(type(raw) is bytes and len(raw)<=MAX_BYTES,'RESPONSE_BOUND_STOP')
 def pairs(items):
  out={}
  for k,v in items:need(k not in out,'DUPLICATE_JSON_STOP');out[k]=v
  return out
 try:out=json.loads(raw.decode(),object_pairs_hook=pairs)
 except Stop:raise
 except Exception:raise Stop('RESPONSE_SHAPE_STOP') from None
 need(type(out) is dict and out.get('success') is True,'RESPONSE_SHAPE_STOP');return out

def expiry(s,now):
 try:d=datetime.fromisoformat(s.replace('Z','+00:00'));n=d.timestamp()
 except Exception:raise Stop('TOKEN_FINITE_EXPIRY_STOP') from None
 need(d.tzinfo is not None and n>now,'TOKEN_EXPIRED_OR_UNBOUNDED_STOP');return d.astimezone(timezone.utc).isoformat()

def request_specs(before):
 return [('backend','GET',VERIFY,None),('read','GET',INVENTORY,None),('read','GET',TARGET,None),('read','GET',TARGET+'/time_travel/bookmark',None)]+[('read','POST',TARGET+'/query',{'sql':q['sql'],'params':q['params']}) for q in queries(before)]+[('read','GET',TARGET+'/time_travel/bookmark',None)]
class Gate:
 def __init__(self,transport,specs):self.transport=transport;self.specs=specs;self.count=0;self.stopped=False
 def call(self,role,method,path,body=None):
  need(not self.stopped and self.count<len(self.specs) and self.count<MAX_CALLS and (role,method,path,body)==self.specs[self.count],'REQUEST_ALLOWLIST_STOP')
  self.count+=1
  try:
   status,raw=self.transport(role,method,path,body)
   need(status==200,'HTTP_STOP');return decode(raw)
  except Stop:self.stopped=True;raise
  except Exception:self.stopped=True;raise Stop('TRANSPORT_UNKNOWN_NO_RETRY') from None

PRIOR_PREFLIGHT_MARKER='audit-evidence/consumed/provider-neutral-0008-fresh-readonly-preflight-20261006-r1.json'
PRIOR_PREFLIGHT_MARKER_SHA256='92d58f4a7027de3f67a8cfcb02af554fa8d08a43f418821e5761cc61989a86fe'
def prior_check(paths):
 for path in paths:
  if path==PRIOR_PREFLIGHT_MARKER:continue
  name=Path(path).name.lower()
  if ('provider-neutral' in name or '0008' in name) and (re.search(r'(sent|send|success|partial|unknown|fail|receipt|approved|import|migration|apply|execution)',name) or path.startswith('audit-evidence/consumed/')):raise Stop('PRIOR_EXECUTION_NO_RESEND_STOP')

def history_check(pages):
 total=None;seen=set()
 for n,d in enumerate(pages,1):
  need(type(d) is dict and type(d.get('total_count')) is int and type(d.get('workflow_runs')) is list,'HISTORY_UNKNOWN_STOP')
  if total is None:total=d['total_count']
  need(total==d['total_count'] and 0<=total<=2000,'HISTORY_CHANGED_STOP')
  for run in d['workflow_runs']:
   need(type(run) is dict and type(run.get('id')) is int and run['id'] not in seen,'HISTORY_UNKNOWN_STOP');seen.add(run['id'])
   path=run.get('path');need(type(path) is str,'HISTORY_UNKNOWN_STOP')
   if ('provider-neutral' in path or '0008' in path) and any(k in path for k in ('migration','approved','import','apply')):raise Stop('PRIOR_EXECUTION_NO_RESEND_STOP')
  if len(seen)==total:return {'complete':True,'total':total,'pages':n,'prior_send':0}
  need(d['workflow_runs'] and len(seen)<total,'HISTORY_INCOMPLETE_STOP')
 raise Stop('HISTORY_INCOMPLETE_STOP')

def preflight(transport,before,now,paths=(),history=None,clock=None):
 out={'identity':IDENTITY,'pass':False,'cloudflare_read_only_calls':0,'d1_writes':0,'maximum_writes':0,'retry':0,'resume':0,'resend':0,'fallback':0,'automatic_rollback':0,'raw_retention':0,'token_scope_api_independently_verified':False,'worker_bundle_equality':'UNVERIFIED','migrations':{'0008':'NOT_APPLIED_REFERENCE_ONLY_UNTIL_FRESH_PROOF','0009':'NOT_APPLIED','0010':'NOT_APPLIED'}}
 gate=Gate(transport,request_specs(before))
 try:
  prior_check(paths);need(history and history.get('complete') is True and history.get('prior_send')==0,'HISTORY_REQUIRED_STOP')
  def call():return gate.call(*gate.specs[gate.count])
  v=call()['result'];need(type(v) is dict and v.get('status')=='active','TOKEN_INACTIVE_STOP')
  need(type(v.get('id')) is str and re.fullmatch('[a-f0-9]{32}',v['id']),'TOKEN_ID_INVALID_STOP')
  exp=expiry(v.get('expires_on'),now)
  out.update(token_status='ACTIVE',token_id=v['id'],token_expires_at=exp,token_type='ACCOUNT_OWNED',scope_api_independently_verified=False,scope_status='OWNER_ATTESTED_D1_WRITE_ONLY_NOT_API_VERIFIED')
  d=call();r=d.get('result');info=d.get('result_info');need(type(r) is list and type(info) is dict and all(type(info.get(k)) is int for k in ('page','count','total_count','per_page')) and info.get('page')==1 and info.get('count')==info.get('total_count')==len(r)==1 and type(info.get('per_page')) is int and info['per_page']>=1,'INVENTORY_INCOMPLETE_STOP')
  need(r[0].get('uuid')==DB and r[0].get('name')==NAME,'INVENTORY_TARGET_STOP')
  d=call()['result'];need(d.get('uuid')==DB and d.get('name')==NAME and d.get('file_size')==before['database_size_bytes'],'DATABASE_METADATA_DRIFT_STOP')
  bookmark=call()['result'].get('bookmark');need(type(bookmark) is str and re.fullmatch('[a-f0-9-]{16,128}',bookmark),'BOOKMARK_REQUIRED_STOP')
  for spec in queries(before):
   d=call();need(type(d.get('result')) is list and len(d['result'])==1,'QUERY_SHAPE_STOP');q=d['result'][0];m=q.get('meta',{})
   need(q.get('success') is True and m.get('served_by_primary') is True and type(m.get('rows_written')) is int and m['rows_written']==0 and m.get('changed_db') is False and m.get('changes')==0,'READ_ONLY_RESPONSE_STOP')
   compare_query(spec,q.get('results'))
  last=call()['result'].get('bookmark');need(last==bookmark,'BOOKMARK_CHANGED_STOP');expiry(v.get('expires_on'),clock() if clock else now)
  out.update(pass_=True,candidate_classification='NOT_APPLIED',bookmark=bookmark,inventory_complete=True,protected_schema_exact=True,protected_rows_exact=True,kv_schema_unchanged=True,kv_content_status='NOT_APPLICABLE_RESERVED_UNQUERYABLE',prior_send=0,hashes=PINS,result='FRESH_PREFLIGHT_SUCCESS_STOP_BEFORE_MIGRATION')
  out['pass']=out.pop('pass_');out['migrations']['0008']='NOT_APPLIED'
 except Stop as e:out['result']=str(e)
 except Exception:out['result']='UNKNOWN_STOP_NO_RETRY'
 out['cloudflare_read_only_calls']=gate.count;return out

def bounded_http(host,path,method,headers,body=None):
 import http.client
 conn=http.client.HTTPSConnection(host,timeout=15)
 try:
  conn.request(method,path,body=body,headers=headers);r=conn.getresponse()
  if r.status!=200:return r.status,b''
  length=r.getheader('Content-Length');need(length is None or (length.isdigit() and int(length)<=MAX_BYTES),'RESPONSE_BOUND_STOP')
  raw=r.read(MAX_BYTES+1);need(len(raw)<=MAX_BYTES,'RESPONSE_BOUND_STOP');return r.status,raw
 finally:conn.close()

def live_transport(read,backend,before):
 need(type(backend) is str and bool(backend.strip()) and '\r' not in backend and '\n' not in backend,'BACKEND_CREDENTIAL_MISSING_STOP')
 need(type(read) is str and bool(read.strip()) and '\r' not in read and '\n' not in read,'CREDENTIAL_MISSING_STOP')
 need(read!=backend,'CREDENTIAL_ROLES_NOT_DISTINCT_STOP')
 allowed=request_specs(before)
 def send(role,method,path,body):
  need((role,method,path,body) in allowed and (role!='backend' or (method,path,body)==('GET',VERIFY,None)),'REQUEST_ALLOWLIST_STOP')
  token=backend if role=='backend' else read
  return bounded_http('api.cloudflare.com','/client/v4'+path,method,{'Authorization':'Bearer '+token,'Content-Type':'application/json'},None if body is None else json.dumps(body).encode())
 return send

def marker_check(marker,plan,before,files):
 keys={'identity','state','prepared_commit_sha','workflow_sha256','helper_sha256','preflight_plan_sha256','candidate_raw_hashes'}
 need(type(marker) is dict and set(marker)==keys and marker['identity']==IDENTITY and marker['state']=='CONSUMED_BEFORE_REMOTE' and marker['prepared_commit_sha']==before and re.fullmatch('[a-f0-9]{40}',before or ''),'MARKER_BINDING_STOP')
 need(marker['candidate_raw_hashes']==PINS and plan['candidate_raw_hashes']==PINS and plan['identity']==IDENTITY and plan['exact_parent_sha']==PARENT,'PLAN_BINDING_STOP')
 need(plan['maximum_cloudflare_read_only_calls']==MAX_CALLS and plan['maximum_writes']==0 and plan['run_attempt']==1 and all(plan[k]==0 for k in ('retry','resend','resume','fallback','automatic_rollback','raw_retention','redirect')),'PLAN_LIMITS_STOP')
 for k,p in [('workflow_sha256',WORKFLOW),('helper_sha256',HELPER),('preflight_plan_sha256',PLAN)]:need(marker[k]==sha(files[p]),'MARKER_HASH_STOP')
 need(plan['workflow_sha256']==marker['workflow_sha256'] and plan['helper_sha256']==marker['helper_sha256'] and plan['marker_schema_sha256']==sha(files[SCHEMA]),'PLAN_HASH_STOP')

def main():
 import os,time
 e=os.environ;out={'identity':IDENTITY,'pass':False,'cloudflare_read_only_calls':0,'d1_writes':0,'result':'PRE_REMOTE_GATE_STOP'}
 try:
  need(e.get('GITHUB_REPOSITORY')==REPO and e.get('GITHUB_REF')=='refs/heads/plm-offline-readiness-v1-20261002' and e.get('GITHUB_EVENT_NAME')=='push' and e.get('GITHUB_RUN_ATTEMPT')=='1' and all(e.get(k)=='true' for k in ('TEST_ONLY','DRY_RUN','NO_PUBLISH','EMERGENCY_STOP')),'EXECUTION_CONTEXT_STOP')
  need(bool(e.get(BACKEND_SECRET,'').strip()),'BACKEND_CREDENTIAL_MISSING_STOP')
  need(bool(e.get(READ_SECRET,'').strip()),'CREDENTIAL_MISSING_STOP')
  need(e[READ_SECRET]!=e[BACKEND_SECRET],'CREDENTIAL_ROLES_NOT_DISTINCT_STOP')
  files={p:Path(p).read_bytes() for p in (PLAN,WORKFLOW,HELPER,SCHEMA)};plan=json.loads(files[PLAN]);marker_check(json.loads(Path(MARKER).read_bytes()),plan,e.get('PLM_APPROVED_BEFORE'),files)
  before,_=load_candidate()
  need(sha(Path(PRIOR_PREFLIGHT_MARKER).read_bytes())==PRIOR_PREFLIGHT_MARKER_SHA256,'PRIOR_PREFLIGHT_EVIDENCE_DRIFT_STOP')
  paths=[str(p) for p in Path('audit-evidence').rglob('*.json') if str(p)!=MARKER];prior_check(paths)
  transport=live_transport(e.get(READ_SECRET),e.get(BACKEND_SECRET),before)
  # Separate bounded GitHub read-only history gate, before any Cloudflare call.
  token=e.get('PLM_HISTORY_GITHUB_TOKEN');need(bool(token),'HISTORY_CREDENTIAL_STOP');pages=[]
  for n in range(1,101):
   status,raw=bounded_http('api.github.com',HISTORY+str(n),'GET',{'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','User-Agent':'PLM-readonly-history'})
   need(status==200,'HISTORY_HTTP_STOP')
   try:d=json.loads(raw)
   except Exception:raise Stop('HISTORY_UNKNOWN_STOP') from None
   pages.append(d)
   try:history=history_check(pages);break
   except Stop as err:
    if str(err)!='HISTORY_INCOMPLETE_STOP':raise
  else:raise Stop('HISTORY_INCOMPLETE_STOP')
  out=preflight(transport,before,time.time(),paths,history,clock=time.time)
 except Stop as err:out['gate_code']=str(err)
 except Exception:out['gate_code']='LOCAL_VALIDATION_UNKNOWN_STOP_NO_RETRY'
 print(json.dumps(out,sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
