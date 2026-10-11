"""0010 exact read-only proof; imported historical utilities never execute old identities."""
import json,re,time,hashlib,sqlite3
from pathlib import Path
import provider_neutral_0009_common as previous
import provider_neutral_0008_fresh_preflight_r6 as old
from provider_neutral_0008_fresh_preflight_r6 import (Stop,need,sha,canonical,ident,details_sql,decode,expiry,HTTPFailure,bounded_http,ACCOUNT,DB,NAME,ROOT,VERIFY,INVENTORY,TARGET,MAX_BYTES,READ_SECRET,BACKEND_SECRET,REPO)
PARENT='dc13343915c7d3bdad14fc808fc9ae4eb2b2f46b'
SQL='serverless/migrations/0010_youtube_pipeline_checkpoint_candidate.sql'
SQL_SHA='79a88960393ad7030b60e707c9de67cceccb16f02d41f7bcf99f41c1f11ea336'
BEFORE='readiness/provider-neutral-0010-before.json'
AFTER='readiness/provider-neutral-0010-after.json'
# Filled during immutable preparation, never accepted from request inputs.
PINS={'serverless/migrations/0009_youtube_queue_result_proposal.sql': '55b87f14918a03150a1ec9e0294d540543a3259c4057797286a902c5d4455d42', 'readiness/provider-neutral-0009-before.json': '58f133b75da124a36a82c04c24e194f8cbfef623e47a54a6d21ace6bd2e3eff3', 'readiness/provider-neutral-0009-after.json': '9bee419bc6ed176d1629ac2279a3fe6eca8c69a83dfee99aa99755eff07316ff', 'serverless/migrations/0008_provider_neutral_roundtrip_backend.sql': '7734fe9ae6d950b5af444cc9a3f917b3da8d050c5e63083f51a79ea42d620bfe', 'serverless/provider-neutral-backend-before.json': '02d8d6c9e0d131dfbfc4088af072ca704589f31e3753a59a80a10cd71b2e31b9', 'serverless/provider-neutral-backend-after.json': 'd0de3cd14ac3aa1afb55a358635c5a32a9c0f90528d1ca42f84ab4beb6fd54c3', 'serverless/provider-neutral-backend-plan.json': '277fcf6ae8f465ae574e4c5f903b8c506689baf632a0e1e2d68ed2bd7dd5820a', 'serverless/migrations/0010_youtube_pipeline_checkpoint_candidate.sql': '79a88960393ad7030b60e707c9de67cceccb16f02d41f7bcf99f41c1f11ea336', 'readiness/provider-neutral-0010-before.json': '9bee419bc6ed176d1629ac2279a3fe6eca8c69a83dfee99aa99755eff07316ff', 'readiness/provider-neutral-0010-after.json': 'ecba796bd4054b09729c9c792b6e624203360ddf1e9d34b7ee73aa59ac91b4c9'}
MAX_WINDOWS=3
HISTORY_PER_PAGE=5
MAX_HISTORY_GETS=100
HISTORY=old.HISTORY

def load_candidate(root=Path('.')):
 for path,h in PINS.items():need(sha((root/path).read_bytes())==h,'RAW_SHA_STOP')
 before=json.loads((root/BEFORE).read_bytes());after=json.loads((root/AFTER).read_bytes())
 need(len(before['schema'])==58 and len(after['schema'])==62,'BASELINE_SCHEMA_STOP')
 return before,after

def classifier(count,total):
 if type(count) is not int or type(total) is not int:return 'STILL_UNKNOWN'
 if count==0 and total==58:return 'NOT_APPLIED'
 if count==4 and total==62:return 'FULL_APPLIED'
 return 'PARTIAL_APPLIED' if count>0 else 'STILL_UNKNOWN'

