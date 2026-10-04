// Read-only final gate. The behavior credential is never passed to the D1 auditor.
import {readFileSync,readdirSync} from 'node:fs';import {pathToFileURL} from 'node:url';
import {ACCOUNT,REPO,BRANCH,baseContext} from './atomicity-schema-audit.mjs';
import {planCheck,TEST_WORKFLOW} from './generalized-behavior-contract.mjs';
import {preflight,readTransport,MESSAGE as READ_MESSAGE} from './generalized-behavior-preflight.mjs';
import {jsonBounded} from './d1-v2-migration.mjs';
export const MESSAGE='PLM generalized behavior token verify final read-only once 20261004-r1';
export const WORKFLOW='.github/workflows/plm-generalized-behavior-final-read-only-preflight.yml';
export const VERIFY=`https://api.cloudflare.com/client/v4/accounts/${ACCOUNT}/tokens/verify`;
const credential=x=>typeof x==='string'&&x.length>0&&x.length<=4096&&!/[\r\n]/.test(x);
export function finalChecks(){const p=planCheck();if(readdirSync(new URL('../audit-evidence/',import.meta.url)).some(n=>/^generalized-behavior-final-preflight-/.test(n)))throw Error('RT_BEHAVIOR_FINAL_PREFLIGHT_ALREADY_CONSUMED');return p;}
export function verifyOnlyTransport(e,f,counts={behavior_verify:0,d1_read_only:0}){
 if(!credential(e.PLM_CF_D1_READ_TOKEN)||!credential(e.PLM_CF_D1_ROUNDTRIP_BEHAVIOR_TOKEN)||e.PLM_CF_D1_READ_TOKEN===e.PLM_CF_D1_ROUNDTRIP_BEHAVIOR_TOKEN)throw Error('RT_BEHAVIOR_CREDENTIAL_SEPARATION_REQUIRED');
 const clean={PLM_CF_D1_READ_TOKEN:e.PLM_CF_D1_READ_TOKEN},read=readTransport(clean,async(u,o)=>{counts.d1_read_only++;return f(u,o);});let used=false;
 return async(u,o)=>{
  if(o.redirect!=='error'||!o.headers||Object.keys(o.headers).some(k=>!['Authorization','Content-Type'].includes(k)))throw Error('RT_BEHAVIOR_FINAL_HEADERS_REJECTED');
  if(o.headers.Authorization===`Bearer ${e.PLM_CF_D1_ROUNDTRIP_BEHAVIOR_TOKEN}`){
   if(u!==VERIFY||o.method!=='GET'||o.body!==undefined||Object.keys(o.headers).join(',')!=='Authorization'||used)throw Error('RT_BEHAVIOR_VERIFY_ONLY_NO_RETRY');
   used=true;counts.behavior_verify++;return f(u,o);
  }
  if(u===VERIFY||o.headers.Authorization!==`Bearer ${e.PLM_CF_D1_READ_TOKEN}`)throw Error('RT_BEHAVIOR_FINAL_READ_TOKEN_ONLY');
  if(o.headers['Content-Type']!==undefined&&o.headers['Content-Type']!=='application/json')throw Error('RT_BEHAVIOR_FINAL_CONTENT_TYPE_REJECTED');
  return read(u,o);
 };
}
export async function finalHistory(e,f){let total,seen=0,current=0;const ids=new Set();for(let page=1;page<=100;page++){
 const r=await f(`https://api.github.com/repos/${REPO}/actions/runs?per_page=20&page=${page}`,{method:'GET',redirect:'error',signal:AbortSignal.timeout(15000),headers:{Authorization:`Bearer ${e.PLM_HISTORY_GITHUB_TOKEN}`}});
 if(!r.ok)throw Error('RT_BEHAVIOR_FINAL_HISTORY_HTTP_UNKNOWN');const b=await jsonBounded(r,1048576);if(!Number.isSafeInteger(b.total_count)||!Array.isArray(b.workflow_runs))throw Error('RT_BEHAVIOR_FINAL_HISTORY_UNKNOWN');if(total===undefined)total=b.total_count;if(total!==b.total_count)throw Error('RT_BEHAVIOR_FINAL_HISTORY_CHANGED');
 for(const x of b.workflow_runs){if(ids.has(x.id))throw Error('RT_BEHAVIOR_FINAL_HISTORY_DUPLICATE');ids.add(x.id);seen++;
  if([TEST_WORKFLOW,'.github/workflows/plm-generalized-behavior-approved-once.yml'].includes(x.path)&&!(x.status==='completed'&&x.conclusion==='skipped'&&x.run_attempt===1))throw Error('RT_BEHAVIOR_PRIOR_EXECUTION_STOP');
  if(x.path===WORKFLOW){if(String(x.id)===e.GITHUB_RUN_ID){if(x.head_sha!==e.GITHUB_SHA||x.run_attempt!==1)throw Error('RT_BEHAVIOR_FINAL_CURRENT_RUN_DRIFT');current++;}else if(x.status!=='completed'||x.conclusion!=='skipped'||x.run_attempt!==1)throw Error('RT_BEHAVIOR_FINAL_PREFLIGHT_ALREADY_USED');}
 }
 if(seen===total){if(current!==1)throw Error('RT_BEHAVIOR_FINAL_CURRENT_RUN_NOT_UNIQUE');return {complete:true,total,pages:page,prior_test_execution:false,current_run_unique:true};}if(!b.workflow_runs.length||seen>total)throw Error('RT_BEHAVIOR_FINAL_HISTORY_INCOMPLETE');
 }throw Error('RT_BEHAVIOR_FINAL_HISTORY_INCOMPLETE');}
