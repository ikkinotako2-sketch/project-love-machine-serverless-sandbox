import {readFileSync,readdirSync} from 'node:fs';import {pathToFileURL} from 'node:url';
import {ACCOUNT,REPO,baseContext,sha} from './atomicity-schema-audit.mjs';
import {v3Plan,v3Oracle,V3_PLAN_SHA as PLAN_SHA} from './generalized-behavior-v3-contract.mjs';
const TEST_WORKFLOW='.github/workflows/plm-generalized-behavior-v3-test-once.yml';
function planCheck(){const p=v3Plan();return {plan_sha256:PLAN_SHA,identity:p.identity,steps:33,budgets:p.budgets,execution_approved:false,allow:false};}
import {preflight as finalPreflight,MESSAGE as FINAL_MESSAGE} from './generalized-behavior-v3-credential-preflight.mjs';
import {fixedPlan,runFixed,mutationTransport,behaviorReadTransport,postCheck} from './generalized-behavior-v3-runner.mjs';
import {exclusiveJournal} from './atomicity-test.mjs';import {jsonBounded} from './d1-v2-migration.mjs';
export const MESSAGE='PLM execute approved fixed generalized behavior v3 33 steps once 20261004-r1';
export const WORKFLOW='.github/workflows/plm-generalized-behavior-v3-approved-once.yml';
export function localChecks(){if(readdirSync(new URL('../audit-evidence/',import.meta.url)).some(n=>/^generalized-behavior-v3-approved-(result|sent)-/.test(n)))throw Error('RT_V3_EXEC_PRIOR_RESULT_NO_RESUME');const p=planCheck();v3Oracle();const raw=readFileSync(new URL('../audit-evidence/generalized-behavior-v3-credential-preflight-37172345807.json',import.meta.url));if(sha(raw)!=='a8ebac03660e776768958553bee70a2617c112edb37b43730928e3afd68ba470')throw Error('RT_V3_EXEC_APPROVED_RECEIPT_DRIFT');const r=JSON.parse(raw);if(r.run_id!==37172345807||!r.result.pass||r.result.plan.plan_sha256!==PLAN_SHA||r.result.transport_counts.v3_verify!==1)throw Error('RT_V3_EXEC_APPROVED_RECEIPT_INVALID');return p;}
export async function executionHistory(e,f){let total,seen=0,current=0;const ids=new Set();for(let page=1;page<=100;page++){
 const r=await f(`https://api.github.com/repos/${REPO}/actions/runs?per_page=20&page=${page}`,{method:'GET',redirect:'error',signal:AbortSignal.timeout(15000),headers:{Authorization:`Bearer ${e.PLM_HISTORY_GITHUB_TOKEN}`}});if(!r.ok)throw Error('RT_V3_EXEC_HISTORY_HTTP_UNKNOWN');const b=await jsonBounded(r,1048576);if(!Number.isSafeInteger(b.total_count)||!Array.isArray(b.workflow_runs))throw Error('RT_V3_EXEC_HISTORY_UNKNOWN');if(total===undefined)total=b.total_count;if(total!==b.total_count)throw Error('RT_V3_EXEC_HISTORY_CHANGED');
 for(const x of b.workflow_runs){
  if(ids.has(x.id))throw Error('RT_V3_EXEC_HISTORY_DUPLICATE');ids.add(x.id);seen++;
  const readonly={'.github/workflows/plm-generalized-behavior-v3-schema-read-only.yml':37170582256,'.github/workflows/plm-generalized-behavior-v3-final-read-only-preflight.yml':37171104181,'.github/workflows/plm-generalized-behavior-v3-credential-read-only-preflight.yml':37172345807};
  if(/^\.github\/workflows\/plm-generalized-behavior-v3-/.test(x.path||'')){
   if(String(x.id)===e.GITHUB_RUN_ID&&x.path===WORKFLOW){if(x.head_sha!==e.GITHUB_SHA||x.run_attempt!==1)throw Error('RT_V3_EXEC_CURRENT_RUN_DRIFT');current++;}
   else if(readonly[x.path]===x.id){if(x.status!=='completed'||x.conclusion!=='success'||x.run_attempt!==1)throw Error('RT_V3_EXEC_PREFLIGHT_HISTORY_DRIFT');}
   else if(x.status!=='completed'||x.conclusion!=='skipped'||x.run_attempt!==1)throw Error('RT_V3_EXEC_PRIOR_SEND_NO_RESUME');
  }
 }
 if(seen===total){if(current!==1)throw Error('RT_V3_EXEC_CURRENT_RUN_NOT_UNIQUE');return {complete:true,total,pages:page,prior_behavior_execution:0,current_run_unique:true};}if(!b.workflow_runs.length||seen>total)throw Error('RT_V3_EXEC_HISTORY_INCOMPLETE');
 }throw Error('RT_V3_EXEC_HISTORY_INCOMPLETE');}
