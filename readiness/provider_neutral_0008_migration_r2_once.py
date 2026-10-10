"""Fixed 0008 REST_IMPORT_SQL_FILE, bounded one-pass state machine. No query writes."""
import json,hashlib,time,re
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
import provider_neutral_0008_fresh_preflight_r6 as p
import provider_neutral_0008_stage_common_r2 as c
CONFIG=c.paths('migration');IDENTITY=CONFIG['identity']
SQL='serverless/migrations/0008_provider_neutral_roundtrip_backend.sql'
IMPORT=p.TARGET+'/import'

def upload_url(value):
 p.need(type(value) is str and len(value)<=4096,'UPLOAD_URL_STOP');u=urlsplit(value)
 p.need(u.scheme=='https' and not u.username and not u.password and not u.port and not u.fragment and re.fullmatch('[a-f0-9]{32}\\.r2\\.cloudflarestorage\\.com',u.hostname or '') and bool(parse_qs(u.query).get('X-Amz-Signature')),'UPLOAD_URL_STOP')
 return u

class LiveImport:
 def __init__(self,token,sql):
  p.need(type(token) is str and bool(token.strip()) and '\r' not in token and '\n' not in token,'BACKEND_CREDENTIAL_MISSING_STOP')
  p.need(p.sha(sql)==p.PINS[SQL],'RAW_SHA_STOP');self.token=token;self.sql=sql;self.etag=hashlib.md5(sql).hexdigest();self.state='init';self.polls=0;self.upload=None;self.filename=None;self.bookmark=None
 def __call__(self,action,fields):
  # Advance/stop before every network request, including timeout and unknown result.
  p.need(action==self.state or (self.state=='poll' and action=='poll'),'IMPORT_SEQUENCE_STOP');self.state='stopped'
  if action=='upload':
   p.need(fields=={'url':self.upload,'sql':self.sql},'UPLOAD_BINDING_STOP');u=upload_url(self.upload)
   import http.client
   conn=http.client.HTTPSConnection(u.hostname,timeout=15)
   try:
    conn.request('PUT',u.path+'?'+u.query,body=self.sql,headers={'Content-Type':'application/sql'})
    r=conn.getresponse();p.need(r.status==200,'UPLOAD_HTTP_UNKNOWN_STOP');p.need(r.getheader('ETag','').strip('"')==self.etag,'UPLOAD_ETAG_UNKNOWN_STOP')
   finally:conn.close()
   self.state='ingest';return {'uploaded':True}
  expected={'init':{'etag':self.etag},'ingest':{'etag':self.etag,'filename':self.filename},'poll':{'current_bookmark':self.bookmark}}
  p.need(action in expected and fields==expected[action],'IMPORT_BINDING_STOP')
  if action=='poll':self.polls+=1;p.need(self.polls<=3,'IMPORT_POLL_BUDGET_STOP')
  status,raw=p.bounded_http('api.cloudflare.com','/client/v4'+IMPORT,'POST',{'Authorization':'Bearer '+self.token,'Content-Type':'application/json'},json.dumps({'action':action,**fields}).encode())
  if status!=200:raise p.HTTPFailure(status,raw)
  result=p.decode(raw).get('result');p.need(type(result) is dict,'IMPORT_SHAPE_STOP')
  if action=='init' and 'upload_url' in result:
   upload_url(result['upload_url']);self.upload=result['upload_url'];self.filename=result.get('filename');self.state='upload'
  elif result.get('status')!='complete':self.bookmark=result.get('at_bookmark');self.state='poll'
  return result

