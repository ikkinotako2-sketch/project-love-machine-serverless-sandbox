// Verify-only migration credential. No migration/dispatch/invocation entrypoint.
import {readFileSync,readdirSync,existsSync} from 'node:fs';
import {pathToFileURL} from 'node:url';
import {stage3Preflight,candidate,stage2Plan,SQL_SHA,EXPECTED} from './durable-stage2-contract.mjs';
import {ACCOUNT,DB,REPO,baseContext,sha,CONTRACT,READ_SQL} from './atomicity-schema-audit.mjs';
import {READ_ROW,PLAN} from './atomicity-test.mjs';
import {jsonBounded} from './d1-v2-migration.mjs';
export const MESSAGE='PLM stage3 final read-only preflight 20261003-r1';
export const LOCKS={
 'readiness/MIGRATION_RECEIPT_37063527954.json':'1c66211047cf2426058cb0a57e7c63b212817c46278220174368932c4a7b0a10',
 'audit-evidence/d1-v2-migration-receipt-37098401244.json':'2310028cfcc6a7222411a059fe9d62f2f5a847fbaabbeaaa1a73ef47c4263e22',
 'audit-evidence/atomicity-test-once-receipt-37101718265.json':'3b91c1667066125e4bc255add16b5412b86e99f163d6c43d85dbb9b40bcbf3a2',
 'serverless/durable-stage2-expected-schema.json':'c56781320a403573c9c76d827eaad2ef47226c70dd7474224a5ecbb7d92bd159',
 'serverless/atomicity-schema-contract.json':'984f9d8589a5c90214ea49ab518db22f51144bbef042ee5ee29d92bd89fac6f7',
 '.github/workflows/plm-d1-stage3-migration-once.yml':'15783d2abcb4ee559ac52cc7f2ac1cf56e948f833c8856add74904b67de60db1'
};
const ROOT=new URL('../',import.meta.url);
export function localStage3Checks({read=p=>readFileSync(new URL(p,ROOT)),journalExists=existsSync('stage3-migration-journal'),receiptNames=readdirSync(new URL('audit-evidence/',ROOT))}={}){
 candidate();stage2Plan();
 for(const [p,h] of Object.entries(LOCKS))if(sha(read(p))!==h)throw Error('STAGE3_IMMUTABLE_INPUT_DRIFT');
 const workflow=read('.github/workflows/plm-d1-stage3-migration-once.yml').toString();
 if(!workflow.includes('    if: false')||!workflow.includes("PLM_STAGE3_ALLOW: 'false'")||!workflow.includes('PLM_STAGE3_OWNER_APPROVAL: UNAPPROVED'))throw Error('STAGE3_EXECUTION_NOT_HARD_DISABLED');
 if(journalExists||receiptNames.some(n=>/^d1-stage3-migration-.*receipt.*\.json$/.test(n)))throw Error('STAGE3_PRIOR_SENT_UNKNOWN_OR_RECEIPT');
 return true;
}
const PATHS=new Map([
 ['.github/workflows/plm-migration-once.yml',37063527954],
 ['.github/workflows/plm-d1-v2-migration-once.yml',37098401244],
 ['.github/workflows/plm-d1-stage3-migration-once.yml',null]
]);
export async function migrationHistory(fetchPage){
 let total;const seen=new Set(),known=new Set(),pages=[];
 for(let page=1;page<=100;page++){
  const d=await fetchPage(page);
  if(!Array.isArray(d.workflow_runs)||d.workflow_runs.length>20||!Number.isSafeInteger(d.total_count)||d.total_count<0||d.total_count>10000)throw Error('STAGE3_HISTORY_INCOMPLETE');
  if(total===undefined)total=d.total_count;if(total!==d.total_count)throw Error('STAGE3_HISTORY_CHANGED');
  const selected=[];
  for(const r of d.workflow_runs){
   if(!Number.isSafeInteger(r.id)||seen.has(r.id))throw Error('STAGE3_HISTORY_DUPLICATE_OR_UNKNOWN');seen.add(r.id);
   if(!PATHS.has(r.path))continue;
   selected.push({run_id:r.id,path:r.path,status:r.status,conclusion:r.conclusion,attempt:r.run_attempt});
   if(r.status!=='completed'||r.run_attempt!==1)throw Error('STAGE3_PRIOR_RUN_UNCONFIRMED');
   if(r.id===PATHS.get(r.path)&&r.conclusion==='success'){known.add(r.id);continue;}
   if(r.conclusion!=='skipped')throw Error('STAGE3_PRIOR_MUTATION_RUN_NO_RESUME');
  }
  pages.push({page,total_count:total,repository_runs:d.workflow_runs.length,migration_runs:selected});
  if(seen.size===total){if(!known.has(37063527954)||!known.has(37098401244))throw Error('STAGE3_PRIOR_SUCCESS_HISTORY_MISSING');return {complete:true,repository_run_count:total,pages,prior_stage3_mutation_run:false};}
  if(!d.workflow_runs.length||seen.size>total)throw Error('STAGE3_HISTORY_INCOMPLETE');
 }
 throw Error('STAGE3_HISTORY_PAGE_LIMIT');
}
export function finalContext(e,checkout){return baseContext(e)&&e.GITHUB_EVENT_NAME==='push'&&/^\d+$/.test(e.GITHUB_RUN_ID||'')&&/^[a-f0-9]{40}$/.test(e.GITHUB_SHA||'')&&/^[a-f0-9]{40}$/.test(e.PLM_STAGE3_APPROVED_COMMIT||'')&&checkout===e.PLM_STAGE3_APPROVED_COMMIT&&e.PLM_STAGE3_EVENT_BEFORE===checkout&&e.PLM_STAGE3_MESSAGE===MESSAGE&&e.PLM_STAGE3_ALLOW==='false'&&e.PLM_STAGE3_OWNER_APPROVAL==='UNAPPROVED'&&e.PLM_STAGE3_SQL_SHA===SQL_SHA&&![e.PLM_CF_WORKER_API_TOKEN,e.PLM_CF_D1_ATOMICITY_TEST_TOKEN,e.PLM_CF_D1_STAGE2_TEST_TOKEN,e.PLM_CF_D1_MIGRATION_V2_TOKEN,e.PLM_CF_D1_API_TOKEN].some(Boolean);}
// Fail closed before network on unexpected URL/method/credential or non-fixed SQL.
export function readOnlyTransport(e,fetcher){return async(url,o)=>{
 const verify=`https://api.cloudflare.com/client/v4/accounts/${ACCOUNT}/tokens/verify`;
 const readBase=`https://api.cloudflare.com/client/v4/accounts/${ACCOUNT}/d1/database`;
 const auth=o?.headers?.Authorization;
 if(url===verify){if(o.method!=='GET'||auth!==`Bearer ${e.PLM_CF_D1_STAGE3_MIGRATION_TOKEN}`)throw Error('STAGE3_TRANSPORT_REJECTED');}
 else if(url.startsWith(`https://api.github.com/repos/${REPO}/actions/runs?per_page=20&page=`)){if(o.method!=='GET'||auth!==`Bearer ${e.PLM_HISTORY_GITHUB_TOKEN}`||!/page=\d+$/.test(url))throw Error('STAGE3_TRANSPORT_REJECTED');}
 else if(auth===`Bearer ${e.PLM_CF_D1_READ_TOKEN}`){
  if(o.method==='GET'){if(!(url==='https://api.cloudflare.com/client/v4/user/tokens/verify'||url===readBase+'/'+DB||url===readBase+'/'+DB+'/time_travel/bookmark'||new RegExp('^'+readBase.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+'\\?page=\\d+&per_page=100$').test(url)))throw Error('STAGE3_TRANSPORT_REJECTED');}
  else if(o.method==='POST'&&url===readBase+'/'+DB+'/query'){const p=JSON.parse(o.body);if(Object.keys(p).sort().join(',')!=='params,sql'||!READ_SQL.includes(p.sql)&&p.sql!==READ_ROW||!Array.isArray(p.params)||JSON.stringify(p.params)!==JSON.stringify(p.sql===READ_ROW?[PLAN.identity.platform,PLAN.identity.account_id,PLAN.identity.intent_id]:[]))throw Error('STAGE3_TRANSPORT_REJECTED');}
  else throw Error('STAGE3_TRANSPORT_REJECTED');
 }else throw Error('STAGE3_TRANSPORT_REJECTED');
 return fetcher(url,o);
};}
export async function finalStage3Preflight(e,fetcher=fetch,{checkout,checks=localStage3Checks,now=Date.now()}={}){
 const out={mode:'STAGE3_FINAL_READ_ONLY_PREFLIGHT',pass:false,cloudflare_read_only_api_calls:0,github_history_get_calls:0,d1_mutation:0,d1_write:0,worker_deploy:0,worker_invocation:0,worker_d1_access:0,live_job:0,ai_api:0,render:0,posting:0,retry:0,resend:0,fallback:0,automatic_rollback:0,execution_workflow_hard_disabled:true,owner_execution_approval:false,token_scope_api_verified:false,token_scope_owner_evidence:true,live_ready:false,posting_permitted:false};
 const stop=code=>({...out,failure_code:code});
 if(!finalContext(e,checkout))return stop('STAGE3_FINAL_CONTEXT_REJECTED_NO_HTTP');
 if(![e.PLM_CF_D1_STAGE3_MIGRATION_TOKEN,e.PLM_CF_D1_READ_TOKEN,e.PLM_HISTORY_GITHUB_TOKEN].every(s=>typeof s==='string'&&s.length>0&&s.length<=4096&&!/[\r\n]/.test(s)))return stop('STAGE3_CREDENTIAL_MISSING_NO_HTTP');
 try{
  checks();out.input_hashes=LOCKS;out.code_commit=checkout;out.event_commit=e.GITHUB_SHA;
  const read=readOnlyTransport(e,fetcher);
  out.history=await migrationHistory(async page=>{out.github_history_get_calls++;const r=await read(`https://api.github.com/repos/${REPO}/actions/runs?per_page=20&page=${page}`,{method:'GET',redirect:'error',signal:AbortSignal.timeout(15000),headers:{Authorization:`Bearer ${e.PLM_HISTORY_GITHUB_TOKEN}`}});if(!r.ok)throw Error('STAGE3_HISTORY_HTTP_UNKNOWN');try{return await jsonBounded(r,1048576);}catch(err){throw Error(err.message==='RESPONSE_TOO_LARGE'?'STAGE3_HISTORY_BODY_TOO_LARGE':'STAGE3_HISTORY_RESPONSE_PARSE_UNKNOWN');}});
  const result=await stage3Preflight({...e,GITHUB_SHA:checkout},read,{now});out.cloudflare_read_only_api_calls=result.cloudflare_read_calls;out.remote=result;
  if(!result.pass)return stop(result.failure_code||'STAGE3_REMOTE_UNCONFIRMED');
  out.token_active=result.token_active;out.token_owner_type='account';out.token_expires_at=result.token_expires_at;out.sql_sha256=SQL_SHA;
  out.schema_fingerprint=CONTRACT.schema_fingerprint;out.new_tables_absent=3;out.new_triggers_absent=6;
  out.sql_counts={create_table:3,create_trigger:6,top_level_create:9,drop:0,delete:0,alter:0,rename:0,existing_table_change:0,trigger_body_future_update:1};
  out.expected_post_schema={sha256:LOCKS['serverless/durable-stage2-expected-schema.json'],new_tables:3,new_triggers:6,columns:Object.fromEntries(Object.entries(EXPECTED.columns).map(([k,v])=>[k,v.length])),indexes:Object.values(EXPECTED.indexes).flat().length,new_table_rows:0,old_atomicity_row_unchanged:true,old_schema_unchanged:true,test_jobs_rows:0};
  out.pass=true;return out;
 }catch(err){return stop(/^STAGE3_[A-Z_]+$/.test(err.message)?err.message:'STAGE3_FINAL_UNKNOWN_NO_RETRY_NO_MUTATION');}
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){try{const r=await finalStage3Preflight(process.env,fetch,{checkout:readFileSync('.git/HEAD','utf8').trim()});console.log('STAGE3_FINAL_PREFLIGHT '+JSON.stringify(r));if(!r.pass)process.exitCode=1;}catch{console.error('STAGE3_FINAL_UNKNOWN_NO_RETRY_NO_MUTATION');process.exitCode=1;}}
