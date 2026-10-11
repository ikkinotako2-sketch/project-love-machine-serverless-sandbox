"""Local immutable chain gates and exact prior-run proof. No Cloudflare operations."""
import json,os,re,subprocess
from pathlib import Path
import provider_neutral_0010_common as p
PARENT=p.PARENT
CONFIG={'preflight': {'identity': 'provider-neutral-0010-fresh-readonly-preflight-20261011-r1', 'helper': 'readiness/provider_neutral_0010_fresh_preflight.py', 'workflow': '.github/workflows/plm-provider-neutral-0010-fresh-readonly-once.yml', 'plan': 'readiness/provider-neutral-0010-fresh-readonly-plan.json', 'schema': 'readiness/provider-neutral-0010-fresh-readonly-marker.schema.json', 'marker': 'audit-evidence/consumed/provider-neutral-0010-fresh-readonly-preflight-20261011-r1.json', 'message': 'PLM 0010 preflight once provider-neutral-0010-fresh-readonly-preflight-20261011-r1'}, 'migration': {'identity': 'provider-neutral-0010-migration-20261011-r1', 'helper': 'readiness/provider_neutral_0010_migration_once.py', 'workflow': '.github/workflows/plm-provider-neutral-0010-migration-once.yml', 'plan': 'readiness/provider-neutral-0010-migration-plan.json', 'schema': 'readiness/provider-neutral-0010-migration-marker.schema.json', 'marker': 'audit-evidence/consumed/provider-neutral-0010-migration-20261011-r1.json', 'message': 'PLM 0010 migration once provider-neutral-0010-migration-20261011-r1'}, 'postcheck': {'identity': 'provider-neutral-0010-postcheck-20261011-r1', 'helper': 'readiness/provider_neutral_0010_postcheck_once.py', 'workflow': '.github/workflows/plm-provider-neutral-0010-postcheck-once.yml', 'plan': 'readiness/provider-neutral-0010-postcheck-plan.json', 'schema': 'readiness/provider-neutral-0010-postcheck-marker.schema.json', 'marker': 'audit-evidence/consumed/provider-neutral-0010-postcheck-20261011-r1.json', 'message': 'PLM 0010 postcheck once provider-neutral-0010-postcheck-20261011-r1'}}
def paths(stage):return CONFIG[stage]

def git(*args):return subprocess.check_output(['git',*args],text=True,stderr=subprocess.DEVNULL).strip()

def check_marker(stage,marker,plan,files):
 c=paths(stage)
 keys={'identity','state','prepared_commit_sha','workflow_sha256','helper_sha256','plan_sha256','candidate_raw_hashes','prerequisite_run_id','prerequisite_commit_sha'}
 p.need(type(marker) is dict and set(marker)==keys and marker['identity']==c['identity'] and marker['state']=='CONSUMED_BEFORE_REMOTE','MARKER_BINDING_STOP')
 for key in ('prepared_commit_sha','prerequisite_commit_sha'):p.need(type(marker[key]) is str and re.fullmatch('[a-f0-9]{40}',marker[key]),'MARKER_BINDING_STOP')
 p.need(type(marker['prerequisite_run_id']) is int and marker['prerequisite_run_id']>0,'PREREQUISITE_REQUIRED_STOP')
 p.need(marker['candidate_raw_hashes']==p.PINS and plan['candidate_raw_hashes']==p.PINS and plan['identity']==c['identity'] and plan['exact_parent_sha']==PARENT,'PLAN_BINDING_STOP')
 for key,kind in [('workflow_sha256','workflow'),('helper_sha256','helper'),('plan_sha256','plan')]:p.need(marker[key]==p.sha(files[c[kind]]),'MARKER_HASH_STOP')
 for key,kind in [('workflow_sha256','workflow'),('helper_sha256','helper'),('marker_schema_sha256','schema')]:p.need(plan[key]==p.sha(files[c[kind]]),'PLAN_HASH_STOP')
 for path,h in plan['dependency_hashes'].items():p.need(p.sha(files[path])==h,'DEPENDENCY_HASH_STOP')
 p.need(plan['run_attempt']==1 and all(plan[k]==0 for k in ('retry','resend','resume','fallback','redirect','automatic_rollback','raw_retention','query_mutation')),'PLAN_LIMITS_STOP')
 return c