class ImportRunner:
 def __init__(self):self.used=False
 def run(self,sql,fresh,transport,journal,now):
  out={'identity':IDENTITY,'pass':False,'migration_executions':0,'side_effect_requests':0,'import_http_calls':0,'polls':0,'query_mutations':0,'retry':0,'resend':0,'resume':0,'fallback':0,'automatic_rollback':0,'raw_retention':0,'candidate':'STILL_UNKNOWN'}
  sent=set();bookmark=None
  def send(action,fields):
   p.need(out['import_http_calls']<6,'IMPORT_BUDGET_STOP')
   if action=='poll':p.need(out['polls']<3,'POLL_BUDGET_STOP');out['polls']+=1
   else:
    p.need(action not in sent and out['side_effect_requests']<3,'NO_RESEND_STOP')
    # The permanent marker and GitHub run already exist. Emit only sanitized reservation metadata.
    journal({'identity':IDENTITY,'state':'RESERVED_NO_RESEND','operation':action,'sql_sha256':p.PINS[SQL]})
    sent.add(action);out['side_effect_requests']+=1;out['migration_executions']=1
   out['import_http_calls']+=1
   return transport(action,fields)
  def state(s,action):
   p.need(type(s) is dict and s.get('success') is not False and 'error' not in s,'IMPORT_STATE_UNKNOWN_STOP')
   if 'upload_url' in s:
    p.need(action=='init' and not any(k in s for k in ('status','at_bookmark','result')),'IMPORT_CONFLICTING_STATE_STOP');upload_url(s['upload_url'])
    p.need(type(s.get('filename')) is str and re.fullmatch('[A-Za-z0-9_.-]{1,256}',s['filename']),'IMPORT_FILENAME_STOP')
   elif s.get('status')=='complete':
    r=s.get('result',{});p.need(type(r) is dict and type(r.get('num_queries')) is int and r['num_queries']==16 and type(r.get('final_bookmark')) is str and re.fullmatch('[a-f0-9-]{16,128}',r['final_bookmark']),'IMPORT_COMPLETE_UNKNOWN_STOP')
   else:p.need(s.get('status') is None and type(s.get('at_bookmark')) is str and re.fullmatch('[a-f0-9-]{16,128}',s['at_bookmark']),'IMPORT_STATE_UNKNOWN_STOP')
   return s
  try:
   p.need(not self.used,'RUNNER_ALREADY_CONSUMED_STOP');self.used=True
   p.need(p.sha(sql)==p.PINS[SQL],'RAW_SHA_STOP')
   p.need(fresh.get('pass') is True and fresh.get('result')=='FRESH_PREFLIGHT_SUCCESS_STOP_BEFORE_MIGRATION' and fresh.get('candidate_classification')=='NOT_APPLIED' and fresh.get('prior_send')==0 and fresh.get('hashes')==p.PINS and fresh.get('protected_schema_exact') is True and fresh.get('protected_rows_exact') is True and fresh.get('inventory_complete') is True and fresh.get('token_status')=='ACTIVE' and fresh.get('stable_window_found') is True and type(fresh.get('stable_window_number')) is int and 1<=fresh['stable_window_number']<=3 and fresh.get('stability_windows_used')==fresh['stable_window_number'],'FRESH_PRE_GATE_STOP')
   p.expiry(fresh.get('token_expires_at'),now)
   etag=hashlib.md5(sql).hexdigest();s=state(send('init',{'etag':etag}),'init')
   if 'upload_url' in s:
    p.need(send('upload',{'url':s['upload_url'],'sql':sql})=={'uploaded':True},'UPLOAD_UNKNOWN_STOP')
    s=state(send('ingest',{'etag':etag,'filename':s['filename']}),'ingest')
   while s.get('status')!='complete':
    if bookmark is None:bookmark=s['at_bookmark']
    p.need(s['at_bookmark']==bookmark,'IMPORT_BOOKMARK_DRIFT_STOP')
    s=state(send('poll',{'current_bookmark':bookmark}),'poll')
   out.update({'pass':True,'result':'0008_IMPORT_ACK_STOP_BEFORE_POSTCHECK','final_bookmark':s['result']['final_bookmark'],'postcheck_required':True})
  except p.HTTPFailure as e:out.update(e.metadata);out['result']='UNKNOWN_NO_RESEND_STOP'
  except Exception:out['result']='UNKNOWN_NO_RESEND_STOP' if out['migration_executions'] else 'PRE_WRITE_GATE_STOP'
  return out

def main():
 import os
 out={'identity':IDENTITY,'pass':False,'migration_executions':0,'side_effect_requests':0,'cloudflare_read_only_calls':0,'query_mutations':0,'result':'PRE_REMOTE_GATE_STOP'}
 try:
  marker,plan=c.local_gate('migration');before,_=p.load_candidate();e=os.environ
  read=p.live_transport(e.get(p.READ_SECRET),e.get(p.BACKEND_SECRET),before)
  c.prerequisite('migration',marker,e.get('PLM_HISTORY_GITHUB_TOKEN'))
  # Only this new, exact validated run is excluded; any other migration run stops.
  rid=e.get('GITHUB_RUN_ID');p.need(type(rid) is str and rid.isdigit(),'RUN_ID_STOP')
  history=p.fetch_history(e.get('PLM_HISTORY_GITHUB_TOKEN'),{'id':int(rid),'path':CONFIG['workflow']})
  paths=[str(x) for x in Path('audit-evidence').rglob('*.json') if str(x) not in (CONFIG['marker'],p.MARKER)]
  fresh=p.preflight(read,before,time.time(),paths,history,clock=time.time);out['cloudflare_read_only_calls']=fresh['cloudflare_read_only_calls']
  if not fresh['pass']:out['result']='FRESH_PRE_GATE_STOP';out['pre_gate']=fresh
  else:
   sql=Path(SQL).read_bytes();transport=LiveImport(e.get(p.BACKEND_SECRET),sql)
   def journal(event):print(json.dumps(event,sort_keys=True),flush=True)
   out=ImportRunner().run(sql,fresh,transport,journal,time.time());out['cloudflare_read_only_calls']=fresh['cloudflare_read_only_calls']
 except p.Stop as err:out['gate_code']=str(err)
 except Exception:out['gate_code']='LOCAL_UNKNOWN_STOP_NO_RETRY'
 print(json.dumps(out,sort_keys=True));return 0 if out.get('pass') else 1
if __name__=='__main__':raise SystemExit(main())
