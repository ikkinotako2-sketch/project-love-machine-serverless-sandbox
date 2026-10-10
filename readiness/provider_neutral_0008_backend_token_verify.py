"""One-shot backend self verification only. No D1 or history client."""
import hashlib,json,re
from pathlib import Path
from datetime import datetime,timezone
IDENTITY='provider-neutral-0008-backend-token-verify-20261010-r1'
PARENT='a0097ad228cafa24b78c715965caef4dd8353c67'
REPO='ikkinotako2-sketch/project-love-machine-serverless-sandbox'
BRANCH='plm-offline-readiness-v1-20261002'
ACCOUNT='6c8ccd6aface937ab5dabef61cb64534'
VERIFY='/accounts/'+ACCOUNT+'/tokens/verify'
SECRET='PLM_CF_D1_ROUNDTRIP_BACKEND_TOKEN'
HELPER='readiness/provider_neutral_0008_backend_token_verify.py'
WORKFLOW='.github/workflows/plm-provider-neutral-0008-backend-token-verify-once.yml'
PLAN='readiness/provider-neutral-0008-backend-token-verify-plan.json'
SCHEMA='readiness/provider-neutral-0008-backend-token-verify-marker.schema.json'
MARKER='audit-evidence/consumed/'+IDENTITY+'.json'
MESSAGE='PLM backend token verify once '+IDENTITY
MAX_BYTES=262144
ERROR_BODY_MAX_BYTES=32768
MAX_ERROR_CODES=8
LIMITS={'maximum_cloudflare_calls':1,'d1_calls':0,'maximum_writes':0,'github_history_calls':0,'worker_calls':0,'youtube_calls':0,'retry':0,'rerun':0,'resume':0,'resend':0,'fallback':0,'redirect':0,'automatic_rollback':0,'raw_retention':0,'run_attempt':1}
class Stop(Exception):pass

def need(ok,code):
 if not ok:raise Stop(code)

def sha(b):return hashlib.sha256(b).hexdigest()

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

def error_diagnostic(raw,body_status=None):
 codes=[]
 if body_status is not None:return {'cloudflare_error_codes':codes,'error_body_status':body_status}
 if type(raw) is not bytes:return {'cloudflare_error_codes':codes,'error_body_status':'INVALID_NOT_RETAINED'}
 if len(raw)>ERROR_BODY_MAX_BYTES:return {'cloudflare_error_codes':codes,'error_body_status':'OVERSIZE_NOT_RETAINED'}
 def pairs(items):
  result={}
  for key,value in items:
   if key in result:raise ValueError()
   result[key]=value
  return result
 try:
  envelope=json.loads(raw.decode('utf-8'),object_pairs_hook=pairs)
  if type(envelope) is not dict or envelope.get('success') is not False or type(envelope.get('errors')) is not list:raise ValueError()
  codes=[e['code'] for e in envelope['errors'] if type(e) is dict and type(e.get('code')) is int][:MAX_ERROR_CODES]
  state='PARSED_CODES_ONLY'
 except Exception:state='NON_JSON_OR_INVALID_ENVELOPE_NOT_RETAINED'
 return {'cloudflare_error_codes':codes,'error_body_status':state}

class HTTPFailure(Stop):
 def __init__(self,status,raw=b'',body_status=None):
  need(type(status) is int and 100<=status<=999,'HTTP_STATUS_INVALID_STOP')
  super().__init__('HTTP_'+str(status)+'_STOP')
  allowed={'OVERSIZE_NOT_RETAINED','INVALID_LENGTH_NOT_RETAINED','READ_FAILED_NOT_RETAINED'}
  need(body_status is None or body_status in allowed,'HTTP_DIAGNOSTIC_INVALID_STOP')
  self.metadata={'http_status':status,**error_diagnostic(raw,body_status)}

def bounded_http(token):
 import http.client
 conn=http.client.HTTPSConnection('api.cloudflare.com',timeout=15)
 try:
  conn.request('GET','/client/v4'+VERIFY,headers={'Authorization':'Bearer '+token});r=conn.getresponse()
  if r.status!=200:
   status=r.status
   try:
    length=r.getheader('Content-Length')
    if length is not None and (not length.isdigit()):raise HTTPFailure(status,body_status='INVALID_LENGTH_NOT_RETAINED')
    if length is not None and int(length)>ERROR_BODY_MAX_BYTES:raise HTTPFailure(status,body_status='OVERSIZE_NOT_RETAINED')
    raw=r.read(ERROR_BODY_MAX_BYTES+1)
   except HTTPFailure:raise
   except Exception:raise HTTPFailure(status,body_status='READ_FAILED_NOT_RETAINED') from None
   raise HTTPFailure(status,raw)
  length=r.getheader('Content-Length');need(length is None or (length.isdigit() and int(length)<=MAX_BYTES),'RESPONSE_BOUND_STOP')
  raw=r.read(MAX_BYTES+1);need(len(raw)<=MAX_BYTES,'RESPONSE_BOUND_STOP');return r.status,raw
 finally:conn.close()

