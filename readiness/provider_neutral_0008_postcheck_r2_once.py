"""Separate read-only 0008 postcheck. No write credential or migration path."""
import json,time,sqlite3
from pathlib import Path
import provider_neutral_0008_fresh_preflight_r6 as p
import provider_neutral_0008_stage_common_r2 as c
CONFIG=c.paths('postcheck')
IDENTITY=CONFIG['identity']
MAX_CALLS=59
MAX_WINDOWS=3

def queries(before,after):
 ref=dict(before,schema=after['schema']);out=p.queries(ref)
 out[0]['expected']['candidate']=16
 for table in sorted(after['new']['rows']):
  cols,indexes=p.details_sql(table)
  out.append({'kind':'new:'+table,'sql':'SELECT COUNT(*) AS total,'+cols+' AS columns_json,'+indexes+' AS indexes_json FROM '+p.ident(table),'params':[], 'expected':{'total':0,'columns_json':after['new']['columns'][table],'indexes_json':sorted(after['new']['indexes'][table],key=lambda x:x['name'])}})
 # Exact autoindex name/table/type/NULL SQL proof, including global namespace total.
 indexes=[(x['name'],table) for table,items in after['new']['indexes'].items() for x in items]
 p.need(len(indexes)==14 and after['new']['counts']['tables']==5 and after['new']['counts']['triggers']==11,'EXPECTED_SCHEMA_STOP')
 clauses=['COUNT(*) AS total']
 for i,(name,table) in enumerate(indexes):clauses.append("SUM(CASE WHEN type='index' AND name='"+name+"' AND tbl_name='"+table+"' AND sql IS NULL THEN 1 ELSE 0 END) AS i"+str(i))
 out.append({'kind':'autoindexes','sql':'SELECT '+','.join(clauses)+" FROM sqlite_master WHERE substr(name,1,7)='sqlite_' AND substr(tbl_name,1,10)='plm_rt_v2_'",'params':[],'expected':{'total':14,**{'i'+str(i):1 for i in range(14)}}})
 p.need(len(out)==17,'QUERY_BUDGET_STOP');return out

def specs(before,after):
 initial=[('GET',p.INVENTORY,None),('GET',p.TARGET,None)]
 window=[('GET',p.TARGET+'/time_travel/bookmark',None)]+[('POST',p.TARGET+'/query',{'sql':q['sql'],'params':q['params']}) for q in queries(before,after)]+[('GET',p.TARGET+'/time_travel/bookmark',None)]
 return initial+window*MAX_WINDOWS

def compare(q,rows):
 p.need(type(rows) is list and len(rows)==1 and type(rows[0]) is dict,'QUERY_SHAPE_STOP');row=dict(rows[0])
 if q['kind']=='schema':p.need(p.classifier(row.get('candidate'),row.get('total'))=='FULL_APPLIED','CANDIDATE_NOT_FULL_STOP')
 for key in ('columns_json','indexes_json'):
  if key in row:
   try:row[key]=json.loads(row[key])
   except Exception:raise p.Stop('QUERY_SHAPE_STOP') from None
 p.need(p.canonical(row)==p.canonical(q['expected']),'POSTCHECK_STATE_DRIFT_STOP')

def live_transport(read,before,after):
 p.need(type(read) is str and bool(read.strip()) and '\r' not in read and '\n' not in read,'CREDENTIAL_MISSING_STOP')
 allowed=specs(before,after);position=0;stopped=False
 def send(method,path,body):
  nonlocal position,stopped
  p.need(not stopped and position<len(allowed) and (method,path,body)==allowed[position],'REQUEST_ALLOWLIST_STOP');position+=1
  try:return p.bounded_http('api.cloudflare.com','/client/v4'+path,method,{'Authorization':'Bearer '+read,'Content-Type':'application/json'},None if body is None else json.dumps(body).encode())
  except Exception:stopped=True;raise
 return send