def local_gate(stage):
 c=paths(stage);e=os.environ
 p.need(e.get('GITHUB_REPOSITORY')==p.REPO and e.get('GITHUB_REF')=='refs/heads/plm-offline-readiness-v1-20261002' and e.get('GITHUB_EVENT_NAME')=='push' and e.get('GITHUB_RUN_ATTEMPT')=='1','EXECUTION_CONTEXT_STOP')
 p.need(all(e.get(k)=='true' for k in ('TEST_ONLY','DRY_RUN','NO_PUBLISH','EMERGENCY_STOP')),'EXECUTION_CONTEXT_STOP')
 marker=json.loads(Path(c['marker']).read_bytes());plan=json.loads(Path(c['plan']).read_bytes())
 filepaths=[c[k] for k in ('workflow','helper','plan','schema')]+list(plan['dependency_hashes'])
 files={path:Path(path).read_bytes() for path in filepaths};check_marker(stage,marker,plan,files)
 before=e.get('PLM_APPROVED_BEFORE');prepared=marker['prepared_commit_sha']
 p.need(git('rev-parse','HEAD^')==before and git('rev-parse','HEAD')==e.get('GITHUB_SHA'),'PARENT_STOP')
 p.need(git('rev-parse',prepared+'^')==PARENT,'PREPARATION_PARENT_STOP')
 p.need(git('diff','--name-only',before,'HEAD')==c['marker'] and git('show','-s','--format=%B','HEAD')==c['message'],'MARKER_ONLY_STOP')
 p.need(subprocess.run(['git','cat-file','-e',before+':'+c['marker']],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode!=0,'ALREADY_CONSUMED_STOP')
 chain=git('rev-list','--reverse',prepared+'..'+before).splitlines()
 expected={'preflight':[], 'migration':['preflight'], 'postcheck':['preflight','migration']}[stage]
 p.need(len(chain)==len(expected),'INTERVENING_COMMIT_STOP')
 if stage=='preflight':p.need(before==prepared,'PREPARATION_HEAD_STOP')
 previous=prepared
 for sha,kind in zip(chain,expected):
  pc=paths(kind);mp=pc['marker'];message=pc['message']
  p.need(git('rev-parse',sha+'^')==previous and git('diff','--name-only',previous,sha)==mp and git('show','-s','--format=%B',sha)==message,'INTERVENING_COMMIT_STOP')
  old=json.loads(git('show',sha+':'+mp));p.need(old['prepared_commit_sha']==prepared,'CHAIN_BINDING_STOP')
  pp=json.loads(Path(pc['plan']).read_bytes());check_marker(kind,old,pp,{path:Path(path).read_bytes() for path in [pc[k] for k in ('workflow','helper','plan','schema')]+list(pp['dependency_hashes'])})
  previous=sha
 p.need(marker['prerequisite_commit_sha']==(PARENT if stage=='preflight' else before),'PREREQUISITE_COMMIT_STOP')
 for path in filepaths+list(p.PINS):p.need(Path(path).read_bytes()==subprocess.check_output(['git','show',prepared+':'+path]),'PREPARED_BYTES_STOP')
 if stage=='preflight':p.need(marker['prerequisite_run_id']==38113308404,'PREREQUISITE_RUN_STOP')
 p.load_candidate()
 return marker,plan

def prerequisite(stage,marker,token,http=None):
 # Two exact read-only GitHub metadata calls, no logs/artifacts/redirects.
 p.need(bool(token),'HISTORY_CREDENTIAL_STOP');http=http or p.bounded_http
 prev={'preflight':None,'migration':'preflight','postcheck':'migration'}[stage];rid=marker['prerequisite_run_id'];expected=paths(prev)['workflow'] if prev else '.github/workflows/plm-provider-neutral-0009-postcheck-once.yml'
 def get(suffix):
  status,raw=http('api.github.com','/repos/'+p.REPO+'/actions/runs/'+str(rid)+suffix,'GET',{'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','User-Agent':'PLM-stage-gate'})
  p.need(status==200 and type(raw) is bytes and len(raw)<=p.MAX_BYTES,'PREREQUISITE_HTTP_STOP')
  try:return json.loads(raw)
  except Exception:raise p.Stop('PREREQUISITE_SHAPE_STOP') from None
 r=get('');p.need(r.get('id')==rid and r.get('path')==expected and r.get('head_sha')==marker['prerequisite_commit_sha'] and r.get('event')=='push' and r.get('run_attempt')==1 and r.get('status')=='completed' and r.get('conclusion')=='success','PREREQUISITE_NOT_SUCCESS_STOP')
 jobs=get('/jobs?per_page=5');j=jobs.get('jobs')
 expected_step='Run exact stage once'
 p.need(jobs.get('total_count')==1 and type(j) is list and len(j)==1 and j[0].get('conclusion')=='success' and any(s.get('name')==expected_step and s.get('conclusion')=='success' for s in j[0].get('steps',[])),'PREREQUISITE_JOB_STOP')
 return True