def queries(state):
 _,baseline=previous.load_candidate();out=previous.queries(baseline)
 # Replace full schema expectations using historical protected proof generator, preserving independent 0008/0009 counts.
 ref=dict(old.load_candidate()[0],schema=state['schema']);schema=old.queries(ref)[0]
 schema['expected']['candidate']=16
 schema['sql']=schema['sql'].replace(' FROM sqlite_master WHERE',", SUM(CASE WHEN substr(name,1,11)='plm_ytq_v1_' OR substr(tbl_name,1,11)='plm_ytq_v1_' THEN 1 ELSE 0 END) AS candidate9, SUM(CASE WHEN substr(name,1,11)='plm_ytp_v1_' OR substr(tbl_name,1,11)='plm_ytp_v1_' THEN 1 ELSE 0 END) AS candidate10 FROM sqlite_master WHERE")
 schema['expected']['candidate9']=13
 count=sum(r['name'].startswith('plm_ytp_v1_') for r in state['schema']);schema['expected']['candidate10']=count;out[0]=schema
 if count:
  t='plm_ytp_v1_binding';cols,indexes=details_sql(t);need(state['rows'][t]==[],'BASELINE_ROWS_STOP')
  out.append({'kind':'new:'+t,'sql':'SELECT COUNT(*) AS total,'+cols+' AS columns_json,'+indexes+' AS indexes_json FROM '+ident(t),'params':[],'expected':{'total':0,'columns_json':state['columns'][t],'indexes_json':state['indexes'][t]}})
  indexes=state['indexes'][t];clauses=['COUNT(*) AS total']+["SUM(CASE WHEN type='index' AND name='"+r['name']+"' AND tbl_name='"+t+"' AND sql IS NULL THEN 1 ELSE 0 END) AS i"+str(i) for i,r in enumerate(indexes)]
  out.append({'kind':'autoindexes10','sql':'SELECT '+','.join(clauses)+" FROM sqlite_master WHERE substr(name,1,7)='sqlite_' AND substr(tbl_name,1,11)='plm_ytp_v1_'",'params':[],'expected':{'total':len(indexes),**{'i'+str(i):1 for i in range(len(indexes))}}})
 need(len(out)==(20 if count==0 else 22),'QUERY_BUDGET_STOP');return out

def compare(q,rows,post):
 need(type(rows) is list and len(rows)==1 and type(rows[0]) is dict,'QUERY_SHAPE_STOP');r=dict(rows[0])
 if q['kind']=='schema':need(classifier(r.get('candidate10'),r.get('total'))==('FULL_APPLIED' if post else 'NOT_APPLIED'),'CANDIDATE_CLASSIFICATION_STOP')
 for k in ('columns_json','indexes_json'):
  if k in r:
   try:r[k]=json.loads(r[k])
   except Exception:raise Stop('QUERY_SHAPE_STOP') from None
 need(canonical(r)==canonical(q['expected']),'PROTECTED_SCHEMA_OR_ROWS_DRIFT_STOP')

def request_specs(state,post=False):
 initial=[] if post else [('backend','GET',VERIFY,None)]
 initial += [('read','GET',INVENTORY,None),('read','GET',TARGET,None)]
 window=[('read','GET',TARGET+'/time_travel/bookmark',None)]+[('read','POST',TARGET+'/query',{'sql':q['sql'],'params':q['params']}) for q in queries(state)]+[('read','GET',TARGET+'/time_travel/bookmark',None)]
 return initial+window*3

def live_transport(read,backend,state,post=False):
 need(type(read) is str and bool(read.strip()) and '\r' not in read and '\n' not in read,'CREDENTIAL_MISSING_STOP')
 if not post:
  need(type(backend) is str and bool(backend.strip()) and '\r' not in backend and '\n' not in backend,'BACKEND_CREDENTIAL_MISSING_STOP');need(read!=backend,'CREDENTIAL_ROLES_NOT_DISTINCT_STOP')
 else:need(backend is None,'BACKEND_FORBIDDEN_STOP')
 specs=request_specs(state,post);position=0;stopped=False
 def send(role,method,path,body):
  nonlocal position,stopped
  need(not stopped and position<len(specs) and (role,method,path,body)==specs[position],'REQUEST_ALLOWLIST_STOP');position+=1
  token=backend if role=='backend' else read
  try:return bounded_http('api.cloudflare.com','/client/v4'+path,method,{'Authorization':'Bearer '+token,'Content-Type':'application/json'},None if body is None else json.dumps(body).encode())
  except Exception:stopped=True;raise
 return send

