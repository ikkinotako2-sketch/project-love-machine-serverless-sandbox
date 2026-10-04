// Read-only only; no execution runner or mutation transport is imported.
import {readFileSync,readdirSync} from 'node:fs';
import {pathToFileURL} from 'node:url';
import {ACCOUNT,REPO,BRANCH,baseContext,sha} from './atomicity-schema-audit.mjs';
import {v2Plan,V2_PLAN_SHA} from './generalized-behavior-v2-contract.mjs';
import {audit as rootAudit,MESSAGE as ROOT_MESSAGE} from './generalized-behavior-root-read-only.mjs';
import {behaviorReadTransport} from './generalized-behavior-runner.mjs';
import {jsonBounded} from './d1-v2-migration.mjs';
export const MESSAGE='PLM generalized behavior v2 final read-only preflight once 20261004-r1';
export const WORKFLOW='.github/workflows/plm-generalized-behavior-v2-final-read-only-preflight.yml';
export const VERIFY=`https://api.cloudflare.com/client/v4/accounts/${ACCOUNT}/tokens/verify`;
const credential=x=>typeof x==='string'&&x.length>0&&x.length<=4096&&!/[\r\n]/.test(x);
export function checks(){
 const p=v2Plan(),files=readdirSync(new URL('../audit-evidence/',import.meta.url));
 if(files.some(n=>/^generalized-behavior-v2-(?:final-preflight|approved-(?:result|sent)|execution)/.test(n)))throw Error('RT_V2_PREFLIGHT_OR_EXECUTION_ALREADY_CONSUMED');
 const raw=readFileSync(new URL('../audit-evidence/generalized-backend-success-37164056976.json',import.meta.url));
 if(sha(raw)!=='c421f7fe9a22dd3a63b5b00c68837e43f1b1a27c77020f1262169242a844a614'||JSON.parse(raw).result.classification!=='FULL_APPLIED')throw Error('RT_V2_MIGRATION_RECEIPT_DRIFT');
 return {plan_sha256:V2_PLAN_SHA,identity:p.identity,steps:33,budgets:p.budgets,old_identity:p.protected_old_identity,migration_receipt_full_applied:true,execution_approved:false,allow:false};
}
export function verifyReadTransport(e,f,counts={v2_verify:0,d1_read_only:0}){
 const token=e.PLM_CF_D1_ROUNDTRIP_BEHAVIOR_V2_TOKEN,readToken=e.PLM_CF_D1_READ_TOKEN;
 if(!credential(token)||!credential(readToken)||token===readToken)throw Error('RT_V2_CREDENTIAL_SEPARATION_REQUIRED');
 let used=false;const read=behaviorReadTransport({PLM_CF_D1_READ_TOKEN:readToken},async(u,o)=>{counts.d1_read_only++;return f(u,o);});
 return async(u,o)=>{
  if(o.redirect!=='error'||!o.headers||Object.keys(o.headers).some(k=>!['Authorization','Content-Type'].includes(k)))throw Error('RT_V2_HEADERS_REJECTED');
  if(o.headers.Authorization===`Bearer ${token}`){
   if(u!==VERIFY||o.method!=='GET'||o.body!==undefined||Object.keys(o.headers).join(',')!=='Authorization'||used)throw Error('RT_V2_VERIFY_ONLY_NO_RETRY');
   used=true;counts.v2_verify++;return f(u,o);
  }
  if(u===VERIFY||o.headers.Authorization!==`Bearer ${readToken}`)throw Error('RT_V2_READ_TOKEN_ONLY');
  return read(u,o);
 };
}
export async function history(e,f){
 let total,seen=0,current=0;const ids=new Set();
 for(let page=1;page<=100;page++){
  const r=await f(`https://api.github.com/repos/${REPO}/actions/runs?per_page=20&page=${page}`,{method:'GET',redirect:'error',signal:AbortSignal.timeout(15000),headers:{Authorization:`Bearer ${e.PLM_HISTORY_GITHUB_TOKEN}`}});
  if(!r.ok)throw Error('RT_V2_HISTORY_HTTP_UNKNOWN');const b=await jsonBounded(r,1048576);
  if(!Number.isSafeInteger(b.total_count)||!Array.isArray(b.workflow_runs))throw Error('RT_V2_HISTORY_UNKNOWN');
  if(total===undefined)total=b.total_count;if(total!==b.total_count)throw Error('RT_V2_HISTORY_CHANGED');
  for(const x of b.workflow_runs){
   if(ids.has(x.id))throw Error('RT_V2_HISTORY_DUPLICATE');ids.add(x.id);seen++;
   if(/^\.github\/workflows\/plm-generalized-behavior-v2-/.test(x.path||'')&&x.path!==WORKFLOW&&!(x.status==='completed'&&x.conclusion==='skipped'&&x.run_attempt===1))throw Error('RT_V2_PRIOR_EXECUTION_STOP');
   if(x.path===WORKFLOW){if(String(x.id)===e.GITHUB_RUN_ID){if(x.head_sha!==e.GITHUB_SHA||x.run_attempt!==1)throw Error('RT_V2_CURRENT_RUN_DRIFT');current++;}else if(x.status!=='completed'||x.conclusion!=='skipped'||x.run_attempt!==1)throw Error('RT_V2_PREFLIGHT_ALREADY_USED');}
  }
  if(seen===total){if(current!==1)throw Error('RT_V2_CURRENT_RUN_NOT_UNIQUE');return {complete:true,total,pages:page,prior_v2_execution:0,current_run_unique:true};}
  if(!b.workflow_runs.length||seen>total)throw Error('RT_V2_HISTORY_INCOMPLETE');
 }throw Error('RT_V2_HISTORY_INCOMPLETE');
}
export async function preflight(e,f=fetch,{checkout,local=checks,historyCheck=history,audit=rootAudit,now=Date.now()}={}){
 const counts={v2_verify:0,d1_read_only:0},out={pass:false,d1_mutation:0,d1_write:0,worker:0,ai:0,render:0,youtube:0,sns:0,external_provider:0,retry:0,resend:0,delete:0,drop:0,reset:0,rollback:0,automatic_rollback:0,fallback:0,allow:false,execution_approved:false,live_ready:false,posting_permitted:false,diagnostics:[]};
 try{
  if(!baseContext(e)||e.GITHUB_EVENT_NAME!=='push'||!/^\d+$/.test(e.GITHUB_RUN_ID||'')||!/^[a-f0-9]{40}$/.test(checkout||'')||checkout!==e.PLM_RT_V2_FINAL_PIN||e.PLM_RT_V2_FINAL_BEFORE!==checkout||e.PLM_RT_V2_FINAL_MESSAGE!==MESSAGE||e.PLM_RT_V2_ALLOW!=='false'||e.PLM_RT_V2_OWNER_APPROVAL!=='UNAPPROVED'||Object.keys(e).some(k=>/^PLM_CF_.*TOKEN$/.test(k)&&!['PLM_CF_D1_READ_TOKEN','PLM_CF_D1_ROUNDTRIP_BEHAVIOR_V2_TOKEN'].includes(k)&&e[k]))throw Error('RT_V2_FINAL_CONTEXT_REJECTED');
  if(![e.PLM_CF_D1_READ_TOKEN,e.PLM_CF_D1_ROUNDTRIP_BEHAVIOR_V2_TOKEN,e.PLM_HISTORY_GITHUB_TOKEN].every(credential)||new Set([e.PLM_CF_D1_READ_TOKEN,e.PLM_CF_D1_ROUNDTRIP_BEHAVIOR_V2_TOKEN,e.PLM_HISTORY_GITHUB_TOKEN]).size!==3)throw Error('RT_V2_FINAL_CREDENTIAL_REJECTED');
  out.plan=local();out.history=await historyCheck(e,f);
  const branch=await f(`https://api.github.com/repos/${REPO}/branches/${BRANCH}`,{method:'GET',redirect:'error',signal:AbortSignal.timeout(15000),headers:{Authorization:`Bearer ${e.PLM_HISTORY_GITHUB_TOKEN}`}});
  if(!branch.ok||(await jsonBounded(branch,65536)).commit?.sha!==e.GITHUB_SHA)throw Error('RT_V2_BRANCH_DRIFT');
  const transport=verifyReadTransport(e,f,counts);
  const r=await transport(VERIFY,{method:'GET',redirect:'error',signal:AbortSignal.timeout(15000),headers:{Authorization:`Bearer ${e.PLM_CF_D1_ROUNDTRIP_BEHAVIOR_V2_TOKEN}`}}),b=await jsonBounded(r,16384);
  if(!r.ok||b.success!==true){out.diagnostics=(Array.isArray(b.errors)?b.errors:[]).slice(0,3).filter(x=>Number.isSafeInteger(x.code)).map(x=>({code:x.code,message:'V2 Token verify rejected; no retry or D1 mutation.'}));throw Error('RT_V2_TOKEN_VERIFY_REJECTED');}
  const expires=typeof b.result?.expires_on==='string'?Date.parse(b.result.expires_on):NaN,nb=b.result?.not_before;
  if(b.result?.status!=='active'||!Number.isFinite(expires)||expires<=now||nb!==undefined&&(!Number.isFinite(Date.parse(nb))||Date.parse(nb)>now))throw Error('RT_V2_TOKEN_INACTIVE_OR_NO_FINITE_EXPIRY');
  out.token_active=true;out.finite_expiry=true;out.token_expires_at=new Date(expires).toISOString();out.token_verified_at=new Date(now).toISOString();out.token_route='ACCOUNT_TOKEN_VERIFY_ONLY';out.token_scope_api_verified=false;
  const clean={...e,PLM_CF_D1_ROUNDTRIP_BEHAVIOR_V2_TOKEN:undefined,PLM_RT_ROOT_PIN:checkout,PLM_RT_ROOT_BEFORE:checkout,PLM_RT_ROOT_MESSAGE:ROOT_MESSAGE,PLM_RT_ROOT_ALLOW:'false'};
  out.readiness=await audit(clean,transport,{checkout});
  if(!out.readiness.pass||out.readiness.d1_mutation!==0||out.readiness.d1_write!==0||!out.readiness.exact_partial_baseline_unchanged||!out.readiness.new_identity_absent||!out.readiness.old_run_permanently_consumed)throw Error('RT_V2_READINESS_UNCONFIRMED');
  out.behavior_workflow_hard_disabled=true;out.pass=true;out.next_gate='STOP_AWAIT_SEPARATE_OWNER_FIXED_V2_33_STEP_APPROVAL';out.completed_at=new Date().toISOString();
 }catch(err){out.failure_code=/^[A-Z_]+$/.test(err.message)?err.message:'RT_V2_FINAL_UNKNOWN_NO_RETRY';}
 return {...out,transport_counts:counts,cloudflare_read_only_calls:counts.v2_verify+counts.d1_read_only,code_pin:checkout,event_commit:e.GITHUB_SHA};
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){const r=await preflight(process.env,fetch,{checkout:readFileSync('.git/HEAD','utf8').trim()});console.log('GENERALIZED_BEHAVIOR_V2_FINAL_READ_ONLY_PREFLIGHT '+JSON.stringify(r));if(!r.pass)process.exitCode=1;}
