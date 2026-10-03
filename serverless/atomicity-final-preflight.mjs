// Verify-only Write Token; all D1 reads use the existing Read Token. No mutation transport.
import {readFileSync,existsSync,readdirSync} from 'node:fs';
import {pathToFileURL} from 'node:url';
import {PLAN,PLAN_SHA,validatePlan,historyClear,expectedRow} from './atomicity-test.mjs';
import {auditSchema,ACCOUNT,DB,REPO,baseContext,sha} from './atomicity-schema-audit.mjs';
import {jsonBounded} from './d1-v2-migration.mjs';
export const MESSAGE='PLM atomicity final read-only preflight 20261003-r1';
export const EXECUTION_WORKFLOW_SHA='93d76194b0e85f12bb12af995a9eb43a88a05bccefee756eef4ad01b172feb5d';
export function localChecks({workflow=readFileSync(new URL('../.github/workflows/plm-d1-atomicity-test-once.yml',import.meta.url)),journalExists=existsSync('atomicity-journal'),receiptNames=readdirSync(new URL('../audit-evidence/',import.meta.url))}={}){
 validatePlan();
 if(sha(workflow)!==EXECUTION_WORKFLOW_SHA||!workflow.toString().includes('    if: false')||!workflow.toString().includes("PLM_ATOMICITY_ALLOW: 'false'")||!workflow.toString().includes('PLM_ATOMICITY_OWNER_APPROVAL: UNAPPROVED'))throw Error('EXECUTION_WORKFLOW_NOT_HARD_DISABLED');
 if(journalExists||receiptNames.some(n=>/^atomicity-test-.*receipt.*\.json$/.test(n)))throw Error('PRIOR_SENT_UNKNOWN_OR_TEST_RECEIPT');
 return true;
}
export function preflightContext(e,checkout){return baseContext(e)&&e.GITHUB_EVENT_NAME==='push'&&/^\d+$/.test(e.GITHUB_RUN_ID||'')&&/^[a-f0-9]{40}$/.test(e.GITHUB_SHA||'')&&/^[a-f0-9]{40}$/.test(e.PLM_PREFLIGHT_CODE_PIN||'')&&checkout===e.PLM_PREFLIGHT_CODE_PIN&&e.PLM_PREFLIGHT_EVENT_BEFORE===e.PLM_PREFLIGHT_CODE_PIN&&e.PLM_PREFLIGHT_MESSAGE===MESSAGE&&e.PLM_ATOMICITY_PLAN_SHA===PLAN_SHA&&e.PLM_ATOMICITY_ALLOW==='false'&&e.PLM_ATOMICITY_OWNER_APPROVAL==='UNAPPROVED'&&!e.PLM_CF_WORKER_API_TOKEN&&!e.PLM_CF_D1_MIGRATION_V2_TOKEN&&!e.PLM_CF_D1_API_TOKEN;}
export async function finalPreflight(e,fetcher=fetch,{checkout,checks=localChecks,now=Date.now()}={}){
 const r={mode:'ATOMICITY_FINAL_READ_ONLY_PREFLIGHT',pass:false,cloudflare_read_only_api_calls:0,cloudflare_get_calls:0,d1_read_query_post_calls:0,github_history_get_calls:0,d1_mutations:0,d1_writes:0,probe_insert:0,worker_deploy:0,worker_invocation:0,live_job:0,ai_api:0,render:0,posting:0,retry:0,fallback:0,resend:0,execution_workflow_hard_disabled:true,owner_execution_approval:false,live_ready:false,posting_permitted:false,token_scope_owner_evidence:true,token_scope_api_verified:false};
 const stop=code=>({...r,failure_code:code});
 if(!preflightContext(e,checkout))return stop('PREFLIGHT_CONTEXT_REJECTED_NO_HTTP');
 if(![e.PLM_CF_D1_ATOMICITY_TEST_TOKEN,e.PLM_CF_D1_READ_TOKEN,e.PLM_HISTORY_GITHUB_TOKEN].every(x=>typeof x==='string'&&x.length>0&&x.length<=4096&&!/[\r\n]/.test(x)))return stop('CREDENTIAL_MISSING_NO_HTTP');
 try{
  checks();r.plan_sha256=PLAN_SHA;r.schema_fingerprint=PLAN.schema_fingerprint;r.migration_receipt_sha256=PLAN.migration_receipt_sha256;r.local_journal_clear=true;
  const pages=[];const clear=await historyClear(async page=>{r.github_history_get_calls++;const resp=await fetcher(`https://api.github.com/repos/${REPO}/actions/workflows/plm-d1-atomicity-test-once.yml/runs?per_page=100&page=${page}`,{method:'GET',redirect:'error',signal:AbortSignal.timeout(15000),headers:{Authorization:`Bearer ${e.PLM_HISTORY_GITHUB_TOKEN}`}});if(!resp.ok)throw Error('HISTORY_HTTP_UNKNOWN');const d=await jsonBounded(resp,1048576);pages.push({page,total_count:d.total_count,runs:Array.isArray(d.workflow_runs)?d.workflow_runs.map(x=>({run_id:x.id,attempt:x.run_attempt,status:x.status,conclusion:x.conclusion})):[]});return d;},e.GITHUB_RUN_ID);
  if(!clear)return stop('PRIOR_RUN_OR_HISTORY_INCOMPLETE');r.history={complete:true,pages};
  r.cloudflare_read_only_api_calls++;r.cloudflare_get_calls++;
  const v=await fetcher(`https://api.cloudflare.com/client/v4/accounts/${ACCOUNT}/tokens/verify`,{method:'GET',redirect:'error',signal:AbortSignal.timeout(15000),headers:{Authorization:`Bearer ${e.PLM_CF_D1_ATOMICITY_TEST_TOKEN}`}});
  r.verify_http_status=v.status;if(!v.ok)return stop('ACCOUNT_TOKEN_VERIFY_REJECTED_NO_FALLBACK');const token=await jsonBounded(v,16384);
  if(token.success!==true||token.result?.status!=='active')return stop('TOKEN_NOT_ACTIVE');
  const expiry=token.result.expires_on;if(typeof expiry!=='string'||!/^\d{4}-\d{2}-\d{2}T/.test(expiry)||!Number.isFinite(Date.parse(expiry))||Date.parse(expiry)<=now)return stop('TOKEN_EXPIRY_UNCONFIRMED_OR_EXPIRED');
  r.token_active=true;r.token_owner_type='account';r.token_expires_at=new Date(expiry).toISOString();
  // Explicitly remove Write Token from the read-only D1 audit environment.
  const clean={...e,PLM_CF_D1_ATOMICITY_TEST_TOKEN:undefined,PLM_HISTORY_GITHUB_TOKEN:undefined};
  const audit=await auditSchema(clean,fetcher);r.cloudflare_read_only_api_calls+=audit.external_api_calls;r.cloudflare_get_calls+=audit.get_calls;r.d1_read_query_post_calls+=audit.read_query_post_calls;
  if(!audit.pass||audit.primary_reads_confirmed!==true)return stop(audit.failure_code||'FRESH_PRIMARY_SCHEMA_UNCONFIRMED');
  r.remote=audit;r.budget=PLAN.budget;r.steps=PLAN.steps.map(x=>({id:x.id,expected_changes:x.expected_changes,expected_state:x.expected_current_state,expected_version:x.expected_current_version,next_version:x.expected_next_version,expected_claimant:x.expected_claimant,expected_fingerprint:x.expected_fingerprint}));
  r.expected_final_row=PLAN.expected_final_row;r.concurrent_http_required=true;r.d1_internal_parallel_execution_claimed=false;r.pass=true;
  return r;
 }catch(err){return stop(['EXECUTION_WORKFLOW_NOT_HARD_DISABLED','PRIOR_SENT_UNKNOWN_OR_TEST_RECEIPT','PLAN_DRIFT','MIGRATION_RECEIPT_DRIFT','HISTORY_HTTP_UNKNOWN'].includes(err.message)?err.message:'PREFLIGHT_UNKNOWN_NO_RETRY_NO_MUTATION');}
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){try{const r=await finalPreflight(process.env,fetch,{checkout:readFileSync('.git/HEAD','utf8').trim()});console.log('ATOMICITY_FINAL_PREFLIGHT '+JSON.stringify(r));if(!r.pass)process.exitCode=1;}catch{console.error('ATOMICITY_PREFLIGHT_UNKNOWN_NO_RETRY_NO_MUTATION');process.exitCode=1;}}
