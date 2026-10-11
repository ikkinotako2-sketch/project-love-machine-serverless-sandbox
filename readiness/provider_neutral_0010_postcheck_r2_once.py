"""Exact one-shot 0010 postcheck; preparation does not execute remote operations."""
import json,os
from pathlib import Path
import provider_neutral_0010_common as p
import provider_neutral_0010_r2_stage_gate as c
CONFIG=c.paths('postcheck');IDENTITY=CONFIG['identity']
SQL='serverless/migrations/0010_youtube_pipeline_checkpoint_candidate.sql'
def main():
 out={'identity':IDENTITY,'pass':False,'cloudflare_read_only_calls':0,'d1_calls':0,'d1_writes':0,'migration_executions':0,'result':'PRE_REMOTE_GATE_STOP'}
 try:
  marker,plan=c.local_gate('postcheck');c.validate_sql(plan,Path(SQL).read_bytes(),helper_sql=SQL);before,after=p.load_candidate();e=os.environ
  transport=p.live_transport(e.get(p.READ_SECRET),None,after,post=True)
  c.prerequisite('postcheck',marker,e.get('PLM_HISTORY_GITHUB_TOKEN'))
  history=None
  out=p.audit(transport,after,post=True,history=history);out['identity']=IDENTITY
 except p.Stop as err:out['gate_code']=str(err)
 except Exception:out['gate_code']='LOCAL_UNKNOWN_STOP_NO_RETRY'
 print(json.dumps(out,sort_keys=True));return 0 if out.get('pass') else 1
if __name__=='__main__':raise SystemExit(main())
