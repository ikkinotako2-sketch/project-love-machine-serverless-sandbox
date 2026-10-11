"""Exact one-shot 0010 preflight; preparation does not execute remote operations."""
import json,os
from pathlib import Path
import provider_neutral_0010_common as p
import provider_neutral_0010_stage_gate as c
CONFIG=c.paths('preflight');IDENTITY=CONFIG['identity']
def main():
 out={'identity':IDENTITY,'pass':False,'cloudflare_read_only_calls':0,'d1_calls':0,'d1_writes':0,'migration_executions':0,'result':'PRE_REMOTE_GATE_STOP'}
 try:
  marker,plan=c.local_gate('preflight');before,after=p.load_candidate();e=os.environ
  transport=p.live_transport(e.get(p.READ_SECRET),e.get(p.BACKEND_SECRET),before,post=False)
  c.prerequisite('preflight',marker,e.get('PLM_HISTORY_GITHUB_TOKEN'))
  p.prior_check([str(x) for x in Path('audit-evidence').rglob('*.json')],CONFIG['marker']);history=p.fetch_history(e.get('PLM_HISTORY_GITHUB_TOKEN'))
  out=p.audit(transport,before,post=False,history=history);out['identity']=IDENTITY
 except p.Stop as err:out['gate_code']=str(err)
 except Exception:out['gate_code']='LOCAL_UNKNOWN_STOP_NO_RETRY'
 print(json.dumps(out,sort_keys=True));return 0 if out.get('pass') else 1
if __name__=='__main__':raise SystemExit(main())