def postcheck(transport,before,after):
 out={'identity':IDENTITY,'pass':False,'read_calls':0,'d1_writes':0,'migration_executions':0,'retry':0,'resume':0,'raw_retention':0};sequence=specs(before,after);position=0
 def call():
  nonlocal position
  p.need(position<MAX_CALLS,'REQUEST_BUDGET_STOP');s=sequence[position];position+=1
  status,raw=transport(*s)
  if status!=200:raise p.HTTPFailure(status,raw)
  return p.decode(raw)
 try:
  d=call();r=d.get('result');i=d.get('result_info',{})
  p.need(type(r) is list and len(r)==1 and i.get('page')==1 and i.get('count')==i.get('total_count')==1 and type(i.get('per_page')) is int and i['per_page']>=1,'INVENTORY_INCOMPLETE_STOP')
  p.need(r[0].get('uuid')==p.DB and r[0].get('name')==p.NAME,'INVENTORY_TARGET_STOP')
  d=call()['result'];p.need(d.get('uuid')==p.DB and d.get('name')==p.NAME and type(d.get('file_size')) is int and d['file_size']>0,'DATABASE_METADATA_STOP')
  out.update(stable_window_found=False,stability_windows_used=0,stability_windows=[])
  for number in range(1,MAX_WINDOWS+1):
   out['stability_windows_used']=number
   bookmark=call()['result'].get('bookmark');p.need(type(bookmark) is str and p.re.fullmatch('[a-f0-9-]{16,128}',bookmark),'BOOKMARK_REQUIRED_STOP')
   for q in queries(before,after):
    d=call();r=d.get('result');p.need(type(r) is list and len(r)==1,'QUERY_SHAPE_STOP');v=r[0];m=v.get('meta',{})
    p.need(v.get('success') is True and m.get('served_by_primary') is True and type(m.get('rows_written')) is int and m['rows_written']==0 and type(m.get('changes')) is int and m['changes']==0 and m.get('changed_db') is False,'READ_ONLY_RESPONSE_STOP');compare(q,v.get('results'))
   last=call()['result'].get('bookmark');p.need(type(last) is str and p.re.fullmatch('[a-f0-9-]{16,128}',last),'BOOKMARK_REQUIRED_STOP')
   stable=last==bookmark;out['stability_windows'].append({'window':number,'stable':'YES' if stable else 'NO','state':'STABLE' if stable else 'DRIFT_OBSERVED'})
   del bookmark,last
   if stable:out.update(stable_window_found=True,stable_window_number=number);break
  p.need(out['stable_window_found'],'BOOKMARK_STABILITY_NOT_OBSERVED_STOP')
  out.update({'pass':True,'result':'0008_POSTCHECK_SUCCESS_STOP','candidate':'FULL_APPLIED','candidate_rows':0,'tables':5,'triggers':11,'autoindexes':14,'protected_schema_exact':True,'protected_rows_exact':True,'unexpected_objects':0,'0009':'NOT_APPLIED','0010':'NOT_APPLIED'})

 except p.HTTPFailure as e:out.update(e.metadata);out['result']=str(e)
 except p.Stop as e:out['result']=str(e)
 except Exception:out['result']='UNKNOWN_STOP_NO_RETRY'
 out['read_calls']=position;return out

def main():
 import os
 out={'identity':IDENTITY,'pass':False,'read_calls':0,'d1_writes':0,'migration_executions':0,'result':'PRE_REMOTE_GATE_STOP'}
 try:
  marker,plan=c.local_gate('postcheck');before,after=p.load_candidate();transport=live_transport(os.environ.get(p.READ_SECRET),before,after)
  c.prerequisite('postcheck',marker,os.environ.get('PLM_HISTORY_GITHUB_TOKEN'))
  out=postcheck(transport,before,after)
 except p.Stop as e:out['gate_code']=str(e)
 except Exception:out['gate_code']='LOCAL_UNKNOWN_STOP_NO_RETRY'
 print(json.dumps(out,sort_keys=True));return 0 if out.get('pass') else 1
if __name__=='__main__':raise SystemExit(main())