def audit(transport,state,post=False,history=None,now=None,clock=time.time):
 out={'pass':False,'cloudflare_read_only_calls':0,'d1_calls':0,'d1_writes':0,'migration_executions':0,'retry':0,'resend':0,'resume':0,'raw_retention':0};seq=request_specs(state,post);position=0;token_exp=None
 def call():
  nonlocal position
  need(position<len(seq),'REQUEST_BUDGET_STOP');s=seq[position];position+=1
  try:status,raw=transport(*s)
  except Stop:raise
  except Exception:raise Stop('TRANSPORT_UNKNOWN_NO_RETRY') from None
  if status!=200:raise HTTPFailure(status,raw)
  return decode(raw)
 try:
  if not post:
   need(history and history.get('complete') is True and history.get('prior_send')==0,'HISTORY_REQUIRED_STOP')
   out.update(history_complete=True,history_total_runs=history['total'],history_pages=history['pages'],prior_send=0)
   v=call()['result'];need(type(v) is dict and v.get('status')=='active','TOKEN_INACTIVE_STOP');need(type(v.get('id')) is str and re.fullmatch('[a-f0-9]{32}',v['id']),'TOKEN_ID_INVALID_STOP')
   token_exp=expiry(v.get('expires_on'),clock() if now is None else now)
   out.update(token_status='ACTIVE',token_expires_at=token_exp,token_type='ACCOUNT_OWNED',scope_api_independently_verified=False,scope_status='OWNER_ATTESTED_D1_WRITE_ONLY_NOT_API_VERIFIED')
  d=call();r=d.get('result');i=d.get('result_info',{})
  need(type(r) is list and len(r)==1 and all(type(i.get(k)) is int for k in ('page','count','total_count','per_page')) and i['page']==1 and i['count']==i['total_count']==1 and i['per_page']>=1,'INVENTORY_INCOMPLETE_STOP')
  need(r[0].get('uuid')==DB and r[0].get('name')==NAME,'INVENTORY_TARGET_STOP')
  d=call()['result'];need(d.get('uuid')==DB and d.get('name')==NAME and type(d.get('file_size')) is int and d['file_size']>0,'DATABASE_METADATA_STOP')
  out.update(inventory_complete=True,stable_window_found=False,stability_windows_used=0,stability_windows=[])
  for number in range(1,4):
   out['stability_windows_used']=number
   if token_exp:expiry(token_exp,clock() if now is None else now)
   first=call()['result'].get('bookmark');need(type(first) is str and re.fullmatch('[a-f0-9-]{16,128}',first),'BOOKMARK_REQUIRED_STOP')
   for q in queries(state):
    r=call().get('result');need(type(r) is list and len(r)==1 and type(r[0]) is dict,'QUERY_SHAPE_STOP');v=r[0];m=v.get('meta',{})
    need(v.get('success') is True and m.get('served_by_primary') is True and type(m.get('rows_written')) is int and m['rows_written']==0 and type(m.get('changes')) is int and m['changes']==0 and m.get('changed_db') is False,'READ_ONLY_RESPONSE_STOP');compare(q,v.get('results'),post)
   last=call()['result'].get('bookmark');need(type(last) is str and re.fullmatch('[a-f0-9-]{16,128}',last),'BOOKMARK_REQUIRED_STOP')
   if token_exp:expiry(token_exp,clock() if now is None else now)
   stable=first==last;out['stability_windows'].append({'window':number,'state':'STABLE' if stable else 'DRIFT_OBSERVED'});del first,last
   if stable:out.update(stable_window_found=True,stable_window_number=number);break
  need(out['stable_window_found'],'BOOKMARK_STABILITY_NOT_OBSERVED_STOP')
  out.update({'pass':True,'candidate_classification':'FULL_APPLIED' if post else 'NOT_APPLIED','0008':'FULL_APPLIED','0009':'FULL_APPLIED','0010':'FULL_APPLIED' if post else 'NOT_APPLIED','protected_schema_exact':True,'protected_rows_exact':True,'unexpected_objects':0,'candidate_rows':0,'rows_written':0,'changes':0,'changed_db':False,'hashes':PINS,'result':'0010_POSTCHECK_SUCCESS_STOP' if post else '0010_FRESH_PREFLIGHT_SUCCESS_STOP_BEFORE_MIGRATION'})
  if post:out.update(tables=1,triggers=3,autoindexes=3)
 except HTTPFailure as e:out.update(e.metadata);out['result']=str(e)
 except Stop as e:out['result']=str(e)
 except Exception:out['result']='UNKNOWN_STOP_NO_RETRY'
 out['cloudflare_read_only_calls']=position;out['d1_calls']=max(0,position-(0 if post else 1));return out