export async function executionEntry(e,f=fetch,{checkout,checks=localChecks,history=executionHistory,fresh=finalPreflight,journalFactory,runner=runFixed,post=postCheck}={}){
 const counts={mutation_sends:0,read_only_calls:0},out={status:'BLOCKED',mutation_sends:0,successful_logical_row_changes:0,reconciliation_sets:0,post_sets:0,delete:0,drop:0,reset:0,retry:0,resend:0,fallback:0,automatic_rollback:0,external_provider:0,worker:0,ai:0,render_execution:0,youtube:0,sns:0,live_ready:false,posting_permitted:false,cleanup_required:true};
 try{
  if(!baseContext(e)||e.GITHUB_EVENT_NAME!=='push'||!/^\d+$/.test(e.GITHUB_RUN_ID||'')||!/^[a-f0-9]{40}$/.test(checkout||'')||e.PLM_RT_V3_EXEC_PIN!==checkout||e.PLM_RT_V3_EXEC_BEFORE!==checkout||e.PLM_RT_V3_EXEC_MESSAGE!==MESSAGE||e.PLM_RT_V3_ALLOW!=='true'||e.PLM_RT_V3_OWNER_APPROVAL!=='EXECUTE_FIXED_GENERALIZED_BEHAVIOR_V3_33_ONCE'||e.PLM_RT_V3_APPROVED_PLAN_SHA!==PLAN_SHA||Object.keys(e).some(k=>/^PLM_CF_.*TOKEN$/.test(k)&&!['PLM_CF_D1_READ_TOKEN','PLM_CF_D1_ROUNDTRIP_BEHAVIOR_V3_TOKEN'].includes(k)&&e[k]))throw Error('RT_V3_EXEC_CONTEXT_REJECTED');
  if(![e.PLM_CF_D1_READ_TOKEN,e.PLM_CF_D1_ROUNDTRIP_BEHAVIOR_V3_TOKEN,e.PLM_HISTORY_GITHUB_TOKEN].every(x=>typeof x==='string'&&x.length>0&&x.length<=4096&&!/[\r\n]/.test(x))||new Set([e.PLM_CF_D1_READ_TOKEN,e.PLM_CF_D1_ROUNDTRIP_BEHAVIOR_V3_TOKEN,e.PLM_HISTORY_GITHUB_TOKEN]).size!==3)throw Error('RT_V3_EXEC_CREDENTIAL_REJECTED');
  checks();out.history=await history(e,f);
  out.preflight=await fresh({...e,PLM_RT_V3_ALLOW:'false',PLM_RT_V3_OWNER_APPROVAL:'UNAPPROVED',PLM_RT_V3_CRED_PIN:checkout,PLM_RT_V3_CRED_BEFORE:checkout,PLM_RT_V3_CRED_MESSAGE:FINAL_MESSAGE},f,{checkout,local:planCheck,historyCheck:async()=>out.history});
  if(!out.preflight.pass||!out.preflight.token_active||!out.preflight.finite_expiry||out.preflight.readiness?.post?.schema_classification!=='FULL_APPLIED')throw Error('RT_V3_EXEC_FRESH_GATE_UNCONFIRMED');
  let journal;if(journalFactory)journal=journalFactory();else{if(!e.RUNNER_TEMP?.startsWith('/'))throw Error('RT_V3_EXEC_JOURNAL_PATH_REQUIRED');const disk=exclusiveJournal(e.RUNNER_TEMP+'/generalized-behavior-v3-fixed33');journal={reserve(id,data){disk.reserve(id,{...data,run_id:e.GITHUB_RUN_ID,code_pin:checkout});console.log('GENERALIZED_BEHAVIOR_V3_SENT '+JSON.stringify({id,sequence:data.sequence,status:'SENT',plan_sha256:PLAN_SHA,run_id:e.GITHUB_RUN_ID}));},finish:(id,status)=>disk.finish(id,status)};}
  const mutate=mutationTransport(e,f,counts),read=behaviorReadTransport(e,async(u,o)=>{counts.read_only_calls++;return f(u,o);});Object.assign(out,await runner(e,{mutate,read,journal,post:()=>post({PLM_CF_D1_READ_TOKEN:e.PLM_CF_D1_READ_TOKEN},read)}));
 }catch(err){out.failure_code=/^[A-Z0-9_]+$/.test(err.message)?err.message:'RT_V3_EXEC_UNKNOWN_NO_RETRY';out.status=counts.mutation_sends?'STOP':'BLOCKED';}
 out.status=out.status==='SUCCESS'?'SUCCESS':counts.mutation_sends?'PARTIAL_APPLIED':'STOPPED_NO_MUTATION';out.permanently_consumed=true;return {...out,transport_counts:counts,plan_sha256:PLAN_SHA,code_pin:checkout,event_commit:e.GITHUB_SHA,completed_at:new Date().toISOString()};
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){const r=await executionEntry(process.env,fetch,{checkout:readFileSync('.git/HEAD','utf8').trim()});console.log('GENERALIZED_BEHAVIOR_V3_EXECUTION_RECEIPT '+JSON.stringify(r));if(r.status!=='SUCCESS')process.exitCode=1;}