def live_transport(token):
 need(type(token) is str and bool(token.strip()) and '\r' not in token and '\n' not in token,'BACKEND_CREDENTIAL_MISSING_STOP')
 used=False
 def send(method,path,body=None):
  nonlocal used
  need(not used,'SECOND_SEND_FORBIDDEN_STOP');used=True
  need((method,path,body)==('GET',VERIFY,None),'REQUEST_ALLOWLIST_STOP')
  return bounded_http(token)
 return send

class Gate:
 def __init__(self,transport):self.transport=transport;self.count=0;self.used=False
 def call(self,method='GET',path=VERIFY,body=None):
  need(not self.used,'SECOND_SEND_FORBIDDEN_STOP');self.used=True
  need((method,path,body)==('GET',VERIFY,None),'REQUEST_ALLOWLIST_STOP')
  self.count=1
  try:
   status,raw=self.transport(method,path,body)
   if status!=200:raise HTTPFailure(status,raw)
   return decode(raw)
  except Stop:raise
  except Exception:raise Stop('TRANSPORT_UNKNOWN_NO_RETRY') from None

def verify(transport,now,clock=None):
 out={'identity':IDENTITY,'pass':False,'cloudflare_calls':0,'d1_calls':0,'d1_reads':0,'d1_writes':0,'github_history_calls':0,'worker_calls':0,'youtube_calls':0,'retry':0,'rerun':0,'resume':0,'resend':0,'fallback':0,'redirect':0,'automatic_rollback':0,'raw_retention':0,'token_type':'ACCOUNT_OWNED','scope_api_independently_verified':False,'scope':'OWNER_ATTESTED_D1_WRITE_ONLY_NOT_API_VERIFIED'}
 gate=Gate(transport)
 try:
  envelope=gate.call();out['http_status']=200;v=envelope.get('result')
  need(type(v) is dict and v.get('status')=='active','TOKEN_INACTIVE_STOP')
  need(type(v.get('id')) is str and re.fullmatch('[a-f0-9]{32}',v['id']),'TOKEN_ID_INVALID_STOP')
  exp=expiry(v.get('expires_on'),clock() if clock else now)
  out.update(token_status='ACTIVE',token_id=v['id'],expires_on=exp,result='BACKEND_TOKEN_VERIFY_SUCCESS_STOP');out['pass']=True
 except HTTPFailure as e:out.update(e.metadata);out['result']=str(e)
 except Stop as e:out['result']=str(e)
 except Exception:out['result']='LOCAL_UNKNOWN_STOP_NO_RETRY'
 out['cloudflare_calls']=gate.count;return out

def marker_check(marker,plan,before,files):
 keys={'identity','state','prepared_commit_sha','workflow_sha256','helper_sha256','plan_sha256'}
 need(type(marker) is dict and set(marker)==keys and marker['identity']==IDENTITY and marker['state']=='CONSUMED_BEFORE_REMOTE' and marker['prepared_commit_sha']==before and re.fullmatch('[a-f0-9]{40}',before or ''),'MARKER_BINDING_STOP')
 need(plan['identity']==IDENTITY and plan['exact_parent_sha']==PARENT and plan['limits']==LIMITS and plan['endpoint']=='https://api.cloudflare.com/client/v4'+VERIFY and plan['credential']==SECRET,'PLAN_BINDING_STOP')
 for key,path in [('workflow_sha256',WORKFLOW),('helper_sha256',HELPER),('plan_sha256',PLAN)]:need(marker[key]==sha(files[path]),'MARKER_HASH_STOP')
 need(plan['workflow_sha256']==marker['workflow_sha256'] and plan['helper_sha256']==marker['helper_sha256'] and plan['marker_schema_sha256']==sha(files[SCHEMA]),'PLAN_HASH_STOP')

def main():
 import os,time
 e=os.environ;out={'identity':IDENTITY,'pass':False,'cloudflare_calls':0,'d1_calls':0,'d1_writes':0,'result':'PRE_REMOTE_GATE_STOP'}
 try:
  need(e.get('GITHUB_REPOSITORY')==REPO and e.get('GITHUB_REF')=='refs/heads/'+BRANCH and e.get('GITHUB_EVENT_NAME')=='push' and e.get('GITHUB_RUN_ATTEMPT')=='1' and all(e.get(k)=='true' for k in ('TEST_ONLY','DRY_RUN','NO_PUBLISH','EMERGENCY_STOP')),'EXECUTION_CONTEXT_STOP')
  transport=live_transport(e.get(SECRET))
  files={p:Path(p).read_bytes() for p in (PLAN,WORKFLOW,HELPER,SCHEMA)}
  marker_check(json.loads(Path(MARKER).read_bytes()),json.loads(files[PLAN]),e.get('PLM_APPROVED_BEFORE'),files)
  out=verify(transport,time.time(),clock=time.time)
 except Stop as err:out['gate_code']=str(err)
 except Exception:out['gate_code']='LOCAL_VALIDATION_UNKNOWN_STOP_NO_RETRY'
 print(json.dumps(out,sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