export async function finalPreflight(e,f=fetch,{checkout,checks=finalChecks,historyCheck=finalHistory,readiness=preflight,now=Date.now()}={}){
 const counts={behavior_verify:0,d1_read_only:0},out={pass:false,d1_mutation:0,d1_write:0,worker:0,ai:0,render:0,youtube:0,sns:0,external_provider:0,delete:0,drop:0,reset:0,retry:0,resend:0,fallback:0,automatic_rollback:0,live_ready:false,posting_permitted:false,allow:false,execution_approved:false,diagnostics:[]};
 try{
  if(!baseContext(e)||e.GITHUB_EVENT_NAME!=='push'||!/^\d+$/.test(e.GITHUB_RUN_ID||'')||!/^[a-f0-9]{40}$/.test(checkout||'')||e.PLM_RT_BEHAVIOR_FINAL_PIN!==checkout||e.PLM_RT_BEHAVIOR_FINAL_BEFORE!==checkout||e.PLM_RT_BEHAVIOR_FINAL_MESSAGE!==MESSAGE||e.PLM_RT_BEHAVIOR_ALLOW!=='false'||e.PLM_RT_BEHAVIOR_OWNER_APPROVAL!=='UNAPPROVED'||Object.keys(e).some(k=>/^PLM_CF_.*TOKEN$/.test(k)&&!['PLM_CF_D1_READ_TOKEN','PLM_CF_D1_ROUNDTRIP_BEHAVIOR_TOKEN'].includes(k)&&e[k]))throw Error('RT_BEHAVIOR_FINAL_CONTEXT_REJECTED');
  if(![e.PLM_CF_D1_READ_TOKEN,e.PLM_CF_D1_ROUNDTRIP_BEHAVIOR_TOKEN,e.PLM_HISTORY_GITHUB_TOKEN].every(credential)||new Set([e.PLM_CF_D1_READ_TOKEN,e.PLM_CF_D1_ROUNDTRIP_BEHAVIOR_TOKEN,e.PLM_HISTORY_GITHUB_TOKEN]).size!==3)throw Error('RT_BEHAVIOR_FINAL_CREDENTIAL_REJECTED');
  out.plan=checks();out.history=await historyCheck(e,f);const transport=verifyOnlyTransport(e,f,counts);
  const r=await transport(VERIFY,{method:'GET',redirect:'error',signal:AbortSignal.timeout(15000),headers:{Authorization:`Bearer ${e.PLM_CF_D1_ROUNDTRIP_BEHAVIOR_TOKEN}`}});
  const b=await jsonBounded(r,16384);if(!r.ok||b.success!==true){out.diagnostics=(Array.isArray(b.errors)?b.errors:[]).slice(0,3).filter(x=>Number.isSafeInteger(x.code)).map(x=>({code:x.code,message:'Behavior Token verify rejected; no retry or D1 writes.'}));throw Error('RT_BEHAVIOR_TOKEN_VERIFY_REJECTED');}
  const expires=typeof b.result?.expires_on==='string'?Date.parse(b.result.expires_on):NaN,notBefore=b.result?.not_before;
  if(b.result?.status!=='active'||!Number.isFinite(expires)||expires<=now||notBefore!==undefined&&(!Number.isFinite(Date.parse(notBefore))||Date.parse(notBefore)>now))throw Error('RT_BEHAVIOR_TOKEN_INACTIVE_OR_NO_FINITE_EXPIRY');
  out.token_active=true;out.finite_expiry=true;out.token_expires_at=new Date(expires).toISOString();out.token_verified_at=new Date(now).toISOString();out.token_scope_api_verified=false;out.behavior_token_route='ACCOUNT_TOKEN_VERIFY_ONLY';
  const clean={...e,PLM_CF_D1_ROUNDTRIP_BEHAVIOR_TOKEN:undefined,PLM_RT_BEHAVIOR_PIN:checkout,PLM_RT_BEHAVIOR_BEFORE:checkout,PLM_RT_BEHAVIOR_MESSAGE:READ_MESSAGE};
  const branchURL=`https://api.github.com/repos/${REPO}/branches/${BRANCH}`;
  const auditTransport=async(u,o)=>{if(u===branchURL){if(o.method!=='GET'||o.body!==undefined||o.redirect!=='error'||Object.keys(o.headers||{}).join(',')!=='Authorization'||o.headers.Authorization!==`Bearer ${e.PLM_HISTORY_GITHUB_TOKEN}`)throw Error('RT_BEHAVIOR_FINAL_BRANCH_AUTH_REJECTED');return f(u,o);}return transport(u,o);};
  out.readiness=await readiness(clean,auditTransport,{checkout,checks:()=>out.plan,historyCheck:async()=>out.history});
  if(!out.readiness.pass||out.readiness.d1_mutation!==0||out.readiness.d1_write!==0)throw Error('RT_BEHAVIOR_FINAL_READINESS_UNCONFIRMED');
  out.behavior_workflow_hard_disabled=true;out.pass=true;out.next_gate='STOP_AWAIT_SEPARATE_OWNER_FIXED_33_STEP_APPROVAL';out.completed_at=new Date().toISOString();
 }catch(err){out.failure_code=/^[A-Z_]+$/.test(err.message)?err.message:'RT_BEHAVIOR_FINAL_UNKNOWN_NO_RETRY';}
 return {...out,transport_counts:counts,cloudflare_read_only_calls:counts.behavior_verify+counts.d1_read_only,code_pin:checkout,event_commit:e.GITHUB_SHA};
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){const r=await finalPreflight(process.env,fetch,{checkout:readFileSync('.git/HEAD','utf8').trim()});console.log('GENERALIZED_BEHAVIOR_FINAL_READ_ONLY_PREFLIGHT '+JSON.stringify(r));if(!r.pass)process.exitCode=1;}