def suspicious(path):
 lower=path.lower();return '0010' in lower and any(k in lower for k in ('migration','approved','import','apply','sent','send','success','partial','unknown','failure','receipt','execution'))

def prior_check(paths,current_marker=None):
 for path in paths:
  if path==current_marker:continue
  if suspicious(path):raise Stop('PRIOR_EXECUTION_NO_RESEND_STOP')

def history_check(pages,current_migration=None):
 total=None;seen=set();need(0<len(pages)<=100,'HISTORY_INCOMPLETE_STOP')
 for n,d in enumerate(pages,1):
  need(type(d) is dict and type(d.get('total_count')) is int and type(d.get('workflow_runs')) is list,'HISTORY_UNKNOWN_STOP')
  if total is None:total=d['total_count']
  need(total==d['total_count'],'HISTORY_CHANGED_STOP');need(0<=total<=500,'HISTORY_INCOMPLETE_STOP')
  runs=d['workflow_runs'];need(len(runs)<=5,'HISTORY_UNKNOWN_STOP')
  for r in runs:
   need(type(r) is dict and type(r.get('id')) is int and r['id'] not in seen and type(r.get('path')) is str,'HISTORY_UNKNOWN_STOP');seen.add(r['id'])
   if current_migration and r['id']==current_migration['id']:need(r['path']==current_migration['path'],'HISTORY_CURRENT_RUN_MISMATCH_STOP');continue
   need(not suspicious(r['path']),'PRIOR_EXECUTION_NO_RESEND_STOP')
  need(len(seen)<=total,'HISTORY_UNKNOWN_STOP')
  if n<len(pages):need(len(runs)==5 and len(seen)<total,'HISTORY_INCOMPLETE_STOP')
 need(len(seen)==total,'HISTORY_INCOMPLETE_STOP');return {'complete':True,'total':total,'pages':len(pages),'prior_send':0}

def fetch_history(token,current_migration=None):
 need(bool(token),'HISTORY_CREDENTIAL_STOP');pages=[]
 for n in range(1,101):
  status,raw=bounded_http('api.github.com',HISTORY+str(n),'GET',{'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','User-Agent':'PLM-0010-history'})
  need(status==200 and type(raw) is bytes and len(raw)<=MAX_BYTES,'HISTORY_HTTP_STOP')
  try:d=json.loads(raw)
  except Exception:raise Stop('HISTORY_UNKNOWN_STOP') from None
  need(type(d) is dict and type(d.get('total_count')) is int and type(d.get('workflow_runs')) is list,'HISTORY_UNKNOWN_STOP');runs=d['workflow_runs'];need(all(type(r) is dict for r in runs),'HISTORY_UNKNOWN_STOP')
  pages.append({'total_count':d['total_count'],'workflow_runs':[{'id':r.get('id'),'path':r.get('path')} for r in runs]});del raw,d
  try:return history_check(pages,current_migration)
  except Stop as e:
   if str(e)!='HISTORY_INCOMPLETE_STOP' or len(runs)!=5 or not 0<=pages[-1]['total_count']<=500:raise
 raise Stop('HISTORY_INCOMPLETE_STOP')
